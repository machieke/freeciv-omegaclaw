"""Persistent shadow lifecycle for grounded founder/ferry operations."""

from dataclasses import dataclass
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.resource_capacity import (
    ResourceCapacityExtractor,
)
from ..pressure.resource_ledger import (
    ResourceReservationLedger,
)
from ..pressure.resource_scheduler import (
    BoundedExactScheduler,
)
from .operation_store import OperationStore, OperationStoreError
from .operations import (
    OperationState,
    TERMINAL_OPERATION_STATES,
)
from .transport_operations import (
    FounderTransportIntent,
    FounderTransportOperationAssembler,
    FounderTransportOperationAssembly,
)


TRANSPORT_LIFECYCLE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TransportLifecycleUpdate:
    operation_id: str
    previous_state: str
    state: str
    disposition: str
    reason: str
    snapshot_id: str
    step_index: int
    phase: str
    next_action: object = None
    schedule: object = None
    reservation: object = None
    released_reservation: object = None

    def __post_init__(self):
        for value, name in (
                (self.operation_id,
                 "operation ID"),
                (self.previous_state,
                 "previous state"),
                (self.state, "state"),
                (self.disposition,
                 "disposition"),
                (self.reason, "reason"),
                (self.snapshot_id,
                 "snapshot ID"),
                (self.phase, "phase")):
            if not isinstance(
                    value, str
                    ) or not value:
                raise ValueError(
                    "transport lifecycle {} is required"
                    .format(name))
        if (
                isinstance(self.step_index, bool)
                or not isinstance(
                    self.step_index, int)
                or self.step_index < 0
        ):
            raise ValueError(
                "transport lifecycle step index is invalid")
        if (
                self.next_action is not None
                and not isinstance(
                    self.next_action, dict)
        ):
            raise TypeError(
                "transport lifecycle next action must be an object or absent")


@dataclass(frozen=True)
class SettlementRetentionResult:
    operation_id: str
    city_id: int
    settlement_tile_id: int
    completion_turn: int
    observation_turn: int
    horizon_turns: int
    retained: bool
    reason: str

    def __post_init__(self):
        if not isinstance(
                self.operation_id, str
                ) or not self.operation_id:
            raise ValueError(
                "retention result requires an operation ID")
        for value, name in (
                (self.city_id, "city ID"),
                (self.settlement_tile_id,
                 "settlement tile"),
                (self.completion_turn,
                 "completion turn"),
                (self.observation_turn,
                 "observation turn"),
                (self.horizon_turns,
                 "horizon")):
            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
            ):
                raise ValueError(
                    "retention {} must be non-negative"
                    .format(name))
        if not isinstance(
                self.retained, bool):
            raise TypeError(
                "retention status must be boolean")
        if not isinstance(
                self.reason, str
                ) or not self.reason:
            raise ValueError(
                "retention reason is required")


@dataclass(frozen=True)
class TransportRepairDecision:
    disposition: str
    reason: str
    original_operation_id: str
    replacement_operation_id: object = None
    partner_switched: bool = False
    registration_updates: tuple = ()

    def __post_init__(self):
        if self.disposition not in (
                "replaced", "abstain"):
            raise ValueError(
                "unknown transport repair disposition")
        if not isinstance(
                self.reason, str
                ) or not self.reason:
            raise ValueError(
                "transport repair reason is required")
        if not isinstance(
                self.original_operation_id,
                str
                ) or not self.original_operation_id:
            raise ValueError(
                "transport repair requires an original operation ID")
        if (
                self.disposition == "replaced"
                and (
                    not isinstance(
                        self.replacement_operation_id,
                        str)
                    or not self
                    .replacement_operation_id)
        ):
            raise ValueError(
                "transport replacement requires a new operation ID")
        if (
                self.disposition == "abstain"
                and self.replacement_operation_id
                    is not None
        ):
            raise ValueError(
                "abstaining repair cannot identify a replacement")
        if not isinstance(
                self.partner_switched, bool):
            raise TypeError(
                "partner switch status must be boolean")
        object.__setattr__(
            self, "registration_updates",
            tuple(
                self.registration_updates))


