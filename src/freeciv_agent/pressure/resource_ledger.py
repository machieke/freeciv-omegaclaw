"""Deterministic reservation lifecycle for identity-bearing resource claims."""

from dataclasses import dataclass, replace
from enum import Enum

from ..events.schema import structural_hash
from .resource_claims import ResourceClaim
from .resource_scheduler import (
    ResourceSchedule,
    _feasible,
)


class ResourceReservationState(str, Enum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ResourceReservation:
    operation_id: str
    claims: tuple
    snapshot_id: str
    state: ResourceReservationState
    reason: object = None

    def __post_init__(self):
        if (not isinstance(
                self.operation_id, str)
                or not self.operation_id):
            raise ValueError(
                "resource reservation requires operation ID")
        claims = tuple(self.claims)
        if (not claims
                or any(not isinstance(
                    row, ResourceClaim)
                    for row in claims)):
            raise TypeError(
                "resource reservation requires resource claims")
        if any(
                row.source_operation_id
                != self.operation_id
                for row in claims):
            raise ValueError(
                "reservation claims must match operation ID")
        object.__setattr__(
            self, "claims",
            tuple(sorted(
                claims,
                key=lambda row: row.sort_key)))
        if (not isinstance(
                self.snapshot_id, str)
                or not self.snapshot_id):
            raise ValueError(
                "resource reservation requires snapshot ID")
        if not isinstance(
                self.state,
                ResourceReservationState):
            raise TypeError(
                "resource reservation state has the wrong type")
        if self.state in (
                ResourceReservationState.RESERVED,
                ResourceReservationState.COMMITTED):
            if self.reason is not None:
                raise ValueError(
                    "active resource reservation has no release reason")
        elif (not isinstance(
                self.reason, str)
              or not self.reason):
            raise ValueError(
                "inactive reservation requires reason")

    @property
    def active(self):
        return self.state in (
            ResourceReservationState.RESERVED,
            ResourceReservationState.COMMITTED)

    def to_dict(self):
        return {
            "claims": [
                row.to_dict()
                for row in self.claims],
            "operation_id":
                self.operation_id,
            "reason": self.reason,
            "snapshot_id":
                self.snapshot_id,
            "state": self.state.value,
        }


class ResourceReservationLedger:
    """Own and release shadow reservations without creating execution authority."""

    LEDGER_IDENTITY = (
        "freeciv-resource-reservation-ledger/1.0")

    def __init__(self, identity):
        if not isinstance(
                identity, str) or not identity:
            raise ValueError(
                "resource ledger identity is required")
        self.identity = identity
        self._reservations = {}

    def reservation(self, operation_id):
        return self._reservations.get(
            str(operation_id))

    def active_claims(self):
        return tuple(sorted(
            (
                claim
                for reservation
                in self._reservations.values()
                if reservation.active
                for claim
                in reservation.claims
            ),
            key=lambda row: row.sort_key))

    def reserve_schedule(self, schedule):
        if not isinstance(
                schedule, ResourceSchedule):
            raise TypeError(
                "resource ledger requires ResourceSchedule")
        snapshot_ids = {
            row.snapshot_id
            for row in schedule.capacities}
        if len(snapshot_ids) > 1:
            raise ValueError(
                "resource schedule capacities disagree on snapshot")
        snapshot_id = (
            next(iter(snapshot_ids))
            if snapshot_ids else
            "capacityless-shadow")
        active = list(
            self.active_claims())
        additions = []
        for operation_id in (
                schedule.selected_operation_ids):
            request = next(
                row for row
                in schedule.requests
                if row.operation_id
                == operation_id)
            existing = self._reservations.get(
                operation_id)
            claims = tuple(
                request.claims)
            if existing is not None and (
                    existing.active):
                if existing.claims != claims:
                    raise ValueError(
                        "active reservation cannot change claims")
                continue
            feasible, reason, _, _ = (
                _feasible(
                    tuple(active)
                    + claims,
                    schedule.capacities))
            if not feasible:
                raise ValueError(
                    "schedule would over-allocate ledger: {}".format(
                        reason))
            reservation = ResourceReservation(
                operation_id=operation_id,
                claims=claims,
                snapshot_id=snapshot_id,
                state=(
                    ResourceReservationState
                    .RESERVED))
            additions.append(
                reservation)
            active.extend(claims)
        for reservation in additions:
            self._reservations[
                reservation.operation_id] = (
                    reservation)
        return tuple(additions)

    def commit(self, operation_id):
        operation_id = str(
            operation_id)
        reservation = self._reservations.get(
            operation_id)
        if reservation is None or not reservation.active:
            raise KeyError(
                "operation has no active resource reservation")
        if reservation.state == (
                ResourceReservationState.COMMITTED):
            return reservation
        committed = replace(
            reservation,
            state=(
                ResourceReservationState
                .COMMITTED))
        self._reservations[
            operation_id] = committed
        return committed

    def release(
            self, operation_id, reason,
            expired=False):
        operation_id = str(
            operation_id)
        if not isinstance(reason, str) or not reason:
            raise ValueError(
                "resource release requires reason")
        reservation = self._reservations.get(
            operation_id)
        if reservation is None:
            return None
        if not reservation.active:
            return reservation
        released = replace(
            reservation,
            state=(
                ResourceReservationState.EXPIRED
                if expired else
                ResourceReservationState.RELEASED),
            reason=reason)
        self._reservations[
            operation_id] = released
        return released

    def reconcile(self, capacity_snapshot):
        capacities = tuple(getattr(
            capacity_snapshot,
            "capacities", ()))
        snapshot_id = str(getattr(
            capacity_snapshot,
            "snapshot_id", ""))
        if not snapshot_id:
            raise ValueError(
                "resource reconciliation requires capacity snapshot")
        retained_claims = []
        released = []
        for operation_id in sorted(
                self._reservations):
            reservation = self._reservations[
                operation_id]
            if not reservation.active:
                continue
            feasible, _, _, _ = (
                _feasible(
                    tuple(retained_claims)
                    + reservation.claims,
                    capacities))
            if not feasible:
                released.append(
                    self.release(
                        operation_id,
                        "capacity-disappeared"))
                continue
            refreshed = replace(
                reservation,
                snapshot_id=snapshot_id)
            self._reservations[
                operation_id] = refreshed
            retained_claims.extend(
                refreshed.claims)
        return tuple(released)

    @property
    def ledger_digest(self):
        return structural_hash({
            "identity": self.identity,
            "ledger_identity":
                self.LEDGER_IDENTITY,
            "reservations": [
                self._reservations[key]
                .to_dict()
                for key in sorted(
                    self._reservations)
            ],
        })

    def to_dict(self):
        return {
            "identity": self.identity,
            "ledger_digest":
                self.ledger_digest,
            "ledger_identity":
                self.LEDGER_IDENTITY,
            "policy_authority": False,
            "reservations": [
                self._reservations[key]
                .to_dict()
                for key in sorted(
                    self._reservations)
            ],
            "shadow_only": True,
        }
