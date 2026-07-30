"""Persistent shadow lifecycle for grounded research enabling operations."""

from dataclasses import dataclass

from ..events.schema import canonical_json_bytes
from ..pressure.resource_capacity import ResourceCapacityExtractor
from ..pressure.resource_ledger import ResourceReservationLedger
from ..pressure.resource_scheduler import BoundedExactScheduler
from .operation_store import OperationStore
from .operations import OperationState
from .research_operations import (
    ResearchEnablingOperationAssembler,
    ResearchOperationAssembly,
)


@dataclass(frozen=True)
class ResearchLifecycleUpdate:
    operation_id: str
    previous_state: str
    state: str
    disposition: str
    reason: str
    snapshot_id: str
    step_index: int
    next_action: object = None
    technology_ref: object = None
    downstream_operation_id: object = None
    dependency_ready: bool = False
    downstream_ready: bool = False
    replan_required: bool = False
    schedule: object = None
    reservation: object = None
    released_reservation: object = None

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
                    "research lifecycle {} is required".format(name))
        if (
                isinstance(self.step_index, bool)
                or not isinstance(self.step_index, int)
                or self.step_index < 0
        ):
            raise ValueError(
                "research lifecycle step is invalid")
        if (
                self.next_action is not None
                and not isinstance(self.next_action, dict)
        ):
            raise TypeError(
                "research next action must be an object or absent")
        for value, name in (
                (self.dependency_ready, "dependency readiness"),
                (self.downstream_ready, "downstream readiness"),
                (self.replan_required, "replan requirement")):
            if not isinstance(value, bool):
                raise TypeError(
                    "research {} must be boolean".format(name))


