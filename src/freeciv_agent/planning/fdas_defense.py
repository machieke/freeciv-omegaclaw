"""FDAS adapter for the existing persistent city-defense operation store."""

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
from .operation_assembler import assemble_city_defense_operation
from .operation_store import OperationStore
from .operations import OperationState


_DEFENSE_TYPES = frozenset((
    "emergency_build_defender",
    "fortify_existing_defender",
    "hold_sole_defender",
    "intercept_immediate_threat",
    "move_defender_to_city",
))


@dataclass(frozen=True)
class FdasDefenseActionBinding:
    operation_id: str
    domain_operation_id: str
    snapshot_id: str
    legal_actions_digest: str
    action: object
    action_key: object
    legal_bound: bool
    binding_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.domain_operation_id, "domain operation ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.legal_actions_digest, "legal-action digest"),
                (self.binding_hash, "binding hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("FDAS defense {} is required".format(name))
        if self.action is None:
            if self.action_key is not None or self.legal_bound:
                raise ValueError("no-action binding cannot be legal-bound")
        elif not isinstance(self.action, dict):
            raise TypeError("FDAS defense action must be an object or absent")

    def to_dict(self):
        return {
            "action": self.action,
            "action_key": self.action_key,
            "binding_hash": self.binding_hash,
            "domain_operation_id": self.domain_operation_id,
            "legal_actions_digest": self.legal_actions_digest,
            "legal_bound": self.legal_bound,
            "operation_id": self.operation_id,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class FdasDefenseLifecycleUpdate:
    operation_id: str
    previous_state: str
    state: str
    disposition: str
    reason: str
    snapshot_id: str
    binding: object = None

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.previous_state, "previous state"),
                (self.state, "state"),
                (self.disposition, "disposition"),
                (self.reason, "reason"),
                (self.snapshot_id, "snapshot ID")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "FDAS defense lifecycle {} is required".format(name))
        if (self.binding is not None
                and not isinstance(self.binding, FdasDefenseActionBinding)):
            raise TypeError("FDAS defense lifecycle binding is invalid")

    def to_dict(self):
        return {
            "binding": None if self.binding is None else self.binding.to_dict(),
            "disposition": self.disposition,
            "operation_id": self.operation_id,
            "previous_state": self.previous_state,
            "reason": self.reason,
            "snapshot_id": self.snapshot_id,
            "state": self.state,
        }


@dataclass(frozen=True)
class FdasDefenseRequirementContext:
    operation_id: str
    snapshot_id: str
    requirement_set: RequirementSet
    resource_claims: tuple
    blocked_premises: tuple
    context_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.context_hash, "context hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "FDAS defense requirement {} is required".format(name))
        if not isinstance(self.requirement_set, RequirementSet):
            raise TypeError("FDAS defense context requires RequirementSet")
        object.__setattr__(self, "resource_claims", tuple(
            self.resource_claims))
        if any(not isinstance(value, ResourceClaim)
               for value in self.resource_claims):
            raise TypeError("FDAS defense resource claim is invalid")
        blocked = tuple(tuple(value) for value in self.blocked_premises)
        if any(len(value) != 2 or any(
                not isinstance(item, str) or not item for item in value)
               for value in blocked):
            raise ValueError("blocked requirement premises are invalid")
        if any(value[0] not in self.requirement_set.premise_ids
               for value in blocked):
            raise ValueError("blocked requirement premise is undeclared")
        if len({value[0] for value in blocked}) != len(blocked):
            raise ValueError("blocked requirement premises must be unique")
        object.__setattr__(self, "blocked_premises", tuple(sorted(blocked)))

    def to_dict(self):
        return {
            "blocked_premises": dict(self.blocked_premises),
            "context_hash": self.context_hash,
            "operation_id": self.operation_id,
            "requirement_set": self.requirement_set.to_dict(),
            "resource_claims": [
                value.to_dict() for value in self.resource_claims],
            "snapshot_id": self.snapshot_id,
        }


