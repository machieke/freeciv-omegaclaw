"""Shadow-only founder/ferry coordination over grounded current steps."""

import json
import math
import re
from dataclasses import dataclass
from typing import Optional

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from ..pressure.coalitions import RequirementSet
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
from .domain_models.transport import (
    transport_unit_profile,
)
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    operation_id_from_components,
)
from .path_corridors import (
    NativeRouteCorridor,
    native_route_corridor,
)


_PHASES = (
    "founder_to_pickup",
    "ferry_to_pickup",
    "embark",
    "ferry_to_landing",
    "disembark",
    "founder_to_settlement",
    "settle",
)


def _normalized_type(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


def _unit_id(value, name):
    if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
    ):
        raise ValueError(
            "{} must be a positive unit ID".format(
                name))
    return value


def _tile_id(value, name):
    if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
    ):
        raise ValueError(
            "{} must be a non-negative tile ID".format(
                name))
    return value


@dataclass(frozen=True)
class FounderTransportIntent:
    """Stable identities and deadlines for one ferry/founder operation."""

    founder_unit_id: int
    ferry_unit_id: int
    pickup_tile_id: int
    landing_carrier_tile_id: int
    landing_tile_id: int
    settlement_tile_id: int
    rendezvous_deadline_turn: int
    settlement_deadline_turn: int
    escort_unit_id: Optional[int] = None

    def __post_init__(self):
        _unit_id(
            self.founder_unit_id,
            "founder")
        _unit_id(
            self.ferry_unit_id,
            "ferry")
        if self.founder_unit_id == (
                self.ferry_unit_id):
            raise ValueError(
                "founder and ferry identities must differ")
        for value, name in (
                (self.pickup_tile_id,
                 "pickup tile"),
                (self.landing_carrier_tile_id,
                 "landing carrier tile"),
                (self.landing_tile_id,
                 "landing tile"),
                (self.settlement_tile_id,
                 "settlement tile")):
            _tile_id(value, name)
        for value, name in (
                (self.rendezvous_deadline_turn,
                 "rendezvous deadline"),
                (self.settlement_deadline_turn,
                 "settlement deadline")):
            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
            ):
                raise ValueError(
                    "{} must be non-negative".format(
                        name))
        if self.settlement_deadline_turn < (
                self.rendezvous_deadline_turn):
            raise ValueError(
                "settlement deadline cannot precede rendezvous")
        if self.escort_unit_id is not None:
            _unit_id(
                self.escort_unit_id,
                "escort")
            if self.escort_unit_id in (
                    self.founder_unit_id,
                    self.ferry_unit_id):
                raise ValueError(
                    "escort identity must be distinct")

    @property
    def target_ref(self):
        return (
            "founder-transport:"
            "pickup={}:landing-carrier={}:"
            "landing={}:settlement={}"
            .format(
                self.pickup_tile_id,
                self.landing_carrier_tile_id,
                self.landing_tile_id,
                self.settlement_tile_id))

    def to_dict(self):
        return {
            "escort_unit_id":
                self.escort_unit_id,
            "ferry_unit_id":
                self.ferry_unit_id,
            "founder_unit_id":
                self.founder_unit_id,
            "landing_carrier_tile_id":
                self.landing_carrier_tile_id,
            "landing_tile_id":
                self.landing_tile_id,
            "pickup_tile_id":
                self.pickup_tile_id,
            "rendezvous_deadline_turn":
                self.rendezvous_deadline_turn,
            "settlement_deadline_turn":
                self.settlement_deadline_turn,
            "settlement_tile_id":
                self.settlement_tile_id,
            "target_ref":
                self.target_ref,
        }


@dataclass(frozen=True)
class TransportOperationReadout:
    disposition: str
    phase: str
    step_index: int
    reason: str
    next_action: object = None
    corridor: object = None

    def __post_init__(self):
        if self.disposition not in (
                "reservable",
                "step_complete",
                "completed",
                "blocked",
                "abandoned"):
            raise ValueError(
                "unknown transport readout disposition")
        if self.phase not in _PHASES:
            raise ValueError(
                "unknown transport operation phase")
        if (
                isinstance(self.step_index, bool)
                or not isinstance(
                    self.step_index, int)
                or self.step_index < 0
        ):
            raise ValueError(
                "transport readout step index is invalid")
        if not isinstance(
                self.reason, str
                ) or not self.reason:
            raise ValueError(
                "transport readout reason is required")
        if (
                self.next_action is not None
                and not isinstance(
                    self.next_action, dict)
        ):
            raise TypeError(
                "transport next action must be an object or absent")
        if (
                self.corridor is not None
                and not isinstance(
                    self.corridor,
                    NativeRouteCorridor)
        ):
            raise TypeError(
                "transport corridor has the wrong type")


