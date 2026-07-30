"""Server-solved city-worker macro assembly and observed result contract."""

import json
import math
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.coalitions import RequirementSet
from ..pressure.resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from ..pressure.resource_scheduler import OperationResourceRequest
from .domain_models import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    city_output_vector,
)
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    operation_id_from_components,
)


@dataclass(frozen=True)
class CityWorkerMacroIntent:
    city_id: int
    food_surplus_minimum: int
    require_happy: bool
    scheduling_bid: float
    operation_type: str = "OPTIMIZE_CITY_WORKERS"

    def __post_init__(self):
        if (
                isinstance(self.city_id, bool)
                or not isinstance(self.city_id, int)
                or self.city_id < 0
        ):
            raise ValueError(
                "city-worker intent city ID must be non-negative")
        if (
                isinstance(self.food_surplus_minimum, bool)
                or not isinstance(self.food_surplus_minimum, int)
                or not 0 <= self.food_surplus_minimum <= 10
        ):
            raise ValueError(
                "city-worker food minimum must be in 0..10")
        if not isinstance(self.require_happy, bool):
            raise TypeError(
                "city-worker happiness requirement must be boolean")
        if (
                not math.isfinite(float(self.scheduling_bid))
                or float(self.scheduling_bid) < 0.0
        ):
            raise ValueError(
                "city-worker scheduling bid must be finite and non-negative")
        if not isinstance(self.operation_type, str) or not self.operation_type:
            raise ValueError(
                "city-worker operation type is required")

    @property
    def target_ref(self):
        return "city-worker:city:{}:food:{}:happy:{}".format(
            self.city_id,
            self.food_surplus_minimum,
            str(self.require_happy).lower())

    def action(self):
        target = {
            "food_surplus_reserve":
                self.food_surplus_minimum,
        }
        if self.require_happy:
            target["require_happy"] = True
        return {
            "action_type": "city_governor",
            "city_id": self.city_id,
            "target": target,
        }


@dataclass(frozen=True)
class CityWorkerMacroAssembly:
    spec: OperationSpec
    intent: CityWorkerMacroIntent
    requirement_set: RequirementSet
    resource_request: OperationResourceRequest
    action_json: str
    model_artifact_json: str
    premise_packets: tuple
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if not isinstance(self.spec, OperationSpec):
            raise TypeError(
                "city-worker assembly requires an operation spec")
        if not isinstance(self.intent, CityWorkerMacroIntent):
            raise TypeError(
                "city-worker assembly requires an intent")
        if not isinstance(self.requirement_set, RequirementSet):
            raise TypeError(
                "city-worker assembly requires a RequirementSet")
        if not isinstance(
                self.resource_request, OperationResourceRequest):
            raise TypeError(
                "city-worker assembly requires a resource request")
        if (
                self.spec.operation_id
                != self.resource_request.operation_id
                or self.requirement_set.requirement_set_id
                != self.resource_request.requirement_set_id
        ):
            raise ValueError(
                "city-worker assembly identities must agree")
        try:
            action = json.loads(self.action_json)
            artifact = json.loads(self.model_artifact_json)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "city-worker assembly JSON is invalid") from error
        if not isinstance(action, dict) or not isinstance(artifact, dict):
            raise ValueError(
                "city-worker assembly JSON must encode objects")
        packets = tuple(self.premise_packets)
        if (
                tuple(sorted(packets)) != packets
                or set(row[0] for row in packets)
                != set(self.requirement_set.premise_ids)
                or any(row[1] != 1 for row in packets)
        ):
            raise ValueError(
                "city-worker premise packets must complete requirements")
        if not self.shadow_only or self.policy_authority:
            raise ValueError(
                "initial city-worker macros are shadow-only")

    @property
    def model_artifact(self):
        return json.loads(self.model_artifact_json)

    def action(self):
        return json.loads(self.action_json)

    def to_dict(self):
        return {
            "action": self.action(),
            "intent": {
                "city_id": self.intent.city_id,
                "food_surplus_minimum":
                    self.intent.food_surplus_minimum,
                "operation_type": self.intent.operation_type,
                "require_happy": self.intent.require_happy,
                "scheduling_bid": float(
                    self.intent.scheduling_bid),
            },
            "model_artifact": self.model_artifact,
            "policy_authority": False,
            "premise_packets": dict(self.premise_packets),
            "requirement_set": self.requirement_set.to_dict(),
            "resource_request": self.resource_request.to_dict(),
            "shadow_only": True,
            "spec": self.spec.to_dict(),
        }


