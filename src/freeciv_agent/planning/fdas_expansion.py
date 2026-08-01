"""Persistent shadow lifecycle for exact FDAS expansion actions."""

from dataclasses import dataclass
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
from ..state.atomspace import population_recovery_profile
from .fdas_defense import (
    FdasDefenseActionBinding,
    FdasDefenseRequirementContext,
)
from .operation_store import OperationStore
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationState,
    OperationStep,
)


FOUND_CITY_OPERATION = "fdas_expansion_found_city"
RECOVER_POPULATION_OPERATION = "fdas_expansion_recover_population"
_EXPANSION_TYPES = frozenset((
    FOUND_CITY_OPERATION,
    RECOVER_POPULATION_OPERATION,
))


@dataclass(frozen=True)
class FdasExpansionLifecycleUpdate:
    operation_id: str
    previous_state: str
    state: str
    disposition: str
    reason: str
    snapshot_id: str
    binding: object = None

    def to_dict(self):
        return {
            "binding": (
                None if self.binding is None else self.binding.to_dict()),
            "disposition": self.disposition,
            "operation_id": self.operation_id,
            "previous_state": self.previous_state,
            "reason": self.reason,
            "snapshot_id": self.snapshot_id,
            "state": self.state,
        }


class FdasExpansionOperationAdapter(object):
    """Reconcile exact FDAS founder actions without granting authority.

    The adapter only binds actions already present byte-for-byte in the
    current legal-action set. ``commit_matching_action`` observes an external
    controller result; it never sends an action or reserves a resource.
    Completion requires a later authoritative state effect.
    """

    ADAPTER_IDENTITY = "fdas-expansion-operation-adapter/1.0"

    def __init__(self, operation_store, ruleset_ir, ruleset_digest):
        if not isinstance(operation_store, OperationStore):
            raise TypeError("FDAS expansion adapter requires OperationStore")
        if ruleset_ir is None:
            raise ValueError("FDAS expansion adapter requires ruleset IR")
        if not isinstance(ruleset_digest, str) or not ruleset_digest:
            raise ValueError("FDAS expansion adapter requires ruleset digest")
        self.store = operation_store
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self._bindings = {}
        self._contexts = {}
        self._candidates = {}

    def binding(self, operation_id):
        return self._bindings.get(str(operation_id))

    def bindings(self):
        return tuple(self._bindings[key] for key in sorted(self._bindings))

    def requirement_context(self, operation_id):
        return self._contexts.get(str(operation_id))

    def requirement_contexts(self):
        return tuple(self._contexts[key] for key in sorted(self._contexts))

    @staticmethod
    def _records_by_scope(revision):
        rows = {}
        for record in revision.records:
            rows.setdefault(record.key.scope_id, []).append(record)
        return dict((key, tuple(value)) for key, value in rows.items())

    @staticmethod
    def _argument(record, index, kind):
        value = record.key.arguments[index]
        if getattr(value, "kind", None) != kind:
            return None
        return value.entity_id

    @classmethod
    def _settlement_candidates(cls, snapshot, revision, records_by_scope):
        candidates = []
        occupied = {value.tile for value in snapshot.cities}
        for scope in revision.scopes:
            if scope.scope_kind != "settlement-site":
                continue
            records = records_by_scope.get(scope.scope_id, ())
            predicates = {value.key.predicate for value in records}
            if "settlement-site-currently-uncontested" not in predicates:
                continue
            if predicates.intersection((
                    "settlement-site-contested-by",
                    "settlement-visible-threat-near",
                    "settlement-escort-required",
                    "settlement-site-blocked-by-threat")):
                continue
            founder_rows = tuple(
                value for value in records
                if value.key.predicate == "founder-can-settle-now")
            for founder_row in founder_rows:
                founder_id = cls._argument(founder_row, 0, "unit")
                founder = snapshot.unit(founder_id)
                if founder is None or founder.tile is None:
                    continue
                tile = int(founder.tile)
                if tile in occupied:
                    continue
                actions = tuple(
                    (json.loads(value), value)
                    for value in snapshot.legal_action_json
                    if (json.loads(value).get("action_type")
                        == "unit_build_city"
                        and str(json.loads(value).get("actor_id"))
                        == str(founder_id)))
                if len(actions) != 1:
                    continue
                candidates.append({
                    "action": actions[0][0],
                    "action_key": actions[0][1],
                    "actor_id": int(founder_id),
                    "operation_type": FOUND_CITY_OPERATION,
                    "source_atom_ids": tuple(sorted(
                        value.atom_id for value in records
                        if value.key.predicate in (
                            "founder-can-settle-now",
                            "settlement-site-currently-uncontested"))),
                    "target_id": tile,
                    "target_ref": "tile:{}".format(tile),
                })
        return candidates

    def _recovery_candidates(self, snapshot, revision, records_by_scope):
        candidates = []
        required = frozenset((
            "founder-population-recovery-capable",
            "founder-population-recovery-colocated",
            "population-recovery-current-legal-action",
            "population-recovery-expected-city-gain",
            "population-recovery-founder",
            "population-recovery-target-city",
        ))
        for scope in revision.scopes:
            if scope.scope_kind != "population-recovery":
                continue
            records = records_by_scope.get(scope.scope_id, ())
            if not required.issubset(
                    value.key.predicate for value in records):
                continue
            founder_row = next(
                value for value in records
                if value.key.predicate == "population-recovery-founder")
            city_row = next(
                value for value in records
                if value.key.predicate == "population-recovery-target-city")
            founder_id = self._argument(founder_row, 1, "unit")
            city_id = self._argument(city_row, 1, "city")
            founder = snapshot.unit(founder_id)
            city = snapshot.city(city_id)
            if founder is None or city is None or city.size is None:
                continue
            profile = population_recovery_profile(
                self.ruleset_ir, founder.unit_type)
            if profile is None:
                continue
            actions = tuple(
                (json.loads(value), value)
                for value in snapshot.legal_action_json
                if (json.loads(value).get("action_type") == "unit_join_city"
                    and str(json.loads(value).get("actor_id"))
                    == str(founder_id)
                    and json.loads(value).get("target", {}).get("city_id")
                    == int(city_id)))
            if len(actions) != 1:
                continue
            gain = int(profile["population_gain"])
            candidates.append({
                "action": actions[0][0],
                "action_key": actions[0][1],
                "actor_id": int(founder_id),
                "baseline_size": int(city.size),
                "expected_size": int(city.size) + gain,
                "operation_type": RECOVER_POPULATION_OPERATION,
                "population_gain": gain,
                "source_atom_ids": tuple(sorted(
                    value.atom_id for value in records
                    if value.key.predicate in required)),
                "target_id": int(city_id),
                "target_ref": "city:{}".format(city_id),
            })
        return candidates

    def _candidates_from_revision(self, snapshot, revision):
        if revision.snapshot_id != snapshot.snapshot_id:
            raise ValueError("FDAS expansion revision is not current")
        records = self._records_by_scope(revision)
        values = (
            self._settlement_candidates(snapshot, revision, records)
            + self._recovery_candidates(snapshot, revision, records))
        keys = [(
            value["operation_type"], value["actor_id"], value["target_ref"])
            for value in values]
        if len(keys) != len(set(keys)):
            raise ValueError("FDAS expansion candidates are ambiguous")
        return tuple(sorted(values, key=lambda value: (
            value["operation_type"], value["actor_id"],
            value["target_ref"])))

    @staticmethod
    def _record_key(record):
        return (
            record.spec.operation_type,
            int(record.spec.participants[0].actor_id.split(":", 1)[1]),
            record.spec.target_ref,
        )

    def _current_record(self, candidate):
        key = (
            candidate["operation_type"], candidate["actor_id"],
            candidate["target_ref"])
        matches = tuple(
            value for value in self.store.nonterminal_records()
            if (value.spec.operation_type in _EXPANSION_TYPES
                and self._record_key(value) == key))
        if len(matches) > 1:
            raise ValueError("duplicate persistent FDAS expansion operation")
        return None if not matches else matches[0]

    def _spec(self, candidate, snapshot):
        operation_id = "operation-" + structural_hash({
            "actor_id": candidate["actor_id"],
            "created_turn": snapshot.turn,
            "operation_type": candidate["operation_type"],
            "ruleset_digest": self.ruleset_digest,
            "target_ref": candidate["target_ref"],
        })[:32]
        requirement_set_id = "fdas-expansion-requirement-" + structural_hash({
            "operation_id": operation_id,
            "source_atom_ids": candidate["source_atom_ids"],
        })[:24]
        if candidate["operation_type"] == FOUND_CITY_OPERATION:
            completion = "fdas-expansion:founder-consumed-and-city-at-tile"
        else:
            completion = (
                "fdas-expansion:founder-consumed-and-city-size-at-least:{}"
                .format(candidate["expected_size"]))
        step_id = "step-" + structural_hash({
            "action_type": candidate["action"]["action_type"],
            "operation_id": operation_id,
            "target_ref": candidate["target_ref"],
        })[:32]
        return OperationSpec(
            OPERATION_SCHEMA_VERSION,
            operation_id,
            candidate["operation_type"],
            ("pf-impact:expansion",),
            (OperationParticipant(
                "founder", "unit:{}".format(candidate["actor_id"]),
                "unit", True),),
            candidate["target_ref"],
            (OperationStep(
                step_id, candidate["action"]["action_type"], "founder",
                candidate["target_ref"], requirement_set_id, completion, 1),),
            int(snapshot.turn), int(snapshot.turn) + 2, 0.0,
            (self.ADAPTER_IDENTITY, "same-snapshot-fdas-proof",
             "server-advertised-legal-action"),
            self.ruleset_digest,
        )

    @staticmethod
    def _expected_recovery_size(record):
        marker = "fdas-expansion:founder-consumed-and-city-size-at-least:"
        predicate = record.spec.steps[0].completion_predicate_id
        if not predicate.startswith(marker):
            raise ValueError("population-recovery completion contract changed")
        return int(predicate[len(marker):])

    @classmethod
    def _effect(cls, record, snapshot):
        if record.progress.state != OperationState.ACTIVE:
            return None
        founder_id = int(
            record.spec.participants[0].actor_id.split(":", 1)[1])
        if snapshot.unit(founder_id) is not None:
            return None
        target_kind, target_id = record.spec.target_ref.split(":", 1)
        if record.spec.operation_type == FOUND_CITY_OPERATION:
            tile = int(target_id)
            return bool(any(value.tile == tile for value in snapshot.cities))
        if record.spec.operation_type == RECOVER_POPULATION_OPERATION:
            if target_kind != "city":
                raise ValueError("population recovery target is not a city")
            city = snapshot.city(int(target_id))
            return bool(
                city is not None and city.size is not None
                and int(city.size) >= cls._expected_recovery_size(record))
        raise ValueError("unsupported FDAS expansion operation")

    @staticmethod
    def _binding(record, candidate, snapshot):
        action = candidate["action"]
        action_key = canonical_json_bytes(action).decode("utf-8")
        legal_bound = bool(
            action_key == candidate["action_key"]
            and action_key in snapshot.legal_action_json)
        semantic = {
            "action": action,
            "action_key": action_key,
            "domain_operation_id": record.spec.operation_id,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "legal_bound": legal_bound,
            "operation_id": record.spec.operation_id,
            "snapshot_id": snapshot.snapshot_id,
        }
        return FdasDefenseActionBinding(
            record.spec.operation_id, record.spec.operation_id,
            snapshot.snapshot_id, snapshot.legal_actions_digest,
            action, action_key, legal_bound, structural_hash(semantic))

    @staticmethod
    def _claims(record, snapshot, active=False):
        if active:
            return ()
        operation_id = record.spec.operation_id
        step_id = record.spec.steps[0].step_id
        player_scope = "player:{}".format(snapshot.player_id)
        window = TurnWindow(int(snapshot.turn), int(snapshot.turn) + 1)
        claims = [
            ResourceClaim(
                ResourceRef(
                    GameResourceKind.ACTOR,
                    record.spec.participants[0].actor_id,
                    "whole_actor", player_scope),
                1, window, ClaimHardness.HARD_CURRENT, True,
                operation_id, step_id),
            ResourceClaim(
                ResourceRef(
                    GameResourceKind.ACTION_BUDGET,
                    player_scope, "controller", player_scope),
                1, window, ClaimHardness.HARD_CURRENT, False,
                operation_id, step_id),
        ]
        if record.spec.operation_type == FOUND_CITY_OPERATION:
            claims.append(ResourceClaim(
                ResourceRef(
                    GameResourceKind.TILE_OCCUPANCY,
                    record.spec.target_ref, "settlement-site",
                    "map:{}".format(snapshot.identity.game_id)),
                1, window, ClaimHardness.CONDITIONAL_FUTURE, True,
                operation_id, step_id))
        return tuple(sorted(claims, key=lambda value: value.sort_key))

    @classmethod
    def _context(cls, record, candidate, snapshot, blocker=None):
        active = record.progress.state == OperationState.ACTIVE
        if record.spec.operation_type == FOUND_CITY_OPERATION:
            premises = (
                "fdas:founder-can-settle-now",
                "fdas:settlement-site-currently-uncontested",
                "fdas:no-current-contest-threat-or-blocker",
                "legal-action:current-byte-identical",
                "resource:current-operation-capacity",
            )
            roles = (
                "capability", "site-safety", "threat-policy",
                "legal-binding", "resource-capacity",
            )
        else:
            premises = (
                "fdas:founder-population-recovery-capable",
                "fdas:founder-population-recovery-colocated",
                "fdas:target-city-size-current",
                "legal-action:current-byte-identical",
                "resource:current-operation-capacity",
            )
            roles = (
                "capability", "colocation", "population-effect",
                "legal-binding", "resource-capacity",
            )
        requirement_set = RequirementSet(
            record.spec.steps[0].requirement_set_id,
            "{}:{}".format(cls.ADAPTER_IDENTITY, record.spec.operation_type),
            premises, roles,
            structural_hash({
                "operation_id": record.spec.operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "source_atom_ids": (
                    () if candidate is None else
                    candidate["source_atom_ids"]),
            }))
        if active:
            blocker = "awaiting-authoritative-expansion-effect"
        elif candidate is None:
            blocker = blocker or "current-fdas-expansion-proof-unavailable"
        blocked = ()
        if blocker:
            premise = (
                "legal-action:current-byte-identical"
                if "action" in blocker or "proof" in blocker
                else "fdas:target-city-size-current"
                if record.spec.operation_type == RECOVER_POPULATION_OPERATION
                else "fdas:settlement-site-currently-uncontested")
            blocked = ((premise, blocker),)
        claims = cls._claims(record, snapshot, active=active or bool(blocker))
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
        return FdasExpansionLifecycleUpdate(
            record.spec.operation_id, previous.value,
            record.progress.state.value, disposition, reason,
            snapshot.snapshot_id, binding)

    def _finish_observed(self, record, snapshot, updates):
        effect = self._effect(record, snapshot)
        if effect is not None:
            previous = record.progress.state
            target = (
                OperationState.COMPLETED if effect else OperationState.FAILED)
            reason = (
                "authoritative-expansion-effect-observed" if effect else
                "founder-consumed-without-required-expansion-effect")
            record = self.store.transition(
                record.spec.operation_id, target, snapshot.snapshot_id,
                int(snapshot.turn), reason=reason)
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts.pop(record.spec.operation_id, None)
            self._candidates.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous,
                "completed" if effect else "failed", reason, snapshot))
            return True
        if int(snapshot.turn) > record.spec.expiry_turn:
            previous = record.progress.state
            record = self.store.transition(
                record.spec.operation_id, OperationState.EXPIRED,
                snapshot.snapshot_id, int(snapshot.turn),
                reason="operation-deadline-passed-without-expansion-effect")
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts.pop(record.spec.operation_id, None)
            self._candidates.pop(record.spec.operation_id, None)
            updates.append(self._update(
                record, previous, "expired",
                "operation-deadline-passed-without-expansion-effect",
                snapshot))
            return True
        return False

    def reconcile(self, snapshot, revision):
        if self.store.quarantined:
            raise ValueError("quarantined operation store cannot reconcile")
        candidates = self._candidates_from_revision(snapshot, revision)
        updates = []
        finished = set()
        for record in tuple(self.store.nonterminal_records()):
            if (record.spec.operation_type in _EXPANSION_TYPES
                    and self._finish_observed(record, snapshot, updates)):
                finished.add(record.spec.operation_id)

        touched = set()
        for candidate in candidates:
            record = self._current_record(candidate)
            if record is None:
                spec = self._spec(candidate, snapshot)
                record = self.store.propose(
                    spec, snapshot.snapshot_id, int(snapshot.turn))
            if record.spec.operation_id in finished:
                continue
            touched.add(record.spec.operation_id)
            self._candidates[record.spec.operation_id] = candidate
            previous = record.progress.state
            if record.progress.state == OperationState.ACTIVE:
                record = self.store.record_observation(
                    record.spec.operation_id, snapshot.snapshot_id,
                    int(snapshot.turn))
                self._bindings.pop(record.spec.operation_id, None)
                self._contexts[record.spec.operation_id] = self._context(
                    record, candidate, snapshot)
                updates.append(self._update(
                    record, previous, "awaiting-effect",
                    "awaiting-authoritative-expansion-effect", snapshot))
                continue
            binding = self._binding(record, candidate, snapshot)
            blocker = (
                None if binding.legal_bound else
                "current-byte-identical-legal-action-unavailable")
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
                self._contexts[record.spec.operation_id] = self._context(
                    record, candidate, snapshot, blocker)
                updates.append(self._update(
                    record, previous, "blocked", blocker, snapshot))
                continue
            if record.progress.state in (
                    OperationState.PROPOSED, OperationState.BLOCKED,
                    OperationState.SUSPENDED):
                record = self.store.transition(
                    record.spec.operation_id, OperationState.RESERVABLE,
                    snapshot.snapshot_id, int(snapshot.turn))
                disposition = "reservable"
                reason = "current-fdas-expansion-step-grounded"
            else:
                record = self.store.record_observation(
                    record.spec.operation_id, snapshot.snapshot_id,
                    int(snapshot.turn))
                disposition = "reconciled"
                reason = "persistent-expansion-step-refreshed"
            self._bindings[record.spec.operation_id] = binding
            self._contexts[record.spec.operation_id] = self._context(
                record, candidate, snapshot)
            updates.append(self._update(
                record, previous, disposition, reason, snapshot, binding))

        for record in tuple(self.store.nonterminal_records()):
            if (record.spec.operation_type not in _EXPANSION_TYPES
                    or record.spec.operation_id in touched
                    or record.spec.operation_id in finished):
                continue
            previous = record.progress.state
            if record.progress.state == OperationState.ACTIVE:
                record = self.store.record_observation(
                    record.spec.operation_id, snapshot.snapshot_id,
                    int(snapshot.turn))
                self._bindings.pop(record.spec.operation_id, None)
                self._contexts[record.spec.operation_id] = self._context(
                    record, None, snapshot)
                updates.append(self._update(
                    record, previous, "awaiting-effect",
                    "awaiting-authoritative-expansion-effect", snapshot))
                continue
            reason = "current-fdas-expansion-proof-unavailable"
            if record.progress.state == OperationState.BLOCKED:
                record = self.store.record_observation(
                    record.spec.operation_id, snapshot.snapshot_id,
                    int(snapshot.turn))
            else:
                record = self.store.transition(
                    record.spec.operation_id, OperationState.BLOCKED,
                    snapshot.snapshot_id, int(snapshot.turn), reason=reason)
            self._bindings.pop(record.spec.operation_id, None)
            self._contexts[record.spec.operation_id] = self._context(
                record, None, snapshot, reason)
            updates.append(self._update(
                record, previous, "blocked", reason, snapshot))
        return tuple(sorted(updates, key=lambda value: value.operation_id))

    def commit_matching_action(self, snapshot, action, accepted, reason=None):
        action_key = canonical_json_bytes(action).decode("utf-8")
        matches = tuple(
            (operation_id, binding)
            for operation_id, binding in self._bindings.items()
            if (binding.snapshot_id == snapshot.snapshot_id
                and binding.action_key == action_key
                and binding.legal_bound))
        if not matches:
            return ()
        if len(matches) != 1:
            raise ValueError("accepted expansion action is ambiguous")
        operation_id, binding = matches[0]
        record = self.store.get(operation_id)
        previous = record.progress.state
        if accepted:
            if record.progress.state != OperationState.RESERVABLE:
                raise ValueError("expansion action is not reservable")
            record = self.store.transition(
                operation_id, OperationState.RESERVED, snapshot.snapshot_id,
                int(snapshot.turn))
            record = self.store.transition(
                operation_id, OperationState.ACTIVE, snapshot.snapshot_id,
                int(snapshot.turn))
            record = self.store.record_attempt(
                operation_id, snapshot.snapshot_id, int(snapshot.turn))
            disposition = "committed-awaiting-effect"
            update_reason = "accepted-action-is-not-yet-expansion-effect"
            candidate = self._candidates.get(operation_id)
            self._contexts[operation_id] = self._context(
                record, candidate, snapshot)
        else:
            update_reason = str(reason or "expansion-action-rejected")
            record = self.store.transition(
                operation_id, OperationState.BLOCKED, snapshot.snapshot_id,
                int(snapshot.turn), reason=update_reason)
            disposition = "blocked"
            candidate = self._candidates.get(operation_id)
            self._contexts[operation_id] = self._context(
                record, candidate, snapshot, update_reason)
        self._bindings.pop(operation_id, None)
        return (self._update(
            record, previous, disposition, update_reason, snapshot,
            None if accepted else binding),)