class SettlementRetentionTracker:
    """Resolve fixed-horizon retention from authoritative city identity."""

    def __init__(self, horizon_turns=10):
        if (
                isinstance(horizon_turns, bool)
                or not isinstance(
                    horizon_turns, int)
                or horizon_turns < 1
        ):
            raise ValueError(
                "retention horizon must be positive")
        self.horizon_turns = (
            horizon_turns)
        self._pending = {}

    def register_completion(
            self, assembly, snapshot):
        if not isinstance(
                assembly,
                FounderTransportOperationAssembly):
            raise TypeError(
                "retention tracking requires a transport assembly")
        city = next((
            row for row in snapshot.cities
            if (
                row.tile
                    == assembly.intent
                    .settlement_tile_id
                and row.owner
                    == snapshot.player_id)
        ), None)
        if city is None:
            raise ValueError(
                "settlement completion requires an authoritative own city")
        self._pending[
            assembly.spec.operation_id] = {
                "city_id": city.city_id,
                "completion_turn":
                    int(snapshot.turn),
                "owner_id":
                    int(snapshot.player_id),
                "settlement_tile_id":
                    assembly.intent
                    .settlement_tile_id,
            }

    def observe(self, snapshot):
        results = []
        for operation_id in sorted(
                tuple(self._pending)):
            pending = self._pending[
                operation_id]
            due = (
                pending[
                    "completion_turn"]
                + self.horizon_turns)
            if int(snapshot.turn) < due:
                continue
            city = snapshot.city(
                pending["city_id"])
            retained = bool(
                city is not None
                and city.owner
                    == pending["owner_id"]
                and city.tile
                    == pending[
                        "settlement_tile_id"])
            results.append(
                SettlementRetentionResult(
                    operation_id=(
                        operation_id),
                    city_id=pending[
                        "city_id"],
                    settlement_tile_id=(
                        pending[
                            "settlement_tile_id"]),
                    completion_turn=(
                        pending[
                            "completion_turn"]),
                    observation_turn=int(
                        snapshot.turn),
                    horizon_turns=(
                        self.horizon_turns),
                    retained=retained,
                    reason=(
                        "city-retained-at-settlement"
                        if retained
                        else
                        "city-identity-or-ownership-not-retained")))
            del self._pending[
                operation_id]
        return tuple(results)

    def to_dict(self):
        return {
            "horizon_turns": self.horizon_turns,
            "pending": [
                {
                    "city_id": value["city_id"],
                    "completion_turn": value["completion_turn"],
                    "operation_id": operation_id,
                    "owner_id": value["owner_id"],
                    "settlement_tile_id": value["settlement_tile_id"],
                }
                for operation_id, value in sorted(self._pending.items())
            ],
            "tracker_identity":
                "freeciv-settlement-retention-tracker/1.0",
        }

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise TypeError("settlement retention state must be an object")
        if value.get("tracker_identity") != (
                "freeciv-settlement-retention-tracker/1.0"):
            raise ValueError("settlement retention identity mismatch")
        try:
            tracker = cls(value["horizon_turns"])
            pending = tuple(value["pending"])
        except KeyError as error:
            raise ValueError(
                "settlement retention field is missing: {}".format(
                    error.args[0]))
        for row in pending:
            if not isinstance(row, dict):
                raise TypeError(
                    "settlement retention entry must be an object")
            try:
                operation_id = row["operation_id"]
                values = {
                    name: row[name]
                    for name in (
                        "city_id", "completion_turn", "owner_id",
                        "settlement_tile_id")
                }
            except KeyError as error:
                raise ValueError(
                    "settlement retention field is missing: {}".format(
                        error.args[0]))
            if not isinstance(operation_id, str) or not operation_id:
                raise ValueError(
                    "settlement retention operation ID is required")
            if operation_id in tracker._pending:
                raise ValueError(
                    "duplicate settlement retention operation")
            if any(
                    isinstance(item, bool)
                    or not isinstance(item, int)
                    or item < 0
                    for item in values.values()):
                raise ValueError(
                    "settlement retention values must be non-negative integers")
            tracker._pending[operation_id] = values
        return tracker


