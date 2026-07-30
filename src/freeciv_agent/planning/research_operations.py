"""Identity-bearing research enabling operations.

Each operation selects one currently researchable technology and then waits
for an authoritative snapshot to report it as known.  A strategic target may
be farther down the dependency graph; completing an immediate prerequisite
requests replanning and does not falsely complete the downstream operation.
"""

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
)
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    operation_id_from_components,
)


@dataclass(frozen=True)
class ResearchEnablingIntent:
    operation_type: str
    immediate_tech: str
    strategic_target_tech: str
    downstream_operation_id: str
    completion_deadline_turn: int
    scheduling_bid: float
    emergency: bool = False

    def __post_init__(self):
        for value, name in (
                (self.operation_type, "operation type"),
                (self.immediate_tech, "immediate technology"),
                (self.strategic_target_tech, "strategic technology"),
                (self.downstream_operation_id, "downstream operation ID")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "research intent {} is required".format(name))
        if (
                isinstance(self.completion_deadline_turn, bool)
                or not isinstance(self.completion_deadline_turn, int)
                or self.completion_deadline_turn < 0
        ):
            raise ValueError(
                "research completion deadline must be non-negative")
        if (
                not math.isfinite(float(self.scheduling_bid))
                or float(self.scheduling_bid) < 0.0
        ):
            raise ValueError(
                "research scheduling bid must be finite and non-negative")
        if not isinstance(self.emergency, bool):
            raise TypeError(
                "research emergency setting must be boolean")

    @property
    def target_ref(self):
        return "research:{}->{}".format(
            self.immediate_tech,
            self.strategic_target_tech)

    def action(self, player_id):
        return {
            "action_type": "tech_research",
            "actor_id": int(player_id),
            "target": {
                "tech_name": self.immediate_tech,
            },
        }


@dataclass(frozen=True)
class ResearchOperationReadout:
    disposition: str
    reason: str
    step_index: int
    next_action: object = None
    technology_ref: object = None
    dependency_ready: bool = False
    downstream_ready: bool = False

    def __post_init__(self):
        if self.disposition not in (
                "reservable",
                "target_satisfied",
                "waiting",
                "completed",
                "blocked",
                "abandoned"):
            raise ValueError(
                "unknown research readout disposition")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError(
                "research readout reason is required")
        if (
                isinstance(self.step_index, bool)
                or not isinstance(self.step_index, int)
                or self.step_index < 0
        ):
            raise ValueError(
                "research readout step is invalid")
        if (
                self.next_action is not None
                and not isinstance(self.next_action, dict)
        ):
            raise TypeError(
                "research next action must be an object or absent")
        if not isinstance(self.dependency_ready, bool):
            raise TypeError(
                "research dependency readiness must be boolean")
        if not isinstance(self.downstream_ready, bool):
            raise TypeError(
                "research downstream readiness must be boolean")


@dataclass(frozen=True)
class ResearchOperationAssembly:
    spec: OperationSpec
    intent: ResearchEnablingIntent
    requirement_set: RequirementSet
    resource_request: OperationResourceRequest
    selection_action_json: str
    model_artifact_json: str
    initial_premise_packets: tuple
    initial_step_index: int
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if not isinstance(self.spec, OperationSpec):
            raise TypeError(
                "research assembly requires an operation spec")
        if not isinstance(self.intent, ResearchEnablingIntent):
            raise TypeError(
                "research assembly requires an intent")
        if not isinstance(self.requirement_set, RequirementSet):
            raise TypeError(
                "research assembly requires a RequirementSet")
        if not isinstance(
                self.resource_request, OperationResourceRequest):
            raise TypeError(
                "research assembly requires a resource request")
        if (
                self.spec.operation_id
                != self.resource_request.operation_id
                or self.requirement_set.requirement_set_id
                != self.resource_request.requirement_set_id
        ):
            raise ValueError(
                "research assembly identities must agree")
        try:
            action = json.loads(self.selection_action_json)
            artifact = json.loads(self.model_artifact_json)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "research assembly JSON is invalid") from error
        if not isinstance(action, dict) or not isinstance(artifact, dict):
            raise ValueError(
                "research assembly JSON must encode objects")
        if self.initial_step_index not in (0, 1):
            raise ValueError(
                "research initial step must be selection or observation")
        packets = tuple(self.initial_premise_packets)
        if (
                tuple(sorted(packets)) != packets
                or set(row[0] for row in packets)
                != set(self.requirement_set.premise_ids)
                or any(row[1] != 1 for row in packets)
        ):
            raise ValueError(
                "research premise packets must complete the RequirementSet")
        if not self.shadow_only or self.policy_authority:
            raise ValueError(
                "initial research operations are shadow-only")

    @property
    def model_artifact(self):
        return json.loads(self.model_artifact_json)

    def selection_action(self):
        return json.loads(self.selection_action_json)

    def to_dict(self):
        return {
            "initial_premise_packets": dict(
                self.initial_premise_packets),
            "initial_step_index": self.initial_step_index,
            "intent": {
                "completion_deadline_turn":
                    self.intent.completion_deadline_turn,
                "downstream_operation_id":
                    self.intent.downstream_operation_id,
                "emergency": self.intent.emergency,
                "immediate_tech": self.intent.immediate_tech,
                "operation_type": self.intent.operation_type,
                "scheduling_bid": float(
                    self.intent.scheduling_bid),
                "strategic_target_tech":
                    self.intent.strategic_target_tech,
            },
            "model_artifact": self.model_artifact,
            "policy_authority": False,
            "requirement_set": self.requirement_set.to_dict(),
            "resource_request": self.resource_request.to_dict(),
            "selection_action": self.selection_action(),
            "shadow_only": True,
            "spec": self.spec.to_dict(),
        }


