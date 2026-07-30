"""Identity-bearing production enabling operations.

Production is represented as two distinct lifecycle steps:

1. select the city queue target;
2. observe the product in a later authoritative snapshot.

The second step has no executable action.  In particular, an advertised queue
change and an in-progress unit never become a combat/transport participant.
"""

import json
import math
import re
from dataclasses import dataclass

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from ..pressure.coalitions import (
    RequirementSet,
)
from ..pressure.resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from ..pressure.resource_scheduler import (
    OperationResourceRequest,
)
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


def _normalized(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


@dataclass(frozen=True)
class ProductionEnablingIntent:
    """Declared downstream need for one concrete city product."""

    operation_type: str
    city_id: int
    production_kind: int
    production_value: int
    target_name: str
    downstream_operation_id: str
    completion_deadline_turn: int
    scheduling_bid: float
    emergency: bool = False

    def __post_init__(self):
        for value, name in (
                (self.operation_type,
                 "operation type"),
                (self.target_name,
                 "target name"),
                (self.downstream_operation_id,
                 "downstream operation ID")):
            if not isinstance(
                    value, str) or not value:
                raise ValueError(
                    "production intent {} is required".format(
                        name))
        for value, name in (
                (self.city_id, "city ID"),
                (self.production_kind,
                 "production kind"),
                (self.production_value,
                 "production value"),
                (self.completion_deadline_turn,
                 "completion deadline")):
            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
            ):
                raise ValueError(
                    "production intent {} must be non-negative".format(
                        name))
        if (
                not math.isfinite(
                    float(
                        self.scheduling_bid))
                or float(
                    self.scheduling_bid) < 0.0
        ):
            raise ValueError(
                "production scheduling bid must be finite and non-negative")
        if not isinstance(
                self.emergency, bool):
            raise TypeError(
                "production emergency setting must be boolean")

    @property
    def target_ref(self):
        return (
            "production:{}:{}:{}@city:{}"
            .format(
                self.production_kind,
                self.production_value,
                _normalized(
                    self.target_name),
                self.city_id))

    def action(self):
        return {
            "action_type":
                "city_production",
            "city_id": self.city_id,
            "production_kind":
                self.production_kind,
            "production_value":
                self.production_value,
            "target": {
                "production_type":
                    self.target_name,
            },
        }


@dataclass(frozen=True)
class ProductionOperationReadout:
    disposition: str
    reason: str
    step_index: int
    next_action: object = None
    product_ref: object = None

    def __post_init__(self):
        if self.disposition not in (
                "reservable",
                "queue_satisfied",
                "waiting",
                "completed",
                "blocked",
                "abandoned"):
            raise ValueError(
                "unknown production readout disposition")
        if not isinstance(
                self.reason, str
                ) or not self.reason:
            raise ValueError(
                "production readout reason is required")
        if (
                isinstance(self.step_index, bool)
                or not isinstance(
                    self.step_index, int)
                or self.step_index < 0
        ):
            raise ValueError(
                "production readout step is invalid")
        if (
                self.next_action is not None
                and not isinstance(
                    self.next_action, dict)
        ):
            raise TypeError(
                "production next action must be an object or absent")


