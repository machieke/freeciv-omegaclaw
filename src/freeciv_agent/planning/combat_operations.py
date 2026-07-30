"""Shadow-only atomic combat operations over native probability intervals."""

import itertools
import json
import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.coalitions import RequirementSet
from ..pressure.resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceCapacity,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from ..pressure.resource_scheduler import OperationResourceRequest
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    operation_id_from_components,
)


@dataclass(frozen=True)
class ConditionalProbabilityInterval:
    """A closed probability interval with an explicit semantic source."""

    lower: float
    upper: float
    source: str

    def __post_init__(self):
        lower = float(self.lower)
        upper = float(self.upper)
        if (
            not math.isfinite(lower)
            or not math.isfinite(upper)
            or not 0.0 <= lower <= upper <= 1.0
        ):
            raise ValueError(
                "probability interval must satisfy 0 <= lower <= upper <= 1")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError(
                "probability interval source is required")

    def to_dict(self):
        return {
            "lower": float(self.lower),
            "source": self.source,
            "upper": float(self.upper),
        }


def conditional_success_interval(
        first_step, second_given_first_failure):
    """Compose an explicitly conditional branch without independence."""
    if not isinstance(
            first_step,
            ConditionalProbabilityInterval):
        raise TypeError(
            "first step must be a probability interval")
    if not isinstance(
            second_given_first_failure,
            ConditionalProbabilityInterval):
        raise TypeError(
            "conditional second step must be a probability interval")
    return ConditionalProbabilityInterval(
        lower=(
            first_step.lower
            + (1.0 - first_step.lower)
            * second_given_first_failure.lower),
        upper=(
            first_step.upper
            + (1.0 - first_step.upper)
            * second_given_first_failure.upper),
        source=(
            "explicit-conditional:first-or-second-given-first-failure"))


@dataclass(frozen=True)
class CombatOperationAssembly:
    """One reservable two-actor attack with a conditional second step."""

    spec: OperationSpec
    requirement_set: RequirementSet
    resource_request: OperationResourceRequest
    action_json_by_step: tuple
    step_probability_intervals: tuple
    operation_probability_interval: ConditionalProbabilityInterval
    target_unit_id: int
    target_tile_id: int
    initial_premise_packets: tuple
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if not isinstance(self.spec, OperationSpec):
            raise TypeError(
                "combat assembly requires an operation spec")
        if not isinstance(
                self.requirement_set,
                RequirementSet):
            raise TypeError(
                "combat assembly requires a RequirementSet")
        if not isinstance(
                self.resource_request,
                OperationResourceRequest):
            raise TypeError(
                "combat assembly requires a resource request")
        if (
            self.spec.operation_id
                != self.resource_request.operation_id
            or self.requirement_set.requirement_set_id
                != self.resource_request.requirement_set_id
        ):
            raise ValueError(
                "combat assembly identities must agree")
        if (
            len(self.action_json_by_step)
                != len(self.spec.steps)
            or len(self.step_probability_intervals)
                != len(self.spec.steps)
        ):
            raise ValueError(
                "combat assembly actions and intervals must match its steps")
        for action_json in self.action_json_by_step:
            try:
                action = json.loads(
                    action_json)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "combat step action must be canonical JSON") from error
            if not isinstance(action, dict):
                raise ValueError(
                    "combat step action must encode an object")
        if any(
                not isinstance(
                    interval,
                    ConditionalProbabilityInterval)
                for interval in
                self.step_probability_intervals):
            raise TypeError(
                "combat step probabilities must be intervals")
        if not isinstance(
                self.operation_probability_interval,
                ConditionalProbabilityInterval):
            raise TypeError(
                "combat operation probability must be an interval")
        if (
            isinstance(self.target_unit_id, bool)
            or not isinstance(
                self.target_unit_id, int)
            or self.target_unit_id < 1
            or isinstance(self.target_tile_id, bool)
            or not isinstance(
                self.target_tile_id, int)
            or self.target_tile_id < 0
        ):
            raise ValueError(
                "combat operation target IDs are invalid")
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
            or any(value != 1
                   for _, value in packets)
        ):
            raise ValueError(
                "combat premise packets must complete the RequirementSet")
        if not self.shadow_only or self.policy_authority:
            raise ValueError(
                "initial combat operations are shadow-only")

    def action_for_step(self, step_index):
        if (
            isinstance(step_index, bool)
            or not isinstance(step_index, int)
            or not 0 <= step_index
                < len(self.action_json_by_step)
        ):
            raise IndexError(
                "combat operation step index is out of range")
        return json.loads(
            self.action_json_by_step[
                step_index])

    def to_dict(self):
        return {
            "actions": [
                json.loads(value)
                for value in
                self.action_json_by_step],
            "initial_premise_packets": dict(
                self.initial_premise_packets),
            "operation_probability_interval":
                self.operation_probability_interval
                .to_dict(),
            "policy_authority": False,
            "requirement_set":
                self.requirement_set.to_dict(),
            "resource_request":
                self.resource_request.to_dict(),
            "shadow_only": True,
            "spec": self.spec.to_dict(),
            "step_probability_intervals": [
                value.to_dict()
                for value in
                self.step_probability_intervals],
            "target_tile_id":
                self.target_tile_id,
            "target_unit_id":
                self.target_unit_id,
        }