@dataclass(frozen=True)
class FounderTransportOperationAssembly:
    """One partner-locked, multi-turn, default-off transport operation."""

    spec: OperationSpec
    intent: FounderTransportIntent
    requirement_set: RequirementSet
    initial_premise_packets: tuple
    initial_step_index: int
    initial_readout: TransportOperationReadout
    resource_request: OperationResourceRequest
    rendezvous_eta_turns: int
    initial_corridors: tuple
    compatible_carrier_profiles: tuple
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if not isinstance(
                self.spec, OperationSpec):
            raise TypeError(
                "transport assembly requires an operation spec")
        if not isinstance(
                self.intent,
                FounderTransportIntent):
            raise TypeError(
                "transport assembly requires an intent")
        if not isinstance(
                self.requirement_set,
                RequirementSet):
            raise TypeError(
                "transport assembly requires a RequirementSet")
        if not isinstance(
                self.resource_request,
                OperationResourceRequest):
            raise TypeError(
                "transport assembly requires a resource request")
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
                "transport assembly identities must agree")
        if self.initial_step_index != (
                self.initial_readout
                .step_index):
            raise ValueError(
                "transport initial step/readout mismatch")
        if not 0 <= self.initial_step_index < (
                len(self.spec.steps)):
            raise ValueError(
                "transport initial step is out of range")
        if (
                isinstance(
                    self.rendezvous_eta_turns,
                    bool)
                or not isinstance(
                    self.rendezvous_eta_turns,
                    int)
                or self.rendezvous_eta_turns
                    < 0
        ):
            raise ValueError(
                "transport rendezvous ETA must be non-negative")
        corridors = tuple(
            self.initial_corridors)
        if any(
                not isinstance(
                    row, NativeRouteCorridor)
                for row in corridors):
            raise TypeError(
                "transport corridors have the wrong type")
        if tuple(sorted(
                corridors,
                key=lambda row: (
                    row.actor_id,
                    row.destination_tile,
                    row.corridor_digest)
        )) != corridors:
            raise ValueError(
                "transport corridors must use canonical order")
        profiles = tuple(
            self.compatible_carrier_profiles)
        if (
                not profiles
                or tuple(sorted(set(
                    profiles))) != profiles
                or any(
                    not isinstance(name, str)
                    or not name
                    or isinstance(capacity, bool)
                    or not isinstance(
                        capacity, int)
                    or capacity < 1
                    for name, capacity
                    in profiles)
        ):
            raise ValueError(
                "transport compatible carrier profiles are invalid")
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
                "transport premise packets must complete the RequirementSet")
        if (
                not self.shadow_only
                or self.policy_authority
        ):
            raise ValueError(
                "initial transport operations are shadow-only")

    def to_dict(self):
        return {
            "initial_corridors": [
                row.to_dict()
                for row in
                self.initial_corridors],
            "compatible_carrier_profiles": [
                {
                    "transport_capacity":
                        capacity,
                    "unit_type": name,
                }
                for name, capacity in
                self.compatible_carrier_profiles],
            "initial_premise_packets":
                dict(
                    self.initial_premise_packets),
            "initial_readout": {
                "corridor": (
                    None
                    if self.initial_readout
                        .corridor is None
                    else self.initial_readout
                        .corridor.to_dict()),
                "disposition":
                    self.initial_readout
                    .disposition,
                "next_action":
                    self.initial_readout
                    .next_action,
                "phase":
                    self.initial_readout
                    .phase,
                "reason":
                    self.initial_readout
                    .reason,
                "step_index":
                    self.initial_readout
                    .step_index,
            },
            "initial_step_index":
                self.initial_step_index,
            "intent": self.intent.to_dict(),
            "policy_authority": False,
            "rendezvous_eta_turns":
                self.rendezvous_eta_turns,
            "requirement_set":
                self.requirement_set
                .to_dict(),
            "resource_request":
                self.resource_request
                .to_dict(),
            "shadow_only": True,
            "spec": self.spec.to_dict(),
        }


@dataclass(frozen=True)
class TransportOperationAssemblyDecision:
    disposition: str
    reason: str
    assembly: object = None
    missing_inputs: tuple = ()

    def __post_init__(self):
        if self.disposition not in (
                "assembled", "abstain"):
            raise ValueError(
                "unknown transport assembly disposition")
        if not isinstance(
                self.reason, str
                ) or not self.reason:
            raise ValueError(
                "transport assembly reason is required")
        if (
                self.disposition == "assembled"
                and not isinstance(
                    self.assembly,
                    FounderTransportOperationAssembly)
        ):
            raise TypeError(
                "assembled transport decision requires an assembly")
        if (
                self.disposition == "abstain"
                and self.assembly is not None
        ):
            raise ValueError(
                "abstaining transport decision cannot contain an assembly")
        missing = tuple(sorted(set(
            self.missing_inputs)))
        if any(
                not isinstance(
                    value, str)
                or not value
                for value in missing):
            raise ValueError(
                "transport missing-input names must be strings")
        object.__setattr__(
            self, "missing_inputs",
            missing)