@dataclass(frozen=True)
class ProductionOperationAssembly:
    """One shadow-only queue-plus-observation operation."""

    spec: OperationSpec
    intent: ProductionEnablingIntent
    requirement_set: RequirementSet
    resource_request: OperationResourceRequest
    queue_action_json: str
    model_artifact_json: str
    initial_premise_packets: tuple
    initial_step_index: int
    baseline_product_ids: tuple
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if not isinstance(
                self.spec, OperationSpec):
            raise TypeError(
                "production assembly requires an operation spec")
        if not isinstance(
                self.intent,
                ProductionEnablingIntent):
            raise TypeError(
                "production assembly requires an intent")
        if not isinstance(
                self.requirement_set,
                RequirementSet):
            raise TypeError(
                "production assembly requires a RequirementSet")
        if not isinstance(
                self.resource_request,
                OperationResourceRequest):
            raise TypeError(
                "production assembly requires a resource request")
        if (
                self.spec.operation_id
                    != self.resource_request
                    .operation_id
                or self.requirement_set
                    .requirement_set_id
                    != self.resource_request
                    .requirement_set_id
        ):
            raise ValueError(
                "production assembly identities must agree")
        try:
            action = json.loads(
                self.queue_action_json)
            artifact = json.loads(
                self.model_artifact_json)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "production assembly JSON is invalid") from error
        if (
                not isinstance(action, dict)
                or not isinstance(
                    artifact, dict)
        ):
            raise ValueError(
                "production assembly JSON must encode objects")
        if self.initial_step_index not in (
                0, 1):
            raise ValueError(
                "production initial step must be queue or completion")
        packets = tuple(
            self.initial_premise_packets)
        if (
                tuple(sorted(packets))
                    != packets
                or set(
                    premise_id
                    for premise_id, _
                    in packets)
                    != set(
                        self.requirement_set
                        .premise_ids)
                or any(
                    value != 1
                    for _, value in packets)
        ):
            raise ValueError(
                "production premise packets must complete the RequirementSet")
        if (
                tuple(sorted(set(
                    self.baseline_product_ids)))
                    != tuple(
                        self.baseline_product_ids)
        ):
            raise ValueError(
                "baseline product IDs must be unique and sorted")
        if not self.shadow_only or self.policy_authority:
            raise ValueError(
                "initial production operations are shadow-only")

    @property
    def model_artifact(self):
        return json.loads(
            self.model_artifact_json)

    @property
    def target_profile(self):
        return self.model_artifact[
            "target_profile"]

    def queue_action(self):
        return json.loads(
            self.queue_action_json)

    def to_dict(self):
        return {
            "baseline_product_ids":
                list(
                    self.baseline_product_ids),
            "initial_premise_packets":
                dict(
                    self.initial_premise_packets),
            "initial_step_index":
                self.initial_step_index,
            "intent": {
                "city_id":
                    self.intent.city_id,
                "completion_deadline_turn":
                    self.intent
                    .completion_deadline_turn,
                "downstream_operation_id":
                    self.intent
                    .downstream_operation_id,
                "emergency":
                    self.intent.emergency,
                "operation_type":
                    self.intent.operation_type,
                "production_kind":
                    self.intent.production_kind,
                "production_value":
                    self.intent.production_value,
                "scheduling_bid":
                    float(
                        self.intent
                        .scheduling_bid),
                "target_name":
                    self.intent.target_name,
            },
            "model_artifact":
                self.model_artifact,
            "policy_authority": False,
            "queue_action":
                self.queue_action(),
            "requirement_set":
                self.requirement_set
                .to_dict(),
            "resource_request":
                self.resource_request
                .to_dict(),
            "shadow_only": True,
            "spec": self.spec.to_dict(),
        }


