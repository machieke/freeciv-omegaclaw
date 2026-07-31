"""Shadow lifecycle for grounded, multi-step combat operations."""

from dataclasses import dataclass

from ..events.schema import canonical_json_bytes
from ..pressure.resource_capacity import (
    ResourceCapacityExtractor,
)
from ..pressure.resource_ledger import (
    ResourceReservationLedger,
)
from ..pressure.resource_scheduler import (
    BoundedExactScheduler,
    OperationResourceRequest,
    _feasible,
)
from .combat_operations import (
    CombatOperationAssembler,
    CombatOperationAssembly,
    combat_target_capacities,
)
from .operation_store import (
    OperationStore,
)
from .operations import (
    OperationState,
)


@dataclass(frozen=True)
class CombatLifecycleUpdate:
    """One attributable lifecycle decision from an authoritative snapshot."""

    operation_id: str
    previous_state: str
    state: str
    disposition: str
    reason: str
    snapshot_id: str
    step_index: int
    next_action: object = None
    probability_interval: object = None
    schedule: object = None
    reservation: object = None
    released_reservation: object = None

    def __post_init__(self):
        for value, name in (
                (self.operation_id,
                 "operation ID"),
                (self.previous_state,
                 "previous state"),
                (self.state,
                 "state"),
                (self.disposition,
                 "disposition"),
                (self.reason,
                 "reason"),
                (self.snapshot_id,
                 "snapshot ID")):
            if not isinstance(
                    value, str) or not value:
                raise ValueError(
                    "combat lifecycle {} is required".format(
                        name))
        if (
            isinstance(self.step_index, bool)
            or not isinstance(
                self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError(
                "combat lifecycle step index is invalid")
        if (
            self.next_action is not None
            and not isinstance(
                self.next_action, dict)
        ):
            raise TypeError(
                "combat lifecycle next action must be an object or absent")


class CombatOperationLifecycle:
    """Persist and re-estimate selected combat operations without authority."""

    CONTROLLER_IDENTITY = (
        "freeciv-combat-operation-lifecycle/1.0")

    def __init__(self, identity):
        if not isinstance(
                identity, str) or not identity:
            raise ValueError(
                "combat lifecycle identity is required")
        self.identity = identity
        self.store = OperationStore(
            "combat:{}".format(
                identity))
        self.ledger = (
            ResourceReservationLedger(
                "combat:{}".format(
                    identity)))
        self._assemblies = {}

    def assembly(self, operation_id):
        return self._assemblies.get(
            str(operation_id))

    @staticmethod
    def _action_key(action):
        return (
            canonical_json_bytes(
                action)
            .decode("utf-8"))

    @staticmethod
    def _update(
            record, previous_state,
            disposition, reason,
            snapshot, next_action=None,
            probability_interval=None,
            schedule=None,
            reservation=None,
            released_reservation=None):
        return CombatLifecycleUpdate(
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
            next_action=next_action,
            probability_interval=(
                probability_interval),
            schedule=schedule,
            reservation=reservation,
            released_reservation=(
                released_reservation))

    def register_schedule(
            self, assemblies, schedule,
            snapshot):
        """Register and reserve only newly selected complete operations."""
        by_id = {
            assembly.spec.operation_id:
                assembly
            for assembly in assemblies
        }
        selected = tuple(
            operation_id
            for operation_id in
            schedule.selected_operation_ids
            if (
                operation_id in by_id
                and self.store.get(
                    operation_id) is None))
        if not selected:
            return ()
        # The per-snapshot combat scheduler cannot see reservations retained
        # by operations from an earlier snapshot.  Admit only new requests
        # that remain feasible beside those identity-bearing claims.  This
        # preserves the existing operation and fails the newcomer closed
        # instead of asking the ledger to discover the conflict by raising.
        active_claims = list(
            self.ledger.active_claims())
        reservable = []
        for operation_id in selected:
            claims = tuple(
                by_id[operation_id]
                .resource_request
                .claims)
            feasible, _, _, _ = (
                _feasible(
                    tuple(active_claims)
                    + claims,
                    schedule.capacities))
            if not feasible:
                continue
            reservable.append(
                operation_id)
            active_claims.extend(
                claims)
        selected = tuple(
            reservable)
        if not selected:
            return ()
        requests = tuple(
            by_id[operation_id]
            .resource_request
            for operation_id in
            selected)
        requirement_sets = tuple(
            by_id[operation_id]
            .requirement_set
            for operation_id in
            selected)
        packets = {
            premise_id: value
            for operation_id in selected
            for premise_id, value
            in by_id[operation_id]
            .initial_premise_packets
        }
        registration_schedule = (
            BoundedExactScheduler(
                node_budget=4096,
                time_budget_ms=20.0)
            .schedule(
                requests,
                schedule.capacities,
                requirement_sets=(
                    requirement_sets),
                premise_packets=(
                    packets)))
        reservations = {
            row.operation_id: row
            for row in
            self.ledger
            .reserve_schedule(
                registration_schedule)
        }
        updates = []
        for operation_id in (
                registration_schedule
                .selected_operation_ids):
            assembly = by_id[
                operation_id]
            record = self.store.propose(
                assembly.spec,
                snapshot.snapshot_id,
                int(snapshot.turn))
            previous = (
                record.progress.state)
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
            self._assemblies[
                operation_id] = assembly
            readout = (
                CombatOperationAssembler
                .readout(
                    assembly, snapshot, 0))
            updates.append(
                self._update(
                    record, previous,
                    "reserved",
                    "complete-operation-reserved",
                    snapshot,
                    next_action=(
                        readout.next_action),
                    probability_interval=(
                        readout
                        .probability_interval),
                    schedule=(
                        registration_schedule),
                    reservation=(
                        reservations.get(
                            operation_id))))
        return tuple(updates)

    def commit_matching_action(
            self, snapshot, action,
            accepted, reason=None):
        """Attribute one real accepted/rejected action to one reserved step."""
        if not isinstance(action, dict):
            return ()
        action_key = self._action_key(
            action)
        matches = []
        for record in (
                self.store
                .nonterminal_records()):
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
                or record.progress.state
                not in (
                    OperationState.RESERVED,
                    OperationState.ACTIVE,
                )
            ):
                continue
            step_index = (
                record.progress
                .current_step_index)
            if step_index >= len(
                    assembly.spec.steps):
                continue
            if self._action_key(
                    assembly.action_for_step(
                        step_index)
            ) == action_key:
                matches.append(
                    record)
        if not matches:
            return ()
        record = sorted(
            matches,
            key=lambda row: (
                -row.progress
                .last_updated_turn,
                row.spec.operation_id))[0]
        operation_id = (
            record.spec.operation_id)
        assembly = self._assemblies[
            operation_id]
        current_readout = (
            CombatOperationAssembler
            .readout(
                assembly, snapshot,
                record.progress
                .current_step_index))
        previous = record.progress.state
        if (
            accepted
            and current_readout
            .disposition
            != "reservable"
        ):
            failure_reason = (
                "commit-revalidation:{}".format(
                    current_readout.reason))
            record = self.store.transition(
                operation_id,
                OperationState.FAILED,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=failure_reason)
            released = self.ledger.release(
                operation_id,
                failure_reason)
            return (
                self._update(
                    record, previous,
                    "failed",
                    failure_reason,
                    snapshot,
                    next_action=action,
                    released_reservation=(
                        released)),)
        if not accepted:
            failure_reason = str(
                reason
                or "current-action-not-accepted")
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
                    record, previous,
                    "failed",
                    failure_reason,
                    snapshot,
                    next_action=action,
                    probability_interval=(
                        current_readout
                        .probability_interval),
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
            "step-{}-committed-reestimate-required"
            .format(
                record.progress
                .current_step_index))
        return (
            self._update(
                record, previous,
                "step_committed",
                "engine-accepted-current-step",
                snapshot,
                next_action=action,
                probability_interval=(
                    current_readout
                    .probability_interval),
                released_reservation=(
                    released)),)

    def _reserve_request(
            self, operation_id,
            request, capacities):
        existing = (
            self.ledger.reservation(
                operation_id))
        refreshed = None
        if (
            existing is not None
            and existing.active
        ):
            refreshed = self.ledger.release(
                operation_id,
                "reservation-refreshed-from-new-snapshot")
        schedule = (
            BoundedExactScheduler(
                node_budget=128,
                time_budget_ms=20.0)
            .schedule(
                (request,),
                capacities))
        if operation_id not in (
                schedule
                .selected_operation_ids):
            return (
                schedule, None,
                refreshed)
        reservations = (
            self.ledger
            .reserve_schedule(
                schedule))
        reservation = (
            reservations[0]
            if reservations else
            self.ledger.reservation(
                operation_id))
        return (
            schedule, reservation,
            refreshed)

    def _reserve_current_step(
            self, record, snapshot):
        operation_id = (
            record.spec.operation_id)
        assembly = self._assemblies[
            operation_id]
        request = (
            CombatOperationAssembler
            .step_resource_request(
                assembly, snapshot,
                record.progress
                .current_step_index))
        if request is None:
            return None, None, None
        capacities = (
            ResourceCapacityExtractor()
            .extract(
                snapshot,
                action_budget=1)
            .capacities
            + combat_target_capacities(
                (assembly,), snapshot))
        return self._reserve_request(
            operation_id,
            request, capacities)

    def _revalidate_reserved(
            self, record, snapshot):
        assembly = self._assemblies[
            record.spec.operation_id]
        readouts = tuple(
            CombatOperationAssembler
            .readout(
                assembly, snapshot,
                step_index)
            for step_index in range(
                record.progress
                .current_step_index,
                len(assembly.spec.steps)))
        unsupported = next((
            row for row in readouts
            if row.disposition
            != "reservable"
        ), None)
        if unsupported is not None:
            return (
                unsupported,
                None, None, None)
        if (
            record.progress
            .current_step_index > 0
        ):
            schedule, reservation, released = (
                self._reserve_current_step(
                    record, snapshot))
            return (
                readouts[0],
                schedule,
                reservation,
                released)
        request = OperationResourceRequest(
            operation_id=(
                record.spec
                .operation_id),
            bid=float(
                readouts[0]
                .probability_interval
                .lower),
            claims=(
                assembly
                .resource_request
                .claims),
            requirement_set_id=None)
        capacities = (
            ResourceCapacityExtractor()
            .extract(
                snapshot,
                action_budget=len(
                    assembly.spec.steps))
            .capacities
            + combat_target_capacities(
                (assembly,), snapshot))
        schedule, reservation, released = (
            self._reserve_request(
                record.spec.operation_id,
                request, capacities))
        return (
            readouts[0],
            schedule, reservation,
            released)

    def _finish(
            self, record, snapshot,
            state, disposition,
            reason):
        previous = (
            record.progress.state)
        record = self.store.transition(
            record.spec.operation_id,
            state,
            snapshot.snapshot_id,
            int(snapshot.turn),
            reason=reason)
        existing = self.ledger.reservation(
            record.spec.operation_id)
        released = (
            self.ledger.release(
                record.spec.operation_id,
                reason,
                expired=(
                    state
                    == OperationState.EXPIRED))
            if (
                existing is not None
                and existing.active)
            else None)
        return self._update(
            record, previous,
            disposition, reason,
            snapshot,
            released_reservation=(
                released))

    def observe(self, snapshot):
        """Resolve or repair each operation from a newer exact snapshot."""
        updates = []
        for original in (
                self.store
                .nonterminal_records()):
            operation_id = (
                original.spec.operation_id)
            assembly = self._assemblies.get(
                operation_id)
            if (
                assembly is None
                or original.progress
                .last_snapshot_id
                == snapshot.snapshot_id
            ):
                continue
            if int(snapshot.turn) > (
                    original.spec
                    .expiry_turn):
                updates.append(
                    self._finish(
                        original, snapshot,
                        OperationState.EXPIRED,
                        "expired",
                        "operation-deadline-passed"))
                continue
            target_present = (
                snapshot.visible_enemy_unit(
                    assembly
                    .target_unit_id)
                is not None)
            if not target_present:
                updates.append(
                    self._finish(
                        original, snapshot,
                        OperationState.COMPLETED,
                        "completed",
                        "target-neutralized"))
                continue
            progress = (
                original.progress)
            if progress.state == (
                    OperationState.RESERVED):
                (
                    readout,
                    schedule,
                    reservation,
                    refreshed,
                ) = self._revalidate_reserved(
                    original, snapshot)
                if readout.disposition != (
                        "reservable"):
                    if readout.disposition == (
                            "completed"):
                        updates.append(
                            self._finish(
                                original, snapshot,
                                OperationState.COMPLETED,
                                "completed",
                                readout.reason))
                    elif readout.disposition == (
                            "abandoned"):
                        updates.append(
                            self._finish(
                                original, snapshot,
                                OperationState.ABANDONED,
                                "abandoned",
                                readout.reason))
                    else:
                        record = self.store.transition(
                            operation_id,
                            OperationState.BLOCKED,
                            snapshot.snapshot_id,
                            int(snapshot.turn),
                            reason=(
                                readout.reason))
                        existing = (
                            self.ledger
                            .reservation(
                                operation_id))
                        released = (
                            self.ledger
                            .release(
                                operation_id,
                                readout.reason)
                            if (
                                existing is not None
                                and existing.active)
                            else None)
                        updates.append(
                            self._update(
                                record,
                                progress.state,
                                "blocked",
                                readout.reason,
                                snapshot,
                                released_reservation=(
                                    released)))
                    continue
                if reservation is None:
                    reason = next(
                        (
                            row.reason
                            for row in
                            schedule.entries
                            if row.operation_id
                            == operation_id
                        ),
                        "whole-operation-resource-capacity-unavailable")
                    record = self.store.transition(
                        operation_id,
                        OperationState.BLOCKED,
                        snapshot.snapshot_id,
                        int(snapshot.turn),
                        reason=reason)
                    updates.append(
                        self._update(
                            record,
                            progress.state,
                            "blocked", reason,
                            snapshot,
                            schedule=schedule,
                            released_reservation=(
                                refreshed)))
                    continue
                updates.append(
                    self._update(
                        original,
                        progress.state,
                        "step_revalidated",
                        "whole-operation-grounded-and-reserved",
                        snapshot,
                        next_action=(
                            readout.next_action),
                        probability_interval=(
                            readout
                            .probability_interval),
                        schedule=schedule,
                        reservation=reservation,
                        released_reservation=(
                            refreshed)))
                continue
            if (
                progress.state
                == OperationState.ACTIVE
                and progress.attempt_count
                > 0
            ):
                next_index = (
                    progress
                    .current_step_index
                    + 1)
                if next_index >= len(
                        assembly.spec.steps):
                    updates.append(
                        self._finish(
                            original, snapshot,
                            OperationState.FAILED,
                            "failed",
                            "all-attacks-resolved-target-survived"))
                    continue
                previous = progress.state
                record = (
                    self.store
                    .advance_step(
                        operation_id,
                        snapshot.snapshot_id,
                        int(snapshot.turn)))
            else:
                previous = progress.state
                record = original
            step_index = (
                record.progress
                .current_step_index)
            readout = (
                CombatOperationAssembler
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
                        readout.reason))
                continue
            if readout.disposition == (
                    "abandoned"):
                updates.append(
                    self._finish(
                        record, snapshot,
                        OperationState.ABANDONED,
                        "abandoned",
                        readout.reason))
                continue
            if readout.disposition != (
                    "reservable"):
                current = (
                    record.progress.state)
                if current != (
                        OperationState.BLOCKED):
                    record = (
                        self.store.transition(
                            operation_id,
                            OperationState.BLOCKED,
                            snapshot.snapshot_id,
                            int(snapshot.turn),
                            reason=(
                                readout.reason)))
                existing = (
                    self.ledger
                    .reservation(
                        operation_id))
                released = (
                    self.ledger.release(
                        operation_id,
                        readout.reason)
                    if (
                        existing is not None
                        and existing.active)
                    else None)
                updates.append(
                    self._update(
                        record, previous,
                        "blocked",
                        readout.reason,
                        snapshot,
                        released_reservation=(
                            released)))
                continue
            repaired = (
                record.progress.state
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
                schedule,
                reservation,
                refreshed,
            ) = (
                self._reserve_current_step(
                    record, snapshot))
            if reservation is None:
                reason = (
                    "current-step-resource-capacity-unavailable"
                    if schedule is None
                    else next(
                        (
                            row.reason
                            for row in
                            schedule.entries
                            if row.operation_id
                            == operation_id
                        ),
                        "current-step-resource-capacity-unavailable"))
                current = (
                    record.progress.state)
                if current != (
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
                        schedule=schedule,
                        released_reservation=(
                            refreshed)))
                continue
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
                        "next-step-grounded-and-reserved"),
                    snapshot,
                    next_action=(
                        readout.next_action),
                    probability_interval=(
                        readout
                        .probability_interval),
                    schedule=schedule,
                    reservation=reservation,
                    released_reservation=(
                        refreshed)))
        return tuple(updates)