class ResearchOperationLifecycle:
    """Reserve one research slot, commit selection, and observe acquisition."""

    CONTROLLER_IDENTITY = (
        "freeciv-research-operation-lifecycle/1.0")

    def __init__(self, identity):
        if not isinstance(identity, str) or not identity:
            raise ValueError(
                "research lifecycle identity is required")
        self.identity = identity
        self.store = OperationStore(
            "research:{}".format(identity))
        self.ledger = ResourceReservationLedger(
            "research:{}".format(identity))
        self._assemblies = {}

    def assembly(self, operation_id):
        return self._assemblies.get(str(operation_id))

    @staticmethod
    def _action_key(action):
        return canonical_json_bytes(action).decode("utf-8")

    @staticmethod
    def _capacities(snapshot):
        return ResourceCapacityExtractor().extract(
            snapshot, action_budget=1).capacities

    def _reserve(self, assembly, snapshot, initial=False):
        request = (
            assembly.resource_request
            if initial else
            ResearchEnablingOperationAssembler
            .current_step_resource_request(
                assembly, snapshot))
        if request is None:
            return None, None, None
        existing = self.ledger.reservation(
            assembly.spec.operation_id)
        released = None
        if existing is not None and existing.active:
            released = self.ledger.release(
                assembly.spec.operation_id,
                "research-reservation-refreshed")
        schedule = BoundedExactScheduler(
            node_budget=128,
            time_budget_ms=20.0).schedule(
                (request,),
                self._capacities(snapshot),
                requirement_sets=(
                    (assembly.requirement_set,)
                    if initial else ()),
                premise_packets=(
                    dict(assembly.initial_premise_packets)
                    if initial else None))
        if assembly.spec.operation_id not in (
                schedule.selected_operation_ids):
            return schedule, None, released
        reservations = self.ledger.reserve_schedule(schedule)
        reservation = (
            reservations[0]
            if reservations else
            self.ledger.reservation(
                assembly.spec.operation_id))
        return schedule, reservation, released

    @staticmethod
    def _update(
            assembly, record, previous_state,
            disposition, reason, snapshot,
            readout=None, schedule=None,
            reservation=None, released=None):
        dependency_ready = bool(
            readout is not None
            and readout.dependency_ready)
        downstream_ready = bool(
            readout is not None
            and readout.downstream_ready)
        return ResearchLifecycleUpdate(
            operation_id=record.spec.operation_id,
            previous_state=previous_state.value,
            state=record.progress.state.value,
            disposition=disposition,
            reason=reason,
            snapshot_id=snapshot.snapshot_id,
            step_index=record.progress.current_step_index,
            next_action=(
                None if readout is None
                else readout.next_action),
            technology_ref=(
                None if readout is None
                else readout.technology_ref),
            downstream_operation_id=(
                assembly.intent.downstream_operation_id
                if downstream_ready else None),
            dependency_ready=dependency_ready,
            downstream_ready=downstream_ready,
            replan_required=bool(
                dependency_ready
                and not downstream_ready),
            schedule=schedule,
            reservation=reservation,
            released_reservation=released)

    def register(self, assembly, snapshot):
        if not isinstance(assembly, ResearchOperationAssembly):
            raise TypeError(
                "research lifecycle requires an assembly")
        operation_id = assembly.spec.operation_id
        if self.store.get(operation_id) is not None:
            return ()
        self._assemblies[operation_id] = assembly
        record = self.store.propose(
            assembly.spec,
            snapshot.snapshot_id,
            int(snapshot.turn))
        previous = record.progress.state
        if assembly.initial_step_index == 1:
            record = self.store.initialize_step(
                operation_id, 1,
                snapshot.snapshot_id,
                int(snapshot.turn))
            for state in (
                    OperationState.RESERVABLE,
                    OperationState.RESERVED,
                    OperationState.ACTIVE):
                record = self.store.transition(
                    operation_id, state,
                    snapshot.snapshot_id,
                    int(snapshot.turn))
            readout = ResearchEnablingOperationAssembler.readout(
                assembly, snapshot, 1)
            return (
                self._update(
                    assembly, record, previous,
                    "waiting",
                    "research-target-was-already-selected",
                    snapshot, readout=readout),)
        schedule, reservation, released = self._reserve(
            assembly, snapshot, initial=True)
        if reservation is None:
            reason = next((
                row.reason for row in getattr(
                    schedule, "entries", ())
                if row.operation_id == operation_id
            ), "research-resource-capacity-unavailable")
            record = self.store.transition(
                operation_id,
                OperationState.BLOCKED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=reason)
            return (
                self._update(
                    assembly, record, previous,
                    "blocked", reason, snapshot,
                    schedule=schedule,
                    released=released),)
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
        readout = ResearchEnablingOperationAssembler.readout(
            assembly, snapshot, 0)
        return (
            self._update(
                assembly, record, previous,
                "reserved",
                "grounded-research-selection-step-reserved",
                snapshot, readout=readout,
                schedule=schedule,
                reservation=reservation,
                released=released),)

    def commit_matching_action(
            self, snapshot, action,
            accepted, reason=None):
        if not isinstance(action, dict):
            return ()
        action_key = self._action_key(action)
        matches = []
        for record in self.store.nonterminal_records():
            assembly = self._assemblies.get(
                record.spec.operation_id)
            reservation = self.ledger.reservation(
                record.spec.operation_id)
            if (
                    assembly is None
                    or record.progress.current_step_index != 0
                    or record.progress.state not in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE)
                    or reservation is None
                    or not reservation.active
            ):
                continue
            if self._action_key(
                    assembly.selection_action()) == action_key:
                matches.append(record)
        if not matches:
            return ()
        record = sorted(
            matches,
            key=lambda row: (
                -row.progress.last_updated_turn,
                row.spec.operation_id))[0]
        assembly = self._assemblies[
            record.spec.operation_id]
        operation_id = record.spec.operation_id
        previous = record.progress.state
        readout = ResearchEnablingOperationAssembler.readout(
            assembly, snapshot, 0)
        if (
                accepted
                and readout.disposition not in (
                    "reservable", "target_satisfied")
        ):
            accepted = False
            reason = "commit-revalidation:{}".format(
                readout.reason)
        if not accepted:
            failure_reason = str(
                reason
                or "research-selection-action-not-accepted")
            record = self.store.transition(
                operation_id,
                OperationState.FAILED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=failure_reason)
            released = self.ledger.release(
                operation_id,
                "action-rejected:{}".format(
                    failure_reason))
            return (
                self._update(
                    assembly, record, previous,
                    "failed", failure_reason,
                    snapshot, readout=readout,
                    released=released),)
        if previous == OperationState.RESERVED:
            record = self.store.transition(
                operation_id,
                OperationState.ACTIVE,
                snapshot.snapshot_id,
                int(snapshot.turn))
        record = self.store.record_attempt(
            operation_id,
            snapshot.snapshot_id,
            int(snapshot.turn))
        self.ledger.commit(operation_id)
        released = self.ledger.release(
            operation_id,
            "research-selection-committed-await-authoritative-observation")
        return (
            self._update(
                assembly, record, previous,
                "step_committed",
                "engine-accepted-research-selection-step",
                snapshot, readout=readout,
                released=released),)

    def _finish(
            self, assembly, record, snapshot,
            state, disposition, reason,
            readout=None):
        previous = record.progress.state
        record = self.store.transition(
            record.spec.operation_id,
            state,
            snapshot.snapshot_id,
            int(snapshot.turn),
            reason=reason)
        reservation = self.ledger.reservation(
            record.spec.operation_id)
        released = (
            self.ledger.release(
                record.spec.operation_id,
                reason,
                expired=state == OperationState.EXPIRED)
            if reservation is not None and reservation.active
            else None)
        return self._update(
            assembly, record, previous,
            disposition, reason, snapshot,
            readout=readout,
            released=released)

    def observe(self, snapshot):
        updates = []
        for original in self.store.nonterminal_records():
            assembly = self._assemblies.get(
                original.spec.operation_id)
            if (
                    assembly is None
                    or original.progress.last_snapshot_id
                    == snapshot.snapshot_id
            ):
                continue
            if int(snapshot.turn) > original.spec.expiry_turn:
                updates.append(self._finish(
                    assembly, original, snapshot,
                    OperationState.EXPIRED,
                    "expired",
                    "research-completion-deadline-passed"))
                continue
            progress = original.progress
            readout = ResearchEnablingOperationAssembler.readout(
                assembly, snapshot,
                progress.current_step_index)
            if readout.disposition == "completed":
                updates.append(self._finish(
                    assembly, original, snapshot,
                    OperationState.COMPLETED,
                    "completed", readout.reason,
                    readout=readout))
                continue
            if readout.disposition == "abandoned":
                updates.append(self._finish(
                    assembly, original, snapshot,
                    OperationState.ABANDONED,
                    "abandoned", readout.reason,
                    readout=readout))
                continue
            if progress.state == OperationState.RESERVED:
                if readout.disposition == "target_satisfied":
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.ACTIVE,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                    record = self.store.advance_satisfied_step(
                        original.spec.operation_id,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                    reservation = self.ledger.reservation(
                        original.spec.operation_id)
                    released = (
                        self.ledger.release(
                            original.spec.operation_id,
                            "research-target-observed")
                        if reservation is not None
                        and reservation.active else None)
                    next_readout = (
                        ResearchEnablingOperationAssembler
                        .readout(assembly, snapshot, 1))
                    updates.append(self._update(
                        assembly, record,
                        progress.state,
                        "waiting",
                        "research-target-observed-awaiting-technology",
                        snapshot,
                        readout=next_readout,
                        released=released))
                    continue
                if readout.disposition != "reservable":
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id,
                        int(snapshot.turn),
                        reason=readout.reason)
                    released = self.ledger.release(
                        original.spec.operation_id,
                        readout.reason)
                    updates.append(self._update(
                        assembly, record,
                        progress.state,
                        "blocked", readout.reason,
                        snapshot, readout=readout,
                        released=released))
                    continue
                schedule, reservation, released = self._reserve(
                    assembly, snapshot)
                if reservation is None:
                    reason = next((
                        row.reason for row in getattr(
                            schedule, "entries", ())
                        if row.operation_id
                        == original.spec.operation_id
                    ), "research-resource-capacity-unavailable")
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id,
                        int(snapshot.turn),
                        reason=reason)
                    updates.append(self._update(
                        assembly, record,
                        progress.state,
                        "blocked", reason, snapshot,
                        readout=readout,
                        schedule=schedule,
                        released=released))
                    continue
                record = self.store.record_observation(
                    original.spec.operation_id,
                    snapshot.snapshot_id,
                    int(snapshot.turn))
                updates.append(self._update(
                    assembly, record,
                    progress.state,
                    "step_revalidated",
                    "research-selection-step-grounded-and-reserved",
                    snapshot, readout=readout,
                    schedule=schedule,
                    reservation=reservation,
                    released=released))
                continue
            if (
                    progress.current_step_index == 0
                    and progress.state == OperationState.ACTIVE
                    and progress.attempt_count > 0
            ):
                if readout.disposition != "target_satisfied":
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id,
                        int(snapshot.turn),
                        reason=(
                            "accepted-research-action-not-observed"))
                    updates.append(self._update(
                        assembly, record,
                        progress.state,
                        "blocked",
                        "accepted-research-action-not-observed",
                        snapshot, readout=readout))
                    continue
                record = self.store.advance_step(
                    original.spec.operation_id,
                    snapshot.snapshot_id,
                    int(snapshot.turn))
                next_readout = (
                    ResearchEnablingOperationAssembler
                    .readout(assembly, snapshot, 1))
                updates.append(self._update(
                    assembly, record, progress.state,
                    "waiting",
                    "research-target-observed-awaiting-technology",
                    snapshot, readout=next_readout))
                continue
            if readout.disposition == "waiting":
                if progress.state == OperationState.BLOCKED:
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.ACTIVE,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                    disposition = "repaired"
                    reason = "research-wait-recovered"
                else:
                    record = self.store.record_observation(
                        original.spec.operation_id,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                    disposition = "waiting"
                    reason = readout.reason
                updates.append(self._update(
                    assembly, record,
                    progress.state,
                    disposition, reason,
                    snapshot, readout=readout))
                continue
            if readout.disposition == "blocked":
                if progress.state == OperationState.BLOCKED:
                    record = self.store.record_observation(
                        original.spec.operation_id,
                        snapshot.snapshot_id,
                        int(snapshot.turn))
                else:
                    record = self.store.transition(
                        original.spec.operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id,
                        int(snapshot.turn),
                        reason=readout.reason)
                updates.append(self._update(
                    assembly, record,
                    progress.state,
                    "blocked", readout.reason,
                    snapshot, readout=readout))
        return tuple(updates)