class ProductionEnablingOperationAssembler:
    """Form a BUILD_* operation from one grounded production estimate."""

    RULE_ID = (
        "gdo7-production-enabling/1.0")

    @staticmethod
    def _claim(
            operation_id, step_id,
            resource, window,
            hardness,
            exclusive=False,
            quantity=1):
        return ResourceClaim(
            resource=resource,
            quantity=quantity,
            window=window,
            hardness=hardness,
            exclusive=exclusive,
            source_operation_id=(
                operation_id),
            source_step_id=step_id)

    @staticmethod
    def _baseline_products(
            snapshot, intent,
            target_profile):
        if target_profile[
                "is_unit"]:
            return tuple(sorted(
                "unit:{}".format(
                    unit.unit_id)
                for unit in
                snapshot.units
                if (
                    unit.homecity
                        == intent.city_id
                    and _normalized(
                        unit.unit_type)
                        == _normalized(
                            intent
                            .target_name))))
        city = snapshot.city(
            intent.city_id)
        return tuple(sorted(
            "building:{}".format(
                building.improvement_id)
            for building in
            getattr(city, "buildings", ())
            if (
                building.improvement_id
                    == intent
                    .production_value
                or _normalized(
                    building.name)
                    == _normalized(
                        intent.target_name))))

    @classmethod
    def assemble(
            cls, snapshot, intent,
            estimate, goal_ids,
            ruleset_digest):
        if not isinstance(
                intent,
                ProductionEnablingIntent):
            raise TypeError(
                "production assembly requires an intent")
        if not isinstance(
                estimate,
                GroundedTransitionEstimate):
            raise TypeError(
                "production assembly requires a grounded estimate")
        if (
                estimate.authority
                not in (
                    EstimateAuthority
                    .EXACT_AUTHORITATIVE,
                    EstimateAuthority
                    .DETERMINISTIC_DERIVED)
                or estimate.estimator_id
                    != "grounded_city_production_queue"
        ):
            return None
        action = intent.action()
        if (
                canonical_json_bytes(
                    action).decode("utf-8")
                not in set(
                    snapshot
                    .legal_action_json)
        ):
            return None
        artifact = estimate.to_dict().get(
            "model_artifact")
        if (
                not isinstance(
                    artifact, dict)
                or artifact.get(
                    "legal_action") != action
                or artifact.get(
                    "availability", {}).get(
                        "queueable_now")
                    is not True
                or artifact.get(
                    "availability", {}).get(
                        "product_available_now")
                    is not False
        ):
            return None
        city = snapshot.city(
            intent.city_id)
        if city is None:
            return None
        if (
                intent
                .completion_deadline_turn
                <= int(snapshot.turn)
        ):
            return None
        eta = artifact.get(
            "completion_eta", {})
        if (
                intent.emergency
                and (
                    eta.get(
                        "latest_completion_turn")
                        is None
                    or int(
                        eta[
                            "latest_completion_turn"])
                        > intent
                        .completion_deadline_turn)
        ):
            return None
        goal_ids = tuple(sorted(
            str(value)
            for value in goal_ids))
        if (
                not goal_ids
                or len(set(goal_ids))
                    != len(goal_ids)
                or any(not value
                       for value in goal_ids)
        ):
            raise ValueError(
                "production operation requires unique goal IDs")
        participants = (
            OperationParticipant(
                role="production_city",
                actor_id="city:{}".format(
                    intent.city_id),
                actor_class="city",
                required=True),
        )
        operation_id = (
            operation_id_from_components(
                intent.operation_type,
                goal_ids,
                participants,
                intent.target_ref,
                str(ruleset_digest),
                snapshot.turn))
        context_digest = structural_hash({
            "downstream_operation_id":
                intent.downstream_operation_id,
            "legal_actions_digest":
                snapshot
                .legal_actions_digest,
            "operation_id":
                operation_id,
            "snapshot_id":
                snapshot.snapshot_id,
            "target_ref":
                intent.target_ref,
        })
        premise_ids = (
            "city:{}:owned".format(
                intent.city_id),
            "target:{}:advertised".format(
                intent.target_ref),
            "target:{}:buildable".format(
                intent.target_ref),
            "target:{}:ruleset-profile".format(
                intent.target_ref),
            "deadline:{}:forecast-supported".format(
                intent
                .completion_deadline_turn),
            "dependency:{}:declared".format(
                intent
                .downstream_operation_id),
        )
        requirement_set = RequirementSet(
            requirement_set_id=(
                "requirement-set:{}".format(
                    structural_hash({
                        "context_digest":
                            context_digest,
                        "premise_ids":
                            premise_ids,
                        "rule_id":
                            cls.RULE_ID,
                    })[:24])),
            rule_id=cls.RULE_ID,
            premise_ids=premise_ids,
            role_ids=(
                "city_owned",
                "queue_action_advertised",
                "target_buildable",
                "ruleset_profile_grounded",
                "completion_forecast_supported",
                "downstream_dependency_declared",
            ),
            context_digest=(
                context_digest))
        steps = (
            OperationStep(
                step_id="step-{}".format(
                    structural_hash({
                        "action": action,
                        "operation_id":
                            operation_id,
                        "phase":
                            "select-queue",
                    })[:32]),
                action_type=(
                    "city_production"),
                actor_role=(
                    "production_city"),
                target_ref=(
                    intent.target_ref),
                requirement_set_id=(
                    requirement_set
                    .requirement_set_id),
                completion_predicate_id=(
                    "production:queue-selected"),
                maximum_attempts=1),
            OperationStep(
                step_id="step-{}".format(
                    structural_hash({
                        "downstream":
                            intent
                            .downstream_operation_id,
                        "operation_id":
                            operation_id,
                        "phase":
                            "observe-completion",
                    })[:32]),
                action_type=(
                    "observe_production_completion"),
                actor_role=(
                    "production_city"),
                target_ref=(
                    intent.target_ref),
                requirement_set_id=(
                    requirement_set
                    .requirement_set_id),
                completion_predicate_id=(
                    "production:product-observed"),
                maximum_attempts=1),
        )
        spec = OperationSpec(
            schema_version=(
                OPERATION_SCHEMA_VERSION),
            operation_id=operation_id,
            operation_type=(
                intent.operation_type),
            goal_ids=goal_ids,
            participants=participants,
            target_ref=(
                intent.target_ref),
            steps=steps,
            created_turn=int(
                snapshot.turn),
            expiry_turn=(
                intent
                .completion_deadline_turn),
            replacement_margin=0.0,
            provenance=(
                "grounded-production-transition-model",
                "server-advertised-queue-action",
                "explicit-downstream-operation-dependency",
                "product-identity-requires-later-observation",
                "shadow-only-gdo7a",
            ),
            ruleset_digest=str(
                ruleset_digest))
        player_scope = (
            "player:{}".format(
                snapshot.player_id))
        initial_step_index = (
            1 if artifact[
                "current_production"][
                    "same_target"]
            else 0)
        claims = []
        if initial_step_index == 0:
            claims.extend((
                cls._claim(
                    operation_id,
                    steps[0].step_id,
                    ResourceRef(
                        GameResourceKind
                        .CITY_PRODUCTION_SLOT,
                        "city:{}".format(
                            intent.city_id),
                        "production",
                        player_scope),
                    TurnWindow(
                        snapshot.turn,
                        snapshot.turn + 1),
                    ClaimHardness
                    .HARD_CURRENT,
                    exclusive=True),
                cls._claim(
                    operation_id,
                    steps[0].step_id,
                    ResourceRef(
                        GameResourceKind
                        .ACTION_BUDGET,
                        player_scope,
                        "controller",
                        player_scope),
                    TurnWindow(
                        snapshot.turn,
                        snapshot.turn + 1),
                    ClaimHardness
                    .HARD_CURRENT),
            ))
        claims.append(
            cls._claim(
                operation_id,
                steps[1].step_id,
                ResourceRef(
                    GameResourceKind
                    .CITY_PRODUCTION_SLOT,
                    "city:{}".format(
                        intent.city_id),
                    "production",
                    player_scope),
                TurnWindow(
                    snapshot.turn + 1,
                    intent
                    .completion_deadline_turn
                    + 1),
                ClaimHardness
                .CONDITIONAL_FUTURE,
                exclusive=True))
        profile = artifact[
            "target_profile"]
        gold_upkeep = int(
            profile[
                "gold_upkeep"]
            + profile[
                "building_upkeep"])
        earliest_completion = (
            eta.get(
                "earliest_completion_turn")
            or snapshot.turn + 1)
        if (
                gold_upkeep > 0
                and earliest_completion
                    <= intent
                    .completion_deadline_turn
        ):
            claims.append(
                cls._claim(
                    operation_id,
                    steps[1].step_id,
                    ResourceRef(
                        GameResourceKind
                        .TREASURY,
                        player_scope,
                        "gold",
                        player_scope),
                    TurnWindow(
                        int(
                            earliest_completion),
                        intent
                        .completion_deadline_turn
                        + 1),
                    ClaimHardness
                    .CONDITIONAL_FUTURE,
                    quantity=gold_upkeep))
        request = OperationResourceRequest(
            operation_id=operation_id,
            bid=float(
                intent.scheduling_bid),
            claims=tuple(claims),
            requirement_set_id=(
                requirement_set
                .requirement_set_id))
        baseline = cls._baseline_products(
            snapshot, intent,
            profile)
        return ProductionOperationAssembly(
            spec=spec,
            intent=intent,
            requirement_set=(
                requirement_set),
            resource_request=request,
            queue_action_json=(
                canonical_json_bytes(
                    action).decode("utf-8")),
            model_artifact_json=(
                json.dumps(
                    artifact,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"))),
            initial_premise_packets=tuple(
                (premise_id, 1)
                for premise_id in
                sorted(premise_ids)),
            initial_step_index=(
                initial_step_index),
            baseline_product_ids=(
                baseline))

    @staticmethod
    def _observed_product(
            assembly, snapshot):
        intent = assembly.intent
        profile = (
            assembly.target_profile)
        baseline = set(
            assembly
            .baseline_product_ids)
        if profile["is_unit"]:
            matches = tuple(sorted(
                "unit:{}".format(
                    unit.unit_id)
                for unit in
                snapshot.units
                if (
                    unit.homecity
                        == intent.city_id
                    and _normalized(
                        unit.unit_type)
                        == _normalized(
                            intent.target_name))))
        else:
            city = snapshot.city(
                intent.city_id)
            matches = tuple(sorted(
                "building:{}".format(
                    building
                    .improvement_id)
                for building in
                getattr(
                    city,
                    "buildings", ())
                if (
                    building.improvement_id
                        == intent
                        .production_value
                    or _normalized(
                        building.name)
                        == _normalized(
                            intent.target_name))))
        return next((
            value for value
            in matches
            if value not in baseline
        ), None)

    @classmethod
    def current_step_resource_request(
            cls, assembly, snapshot):
        """Rebind queue-step hard claims to one exact current snapshot."""
        if not isinstance(
                assembly,
                ProductionOperationAssembly):
            raise TypeError(
                "production request requires an assembly")
        if int(snapshot.turn) > (
                assembly.intent
                .completion_deadline_turn):
            return None
        player_scope = (
            "player:{}".format(
                snapshot.player_id))
        step = assembly.spec.steps[0]
        claims = [
            cls._claim(
                assembly.spec.operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind
                    .CITY_PRODUCTION_SLOT,
                    "city:{}".format(
                        assembly.intent
                        .city_id),
                    "production",
                    player_scope),
                TurnWindow(
                    snapshot.turn,
                    snapshot.turn + 1),
                ClaimHardness
                .HARD_CURRENT,
                exclusive=True),
            cls._claim(
                assembly.spec.operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind
                    .ACTION_BUDGET,
                    player_scope,
                    "controller",
                    player_scope),
                TurnWindow(
                    snapshot.turn,
                    snapshot.turn + 1),
                ClaimHardness
                .HARD_CURRENT),
        ]
        claims.extend(
            claim
            for claim in
            assembly.resource_request
            .claims
            if (
                claim.hardness
                    == ClaimHardness
                    .CONDITIONAL_FUTURE
                and claim.window
                    .end_turn_exclusive
                    > snapshot.turn + 1))
        return OperationResourceRequest(
            operation_id=(
                assembly.spec
                .operation_id),
            bid=float(
                assembly.intent
                .scheduling_bid),
            claims=tuple(claims),
            requirement_set_id=None)

    @classmethod
    def readout(
            cls, assembly, snapshot,
            step_index):
        if not isinstance(
                assembly,
                ProductionOperationAssembly):
            raise TypeError(
                "production readout requires an assembly")
        if (
                isinstance(step_index, bool)
                or not isinstance(
                    step_index, int)
                or step_index < 0
        ):
            raise ValueError(
                "production readout step is invalid")
        city = snapshot.city(
            assembly.intent.city_id)
        if city is None:
            return ProductionOperationReadout(
                "abandoned",
                "production-city-removed",
                step_index)
        product = cls._observed_product(
            assembly, snapshot)
        if product is not None:
            return ProductionOperationReadout(
                "completed",
                "authoritative-product-identity-observed",
                step_index,
                product_ref=product)
        same_target = bool(
            city.production_kind
                == assembly.intent
                .production_kind
            and city.production_value
                == assembly.intent
                .production_value)
        if step_index == 0:
            if same_target:
                return ProductionOperationReadout(
                    "queue_satisfied",
                    "authoritative-queue-target-observed",
                    step_index)
            action = assembly.queue_action()
            if (
                    canonical_json_bytes(
                        action).decode("utf-8")
                    not in set(
                        snapshot
                        .legal_action_json)
            ):
                return ProductionOperationReadout(
                    "blocked",
                    "queue-action-no-longer-advertised",
                    step_index)
            return ProductionOperationReadout(
                "reservable",
                "grounded-queue-action-currently-legal",
                step_index,
                next_action=action)
        if not same_target:
            return ProductionOperationReadout(
                "blocked",
                "production-target-diverged-before-product-observation",
                step_index)
        shield_rate = (
            city.surplus[1]
            if len(city.surplus) > 1
            else None)
        shield_stock = (
            city.shield_stock)
        build_cost = int(
            assembly.target_profile[
                "build_cost"])
        if (
                isinstance(
                    shield_rate, (int, float))
                and not isinstance(
                    shield_rate, bool)
                and shield_rate <= 0
                and isinstance(
                    shield_stock, int)
                and shield_stock
                    < build_cost
        ):
            return ProductionOperationReadout(
                "blocked",
                "production-shield-output-stalled",
                step_index)
        return ProductionOperationReadout(
            "waiting",
            "queue-selected-product-not-yet-observed",
            step_index)