class FounderTransportOperationAssembler:
    """Assemble only exact current-step founder/ferry coordination."""

    OPERATION_TYPE = (
        "founder_transport_operation")
    RULE_ID = (
        "transport-operation:"
        "partner-locked-settlement")

    @staticmethod
    def _actions(snapshot):
        return tuple(
            json.loads(value)
            for value in getattr(
                snapshot,
                "legal_action_json", ()))

    @staticmethod
    def _target_tile(
            snapshot, action):
        target = action.get(
            "target")
        if (
                not isinstance(
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
            return None
        return (
            int(target["x"])
            + int(target["y"])
            * int(snapshot.map_width))

    @classmethod
    def _matching_actions(
            cls, snapshot, action_type,
            actor_id, target_tile=None):
        rows = []
        for action in cls._actions(
                snapshot):
            if (
                    action.get(
                        "action_type")
                        != action_type
                    or action.get(
                        "actor_id")
                        != actor_id
            ):
                continue
            if (
                    target_tile is not None
                    and cls._target_tile(
                        snapshot, action)
                        != target_tile
            ):
                continue
            rows.append(action)
        return tuple(sorted(
            rows,
            key=lambda value:
                canonical_json_bytes(
                    value)))

    @classmethod
    def _unique_action(
            cls, snapshot, action_type,
            actor_id, target_tile=None,
            transport_required=None):
        rows = cls._matching_actions(
            snapshot, action_type,
            actor_id, target_tile)
        if transport_required is not None:
            rows = tuple(
                row for row in rows
                if row.get(
                    "transport_required")
                    is transport_required)
        return (
            rows[0]
            if len(rows) == 1
            else None)

    @classmethod
    def _route_action(
            cls, snapshot, actor_id,
            destination_tile,
            allow_transport):
        try:
            corridor = (
                native_route_corridor(
                    snapshot,
                    actor_id,
                    destination_tile))
        except ValueError:
            return None, None
        rows = cls._matching_actions(
            snapshot,
            "unit_move",
            actor_id,
            corridor.first_step_tile)
        rows = tuple(
            row for row in rows
            if (
                row.get(
                    "movement_cost")
                    == snapshot
                    .movement_route(
                        actor_id,
                        destination_tile)
                    .first_step_movement_cost
                and (
                    allow_transport
                    or row.get(
                        "transport_required")
                        is False)))
        if len(rows) != 1:
            return corridor, None
        return corridor, rows[0]

    @staticmethod
    def _critical_tiles(intent):
        return frozenset((
            intent.pickup_tile_id,
            intent.landing_carrier_tile_id,
            intent.landing_tile_id,
            intent.settlement_tile_id,
        ))

    @staticmethod
    def _known_tiles(snapshot):
        return frozenset(
            int(row["index"])
            for row in getattr(
                snapshot, "map_tiles", ())
            if isinstance(row, dict)
            and row.get("index") is not None
        ).union(
            getattr(
                snapshot,
                "visible_tile_ids", ()))

    @classmethod
    def _rendezvous_inputs(
            cls, snapshot, intent):
        founder = snapshot.unit(
            intent.founder_unit_id)
        ferry = snapshot.unit(
            intent.ferry_unit_id)
        if founder is None or ferry is None:
            return (
                None, None, None,
                ("founder" if founder is None
                 else "ferry",))

        embark = cls._unique_action(
            snapshot, "unit_move",
            intent.founder_unit_id,
            intent.pickup_tile_id,
            transport_required=True)
        founder_corridor = None
        founder_eta = 0
        if embark is None:
            (
                founder_corridor,
                founder_action,
            ) = cls._route_action(
                snapshot,
                intent.founder_unit_id,
                intent.pickup_tile_id,
                allow_transport=True)
            if (
                    founder_corridor is None
                    or founder_action is None
            ):
                return (
                    None, None, None,
                    ("founder_pickup_route",))
            founder_eta = (
                founder_corridor
                .estimated_turns)

        ferry_corridor = None
        ferry_eta = 0
        if ferry.tile != (
                intent.pickup_tile_id):
            (
                ferry_corridor,
                ferry_action,
            ) = cls._route_action(
                snapshot,
                intent.ferry_unit_id,
                intent.pickup_tile_id,
                allow_transport=False)
            if (
                    ferry_corridor is None
                    or ferry_action is None
            ):
                return (
                    None, None, None,
                    ("ferry_pickup_route",))
            ferry_eta = (
                ferry_corridor
                .estimated_turns)
        corridors = tuple(sorted(
            (
                row
                for row in (
                    founder_corridor,
                    ferry_corridor)
                if row is not None
            ),
            key=lambda row: (
                row.actor_id,
                row.destination_tile,
                row.corridor_digest)))
        return (
            max(
                founder_eta,
                ferry_eta),
            founder_eta,
            ferry_eta,
            corridors)

    @staticmethod
    def _step(
            operation_id, phase,
            role, target_ref,
            requirement_set_id,
            maximum_attempts):
        return OperationStep(
            step_id="step-" + structural_hash({
                "operation_id":
                    operation_id,
                "phase": phase,
                "role": role,
                "target_ref":
                    target_ref,
            })[:32],
            action_type=(
                "unit_build_city"
                if phase == "settle"
                else "unit_move"),
            actor_role=role,
            target_ref=target_ref,
            requirement_set_id=(
                requirement_set_id),
            completion_predicate_id=(
                "transport:{}".format(
                    phase)),
            maximum_attempts=max(
                1, maximum_attempts))

    @staticmethod
    def _phase_for_step(
            spec, step_index):
        if not 0 <= step_index < (
                len(spec.steps)):
            raise IndexError(
                "transport operation step index is out of range")
        predicate = (
            spec.steps[
                step_index]
            .completion_predicate_id)
        prefix = "transport:"
        if not predicate.startswith(
                prefix):
            raise ValueError(
                "transport step has an invalid completion predicate")
        phase = predicate[
            len(prefix):]
        if phase not in _PHASES:
            raise ValueError(
                "transport step has an unknown phase")
        return phase

    @classmethod
    def readout(
            cls, assembly, snapshot,
            step_index):
        if not isinstance(
                assembly,
                FounderTransportOperationAssembly):
            raise TypeError(
                "transport readout requires an assembly")
        return cls._readout(
            assembly.spec,
            assembly.intent,
            assembly
            .compatible_carrier_profiles,
            snapshot,
            step_index)

    @classmethod
    def _readout(
            cls, spec, intent,
            compatible_carrier_profiles,
            snapshot, step_index):
        phase = cls._phase_for_step(
            spec, step_index)
        founder = snapshot.unit(
            intent.founder_unit_id)
        ferry = snapshot.unit(
            intent.ferry_unit_id)
        city_at_target = next((
            city for city in
            snapshot.cities
            if city.tile
                == intent
                .settlement_tile_id
        ), None)
        if (
                phase == "settle"
                and city_at_target
                    is not None
                and founder is None
        ):
            return TransportOperationReadout(
                "completed", phase,
                step_index,
                "settlement-created")
        if founder is None:
            return TransportOperationReadout(
                "abandoned", phase,
                step_index,
                "required-founder-removed")
        if (
                ferry is None
                and phase not in (
                    "founder_to_settlement",
                    "settle")
        ):
            return TransportOperationReadout(
                "abandoned", phase,
                step_index,
                "required-ferry-removed")
        if (
                founder.transported is True
                and founder.transported_by
                    != intent.ferry_unit_id
        ):
            return TransportOperationReadout(
                "abandoned", phase,
                step_index,
                "founder-carrier-partner-mismatch")

        if phase == "founder_to_pickup":
            if (
                    founder.transported is True
                    and founder.transported_by
                        == intent.ferry_unit_id
            ):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "founder-already-embarked")
            embark = cls._unique_action(
                snapshot, "unit_move",
                intent.founder_unit_id,
                intent.pickup_tile_id,
                transport_required=True)
            if embark is not None:
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "embark-edge-advertised")
            corridor, action = (
                cls._route_action(
                    snapshot,
                    intent.founder_unit_id,
                    intent.pickup_tile_id,
                    allow_transport=False))
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "founder-pickup-route-or-action-unavailable",
                    corridor=corridor)
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "founder-pickup-step-grounded",
                action, corridor)

        if phase == "ferry_to_pickup":
            if ferry.tile == (
                    intent.pickup_tile_id):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "ferry-at-pickup")
            corridor, action = (
                cls._route_action(
                    snapshot,
                    intent.ferry_unit_id,
                    intent.pickup_tile_id,
                    allow_transport=False))
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "ferry-pickup-route-or-action-unavailable",
                    corridor=corridor)
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "ferry-pickup-step-grounded",
                action, corridor)

        if phase == "embark":
            if (
                    founder.transported is True
                    and founder.transported_by
                        == intent.ferry_unit_id
            ):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "founder-embarked-on-locked-ferry")
            if ferry.tile != (
                    intent.pickup_tile_id):
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "locked-ferry-not-at-pickup")
            capacity_by_type = dict(
                compatible_carrier_profiles)
            compatible_ids = tuple(sorted(
                unit.unit_id
                for unit in snapshot.units
                if (
                    unit.tile
                        == intent.pickup_tile_id
                    and _normalized_type(
                        unit.unit_type)
                        in capacity_by_type
                    and unit.carrying
                        is not None
                    and 0 <= unit.carrying
                        < capacity_by_type[
                            _normalized_type(
                                unit.unit_type)]
                )))
            if compatible_ids != (
                    intent.ferry_unit_id,):
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "locked-ferry-not-unique-compatible-carrier")
            action = cls._unique_action(
                snapshot, "unit_move",
                intent.founder_unit_id,
                intent.pickup_tile_id,
                transport_required=True)
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "advertised-embark-action-unavailable")
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "unique-embark-action-grounded",
                action)

        if phase == "ferry_to_landing":
            if not (
                    founder.transported is True
                    and founder.transported_by
                        == intent.ferry_unit_id
            ):
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "founder-not-on-locked-ferry")
            if ferry.tile == (
                    intent
                    .landing_carrier_tile_id):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "ferry-at-landing-corridor")
            corridor, action = (
                cls._route_action(
                    snapshot,
                    intent.ferry_unit_id,
                    intent
                    .landing_carrier_tile_id,
                    allow_transport=False))
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "ferry-landing-route-or-action-unavailable",
                    corridor=corridor)
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "ferry-landing-step-grounded",
                action, corridor)

        if phase == "disembark":
            if (
                    founder.transported is False
                    and founder.tile
                        == intent
                        .landing_tile_id
            ):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "founder-disembarked-at-landing")
            if not (
                    founder.transported is True
                    and founder.transported_by
                        == intent.ferry_unit_id
                    and ferry.tile
                        == intent
                        .landing_carrier_tile_id
            ):
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "disembark-carrier-state-mismatch")
            action = cls._unique_action(
                snapshot, "unit_move",
                intent.founder_unit_id,
                intent.landing_tile_id,
                transport_required=False)
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "advertised-disembark-action-unavailable")
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "unique-disembark-action-grounded",
                action)

        if phase == "founder_to_settlement":
            if founder.transported is True:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "founder-still-transported")
            if founder.tile == (
                    intent.settlement_tile_id):
                return TransportOperationReadout(
                    "step_complete", phase,
                    step_index,
                    "founder-at-settlement-target")
            corridor, action = (
                cls._route_action(
                    snapshot,
                    intent.founder_unit_id,
                    intent.settlement_tile_id,
                    allow_transport=False))
            if action is None:
                return TransportOperationReadout(
                    "blocked", phase,
                    step_index,
                    "founder-settlement-route-or-action-unavailable",
                    corridor=corridor)
            return TransportOperationReadout(
                "reservable", phase,
                step_index,
                "founder-settlement-step-grounded",
                action, corridor)

        if city_at_target is not None:
            return TransportOperationReadout(
                "completed", phase,
                step_index,
                "settlement-created")
        if (
                founder.transported is True
                or founder.tile
                    != intent
                    .settlement_tile_id
        ):
            return TransportOperationReadout(
                "blocked", phase,
                step_index,
                "founder-not-ready-to-settle")
        action = cls._unique_action(
            snapshot,
            "unit_build_city",
            intent.founder_unit_id)
        if action is None:
            return TransportOperationReadout(
                "blocked", phase,
                step_index,
                "advertised-settlement-action-unavailable")
        return TransportOperationReadout(
            "reservable", phase,
            step_index,
            "unique-settlement-action-grounded",
            action)

    @staticmethod
    def _claim(
            operation_id, step_id,
            resource, turn, hardness,
            quantity=1, exclusive=False,
            end_turn_exclusive=None):
        return ResourceClaim(
            resource=resource,
            quantity=quantity,
            window=TurnWindow(
                int(turn),
                int(
                    end_turn_exclusive
                    if end_turn_exclusive
                        is not None
                    else turn + 1)),
            hardness=hardness,
            exclusive=exclusive,
            source_operation_id=(
                operation_id),
            source_step_id=step_id)

    @classmethod
    def current_step_resource_request(
            cls, assembly, snapshot,
            step_index, bid=None):
        readout = cls.readout(
            assembly, snapshot,
            step_index)
        if readout.disposition != (
                "reservable"):
            return readout, None
        request = cls._resource_request(
            assembly.spec,
            assembly.intent,
            assembly.requirement_set,
            snapshot,
            readout,
            bid=bid)
        if request is None:
            return (
                TransportOperationReadout(
                    "blocked",
                    readout.phase,
                    step_index,
                    "current-transport-resource-claim-input-invalid",
                    corridor=(
                        readout.corridor)),
                None)
        return readout, request

    @classmethod
    def _resource_request(
            cls, spec, intent,
            requirement_set,
            snapshot, readout,
            bid=None):
        step_index = (
            readout.step_index)
        action = readout.next_action
        actor_id = action.get(
            "actor_id")
        if (
                isinstance(actor_id, bool)
                or not isinstance(
                    actor_id, int)
        ):
            return None
        operation_id = (
            spec.operation_id)
        step = spec.steps[
            step_index]
        scope = "player:{}".format(
            snapshot.player_id)
        actor_ref = "unit:{}".format(
            actor_id)
        claims = [
            cls._claim(
                operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind.ACTOR,
                    actor_ref,
                    "whole_actor",
                    scope),
                snapshot.turn,
                ClaimHardness.HARD_CURRENT,
                exclusive=True),
            cls._claim(
                operation_id,
                step.step_id,
                ResourceRef(
                    GameResourceKind.ACTION_BUDGET,
                    scope,
                    "controller",
                    scope),
                snapshot.turn,
                ClaimHardness.HARD_CURRENT),
        ]
        movement_cost = action.get(
            "movement_cost")
        if movement_cost is not None:
            if (
                    isinstance(
                        movement_cost, bool)
                    or not isinstance(
                        movement_cost,
                        (int, float))
                    or int(movement_cost)
                        != movement_cost
                    or int(movement_cost)
                        <= 0
            ):
                return None
            claims.append(
                cls._claim(
                    operation_id,
                    step.step_id,
                    ResourceRef(
                        GameResourceKind
                        .MOVE_POINTS,
                        actor_ref,
                        "current_turn",
                        scope),
                    snapshot.turn,
                    ClaimHardness
                    .HARD_CURRENT,
                    quantity=int(
                        movement_cost)))

        ferry_ref = "unit:{}".format(
            intent.ferry_unit_id)
        if readout.phase in (
                "embark", "disembark"):
            claims.append(
                cls._claim(
                    operation_id,
                    step.step_id,
                    ResourceRef(
                        GameResourceKind.ACTOR,
                        ferry_ref,
                        "whole_actor",
                        scope),
                    snapshot.turn,
                    ClaimHardness
                    .HARD_CURRENT,
                    exclusive=True))
        if readout.phase == "embark":
            claims.append(
                cls._claim(
                    operation_id,
                    step.step_id,
                    ResourceRef(
                        GameResourceKind
                        .TRANSPORT_SEAT,
                        ferry_ref,
                        "cargo",
                        scope),
                    snapshot.turn,
                    ClaimHardness
                    .HARD_CURRENT))

        future_start = (
            int(snapshot.turn) + 1)
        future_end = (
            int(
                intent
                .settlement_deadline_turn)
            + 1)
        if future_start < future_end:
            for unit_ref in (
                    "unit:{}".format(
                        intent
                        .founder_unit_id),
                    ferry_ref):
                claims.append(
                    cls._claim(
                        operation_id,
                        step.step_id,
                        ResourceRef(
                            GameResourceKind.ACTOR,
                            unit_ref,
                            "operation_partner",
                            scope),
                        future_start,
                        ClaimHardness
                        .CONDITIONAL_FUTURE,
                        exclusive=True,
                        end_turn_exclusive=(
                            future_end)))
            claims.append(
                cls._claim(
                    operation_id,
                    step.step_id,
                    ResourceRef(
                        GameResourceKind
                        .TRANSPORT_SEAT,
                        ferry_ref,
                        "cargo",
                        scope),
                    future_start,
                    ClaimHardness
                    .CONDITIONAL_FUTURE,
                    end_turn_exclusive=(
                        future_end)))
            for tile_id, purpose in (
                    (
                        intent
                        .pickup_tile_id,
                        "pickup"),
                    (
                        intent
                        .landing_carrier_tile_id,
                        "landing_carrier"),
                    (
                        intent
                        .landing_tile_id,
                        "landing"),
                    (
                        intent
                        .settlement_tile_id,
                        "settlement")):
                claims.append(
                    cls._claim(
                        operation_id,
                        step.step_id,
                        ResourceRef(
                            GameResourceKind
                            .TILE_OCCUPANCY,
                            "tile:{}".format(
                                tile_id),
                            purpose,
                            "map:{}".format(
                                snapshot.identity
                                .game_id)),
                        future_start,
                        ClaimHardness
                        .CONDITIONAL_FUTURE,
                        exclusive=True,
                        end_turn_exclusive=(
                            future_end)))
        return OperationResourceRequest(
            operation_id=(
                operation_id),
            bid=float(
                1.0 if bid is None
                else bid),
            claims=tuple(claims),
            requirement_set_id=(
                requirement_set
                .requirement_set_id))

    @classmethod
    def assemble(
            cls, snapshot, ruleset_ir,
            ruleset_digest, intent,
            goal_ids=(
                "pf-impact:expansion",),
            replacement_margin=0.05):
        if not isinstance(
                intent,
                FounderTransportIntent):
            raise TypeError(
                "transport assembler requires a transport intent")
        if (
                isinstance(
                    replacement_margin, bool)
                or not isinstance(
                    replacement_margin,
                    (int, float))
                or not math.isfinite(
                    float(
                        replacement_margin))
                or float(
                    replacement_margin) < 0.0
        ):
            raise ValueError(
                "transport replacement margin must be finite and non-negative")
        if int(snapshot.turn) > (
                intent
                .rendezvous_deadline_turn):
            return TransportOperationAssemblyDecision(
                "abstain",
                "rendezvous-deadline-passed")
        tile_count = (
            int(snapshot.map_width)
            * int(snapshot.map_height))
        if any(
                tile_id >= tile_count
                for tile_id in
                cls._critical_tiles(
                    intent)):
            return TransportOperationAssemblyDecision(
                "abstain",
                "transport-intent-tile-out-of-map")
        missing_tiles = tuple(sorted(
            cls._critical_tiles(intent)
            - cls._known_tiles(snapshot)))
        if missing_tiles:
            return TransportOperationAssemblyDecision(
                "abstain",
                "transport-intent-tile-unknown",
                missing_inputs=tuple(
                    "tile:{}".format(
                        value)
                    for value in
                    missing_tiles))
        if intent.escort_unit_id is not None:
            return TransportOperationAssemblyDecision(
                "abstain",
                "grounded-escort-risk-model-required",
                missing_inputs=(
                    "escort_survival_estimate",))
        if any(
                unit.tile in
                cls._critical_tiles(intent)
                for unit in
                snapshot.visible_enemy_units):
            return TransportOperationAssemblyDecision(
                "abstain",
                "visible-threat-on-transport-corridor-requires-escort-estimate",
                missing_inputs=(
                    "escort_survival_estimate",))

        founder = snapshot.unit(
            intent.founder_unit_id)
        ferry = snapshot.unit(
            intent.ferry_unit_id)
        if founder is None or ferry is None:
            missing = tuple(
                value for value, present
                in (
                    ("founder", founder),
                    ("ferry", ferry))
                if present is None)
            return TransportOperationAssemblyDecision(
                "abstain",
                "transport-required-participant-missing",
                missing_inputs=missing)
        founder_profile = (
            transport_unit_profile(
                ruleset_ir,
                founder.unit_type))
        ferry_profile = (
            transport_unit_profile(
                ruleset_ir,
                ferry.unit_type))
        if (
                founder_profile is None
                or not founder_profile
                    .founder_capable
        ):
            return TransportOperationAssemblyDecision(
                "abstain",
                "founder-profile-not-grounded",
                missing_inputs=(
                    "founder_unit_profile",))
        if (
                ferry_profile is None
                or ferry_profile
                    .transport_capacity <= 0
                or founder_profile
                    .unit_class
                    not in ferry_profile
                    .cargo_classes
                or ferry.carrying is None
                or ferry.carrying < 0
                or ferry.carrying
                    >= ferry_profile
                    .transport_capacity
        ):
            return TransportOperationAssemblyDecision(
                "abstain",
                "ferry-profile-load-or-cargo-incompatible",
                missing_inputs=(
                    "compatible_free_transport_seat",))
        compatible_carrier_profiles = []
        for rule in getattr(
                ruleset_ir, "rules", ()):
            if getattr(
                    rule, "target_kind",
                    None) != "unit":
                continue
            unit_type = str(
                getattr(
                    rule, "display_name",
                    "") or getattr(
                    rule, "rule_name",
                    ""))
            profile = (
                transport_unit_profile(
                    ruleset_ir,
                    unit_type))
            if (
                    profile is not None
                    and profile
                    .transport_capacity > 0
                    and founder_profile
                    .unit_class
                    in profile
                    .cargo_classes
            ):
                compatible_carrier_profiles.append((
                    _normalized_type(
                        profile.unit_type),
                    profile
                    .transport_capacity))
        compatible_carrier_profiles = tuple(sorted(set(
            compatible_carrier_profiles)))
        if not compatible_carrier_profiles:
            return TransportOperationAssemblyDecision(
                "abstain",
                "compatible-carrier-profile-set-empty",
                missing_inputs=(
                    "compatible_carrier_profiles",))

        (
            rendezvous_eta,
            founder_eta,
            ferry_eta,
            corridors,
        ) = cls._rendezvous_inputs(
            snapshot, intent)
        if rendezvous_eta is None:
            return TransportOperationAssemblyDecision(
                "abstain",
                "rendezvous-route-input-missing",
                missing_inputs=(
                    corridors
                    if isinstance(
                        corridors, tuple)
                    else ()))
        if (
                int(snapshot.turn)
                + rendezvous_eta
                > intent
                .rendezvous_deadline_turn
        ):
            return TransportOperationAssemblyDecision(
                "abstain",
                "rendezvous-route-misses-deadline")

        participants = (
            OperationParticipant(
                "founder",
                "unit:{}".format(
                    intent
                    .founder_unit_id),
                "unit", True),
            OperationParticipant(
                "ferry",
                "unit:{}".format(
                    intent
                    .ferry_unit_id),
                "unit", True),
        )
        operation_id = (
            operation_id_from_components(
                cls.OPERATION_TYPE,
                tuple(goal_ids),
                participants,
                intent.target_ref,
                str(ruleset_digest),
                int(snapshot.turn)))
        context_digest = structural_hash({
            "intent": intent.to_dict(),
            "legal_actions_digest":
                snapshot
                .legal_actions_digest,
            "operation_id":
                operation_id,
            "ruleset_digest":
                str(ruleset_digest),
            "snapshot_id":
                snapshot.snapshot_id,
        })
        premise_ids = (
            "founder:{}:present-and-founder-capable"
            .format(
                intent.founder_unit_id),
            "ferry:{}:present-compatible-and-free-seat"
            .format(
                intent.ferry_unit_id),
            "pickup:{}:known".format(
                intent.pickup_tile_id),
            "landing-carrier:{}:known"
            .format(
                intent
                .landing_carrier_tile_id),
            "landing:{}:known".format(
                intent.landing_tile_id),
            "settlement:{}:known".format(
                intent
                .settlement_tile_id),
            "rendezvous:native-routes-fit-deadline",
            "escort:not-required-no-visible-critical-tile-threat",
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
                "founder",
                "ferry",
                "pickup",
                "landing_carrier",
                "landing",
                "settlement",
                "rendezvous",
                "escort_policy",
            ),
            context_digest=(
                context_digest))

        # Move the slower rendezvous participant first. This minimizes
        # deterministic partner idle time without generic path persistence.
        rendezvous_phases = (
            (
                ("ferry_to_pickup",
                 "ferry")
                if ferry_eta
                    > founder_eta
                else (
                    "founder_to_pickup",
                    "founder")),
            (
                ("founder_to_pickup",
                 "founder")
                if ferry_eta
                    > founder_eta
                else (
                    "ferry_to_pickup",
                    "ferry")),
        )
        phase_roles = (
            rendezvous_phases
            + (
                ("embark", "founder"),
                ("ferry_to_landing",
                 "ferry"),
                ("disembark", "founder"),
                ("founder_to_settlement",
                 "founder"),
                ("settle", "founder"),
            ))
        target_by_phase = {
            "founder_to_pickup":
                "tile:{}".format(
                    intent.pickup_tile_id),
            "ferry_to_pickup":
                "tile:{}".format(
                    intent.pickup_tile_id),
            "embark":
                "unit:{}".format(
                    intent.ferry_unit_id),
            "ferry_to_landing":
                "tile:{}".format(
                    intent
                    .landing_carrier_tile_id),
            "disembark":
                "tile:{}".format(
                    intent.landing_tile_id),
            "founder_to_settlement":
                "tile:{}".format(
                    intent
                    .settlement_tile_id),
            "settle":
                "tile:{}".format(
                    intent
                    .settlement_tile_id),
        }
        attempt_limit = max(
            1,
            intent
            .settlement_deadline_turn
            - int(snapshot.turn)
            + 1)
        steps = tuple(
            cls._step(
                operation_id,
                phase, role,
                target_by_phase[phase],
                requirement_set
                .requirement_set_id,
                attempt_limit)
            for phase, role
            in phase_roles)
        spec = OperationSpec(
            schema_version=(
                OPERATION_SCHEMA_VERSION),
            operation_id=(
                operation_id),
            operation_type=(
                cls.OPERATION_TYPE),
            goal_ids=tuple(
                goal_ids),
            participants=participants,
            target_ref=(
                intent.target_ref),
            steps=steps,
            created_turn=int(
                snapshot.turn),
            expiry_turn=int(
                intent
                .settlement_deadline_turn),
            replacement_margin=float(
                replacement_margin),
            provenance=(
                "authoritative-own-units",
                "compiled-transport-rules",
                "freeciv-server-pathfinder",
                "server-advertised-current-step",
                "shadow-only-gdo6",
            ),
            ruleset_digest=str(
                ruleset_digest))

        # Find the first current step that is not already satisfied. The
        # completed prefix is advanced by the lifecycle before reservation.
        initial_step = 0
        while initial_step < len(steps):
            readout = cls._readout(
                spec, intent,
                compatible_carrier_profiles,
                snapshot,
                initial_step)
            if readout.disposition != (
                    "step_complete"):
                break
            initial_step += 1
        if initial_step >= len(steps):
            return TransportOperationAssemblyDecision(
                "abstain",
                "transport-operation-already-complete")
        initial_readout = cls._readout(
            spec, intent,
            compatible_carrier_profiles,
            snapshot,
            initial_step)
        if initial_readout.disposition != (
                "reservable"):
            return TransportOperationAssemblyDecision(
                "abstain",
                "initial-transport-step-not-grounded",
                missing_inputs=(
                    initial_readout.reason,))

        bid = 1.0 / (
            1.0
            + float(rendezvous_eta))
        readout = initial_readout
        request = cls._resource_request(
            spec, intent,
            requirement_set,
            snapshot,
            readout,
            bid=bid)
        if request is None:
            return TransportOperationAssemblyDecision(
                "abstain",
                "initial-transport-resource-request-not-grounded",
                missing_inputs=(
                    readout.reason,))
        assembly = (
            FounderTransportOperationAssembly(
                spec=spec,
                intent=intent,
                requirement_set=(
                    requirement_set),
                initial_premise_packets=tuple(
                    (premise_id, 1)
                    for premise_id
                    in sorted(
                        premise_ids)),
                initial_step_index=(
                    initial_step),
                initial_readout=readout,
                resource_request=request,
                rendezvous_eta_turns=(
                    rendezvous_eta),
                initial_corridors=(
                    corridors),
                compatible_carrier_profiles=(
                    compatible_carrier_profiles)))
        return TransportOperationAssemblyDecision(
            "assembled",
            "fully-grounded-current-transport-step",
            assembly=assembly)