@dataclass(frozen=True)
class CityWorkerMacroResult:
    operation_id: str
    accepted: bool
    before_snapshot_id: str
    after_snapshot_id: str
    solver_status: str
    configuration_observed: bool
    constraints_met: object
    actual_output_vector: object
    optimality_gap: object
    optimality_gap_status: str
    citizen_assignments_visible: bool
    result_hash: str

    def to_dict(self):
        return {
            "accepted": self.accepted,
            "actual_output_vector": self.actual_output_vector,
            "after_snapshot_id": self.after_snapshot_id,
            "before_snapshot_id": self.before_snapshot_id,
            "citizen_assignments_visible":
                self.citizen_assignments_visible,
            "configuration_observed":
                self.configuration_observed,
            "constraints_met": self.constraints_met,
            "operation_id": self.operation_id,
            "optimality_gap": self.optimality_gap,
            "optimality_gap_status":
                self.optimality_gap_status,
            "result_hash": self.result_hash,
            "solver_status": self.solver_status,
        }


class CityWorkerMacroAssembler:
    """Allocate optimization budget to one atomic server macro."""

    RULE_ID = "gdo7-city-worker-macro/1.0"

    @classmethod
    def assemble(
            cls, snapshot, intent, estimate,
            goal_ids, ruleset_digest):
        if not isinstance(intent, CityWorkerMacroIntent):
            raise TypeError(
                "city-worker assembly requires an intent")
        if not isinstance(estimate, GroundedTransitionEstimate):
            raise TypeError(
                "city-worker assembly requires a grounded estimate")
        if (
                estimate.authority not in (
                    EstimateAuthority.EXACT_AUTHORITATIVE,
                    EstimateAuthority.DETERMINISTIC_DERIVED)
                or estimate.estimator_id
                != "grounded_city_worker_macro"
        ):
            return None
        action = intent.action()
        action_json = canonical_json_bytes(
            action).decode("utf-8")
        if action_json not in set(snapshot.legal_action_json):
            return None
        artifact = estimate.to_dict().get("model_artifact")
        if (
                not isinstance(artifact, dict)
                or artifact.get("legal_action") != action
                or artifact.get("assignment", {}).get(
                    "macro_action_atomic") is not True
                or artifact.get("assignment", {}).get(
                    "citizen_actions_emitted") is not False
        ):
            return None
        goal_ids = tuple(sorted(str(value) for value in goal_ids))
        if (
                not goal_ids
                or len(set(goal_ids)) != len(goal_ids)
                or any(not value for value in goal_ids)
        ):
            raise ValueError(
                "city-worker macro requires unique goal IDs")
        participant = OperationParticipant(
            role="optimized_city",
            actor_id="city:{}".format(intent.city_id),
            actor_class="city",
            required=True)
        operation_id = operation_id_from_components(
            intent.operation_type,
            goal_ids,
            (participant,),
            intent.target_ref,
            str(ruleset_digest),
            snapshot.turn)
        context_digest = structural_hash({
            "legal_actions_digest": snapshot.legal_actions_digest,
            "operation_id": operation_id,
            "snapshot_id": snapshot.snapshot_id,
            "target_ref": intent.target_ref,
        })
        premise_ids = (
            "city:{}:owned".format(intent.city_id),
            "city:{}:governor-available".format(intent.city_id),
            "city:{}:macro-advertised".format(intent.city_id),
            "city:{}:output-vector-grounded".format(intent.city_id),
            "city:{}:constraints-bounded".format(intent.city_id),
            "city:{}:assignment-delegated".format(intent.city_id),
        )
        requirement_set = RequirementSet(
            requirement_set_id="requirement-set:{}".format(
                structural_hash({
                    "context_digest": context_digest,
                    "premise_ids": premise_ids,
                    "rule_id": cls.RULE_ID,
                })[:24]),
            rule_id=cls.RULE_ID,
            premise_ids=premise_ids,
            role_ids=(
                "city_owned",
                "governor_capability",
                "macro_action_advertised",
                "current_outputs_grounded",
                "minimum_constraints_bounded",
                "assignment_solver_delegated",
            ),
            context_digest=context_digest)
        step = OperationStep(
            step_id="step-{}".format(
                structural_hash({
                    "action": action,
                    "operation_id": operation_id,
                })[:32]),
            action_type="city_governor",
            actor_role="optimized_city",
            target_ref=intent.target_ref,
            requirement_set_id=(
                requirement_set.requirement_set_id),
            completion_predicate_id=(
                "city-worker:macro-result-observed"),
            maximum_attempts=1)
        spec = OperationSpec(
            schema_version=OPERATION_SCHEMA_VERSION,
            operation_id=operation_id,
            operation_type=intent.operation_type,
            goal_ids=goal_ids,
            participants=(participant,),
            target_ref=intent.target_ref,
            steps=(step,),
            created_turn=int(snapshot.turn),
            expiry_turn=int(snapshot.turn) + 1,
            replacement_margin=0.0,
            provenance=(
                "grounded-city-worker-transition-model",
                "server-advertised-city-governor-macro",
                "pressure-selects-city-and-constraints",
                "server-selects-citizen-assignment",
                "shadow-only-gdo7c",
            ),
            ruleset_digest=str(ruleset_digest))
        player_scope = "player:{}".format(snapshot.player_id)
        claims = (
            ResourceClaim(
                resource=ResourceRef(
                    GameResourceKind.CITY_WORKER_ASSIGNMENT,
                    "city:{}".format(intent.city_id),
                    "citizen_manager",
                    player_scope),
                quantity=1,
                window=TurnWindow(
                    snapshot.turn, snapshot.turn + 1),
                hardness=ClaimHardness.HARD_CURRENT,
                exclusive=True,
                source_operation_id=operation_id,
                source_step_id=step.step_id),
            ResourceClaim(
                resource=ResourceRef(
                    GameResourceKind.ACTION_BUDGET,
                    player_scope, "controller",
                    player_scope),
                quantity=1,
                window=TurnWindow(
                    snapshot.turn, snapshot.turn + 1),
                hardness=ClaimHardness.HARD_CURRENT,
                exclusive=False,
                source_operation_id=operation_id,
                source_step_id=step.step_id),
        )
        request = OperationResourceRequest(
            operation_id=operation_id,
            bid=float(intent.scheduling_bid),
            claims=claims,
            requirement_set_id=(
                requirement_set.requirement_set_id))
        return CityWorkerMacroAssembly(
            spec=spec,
            intent=intent,
            requirement_set=requirement_set,
            resource_request=request,
            action_json=action_json,
            model_artifact_json=json.dumps(
                artifact, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")),
            premise_packets=tuple(
                (premise_id, 1)
                for premise_id in sorted(premise_ids)))

    @staticmethod
    def observe_result(
            assembly, before_snapshot,
            after_snapshot, accepted):
        if not isinstance(assembly, CityWorkerMacroAssembly):
            raise TypeError(
                "city-worker result requires an assembly")
        if not isinstance(accepted, bool):
            raise TypeError(
                "city-worker acceptance must be boolean")
        after_city = after_snapshot.city(
            assembly.intent.city_id)
        output = (
            city_output_vector(after_city)
            if after_city is not None else None)
        newer = bool(
            after_snapshot.snapshot_id
            != before_snapshot.snapshot_id)
        configuration_observed = bool(
            after_city is not None
            and after_city.governor_enabled is True
            and len(after_city.governor_minimal_surplus) >= 1
            and after_city.governor_minimal_surplus[0]
            == assembly.intent.food_surplus_minimum
            and after_city.governor_require_happy
            is assembly.intent.require_happy)
        constraints_met = (
            bool(
                output["net"]["food"]
                >= assembly.intent.food_surplus_minimum
                and (
                    not assembly.intent.require_happy
                    or (
                        after_city.was_happy is True
                        and after_city.disorder is not True)))
            if configuration_observed and output is not None
            else None)
        if not accepted:
            status = "action-rejected"
        elif not newer:
            status = "awaiting-newer-authoritative-snapshot"
        elif after_city is None:
            status = "city-removed-before-result"
        elif not configuration_observed:
            status = "configuration-not-observed"
        elif constraints_met:
            status = "observed-constraints-satisfied"
        else:
            status = "observed-constraints-unsatisfied"
        material = {
            "accepted": accepted,
            "actual_output_vector": output,
            "after_snapshot_id": after_snapshot.snapshot_id,
            "before_snapshot_id": before_snapshot.snapshot_id,
            "citizen_assignments_visible": False,
            "configuration_observed": configuration_observed,
            "constraints_met": constraints_met,
            "operation_id": assembly.spec.operation_id,
            "optimality_gap": None,
            "optimality_gap_status":
                "not-exposed-by-server-interface",
            "solver_status": status,
        }
        return CityWorkerMacroResult(
            operation_id=assembly.spec.operation_id,
            accepted=accepted,
            before_snapshot_id=before_snapshot.snapshot_id,
            after_snapshot_id=after_snapshot.snapshot_id,
            solver_status=status,
            configuration_observed=configuration_observed,
            constraints_met=constraints_met,
            actual_output_vector=output,
            optimality_gap=None,
            optimality_gap_status=(
                "not-exposed-by-server-interface"),
            citizen_assignments_visible=False,
            result_hash=structural_hash(material))
