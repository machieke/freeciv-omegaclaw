"""Persistent shadow lifecycle for coordinated FDAS defender replacement."""

import json

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.coalitions import RequirementSet
from ..pressure.resource_claims import (
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from .fdas import ShadowOperationCandidate
from .fdas_defense import (
    FdasDefenseActionBinding,
    FdasDefenseLifecycleUpdate,
    FdasDefenseRequirementContext,
)
from .operation_store import OperationStore
from .operations import OperationState, TERMINAL_OPERATION_STATES


_OPERATION_TYPE = "fdas-defense:coordinated-replacement"


class FdasCoordinatedReplacementAdapter(object):
    """Reconcile a two-step replacement operation without granting authority."""

    ADAPTER_IDENTITY = "fdas-coordinated-replacement-adapter/1.0"

    def __init__(self, operation_store, ruleset_digest):
        if not isinstance(operation_store, OperationStore):
            raise TypeError("replacement adapter requires OperationStore")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("replacement adapter requires ruleset digest")
        self.store = operation_store
        self.ruleset_digest = ruleset_digest
        self._bindings = {}
        self._contexts = {}

    def binding(self, operation_id):
        return self._bindings.get(str(operation_id))

    def bindings(self):
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    def requirement_context(self, operation_id):
        return self._contexts.get(str(operation_id))

    def requirement_contexts(self):
        return tuple(self._contexts[key] for key in sorted(self._contexts))

    @staticmethod
    def _participants(record):
        return dict(
            (value.role, int(value.actor_id))
            for value in record.spec.participants)

    @staticmethod
    def _target_city_id(target_ref):
        if not isinstance(target_ref, str) or not target_ref.startswith("city:"):
            raise ValueError("replacement step requires city target")
        return int(target_ref.split(":", 1)[1])

    def _validate_candidate(self, snapshot, candidate):
        if not isinstance(candidate, ShadowOperationCandidate):
            raise TypeError(
                "replacement lifecycle requires ShadowOperationCandidate")
        spec = candidate.operation
        if spec.operation_type != _OPERATION_TYPE:
            raise ValueError("unsupported coordinated replacement operation")
        if spec.ruleset_digest != self.ruleset_digest:
            raise ValueError("replacement operation ruleset changed")
        if len(spec.steps) != 2 or tuple(
                value.actor_role for value in spec.steps) != (
                    "replacement", "reinforcement"):
            raise ValueError("replacement operation step schema is invalid")
        if set(self._participants_from_spec(spec)) != {
                "replacement", "reinforcement"}:
            raise ValueError("replacement operation participants are invalid")
        if (not candidate.legal_bound
                or candidate.authority_eligible
                or candidate.action_key not in snapshot.legal_action_json
                or canonical_json_bytes(candidate.action).decode("utf-8")
                != candidate.action_key):
            raise ValueError(
                "replacement first step requires current exact legal binding")
        replacement_id = self._participants_from_spec(spec)["replacement"]
        if (candidate.action.get("action_type") != "unit_move"
                or int(candidate.action.get("actor_id", -1))
                != replacement_id):
            raise ValueError("replacement first action names the wrong actor")
        source_city = snapshot.city(self._target_city_id(spec.steps[0].target_ref))
        action_row, _route, blocker = self._legal_route_action(
            snapshot, replacement_id, source_city)
        if blocker is not None or action_row[1] != candidate.action_key:
            raise ValueError(
                "replacement first action is not the current native route step")

    @staticmethod
    def _participants_from_spec(spec):
        return dict(
            (value.role, int(value.actor_id)) for value in spec.participants)

    @staticmethod
    def _legal_route_action(snapshot, actor_id, city):
        actor = snapshot.unit(actor_id)
        if actor is None or actor.tile is None or city is None or city.tile is None:
            return None, None, "current-operation-actor-or-target-unavailable"
        route = snapshot.movement_route(actor_id, city.tile)
        if (route is None or not route.reachable
                or route.authority != "freeciv-server-pathfinder"
                or route.schema_version != "1.0"
                or route.origin_tile != actor.tile
                or route.turn != snapshot.turn
                or route.source_seq > snapshot.identity.source_seq
                or snapshot.map_width <= 0):
            return None, route, "current-native-route-unavailable"
        first_x = route.first_step_tile % snapshot.map_width
        first_y = route.first_step_tile // snapshot.map_width
        rows = []
        for action_key in snapshot.legal_action_json:
            action = json.loads(action_key)
            target = action.get("target")
            if (action.get("action_type") == "unit_move"
                    and int(action.get("actor_id", -1)) == actor_id
                    and isinstance(target, dict)
                    and target.get("x") == first_x
                    and target.get("y") == first_y):
                rows.append((action, action_key))
        if len(rows) != 1:
            return None, route, "current-byte-identical-legal-action-unavailable"
        return rows[0], route, None

    @staticmethod
    def _binding(record, snapshot, action, action_key):
        semantic = {
            "action": action,
            "action_key": action_key,
            "domain_operation_id": record.spec.operation_id,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "legal_bound": True,
            "operation_id": record.spec.operation_id,
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseActionBinding(
            record.spec.operation_id,
            record.spec.operation_id,
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            action,
            action_key,
            True,
            structural_hash(semantic),
        )

    @staticmethod
    def _context(record, snapshot, actor_id, city, route, blocker):
        step = record.spec.steps[record.progress.current_step_index]
        city_id = int(step.target_ref.split(":", 1)[1])
        arrival_turn = (
            None if route is None else
            int(snapshot.turn) + int(route.estimated_turns))
        premises = (
            "capability:persistent-defense:unit:{}".format(actor_id),
            "availability:source-garrison-covered",
            "route:native:unit:{}:city:{}".format(actor_id, city_id),
            "deadline:arrival:{}<=operation:{}".format(
                arrival_turn, record.spec.expiry_turn),
            "legal-action:current-byte-identical",
            "resource:current-operation-capacity",
        )
        roles = (
            "capability", "availability", "route", "deadline",
            "legal-binding", "resource-capacity",
        )
        requirement_set = RequirementSet(
            step.requirement_set_id,
            "fdas-defense:coordinated-replacement:{}".format(
                record.progress.current_step_index),
            premises,
            roles,
            structural_hash({
                "operation_id": record.spec.operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "step_id": step.step_id,
            }),
        )
        blocked = ()
        if blocker is not None:
            premise = (
                premises[1] if "source" in blocker else
                premises[2] if "route" in blocker or "actor" in blocker
                else premises[3] if "deadline" in blocker
                else premises[4])
            blocked = ((premise, blocker),)
        claims = ()
        if blocker is None:
            window = TurnWindow(int(snapshot.turn), int(snapshot.turn) + 1)
            claims = (
                ResourceClaim(
                    ResourceRef(
                        GameResourceKind.ACTOR, "unit:{}".format(actor_id),
                        "whole_actor", "player:{}".format(snapshot.player_id)),
                    1, window, ClaimHardness.HARD_CURRENT, True,
                    record.spec.operation_id, step.step_id),
                ResourceClaim(
                    ResourceRef(
                        GameResourceKind.MOVE_POINTS,
                        "unit:{}".format(actor_id), "current_turn",
                        "player:{}".format(snapshot.player_id)),
                    int(route.first_step_movement_cost), window,
                    ClaimHardness.HARD_CURRENT, False,
                    record.spec.operation_id, step.step_id),
            )
        material = {
            "blocked_premises": dict(blocked),
            "operation_id": record.spec.operation_id,
            "requirement_set": requirement_set.to_dict(),
            "resource_claims": [value.to_dict() for value in claims],
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseRequirementContext(
            record.spec.operation_id, snapshot.snapshot_id,
            requirement_set, claims, blocked, structural_hash(material))

    @staticmethod
    def _update(record, previous, disposition, reason, snapshot, binding=None):
        return FdasDefenseLifecycleUpdate(
            record.spec.operation_id, previous.value,
            record.progress.state.value, disposition, reason,
            snapshot.snapshot_id, binding)

    def _clear(self, operation_id):
        self._bindings.pop(operation_id, None)
        self._contexts.pop(operation_id, None)

    def _refresh(self, record, snapshot):
        updates = []
        if int(snapshot.turn) > record.spec.expiry_turn:
            previous = record.progress.state
            record = self.store.transition(
                record.spec.operation_id, OperationState.EXPIRED,
                snapshot.snapshot_id, int(snapshot.turn),
                reason="operation-deadline-passed")
            self._clear(record.spec.operation_id)
            return (self._update(
                record, previous, "expired", "operation-deadline-passed",
                snapshot),)
        participants = self._participants(record)
        source_city = snapshot.city(self._target_city_id(
            record.spec.steps[0].target_ref))
        target_city = snapshot.city(self._target_city_id(
            record.spec.steps[1].target_ref))
        replacement = snapshot.unit(participants["replacement"])
        reinforcement = snapshot.unit(participants["reinforcement"])

        while record.progress.current_step_index < len(record.spec.steps):
            index = record.progress.current_step_index
            actor = replacement if index == 0 else reinforcement
            city = source_city if index == 0 else target_city
            source_guard = reinforcement if index == 0 else replacement
            if (source_city is None or source_city.tile is None
                    or source_guard is None
                    or source_guard.tile != source_city.tile):
                break
            if (actor is None or city is None or city.tile is None
                    or actor.tile != city.tile):
                break
            previous = record.progress.state
            record = self.store.advance_satisfied_step(
                record.spec.operation_id, snapshot.snapshot_id,
                int(snapshot.turn))
            if record.progress.state in TERMINAL_OPERATION_STATES:
                self._clear(record.spec.operation_id)
                return (self._update(
                    record, previous, "completed",
                    "all-step-predicates-satisfied", snapshot),)
            updates.append(self._update(
                record, previous, "step-advanced",
                "authoritative-step-predicate-satisfied", snapshot))

        index = record.progress.current_step_index
        actor_id = (
            participants["replacement"] if index == 0
            else participants["reinforcement"])
        city = source_city if index == 0 else target_city
        source_guard = (
            reinforcement if index == 0 else replacement)
        blocker = None
        if (source_city is None or source_city.tile is None
                or source_guard is None
                or source_guard.tile != source_city.tile):
            blocker = "protected-source-garrison-not-covered"
        action_row, route, route_blocker = self._legal_route_action(
            snapshot, actor_id, city)
        if blocker is None:
            blocker = route_blocker
        if (blocker is None
                and int(snapshot.turn) + int(route.estimated_turns)
                > record.spec.expiry_turn):
            blocker = "arrival-after-operation-deadline"
        context = self._context(
            record, snapshot, actor_id, city, route, blocker)
        self._contexts[record.spec.operation_id] = context
        previous = record.progress.state
        if blocker is not None:
            if record.progress.state == OperationState.BLOCKED:
                record = self.store.record_observation(
                    record.spec.operation_id, snapshot.snapshot_id,
                    int(snapshot.turn))
            else:
                record = self.store.transition(
                    record.spec.operation_id, OperationState.BLOCKED,
                    snapshot.snapshot_id, int(snapshot.turn), reason=blocker)
            self._bindings.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous, "blocked", blocker, snapshot))
            return tuple(updates)
        binding = self._binding(
            record, snapshot, action_row[0], action_row[1])
        if record.progress.state in (
                OperationState.PROPOSED, OperationState.BLOCKED,
                OperationState.SUSPENDED):
            record = self.store.transition(
                record.spec.operation_id, OperationState.RESERVABLE,
                snapshot.snapshot_id, int(snapshot.turn))
            disposition = "reservable"
        else:
            record = self.store.record_observation(
                record.spec.operation_id, snapshot.snapshot_id,
                int(snapshot.turn))
            disposition = "reconciled"
        self._bindings[record.spec.operation_id] = binding
        updates.append(self._update(
            record, previous, disposition,
            "current-coordinated-step-grounded", snapshot, binding))
        return tuple(updates)

    def reconcile(self, snapshot, candidates=()):
        if self.store.quarantined:
            raise ValueError("quarantined operation store cannot reconcile")
        candidates = tuple(candidates)
        ids = [value.operation.operation_id for value in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("replacement candidates must be unique")
        for candidate in candidates:
            self._validate_candidate(snapshot, candidate)
        for candidate in candidates:
            self.store.propose(
                candidate.operation, snapshot.snapshot_id, int(snapshot.turn))
        updates = []
        for record in self.store.nonterminal_records():
            if record.spec.operation_type != _OPERATION_TYPE:
                continue
            updates.extend(self._refresh(record, snapshot))
        return tuple(updates)