class FounderTransportOperationLifecycle:
    """Persist, reserve, revalidate, and resolve transport steps."""

    CONTROLLER_IDENTITY = (
        "freeciv-founder-transport-lifecycle/1.0")

    def __init__(
            self, identity,
            ruleset_ir,
            operation_store=None,
            assemblies=(),
            repair_counts=(),
            retention=None):
        if not isinstance(
                identity, str
                ) or not identity:
            raise ValueError(
                "transport lifecycle identity is required")
        self.identity = identity
        self.ruleset_ir = ruleset_ir
        persistence_identity = (
            "transport:{}".format(
                identity))
        if operation_store is None:
            operation_store = OperationStore(
                persistence_identity)
        if not isinstance(
                operation_store,
                OperationStore):
            raise TypeError(
                "transport lifecycle requires OperationStore")
        if operation_store.persistence_identity != (
                persistence_identity):
            raise ValueError(
                "transport operation persistence identity mismatch")
        self.store = operation_store
        self.ledger = (
            ResourceReservationLedger(
                persistence_identity))
        if retention is None:
            retention = SettlementRetentionTracker()
        if not isinstance(
                retention,
                SettlementRetentionTracker):
            raise TypeError(
                "transport lifecycle requires retention tracker")
        self.retention = retention
        assembly_rows = tuple(assemblies)
        if any(
                not isinstance(
                    row,
                    FounderTransportOperationAssembly)
                for row in assembly_rows):
            raise TypeError(
                "transport lifecycle assemblies have the wrong type")
        self._assemblies = {
            row.spec.operation_id: row
            for row in assembly_rows}
        if len(self._assemblies) != len(assembly_rows):
            raise ValueError(
                "transport lifecycle assemblies contain duplicate IDs")
        repair_rows = tuple(repair_counts)
        if any(
                not isinstance(operation_id, str)
                or not operation_id
                or isinstance(count, bool)
                or not isinstance(count, int)
                or not 0 <= count <= 1
                for operation_id, count in repair_rows):
            raise ValueError(
                "transport lifecycle repair counts are invalid")
        self._repair_counts = dict(repair_rows)
        if len(self._repair_counts) != len(repair_rows):
            raise ValueError(
                "transport lifecycle repair counts contain duplicate IDs")
        if not self.store.quarantined:
            record_by_id = {
                row.spec.operation_id: row
                for row in self.store.records()}
            if set(record_by_id) != set(self._assemblies):
                raise ValueError(
                    "transport operation records and assemblies disagree")
            if any(
                    record_by_id[operation_id].spec.spec_digest
                        != assembly.spec.spec_digest
                    for operation_id, assembly
                    in self._assemblies.items()):
                raise ValueError(
                    "transport operation record and assembly digest mismatch")
            if not set(self._repair_counts).issubset(record_by_id):
                raise ValueError(
                    "transport repair count lacks an operation")

    @property
    def quarantined(self):
        return self.store.quarantined

    def to_dict(self, include_digest=True):
        value = {
            "assemblies": [
                self._assemblies[key].to_dict()
                for key in sorted(self._assemblies)],
            "controller_identity": self.CONTROLLER_IDENTITY,
            "operation_store": self.store.to_dict(),
            "persistence_identity": self.store.persistence_identity,
            "policy_authority": False,
            "repair_counts": dict(sorted(self._repair_counts.items())),
            "retention": self.retention.to_dict(),
            "schema_version": TRANSPORT_LIFECYCLE_SCHEMA_VERSION,
            "shadow_only": True,
        }
        if include_digest:
            value["lifecycle_digest"] = structural_hash(value)
        return value

    def save(self, path):
        if self.quarantined:
            raise OperationStoreError(
                "transport lifecycle is quarantined: {}".format(
                    self.store.quarantine_reason))
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".transport-lifecycle-",
            suffix=".json",
            dir=directory or None)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(self.to_dict()))
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def from_dict(cls, value, identity, ruleset_ir):
        if not isinstance(value, dict):
            raise TypeError("transport lifecycle root is not an object")
        if value.get("schema_version") != TRANSPORT_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported transport lifecycle schema")
        if value.get("controller_identity") != cls.CONTROLLER_IDENTITY:
            raise ValueError("transport lifecycle controller mismatch")
        expected_identity = "transport:{}".format(identity)
        if value.get("persistence_identity") != expected_identity:
            raise ValueError("transport lifecycle persistence mismatch")
        digest = value.get("lifecycle_digest")
        unsigned = dict(value)
        unsigned.pop("lifecycle_digest", None)
        if not isinstance(digest, str) or digest != structural_hash(unsigned):
            raise ValueError("transport lifecycle digest mismatch")
        repair_counts = value.get("repair_counts", {})
        if not isinstance(repair_counts, dict):
            raise TypeError("transport repair counts must be an object")
        if value.get("shadow_only") is not True or value.get(
                "policy_authority") is not False:
            raise ValueError("transport lifecycle authority boundary changed")
        return cls(
            identity,
            ruleset_ir,
            operation_store=OperationStore.from_dict(
                value["operation_store"], expected_identity),
            assemblies=tuple(
                FounderTransportOperationAssembly.from_dict(row)
                for row in value.get("assemblies", ())),
            repair_counts=tuple(sorted(repair_counts.items())),
            retention=SettlementRetentionTracker.from_dict(
                value["retention"]),
        )

    @classmethod
    def load(cls, path, identity, ruleset_ir):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return cls(identity, ruleset_ir)
        try:
            with open(path, encoding="utf-8") as stream:
                value = json.load(stream)
            return cls.from_dict(value, identity, ruleset_ir)
        except (
                OSError, TypeError, ValueError, KeyError,
                json.JSONDecodeError) as error:
            persistence_identity = "transport:{}".format(identity)
            return cls(
                identity,
                ruleset_ir,
                operation_store=OperationStore(
                    persistence_identity,
                    quarantine_reason="load-failed:{}".format(
                        type(error).__name__)))

    def assembly(self, operation_id):
        return self._assemblies.get(
            str(operation_id))

    def recover(self, snapshot):
        """Rebuild only exact current reservations after a clean restart."""
        if self.quarantined:
            raise OperationStoreError(
                "transport lifecycle is quarantined: {}".format(
                    self.store.quarantine_reason))
        updates = []
        for record in self.store.nonterminal_records():
            if record.progress.last_snapshot_id != snapshot.snapshot_id:
                continue
            assembly = self._assemblies[record.spec.operation_id]
            if record.progress.state == OperationState.RESERVED:
                readout, request = (
                    FounderTransportOperationAssembler
                    .current_step_resource_request(
                        assembly,
                        snapshot,
                        record.progress.current_step_index))
                if request is None or readout.disposition != "reservable":
                    raise OperationStoreError(
                        "transport reservation cannot be reconstructed")
                _, schedule, reservation, _ = self._reserve(
                    assembly,
                    snapshot,
                    record.progress.current_step_index,
                    request=request)
                if reservation is None:
                    raise OperationStoreError(
                        "transport reservation reconstruction failed closed")
                updates.append(self._update(
                    record,
                    record.progress.state,
                    "reservation_reconstructed",
                    "exact-current-transport-reservation-reconstructed",
                    snapshot,
                    phase=readout.phase,
                    next_action=readout.next_action,
                    schedule=schedule,
                    reservation=reservation))
            elif record.progress.state in (
                    OperationState.PROPOSED,
                    OperationState.RESERVABLE):
                raise OperationStoreError(
                    "transport lifecycle persisted an incomplete transition")
        updates.extend(self.observe(snapshot))
        return tuple(updates)

    @staticmethod
    def _action_key(action):
        return (
            canonical_json_bytes(
                action)
            .decode("utf-8"))

    @staticmethod
    def _phase(record):
        predicate = (
            record.spec.steps[
                record.progress
                .current_step_index]
            .completion_predicate_id)
        return predicate.split(
            ":", 1)[-1]

    @classmethod
    def _update(
            cls, record, previous_state,
            disposition, reason,
            snapshot, phase=None,
            next_action=None,
            schedule=None,
            reservation=None,
            released_reservation=None):
        return TransportLifecycleUpdate(
            operation_id=(
                record.spec.operation_id),
            previous_state=(
                previous_state.value),
            state=(
                record.progress
                .state.value),
            disposition=disposition,
            reason=reason,
            snapshot_id=(
                snapshot.snapshot_id),
            step_index=(
                record.progress
                .current_step_index),
            phase=(
                phase
                or cls._phase(record)),
            next_action=(
                next_action),
            schedule=schedule,
            reservation=reservation,
            released_reservation=(
                released_reservation))

    def _capacities(self, snapshot):
        return (
            ResourceCapacityExtractor()
            .extract(
                snapshot,
                ruleset_ir=(
                    self.ruleset_ir),
                action_budget=1)
            .capacities)

    def _reserve(
            self, assembly,
            snapshot, step_index,
            request=None):
        readout = None
        if request is None:
            readout, request = (
                FounderTransportOperationAssembler
                .current_step_resource_request(
                    assembly,
                    snapshot,
                    step_index))
        if request is None:
            return (
                readout, None,
                None, None)
        existing = self.ledger.reservation(
            assembly.spec.operation_id)
        released = None
        if (
                existing is not None
                and existing.active
        ):
            released = self.ledger.release(
                assembly.spec.operation_id,
                "reservation-refreshed-from-new-snapshot")
        schedule = (
            BoundedExactScheduler(
                node_budget=256,
                time_budget_ms=20.0)
            .schedule(
                (request,),
                self._capacities(
                    snapshot),
                requirement_sets=(
                    assembly
                    .requirement_set,),
                premise_packets=dict(
                    assembly
                    .initial_premise_packets)))
        if assembly.spec.operation_id not in (
                schedule
                .selected_operation_ids):
            return (
                readout, schedule,
                None, released)
        try:
            reservations = (
                self.ledger
                .reserve_schedule(
                    schedule))
        except ValueError:
            return (
                readout, schedule,
                None, released)
        reservation = (
            reservations[0]
            if reservations else
            self.ledger.reservation(
                assembly.spec
                .operation_id))
        return (
            readout, schedule,
            reservation, released)

    def register(
            self, assembly, snapshot):
        if not isinstance(
                assembly,
                FounderTransportOperationAssembly):
            raise TypeError(
                "transport lifecycle requires an assembly")
        operation_id = (
            assembly.spec.operation_id)
        if self.store.get(
                operation_id) is not None:
            return ()
        record = self.store.propose(
            assembly.spec,
            snapshot.snapshot_id,
            int(snapshot.turn))
        if assembly.initial_step_index:
            record = self.store.initialize_step(
                operation_id,
                assembly.initial_step_index,
                snapshot.snapshot_id,
                int(snapshot.turn))
        self._assemblies[
            operation_id] = assembly
        (
            readout,
            schedule,
            reservation,
            released,
        ) = self._reserve(
            assembly, snapshot,
            record.progress
            .current_step_index,
            request=(
                assembly
                .resource_request))
        previous = (
            record.progress.state)
        if reservation is None:
            reason = (
                None
                if schedule is None
                else next(
                    (
                        row.reason
                        for row in
                        schedule.entries
                        if (
                            row.operation_id
                                == operation_id
                            and not row.selected)
                    ),
                    None))
            reason = (
                reason
                or "current-step-resource-capacity-unavailable")
            record = self.store.transition(
                operation_id,
                OperationState.BLOCKED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=reason)
            return (
                self._update(
                    record, previous,
                    "blocked", reason,
                    snapshot,
                    phase=(
                        assembly
                        .initial_readout
                        .phase),
                    schedule=schedule,
                    released_reservation=(
                        released)),)
        record = self.store.transition(
            operation_id,
            OperationState.RESERVABLE,
            snapshot.snapshot_id,
            int(snapshot.turn))
        record = self.store.transition(
            operation_id,
            OperationState.RESERVED,
            snapshot.snapshot_id,
            int(snapshot.turn))
        return (
            self._update(
                record, previous,
                "reserved",
                "grounded-current-transport-step-reserved",
                snapshot,
                phase=(
                    assembly
                    .initial_readout
                    .phase),
                next_action=(
                    assembly
                    .initial_readout
                    .next_action),
                schedule=schedule,
                reservation=reservation,
                released_reservation=(
                    released)),)

    def commit_matching_action(
            self, snapshot, action,
            accepted, reason=None):
        if not isinstance(
                action, dict):
            return ()
        action_key = self._action_key(
            action)
        matches = []
        for record in (
                self.store
                .nonterminal_records()):
            if record.progress.state not in (
                    OperationState.RESERVED,
                    OperationState.ACTIVE):
                continue
            assembly = self._assemblies.get(
                record.spec.operation_id)
            reservation = (
                self.ledger.reservation(
                    record.spec
                    .operation_id))
            if (
                    assembly is None
                    or reservation is None
                    or not reservation.active
            ):
                continue
            readout = (
                FounderTransportOperationAssembler
                .readout(
                    assembly, snapshot,
                    record.progress
                    .current_step_index))
            if (
                    readout.disposition
                        == "reservable"
                    and self._action_key(
                        readout.next_action)
                        == action_key
            ):
                matches.append((
                    record, readout,
                    reservation))
        if not matches:
            return ()
        record, readout, reservation = (
            sorted(
                matches,
                key=lambda row: (
                    -row[0].progress
                    .last_updated_turn,
                    row[0].spec
                    .operation_id))[0])
        operation_id = (
            record.spec.operation_id)
        previous = (
            record.progress.state)
        (
            current_readout,
            request,
        ) = (
            FounderTransportOperationAssembler
            .current_step_resource_request(
                self._assemblies[
                    operation_id],
                snapshot,
                record.progress
                .current_step_index))
        exact_reservation = bool(
            request is not None
            and reservation.snapshot_id
                == snapshot.snapshot_id
            and reservation.claims
                == request.claims)
        if (
                not accepted
                or current_readout
                    .disposition
                    != "reservable"
                or not exact_reservation
        ):
            failure_reason = (
                str(
                    reason
                    or "current-action-rejected")
                if not accepted
                else
                "transport-commit-revalidation-failed")
            record = self.store.transition(
                operation_id,
                OperationState.FAILED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=(
                    failure_reason))
            released = self.ledger.release(
                operation_id,
                failure_reason)
            return (
                self._update(
                    record, previous,
                    "failed",
                    failure_reason,
                    snapshot,
                    phase=readout.phase,
                    next_action=action,
                    released_reservation=(
                        released)),)
        if previous == (
                OperationState.RESERVED):
            record = self.store.transition(
                operation_id,
                OperationState.ACTIVE,
                snapshot.snapshot_id,
                int(snapshot.turn))
        record = self.store.record_attempt(
            operation_id,
            snapshot.snapshot_id,
            int(snapshot.turn))
        self.ledger.commit(
            operation_id)
        released = self.ledger.release(
            operation_id,
            "transport-step-{}-committed-reestimate-required"
            .format(
                record.progress
                .current_step_index))
        return (
            self._update(
                record, previous,
                "step_committed",
                "engine-accepted-current-transport-step",
                snapshot,
                phase=readout.phase,
                next_action=action,
                released_reservation=(
                    released)),)

    def repair_blocked(
            self, operation_id,
            snapshot,
            replacement_intent,
            ruleset_digest):
        """Adopt at most one fully grounded, margin-improving replacement."""
        operation_id = str(
            operation_id)
        record = self.store.get(
            operation_id)
        original = self._assemblies.get(
            operation_id)
        if (
                record is None
                or original is None
                or record.progress.state
                    != OperationState.BLOCKED
        ):
            return TransportRepairDecision(
                "abstain",
                "only-blocked-transport-operation-can-repair",
                operation_id)
        if self._repair_counts.get(
                operation_id, 0) >= 1:
            return TransportRepairDecision(
                "abstain",
                "transport-repair-budget-exhausted",
                operation_id)
        if not isinstance(
                replacement_intent,
                FounderTransportIntent):
            raise TypeError(
                "transport repair requires a replacement intent")
        if (
                replacement_intent
                    .founder_unit_id
                    != original.intent
                    .founder_unit_id
                or replacement_intent
                    .settlement_tile_id
                    != original.intent
                    .settlement_tile_id
        ):
            return TransportRepairDecision(
                "abstain",
                "transport-repair-cannot-change-founder-or-settlement",
                operation_id)
        changed = any(
            getattr(
                replacement_intent,
                name)
            != getattr(
                original.intent,
                name)
            for name in (
                "ferry_unit_id",
                "pickup_tile_id",
                "landing_carrier_tile_id",
                "landing_tile_id"))
        if not changed:
            return TransportRepairDecision(
                "abstain",
                "transport-repair-must-change-corridor-or-ferry",
                operation_id)
        decision = (
            FounderTransportOperationAssembler()
            .assemble(
                snapshot,
                self.ruleset_ir,
                ruleset_digest,
                replacement_intent,
                goal_ids=(
                    original.spec
                    .goal_ids),
                replacement_margin=(
                    original.spec
                    .replacement_margin)))
        if decision.disposition != (
                "assembled"):
            return TransportRepairDecision(
                "abstain",
                "replacement-not-grounded:{}".format(
                    decision.reason),
                operation_id)
        replacement = (
            decision.assembly)
        minimum_bid = (
            original.resource_request.bid
            + original.spec
            .replacement_margin)
        if replacement.resource_request.bid < (
                minimum_bid):
            return TransportRepairDecision(
                "abstain",
                "replacement-bid-below-explicit-margin",
                operation_id)
        (
            _,
            _,
            preflight_reservation,
            _,
        ) = self._reserve(
            replacement,
            snapshot,
            replacement
            .initial_step_index,
            request=(
                replacement
                .resource_request))
        if preflight_reservation is None:
            return TransportRepairDecision(
                "abstain",
                "replacement-resource-preflight-failed",
                operation_id)
        self.ledger.release(
            replacement.spec.operation_id,
            "replacement-resource-preflight-complete")
        reservation = self.ledger.reservation(
            operation_id)
        if (
                reservation is not None
                and reservation.active
        ):
            self.ledger.release(
                operation_id,
                "bounded-transport-replacement-adopted")
        self.store.transition(
            operation_id,
            OperationState.ABANDONED,
            snapshot.snapshot_id,
            int(snapshot.turn),
            reason=(
                "bounded-replacement:{}".format(
                    replacement.spec
                    .operation_id)))
        self._repair_counts[
            operation_id] = 1
        registration = self.register(
            replacement, snapshot)
        if (
                not registration
                or registration[-1]
                    .state != "reserved"
        ):
            return TransportRepairDecision(
                "abstain",
                "replacement-registration-failed-closed",
                operation_id)
        return TransportRepairDecision(
            "replaced",
            "grounded-replacement-clears-explicit-margin",
            operation_id,
            replacement_operation_id=(
                replacement.spec
                .operation_id),
            partner_switched=(
                replacement.intent
                .ferry_unit_id
                != original.intent
                .ferry_unit_id),
            registration_updates=(
                registration))

    def _finish(
            self, record, snapshot,
            state, disposition,
            reason, phase):
        previous = (
            record.progress.state)
        record = self.store.transition(
            record.spec.operation_id,
            state,
            snapshot.snapshot_id,
            int(snapshot.turn),
            reason=reason)
        reservation = (
            self.ledger.reservation(
                record.spec.operation_id))
        released = (
            self.ledger.release(
                record.spec.operation_id,
                reason,
                expired=(
                    state
                    == OperationState.EXPIRED))
            if (
                reservation is not None
                and reservation.active)
            else None)
        if (
                state
                    == OperationState.COMPLETED
                and reason
                    == "settlement-created"
        ):
            self.retention.register_completion(
                self._assemblies[
                    record.spec
                    .operation_id],
                snapshot)
        return self._update(
            record, previous,
            disposition, reason,
            snapshot,
            phase=phase,
            released_reservation=(
                released))

    def observe(self, snapshot):
        updates = []
        for original in (
                self.store
                .nonterminal_records()):
            if original.progress.last_snapshot_id == (
                    snapshot.snapshot_id):
                continue
            operation_id = (
                original.spec.operation_id)
            assembly = self._assemblies.get(
                operation_id)
            if assembly is None:
                continue
            if int(snapshot.turn) > (
                    original.spec
                    .expiry_turn):
                updates.append(
                    self._finish(
                        original, snapshot,
                        OperationState.EXPIRED,
                        "expired",
                        "operation-deadline-passed",
                        self._phase(original)))
                continue
            record = original
            while record.progress.state not in (
                    TERMINAL_OPERATION_STATES):
                step_index = (
                    record.progress
                    .current_step_index)
                readout = (
                    FounderTransportOperationAssembler
                    .readout(
                        assembly, snapshot,
                        step_index))
                if readout.disposition == (
                        "completed"):
                    updates.append(
                        self._finish(
                            record, snapshot,
                            OperationState.COMPLETED,
                            "completed",
                            readout.reason,
                            readout.phase))
                    break
                if readout.disposition == (
                        "abandoned"):
                    updates.append(
                        self._finish(
                            record, snapshot,
                            OperationState.ABANDONED,
                            "abandoned",
                            readout.reason,
                            readout.phase))
                    break
                if readout.disposition == (
                        "step_complete"):
                    previous = (
                        record.progress.state)
                    reservation = (
                        self.ledger.reservation(
                            operation_id))
                    released = (
                        self.ledger.release(
                            operation_id,
                            "transport-step-predicate-satisfied")
                        if (
                            reservation is not None
                            and reservation.active)
                        else None)
                    record = (
                        self.store
                        .advance_satisfied_step(
                            operation_id,
                            snapshot
                            .snapshot_id,
                            int(snapshot.turn)))
                    updates.append(
                        self._update(
                            record, previous,
                            "step_completed",
                            readout.reason,
                            snapshot,
                            phase=(
                                readout.phase),
                            released_reservation=(
                                released)))
                    if record.progress.state in (
                            TERMINAL_OPERATION_STATES):
                        break
                    continue
                if readout.disposition == (
                        "blocked"):
                    previous = (
                        record.progress.state)
                    if previous != (
                            OperationState.BLOCKED):
                        record = self.store.transition(
                            operation_id,
                            OperationState.BLOCKED,
                            snapshot.snapshot_id,
                            int(snapshot.turn),
                            reason=(
                                readout.reason))
                    reservation = (
                        self.ledger.reservation(
                            operation_id))
                    released = (
                        self.ledger.release(
                            operation_id,
                            readout.reason)
                        if (
                            reservation is not None
                            and reservation.active)
                        else None)
                    updates.append(
                        self._update(
                            record, previous,
                            "blocked",
                            readout.reason,
                            snapshot,
                            phase=(
                                readout.phase),
                            released_reservation=(
                                released)))
                    break

                previous = (
                    record.progress.state)
                repaired = (
                    previous
                    == OperationState.BLOCKED)
                if repaired:
                    record = self.store.transition(
                        operation_id,
                        OperationState.RESERVABLE,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                    record = self.store.transition(
                        operation_id,
                        OperationState.RESERVED,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                (
                    current_readout,
                    schedule,
                    reservation,
                    refreshed,
                ) = self._reserve(
                    assembly, snapshot,
                    step_index)
                if reservation is None:
                    reason = (
                        None
                        if schedule is None
                        else next(
                            (
                                row.reason
                                for row in
                                schedule.entries
                                if (
                                    row.operation_id
                                        == operation_id
                                    and not row.selected)
                            ),
                            None))
                    reason = (
                        reason
                        or "current-step-resource-capacity-unavailable")
                    if record.progress.state != (
                            OperationState.BLOCKED):
                        record = self.store.transition(
                            operation_id,
                            OperationState.BLOCKED,
                            snapshot.snapshot_id,
                            int(snapshot.turn),
                            reason=reason)
                    updates.append(
                        self._update(
                            record, previous,
                            "blocked", reason,
                            snapshot,
                            phase=(
                                readout.phase),
                            schedule=schedule,
                            released_reservation=(
                                refreshed)))
                    break
                updates.append(
                    self._update(
                        record, previous,
                        (
                            "repaired"
                            if repaired
                            else
                            "step_reestimated"),
                        (
                            "blocked-step-repaired"
                            if repaired
                            else
                            "next-transport-step-grounded-and-reserved"),
                        snapshot,
                        phase=(
                            current_readout
                            .phase),
                        next_action=(
                            current_readout
                            .next_action),
                        schedule=schedule,
                        reservation=(
                            reservation),
                        released_reservation=(
                            refreshed)))
                break
        return tuple(updates)