class FdasCityDefenseOperationAdapter(object):
    """Reconcile defense rows into a caller-owned durable operation store.

    The adapter reserves no resources and grants no authority. It keeps
    immutable operation intent stable while refreshing the current exact legal
    action binding as a separate snapshot-scoped value.
    """

    ADAPTER_IDENTITY = "fdas-city-defense-operation-adapter/1.0"

    def __init__(self, operation_store, ruleset_digest):
        if not isinstance(operation_store, OperationStore):
            raise TypeError("FDAS defense adapter requires OperationStore")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("FDAS defense adapter requires ruleset digest")
        self.store = operation_store
        self.ruleset_digest = ruleset_digest
        self._bindings = {}
        self._contexts = {}

    def binding(self, operation_id):
        return self._bindings.get(str(operation_id))

    def bindings(self):
        return tuple(
            self._bindings[key] for key in sorted(self._bindings))

    def requirement_context(self, operation_id):
        return self._contexts.get(str(operation_id))

    def requirement_contexts(self):
        return tuple(self._contexts[key] for key in sorted(self._contexts))

    @staticmethod
    def _row(value):
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        if not isinstance(value, dict):
            raise TypeError("city-defense operation must be an object")
        return dict(value)

    @staticmethod
    def _row_key(row):
        return (
            str(row.get("operation_type") or ""),
            row.get("actor_id"),
            row.get("city_id"),
        )

    @staticmethod
    def _record_key(record):
        participant = record.spec.participants[0]
        actor_id = participant.actor_id
        if actor_id.startswith("unit:"):
            actor_id = int(actor_id.split(":", 1)[1])
        else:
            actor_id = None
        city_id = int(record.spec.target_ref.split(":", 1)[1])
        return record.spec.operation_type, actor_id, city_id

    def _current_record(self, row, turn):
        matches = tuple(
            record for record in self.store.nonterminal_records()
            if (record.spec.operation_type in _DEFENSE_TYPES
                and self._record_key(record) == self._row_key(row)
                and record.spec.expiry_turn >= int(turn)))
        return (None if not matches else sorted(
            matches,
            key=lambda value: (
                value.spec.expiry_turn, value.spec.operation_id))[0])

    @staticmethod
    def _completion(record, snapshot):
        operation_type = record.spec.operation_type
        actor_ref = record.spec.participants[0].actor_id
        city_id = int(record.spec.target_ref.split(":", 1)[1])
        city = snapshot.city(city_id)
        if city is None or city.tile is None:
            return None
        actor = (
            snapshot.unit(int(actor_ref.split(":", 1)[1]))
            if actor_ref.startswith("unit:") else None)
        if operation_type == "move_defender_to_city":
            return bool(actor is not None and actor.tile == city.tile)
        if operation_type == "fortify_existing_defender":
            return bool(
                actor is not None and actor.tile == city.tile
                and str(actor.activity or "").lower() in (
                    "fortify", "fortified", "fortifying"))
        if operation_type == "hold_sole_defender":
            return bool(
                int(snapshot.turn) >= record.spec.expiry_turn
                and actor is not None and actor.tile == city.tile)
        # Enemy disappearance is not proof of interception, and production
        # completion needs a before/after product identity. Preserve unknown.
        return None

    @staticmethod
    def _binding(record, row, snapshot):
        action = row.get("next_action")
        action_key = (
            None if action is None else
            canonical_json_bytes(action).decode("utf-8"))
        legal_bound = bool(
            action_key is not None
            and action_key in snapshot.legal_action_json)
        semantic = {
            "action": action,
            "action_key": action_key,
            "domain_operation_id": row["operation_id"],
            "legal_actions_digest": snapshot.legal_actions_digest,
            "legal_bound": legal_bound,
            "operation_id": record.spec.operation_id,
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseActionBinding(
            record.spec.operation_id,
            str(row["operation_id"]),
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            action,
            action_key,
            legal_bound,
            structural_hash(semantic),
        )

    @staticmethod
    def _requirement_context(record, row, snapshot, binding, blocker):
        operation_id = record.spec.operation_id
        step = record.spec.steps[record.progress.current_step_index]
        actor_id = row.get("actor_id")
        city_id = int(row["city_id"])
        premises = [
            "capability:persistent-defense:{}".format(
                "city:producer" if actor_id is None else "unit:{}".format(
                    actor_id)),
            "availability:not-protected-source:{}".format(
                "city:producer" if actor_id is None else "unit:{}".format(
                    actor_id)),
            "deadline:arrival:{}<=threat:{}".format(
                row.get("arrival_turn"), row.get("deadline_turn")),
            "legal-action:current-byte-identical",
            "resource:current-operation-capacity",
        ]
        roles = [
            "capability", "availability", "deadline", "legal-binding",
            "resource-capacity",
        ]
        if row.get("operation_type") == "move_defender_to_city":
            premises.insert(2, "route:native:unit:{}:city:{}".format(
                actor_id, city_id))
            roles.insert(2, "route")
        requirement_set = RequirementSet(
            step.requirement_set_id,
            "fdas-defense:{}".format(row["operation_type"]),
            tuple(premises), tuple(roles),
            structural_hash({
                "operation_id": operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "step_id": step.step_id,
            }))
        claims = ()
        if (blocker is None and actor_id is not None
                and row.get("next_action") is not None):
            resource = ResourceRef(
                GameResourceKind.ACTOR, str(actor_id), "current-action",
                "player:{}".format(snapshot.player_id))
            claims = (ResourceClaim(
                resource, 1,
                TurnWindow(int(snapshot.turn), int(snapshot.turn) + 1),
                ClaimHardness.HARD_CURRENT, True, operation_id, step.step_id),)
        elif (blocker is None and actor_id is None
              and row.get("operation_type") == "emergency_build_defender"):
            resource = ResourceRef(
                GameResourceKind.CITY_PRODUCTION_SLOT, str(city_id), None,
                "city:{}".format(city_id))
            claims = (ResourceClaim(
                resource, 1,
                TurnWindow(int(snapshot.turn), int(snapshot.turn) + 1),
                ClaimHardness.HARD_CURRENT, True, operation_id, step.step_id),)
        blocked_premises = ()
        if blocker is not None:
            premise = (
                "legal-action:current-byte-identical"
                if blocker == "current-byte-identical-legal-action-unavailable"
                else "deadline:arrival:{}<=threat:{}".format(
                    row.get("arrival_turn"), row.get("deadline_turn"))
                if "deadline" in blocker or "arrival" in blocker
                else "availability:not-protected-source:{}".format(
                    "city:producer" if actor_id is None
                    else "unit:{}".format(actor_id)))
            blocked_premises = ((premise, blocker),)
        material = {
            "blocked_premises": dict(blocked_premises),
            "operation_id": operation_id,
            "requirement_set": requirement_set.to_dict(),
            "resource_claims": [value.to_dict() for value in claims],
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseRequirementContext(
            operation_id, snapshot.snapshot_id, requirement_set, claims,
            blocked_premises, structural_hash(material))

    @staticmethod
    def _update(record, previous, disposition, reason, snapshot, binding=None):
        return FdasDefenseLifecycleUpdate(
            record.spec.operation_id,
            previous.value,
            record.progress.state.value,
            disposition,
            reason,
            snapshot.snapshot_id,
            binding,
        )

    def _finish_observed(self, record, snapshot, updates):
        completed = self._completion(record, snapshot)
        if completed is True:
            previous = record.progress.state
            record = self.store.transition(
                record.spec.operation_id,
                OperationState.COMPLETED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason="authoritative-completion-observed")
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous, "completed",
                "authoritative-completion-observed", snapshot))
            return "completed"
        if int(snapshot.turn) > record.spec.expiry_turn:
            previous = record.progress.state
            record = self.store.transition(
                record.spec.operation_id,
                OperationState.EXPIRED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason="operation-deadline-passed")
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous, "expired",
                "operation-deadline-passed", snapshot))
            return "expired"
        return None

    def reconcile(self, snapshot, operations, selected_operation_ids=None):
        if self.store.quarantined:
            raise ValueError("quarantined operation store cannot reconcile")
        rows = tuple(self._row(value) for value in operations)
        operation_ids = tuple(str(value.get("operation_id") or "")
                              for value in rows)
        if any(not value for value in operation_ids):
            raise ValueError("city-defense operation ID is required")
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("city-defense operation IDs must be unique")
        selected = (
            frozenset(operation_ids)
            if selected_operation_ids is None else
            frozenset(str(value) for value in selected_operation_ids))
        if not selected.issubset(operation_ids):
            raise ValueError("selected city-defense operation is unavailable")
        rows = tuple(
            value for value in rows
            if str(value["operation_id"]) in selected)
        updates = []
        completed_keys = set()
        for record in tuple(self.store.nonterminal_records()):
            if record.spec.operation_type not in _DEFENSE_TYPES:
                continue
            disposition = self._finish_observed(record, snapshot, updates)
            if disposition == "completed":
                completed_keys.add(self._record_key(record))

        touched = set()
        for row in sorted(rows, key=lambda value: str(value["operation_id"])):
            if self._row_key(row) in completed_keys:
                continue
            if row.get("operation_type") not in _DEFENSE_TYPES:
                raise ValueError("unsupported city-defense operation type")
            supported = bool(
                row.get("support_reason") is None
                and int(row.get("arrival_turn", 0))
                <= int(row.get("deadline_turn", -1)))
            record = self._current_record(row, snapshot.turn)
            if record is None:
                lifecycle_row = dict(row)
                operation_id = str(row["operation_id"])
                if self.store.get(operation_id) is not None:
                    operation_id = "operation-" + structural_hash({
                        "domain_operation_id": row["operation_id"],
                        "snapshot_id": snapshot.snapshot_id,
                    })[:32]
                    lifecycle_row["operation_id"] = operation_id
                spec = assemble_city_defense_operation(
                    lifecycle_row, int(snapshot.turn), self.ruleset_digest)
                record = self.store.propose(
                    spec, snapshot.snapshot_id, int(snapshot.turn))
            touched.add(record.spec.operation_id)
            previous = record.progress.state
            binding = self._binding(record, row, snapshot)
            blocker = (
                str(row.get("support_reason"))
                if not supported else
                "current-byte-identical-legal-action-unavailable"
                if row.get("next_action") is not None and not binding.legal_bound
                else None)
            context = self._requirement_context(
                record, row, snapshot, binding, blocker)
            self._contexts[record.spec.operation_id] = context
            if blocker is not None:
                if record.progress.state == OperationState.BLOCKED:
                    record = self.store.record_observation(
                        record.spec.operation_id,
                        snapshot.snapshot_id, int(snapshot.turn))
                else:
                    record = self.store.transition(
                        record.spec.operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id, int(snapshot.turn), reason=blocker)
                self._bindings.pop(record.spec.operation_id, None)
                updates.append(self._update(
                    record, previous, "blocked", blocker, snapshot))
                continue
            if record.progress.state in (
                    OperationState.PROPOSED,
                    OperationState.BLOCKED,
                    OperationState.SUSPENDED):
                record = self.store.transition(
                    record.spec.operation_id,
                    OperationState.RESERVABLE,
                    snapshot.snapshot_id, int(snapshot.turn))
                disposition = "reservable"
                reason = "current-defense-step-grounded"
            else:
                record = self.store.record_observation(
                    record.spec.operation_id,
                    snapshot.snapshot_id, int(snapshot.turn))
                disposition = "reconciled"
                reason = "persistent-defense-step-refreshed"
            self._bindings[record.spec.operation_id] = binding
            updates.append(self._update(
                record, previous, disposition, reason, snapshot, binding))

        updated_ids = {value.operation_id for value in updates}
        for record in tuple(self.store.nonterminal_records()):
            if (record.spec.operation_type not in _DEFENSE_TYPES
                    or record.spec.operation_id in touched
                    or record.spec.operation_id in updated_ids):
                continue
            previous = record.progress.state
            reason = "current-assignment-no-longer-supports-operation"
            if record.progress.state == OperationState.BLOCKED:
                record = self.store.record_observation(
                    record.spec.operation_id,
                    snapshot.snapshot_id, int(snapshot.turn))
            else:
                record = self.store.transition(
                    record.spec.operation_id,
                    OperationState.BLOCKED,
                    snapshot.snapshot_id, int(snapshot.turn), reason=reason)
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous, "blocked", reason, snapshot))
        return tuple(sorted(updates, key=lambda value: value.operation_id))
