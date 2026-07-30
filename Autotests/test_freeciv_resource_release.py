"""Identity reservation ledger release and capacity reconciliation."""

import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    GreedyIdentityScheduler,
    OperationResourceRequest,
    ResourceCapacity,
    ResourceCapacitySnapshot,
    ResourceClaim,
    ResourceRef,
    ResourceReservationLedger,
    ResourceReservationState,
    TurnWindow,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import ControlEventEmitter  # noqa: E402


def _resource():
    return ResourceRef(
        GameResourceKind.ACTOR,
        "unit:7", "whole_actor",
        "player:1")


def _claim(operation_id):
    return ResourceClaim(
        _resource(), 1,
        TurnWindow(5, 6),
        ClaimHardness.HARD_CURRENT,
        True, operation_id, "step")


def _capacity(quantity=1, snapshot="snapshot"):
    return ResourceCapacity(
        _resource(), quantity,
        TurnWindow(5, 6),
        snapshot,
        "authoritative-own-unit")


def _schedule(operation_id="operation"):
    request = OperationResourceRequest(
        operation_id, 2.0,
        (_claim(operation_id),))
    return GreedyIdentityScheduler().schedule(
        (request,), (_capacity(),))


def test_reserve_commit_and_release_are_idempotent_and_attributable():
    ledger = ResourceReservationLedger(
        "ledger")
    schedule = _schedule()

    created = ledger.reserve_schedule(
        schedule)
    duplicate = ledger.reserve_schedule(
        schedule)
    committed = ledger.commit(
        "operation")
    released = ledger.release(
        "operation",
        "commit-revalidation-rejected")

    assert len(created) == 1
    assert duplicate == ()
    assert committed.state == (
        ResourceReservationState.COMMITTED)
    assert released.state == (
        ResourceReservationState.RELEASED)
    assert released.reason == (
        "commit-revalidation-rejected")
    assert ledger.active_claims() == ()
    assert len(ledger.ledger_digest) == 64


def test_separate_schedules_cannot_double_reserve_one_actor():
    ledger = ResourceReservationLedger(
        "ledger")
    ledger.reserve_schedule(
        _schedule("first"))

    with pytest.raises(
            ValueError,
            match="over-allocate"):
        ledger.reserve_schedule(
            _schedule("second"))


def test_capacity_disappearance_releases_current_claim():
    ledger = ResourceReservationLedger(
        "ledger")
    ledger.reserve_schedule(
        _schedule())
    empty = ResourceCapacitySnapshot(
        snapshot_id="snapshot-2",
        turn=5,
        capacities=(),
        omissions=(
            "actor-disappeared",),
        extractor_identity="test")

    released = ledger.reconcile(
        empty)

    assert len(released) == 1
    assert released[0].reason == (
        "capacity-disappeared")
    assert ledger.reservation(
        "operation").state == (
            ResourceReservationState.RELEASED)


def test_reconcile_refreshes_retained_reservation_snapshot():
    ledger = ResourceReservationLedger(
        "ledger")
    ledger.reserve_schedule(
        _schedule())
    refreshed = ResourceCapacitySnapshot(
        snapshot_id="snapshot-2",
        turn=5,
        capacities=(
            _capacity(
                snapshot="snapshot-2"),),
        omissions=(),
        extractor_identity="test")

    assert ledger.reconcile(
        refreshed) == ()
    assert ledger.reservation(
        "operation").snapshot_id == (
            "snapshot-2")


def test_release_event_preserves_full_resource_identity_and_reason():
    ledger = ResourceReservationLedger(
        "ledger")
    ledger.reserve_schedule(
        _schedule())
    released = (
        ledger.release(
            "operation",
            "commit-revalidation-rejected"),)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "events.jsonl")
        writer = EventWriter(
            path, "resource-release-events",
            durable=False)
        events = (
            ControlEventEmitter
            .emit_resource_releases(
                writer, 5, released,
                ledger.ledger_digest,
                ledger.LEDGER_IDENTITY))
        report = validate_file(path)

    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["resource"] == (
        _resource().to_dict())
    assert payload["window"] == (
        TurnWindow(5, 6).to_dict())
    assert payload["reason"] == (
        "commit-revalidation-rejected")
    assert report.valid, [
        row.to_dict()
        for row in report.errors]