class ResearchEnablingOperationAssembler:
    """Form one prerequisite-selection operation from a grounded estimate."""

    RULE_ID = "gdo7-research-enabling/1.0"

    @staticmethod
    def _claim(
            operation_id, step_id, resource,
            window, hardness, exclusive=False):
        return ResourceClaim(
            resource=resource,
            quantity=1,
            window=window,
            hardness=hardness,
            exclusive=exclusive,
            source_operation_id=operation_id,
            source_step_id=step_id)

    @classmethod
    def assemble(
            cls, snapshot, intent, estimate,
            goal_ids, ruleset_digest):
        if not isinstance(intent, ResearchEnablingIntent):
            raise TypeError(
                "research assembly requires an intent")
        if not isinstance(estimate, GroundedTransitionEstimate):
            raise TypeError(
                "research assembly requires a grounded estimate")
        if (
                estimate.authority not in (
                    EstimateAuthority.EXACT_AUTHORITATIVE,
                    EstimateAuthority.DETERMINISTIC_DERIVED)
                or estimate.estimator_id
                != "grounded_research_selection"
        ):
            return None
        action = intent.action(snapshot.player_id)
        if (
                canonical_json_bytes(action).decode("utf-8")
                not in set(snapshot.legal_action_json)
        ):
            return None
        artifact = estimate.to_dict().get("model_artifact")
        dependency = (
            artifact.get("dependency_profile", {})
            if isinstance(artifact, dict) else {})
        if (
                not isinstance(artifact, dict)
                or artifact.get("legal_action") != action
                or artifact.get("immediate_target_tech")
                != intent.immediate_tech
                or artifact.get("strategic_target_tech")
                != intent.strategic_target_tech
                or artifact.get("availability", {}).get(
                    "research_target_selectable_now") is not True
                or artifact.get("availability", {}).get(
                    "technology_known_now") is not False
                or dependency.get("propagation_mode")
                != "decomposed_ruleset_dependency_graph"
                or dependency.get("legacy_tech_want_applied") is not False
                or intent.immediate_tech not in set(
                    dependency.get(
                        "currently_researchable_frontier", ()))
        ):
            return None
        if intent.completion_deadline_turn <= int(snapshot.turn):
            return None
        eta = artifact.get("completion_eta", {})
        if (
                intent.emergency
                and (
                    eta.get("latest_completion_turn") is None
                    or int(eta["latest_completion_turn"])
                    > intent.completion_deadline_turn)
        ):
            return None
        goal_ids = tuple(sorted(str(value) for value in goal_ids))
        if (
                not goal_ids
                or len(set(goal_ids)) != len(goal_ids)
                or any(not value for value in goal_ids)
        ):
            raise ValueError(
                "research operation requires unique goal IDs")
        player_scope = "player:{}".format(snapshot.player_id)
        participants = (
            OperationParticipant(
                role="research_program",
                actor_id=player_scope,
                actor_class="research_slot",
                required=True),
        )
        operation_id = operation_id_from_components(
            intent.operation_type,
            goal_ids,
            participants,
            intent.target_ref,
            str(ruleset_digest),
            snapshot.turn)
        context_digest = structural_hash({
            "dependency_proof_hash": dependency.get("proof_hash"),
            "downstream_operation_id":
                intent.downstream_operation_id,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "operation_id": operation_id,
            "snapshot_id": snapshot.snapshot_id,
            "target_ref": intent.target_ref,
        })
        dependency_premises = tuple(
            "dependency:{}:declared".format(tech)
            for tech in dependency.get(
                "missing_prerequisite_techs", ()))
        premise_ids = (
            "research-slot:{}:available".format(player_scope),
            "research:{}:advertised".format(intent.immediate_tech),
            "research:{}:frontier".format(intent.immediate_tech),
            "research:{}:cost-grounded".format(intent.immediate_tech),
            "research-proof:{}:verified".format(
                dependency.get("proof_hash")),
            "deadline:{}:forecast-supported".format(
                intent.completion_deadline_turn),
            "dependency:{}:declared".format(
                intent.downstream_operation_id),
        ) + dependency_premises
        role_ids = (
            "research_slot_available",
            "selection_action_advertised",
            "immediate_dependency_researchable",
            "target_cost_grounded",
            "dependency_proof_verified",
            "completion_forecast_supported",
            "downstream_dependency_declared",
        ) + tuple(
            "technology_prerequisite_declared"
            for _ in dependency_premises)
        requirement_set = RequirementSet(
            requirement_set_id="requirement-set:{}".format(
                structural_hash({
                    "context_digest": context_digest,
                    "premise_ids": premise_ids,
                    "rule_id": cls.RULE_ID,
                })[:24]),
            rule_id=cls.RULE_ID,
            premise_ids=premise_ids,
            role_ids=role_ids,
            context_digest=context_digest)
        steps = (
            OperationStep(
                step_id="step-{}".format(
                    structural_hash({
                        "action": action,
                        "operation_id": operation_id,
                        "phase": "select-research",
                    })[:32]),
                action_type="tech_research",
                actor_role="research_program",
                target_ref=intent.target_ref,
                requirement_set_id=(
                    requirement_set.requirement_set_id),
                completion_predicate_id=(
                    "research:target-selected"),
                maximum_attempts=1),
            OperationStep(
                step_id="step-{}".format(
                    structural_hash({
                        "operation_id": operation_id,
                        "phase": "observe-technology",
                        "tech": intent.immediate_tech,
                    })[:32]),
                action_type="observe_research_completion",
                actor_role="research_program",
                target_ref=intent.target_ref,
                requirement_set_id=(
                    requirement_set.requirement_set_id),
                completion_predicate_id=(
                    "research:technology-observed"),
                maximum_attempts=1),
        )
        spec = OperationSpec(
            schema_version=OPERATION_SCHEMA_VERSION,
            operation_id=operation_id,
            operation_type=intent.operation_type,
            goal_ids=goal_ids,
            participants=participants,
            target_ref=intent.target_ref,
            steps=steps,
            created_turn=int(snapshot.turn),
            expiry_turn=intent.completion_deadline_turn,
            replacement_margin=0.0,
            provenance=(
                "grounded-research-transition-model",
                "server-advertised-research-action",
                "canonical-dependency-oracle-proof",
                "decomposed-dependency-graph-only",
                "technology-requires-later-observation",
                "shadow-only-gdo7b",
            ),
            ruleset_digest=str(ruleset_digest))
        initial_step_index = (
            1 if snapshot.research.target_name
            == intent.immediate_tech else 0)
        claims = []
        if initial_step_index == 0:
            claims.extend((
                cls._claim(
                    operation_id, steps[0].step_id,
                    ResourceRef(
                        GameResourceKind.RESEARCH_SLOT,
                        player_scope, "current_target",
                        player_scope),
                    TurnWindow(snapshot.turn, snapshot.turn + 1),
                    ClaimHardness.HARD_CURRENT,
                    exclusive=True),
                cls._claim(
                    operation_id, steps[0].step_id,
                    ResourceRef(
                        GameResourceKind.ACTION_BUDGET,
                        player_scope, "controller",
                        player_scope),
                    TurnWindow(snapshot.turn, snapshot.turn + 1),
                    ClaimHardness.HARD_CURRENT),
            ))
        claims.append(
            cls._claim(
                operation_id, steps[1].step_id,
                ResourceRef(
                    GameResourceKind.RESEARCH_SLOT,
                    player_scope, "current_target",
                    player_scope),
                TurnWindow(
                    snapshot.turn + 1,
                    intent.completion_deadline_turn + 1),
                ClaimHardness.CONDITIONAL_FUTURE,
                exclusive=True))
        request = OperationResourceRequest(
            operation_id=operation_id,
            bid=float(intent.scheduling_bid),
            claims=tuple(claims),
            requirement_set_id=(
                requirement_set.requirement_set_id))
        return ResearchOperationAssembly(
            spec=spec,
            intent=intent,
            requirement_set=requirement_set,
            resource_request=request,
            selection_action_json=canonical_json_bytes(
                action).decode("utf-8"),
            model_artifact_json=json.dumps(
                artifact, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")),
            initial_premise_packets=tuple(
                (premise_id, 1)
                for premise_id in sorted(premise_ids)),
            initial_step_index=initial_step_index)

    @classmethod
    def current_step_resource_request(
            cls, assembly, snapshot):
        if not isinstance(assembly, ResearchOperationAssembly):
            raise TypeError(
                "research request requires an assembly")
        if int(snapshot.turn) > (
                assembly.intent.completion_deadline_turn):
            return None
        player_scope = "player:{}".format(snapshot.player_id)
        step = assembly.spec.steps[0]
        claims = [
            cls._claim(
                assembly.spec.operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind.RESEARCH_SLOT,
                    player_scope, "current_target",
                    player_scope),
                TurnWindow(snapshot.turn, snapshot.turn + 1),
                ClaimHardness.HARD_CURRENT,
                exclusive=True),
            cls._claim(
                assembly.spec.operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind.ACTION_BUDGET,
                    player_scope, "controller",
                    player_scope),
                TurnWindow(snapshot.turn, snapshot.turn + 1),
                ClaimHardness.HARD_CURRENT),
        ]
        claims.extend(
            claim
            for claim in assembly.resource_request.claims
            if (
                claim.hardness
                == ClaimHardness.CONDITIONAL_FUTURE
                and claim.window.end_turn_exclusive
                > snapshot.turn + 1))
        return OperationResourceRequest(
            operation_id=assembly.spec.operation_id,
            bid=float(assembly.intent.scheduling_bid),
            claims=tuple(claims),
            requirement_set_id=None)

    @classmethod
    def readout(cls, assembly, snapshot, step_index):
        if not isinstance(assembly, ResearchOperationAssembly):
            raise TypeError(
                "research readout requires an assembly")
        if (
                isinstance(step_index, bool)
                or not isinstance(step_index, int)
                or step_index < 0
        ):
            raise ValueError(
                "research readout step is invalid")
        research = getattr(snapshot, "research", None)
        if research is None or research.available is not True:
            return ResearchOperationReadout(
                "abandoned",
                "authoritative-research-state-unavailable",
                step_index)
        known = set(research.known_techs)
        if assembly.intent.immediate_tech in known:
            strategic_complete = bool(
                assembly.intent.strategic_target_tech in known)
            return ResearchOperationReadout(
                "completed",
                "authoritative-technology-observed",
                step_index,
                technology_ref="technology:{}".format(
                    assembly.intent.immediate_tech),
                dependency_ready=True,
                downstream_ready=strategic_complete)
        same_target = bool(
            research.target_name
            == assembly.intent.immediate_tech)
        if step_index == 0:
            if same_target:
                return ResearchOperationReadout(
                    "target_satisfied",
                    "authoritative-research-target-observed",
                    step_index)
            action = assembly.selection_action()
            if (
                    canonical_json_bytes(action).decode("utf-8")
                    not in set(snapshot.legal_action_json)
            ):
                return ResearchOperationReadout(
                    "blocked",
                    "research-action-no-longer-advertised",
                    step_index)
            return ResearchOperationReadout(
                "reservable",
                "grounded-research-action-currently-legal",
                step_index,
                next_action=action)
        if not same_target:
            return ResearchOperationReadout(
                "blocked",
                "research-target-diverged-before-technology-observation",
                step_index)
        if (
                isinstance(research.beakers_per_turn, int)
                and not isinstance(research.beakers_per_turn, bool)
                and research.beakers_per_turn <= 0
                and isinstance(research.progress, int)
                and isinstance(research.cost, int)
                and research.progress < research.cost
        ):
            return ResearchOperationReadout(
                "blocked",
                "research-beaker-output-stalled",
                step_index)
        return ResearchOperationReadout(
            "waiting",
            "research-selected-technology-not-yet-observed",
            step_index)