@dataclass(frozen=True)
class CombatOperationReadout:
    disposition: str
    next_action: object
    reason: str
    step_index: int

    def __post_init__(self):
        if self.disposition not in (
                "reservable", "completed",
                "blocked", "abandoned"):
            raise ValueError(
                "unknown combat operation disposition")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError(
                "combat operation readout reason is required")
        if (
            isinstance(self.step_index, bool)
            or not isinstance(
                self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError(
                "combat operation readout step is invalid")
        if (
            self.next_action is not None
            and not isinstance(
                self.next_action, dict)
        ):
            raise TypeError(
                "combat next action must be an object or absent")


class CombatOperationAssembler:
    """Enumerate deterministic two-actor conditional attack operations."""

    OPERATION_TYPE = (
        "attack_then_conditional_attack")
    RULE_ID = (
        "combat-operation:conditional-target-neutralization")

    @staticmethod
    def _legal_attacks(snapshot):
        result = {}
        for action_json in getattr(
                snapshot,
                "legal_action_json", ()):
            action = json.loads(
                action_json)
            if action.get(
                    "action_type") != (
                    "unit_attack"):
                continue
            actor_id = action.get(
                "actor_id")
            target = action.get(
                "target")
            if (
                isinstance(actor_id, bool)
                or not isinstance(
                    actor_id, int)
                or not isinstance(
                    target, dict)
                or isinstance(
                    target.get("x"), bool)
                or not isinstance(
                    target.get("x"), int)
                or isinstance(
                    target.get("y"), bool)
                or not isinstance(
                    target.get("y"), int)
            ):
                continue
            target_tile = (
                target["x"]
                + target["y"]
                * snapshot.map_width)
            key = (
                actor_id,
                target_tile)
            result.setdefault(
                key, action_json)
        return result

    @staticmethod
    def _candidates(snapshot):
        legal = (
            CombatOperationAssembler
            ._legal_attacks(snapshot))
        candidates = []
        for result in getattr(
                snapshot,
                "combat_probabilities", ()):
            action_json = legal.get((
                result.actor_unit_id,
                result.target_tile_id))
            probability = (
                result.action_probability(
                    "attack"))
            target_unit_id = (
                result.target_unit_id)
            if target_unit_id == 0:
                if len(
                        result.target_unit_ids) != 1:
                    continue
                target_unit_id = (
                    result
                    .target_unit_ids[0])
            target = snapshot.visible_enemy_unit(
                target_unit_id)
            actor = snapshot.unit(
                result.actor_unit_id)
            if (
                action_json is None
                or actor is None
                or target is None
                or target.tile
                    != result.target_tile_id
                or probability is None
                or probability.status
                    != "bounded"
                or probability
                    .upper_probability
                    <= 0.0
            ):
                continue
            candidates.append({
                "action_json":
                    action_json,
                "actor_id":
                    result.actor_unit_id,
                "interval":
                    ConditionalProbabilityInterval(
                        probability
                        .lower_probability,
                        probability
                        .upper_probability,
                        "freeciv-server-action-probability"),
                "target_tile_id":
                    result.target_tile_id,
                "target_unit_id":
                    target_unit_id,
            })
        return tuple(sorted(
            candidates,
            key=lambda row: (
                row["target_tile_id"],
                row["target_unit_id"],
                -row["interval"].lower,
                -row["interval"].upper,
                row["actor_id"])))

    @staticmethod
    def _claim(
            operation_id, step_id,
            resource, hardness,
            turn, exclusive=False):
        return ResourceClaim(
            resource=resource,
            quantity=1,
            window=TurnWindow(
                turn, turn + 1),
            hardness=hardness,
            exclusive=exclusive,
            source_operation_id=(
                operation_id),
            source_step_id=step_id)

    def assemble(
            self, snapshot,
            ruleset_digest,
            goal_ids=(
                "pf-impact:survival",),
            maximum_operations=32):
        if (
            isinstance(maximum_operations, bool)
            or not isinstance(
                maximum_operations, int)
            or not 1 <= maximum_operations <= 128
        ):
            raise ValueError(
                "maximum_operations must be in 1..128")
        grouped = {}
        for candidate in self._candidates(
                snapshot):
            grouped.setdefault((
                candidate[
                    "target_unit_id"],
                candidate[
                    "target_tile_id"]),
                []).append(candidate)
        assemblies = []
        for target_key in sorted(grouped):
            target_unit_id, target_tile_id = (
                target_key)
            for pair in itertools.combinations(
                    grouped[target_key], 2):
                ordered = tuple(sorted(
                    pair,
                    key=lambda row: (
                        -row["interval"].lower,
                        -row["interval"].upper,
                        row["actor_id"])))
                participants = (
                    OperationParticipant(
                        role="primary_attacker",
                        actor_id="unit:{}".format(
                            ordered[0][
                                "actor_id"]),
                        actor_class="unit",
                        required=True),
                    OperationParticipant(
                        role="conditional_attacker",
                        actor_id="unit:{}".format(
                            ordered[1][
                                "actor_id"]),
                        actor_class="unit",
                        required=True),
                )
                target_ref = (
                    "unit:{}@tile:{}"
                    .format(
                        target_unit_id,
                        target_tile_id))
                operation_id = (
                    operation_id_from_components(
                        self.OPERATION_TYPE,
                        tuple(goal_ids),
                        participants,
                        target_ref,
                        str(ruleset_digest),
                        snapshot.turn))
                context_digest = structural_hash({
                    "legal_actions_digest":
                        snapshot
                        .legal_actions_digest,
                    "operation_id":
                        operation_id,
                    "snapshot_id":
                        snapshot.snapshot_id,
                    "target_ref":
                        target_ref,
                })
                premise_ids = (
                    "actor:{}:present".format(
                        ordered[0][
                            "actor_id"]),
                    "actor:{}:native-attack-supported".format(
                        ordered[0][
                            "actor_id"]),
                    "actor:{}:present".format(
                        ordered[1][
                            "actor_id"]),
                    "actor:{}:native-attack-supported".format(
                        ordered[1][
                            "actor_id"]),
                    "target:{}:visible".format(
                        target_unit_id),
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
                                    self.RULE_ID,
                            })[:24])),
                    rule_id=self.RULE_ID,
                    premise_ids=premise_ids,
                    role_ids=(
                        "primary_attacker_present",
                        "primary_attack_supported",
                        "conditional_attacker_present",
                        "conditional_attack_supported",
                        "target_visible",
                    ),
                    context_digest=(
                        context_digest))
                steps = []
                for index, (
                        role, candidate) in enumerate(zip(
                            (
                                "primary_attacker",
                                "conditional_attacker"),
                            ordered)):
                    steps.append(
                        OperationStep(
                            step_id=(
                                "step-{}".format(
                                    structural_hash({
                                        "action_json":
                                            candidate[
                                                "action_json"],
                                        "operation_id":
                                            operation_id,
                                        "role": role,
                                    })[:32])),
                            action_type=(
                                "unit_attack"),
                            actor_role=role,
                            target_ref=(
                                target_ref),
                            requirement_set_id=(
                                requirement_set
                                .requirement_set_id),
                            completion_predicate_id=(
                                "combat:target-neutralized"
                                if index == 0
                                else
                                "combat:conditional-follow-up-resolved"),
                            maximum_attempts=1))
                spec = OperationSpec(
                    schema_version=(
                        OPERATION_SCHEMA_VERSION),
                    operation_id=(
                        operation_id),
                    operation_type=(
                        self.OPERATION_TYPE),
                    goal_ids=tuple(
                        goal_ids),
                    participants=(
                        participants),
                    target_ref=(
                        target_ref),
                    steps=tuple(steps),
                    created_turn=int(
                        snapshot.turn),
                    expiry_turn=int(
                        snapshot.turn),
                    replacement_margin=0.0,
                    provenance=(
                        "server-advertised-legal-actions",
                        "freeciv-server-action-probability",
                        "explicit-conditional-follow-up",
                        "shadow-only-gdo5",
                    ),
                    ruleset_digest=str(
                        ruleset_digest))
                player_scope = (
                    "player:{}".format(
                        snapshot.player_id))
                claims = []
                for step, candidate in zip(
                        steps, ordered):
                    unit_ref = (
                        "unit:{}".format(
                            candidate[
                                "actor_id"]))
                    claims.extend((
                        self._claim(
                            operation_id,
                            step.step_id,
                            ResourceRef(
                                GameResourceKind.ACTOR,
                                unit_ref,
                                "whole_actor",
                                player_scope),
                            ClaimHardness
                            .HARD_CURRENT,
                            snapshot.turn,
                            exclusive=True),
                        self._claim(
                            operation_id,
                            step.step_id,
                            ResourceRef(
                                GameResourceKind
                                .MOVE_POINTS,
                                unit_ref,
                                "current_turn",
                                player_scope),
                            ClaimHardness
                            .HARD_CURRENT,
                            snapshot.turn),
                    ))
                claims.append(
                    self._claim(
                        operation_id,
                        steps[0].step_id,
                        ResourceRef(
                            GameResourceKind
                            .TILE_OCCUPANCY,
                            "tile:{}".format(
                                target_tile_id),
                            "combat_target",
                            "map:{}".format(
                                snapshot.identity
                                .game_id)),
                        ClaimHardness
                        .HARD_CURRENT,
                        snapshot.turn,
                        exclusive=True))
                request = OperationResourceRequest(
                    operation_id=(
                        operation_id),
                    bid=float(
                        ordered[0][
                            "interval"].lower),
                    claims=tuple(claims),
                    requirement_set_id=(
                        requirement_set
                        .requirement_set_id))
                # Until an after-failure state exists, only the first branch
                # lower bound is grounded. The follow-up upper bound remains
                # one and must be re-estimated after step one.
                operation_interval = (
                    ConditionalProbabilityInterval(
                        ordered[0][
                            "interval"].lower,
                        1.0,
                        "first-step-bound-plus-unobserved-conditional-follow-up"))
                assemblies.append(
                    CombatOperationAssembly(
                        spec=spec,
                        requirement_set=(
                            requirement_set),
                        resource_request=(
                            request),
                        action_json_by_step=tuple(
                            candidate[
                                "action_json"]
                            for candidate
                            in ordered),
                        step_probability_intervals=tuple(
                            candidate[
                                "interval"]
                            for candidate
                            in ordered),
                        operation_probability_interval=(
                            operation_interval),
                        target_unit_id=(
                            target_unit_id),
                        target_tile_id=(
                            target_tile_id),
                        initial_premise_packets=tuple(
                            (premise_id, 1)
                            for premise_id
                            in sorted(
                                premise_ids))))
                if len(assemblies) >= (
                        maximum_operations):
                    return tuple(sorted(
                        assemblies,
                        key=lambda value:
                            value.spec
                            .operation_id))
        return tuple(sorted(
            assemblies,
            key=lambda value:
                value.spec.operation_id))

    @staticmethod
    def readout(
            assembly, snapshot,
            step_index):
        if not isinstance(
                assembly,
                CombatOperationAssembly):
            raise TypeError(
                "combat readout requires an assembly")
        if (
            isinstance(step_index, bool)
            or not isinstance(step_index, int)
            or step_index < 0
        ):
            raise ValueError(
                "combat readout step must be non-negative")
        if snapshot.visible_enemy_unit(
                assembly.target_unit_id) is None:
            return CombatOperationReadout(
                "completed", None,
                "target-destroyed-before-next-step",
                step_index)
        if step_index >= len(
                assembly.spec.steps):
            return CombatOperationReadout(
                "completed", None,
                "all-combat-steps-resolved",
                step_index)
        action = assembly.action_for_step(
            step_index)
        actor_id = action.get(
            "actor_id")
        if snapshot.unit(actor_id) is None:
            return CombatOperationReadout(
                "abandoned", None,
                "required-participant-removed",
                step_index)
        action_json = json.dumps(
            action, ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"))
        if action_json not in set(
                snapshot.legal_action_json):
            return CombatOperationReadout(
                "blocked", None,
                "current-step-action-no-longer-legal",
                step_index)
        result = snapshot.combat_probability(
            actor_id,
            assembly.target_tile_id)
        probability = (
            None if result is None
            else result.action_probability(
                "attack"))
        if (
            result is None
            or result.target_unit_id
                != assembly.target_unit_id
            or probability is None
            or probability.status
                != "bounded"
        ):
            return CombatOperationReadout(
                "blocked", None,
                "conditional-combat-support-incomplete",
                step_index)
        return CombatOperationReadout(
            "reservable", action,
            "current-step-grounded-and-legal",
            step_index)


def combat_target_capacities(
        assemblies, snapshot):
    """Declare one shadow coordination slot per currently visible target."""
    resources = {
        claim.resource
        for assembly in assemblies
        for claim in assembly
            .resource_request.claims
        if claim.resource.kind
            == GameResourceKind
            .TILE_OCCUPANCY
    }
    return tuple(sorted(
        (
            ResourceCapacity(
                resource=resource,
                quantity=1,
                window=TurnWindow(
                    snapshot.turn,
                    snapshot.turn + 1),
                snapshot_id=(
                    snapshot.snapshot_id),
                authority=(
                    "shadow-combat-target-exclusivity"))
            for resource in resources
        ),
        key=lambda row: row.sort_key))
