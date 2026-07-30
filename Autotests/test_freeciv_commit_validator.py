"""Stage-S5 exact candidate commit revalidation gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
)
from freeciv_agent.planning import (  # noqa: E402
    ImpactCandidate,
    ImpactCommitValidator,
    ImpactControlAdapter,
    ValidationDisposition,
)
from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    GreedyIdentityScheduler,
    OperationResourceRequest,
    PacketCost,
    PacketReservation,
    ResourceCapacity,
    ResourceClaim,
    ResourceRef,
    ResourceReservationLedger,
    ResourceReservationState,
    ResourceKind,
    TurnWindow,
)


class _Snapshot:
    def __init__(
            self, snapshot_id="snapshot-1",
            legal_digest="legal-1", candidates=()):
        self.snapshot_id = snapshot_id
        self.legal_actions_digest = legal_digest
        self.turn = 5
        self.legal_action_json = tuple(
            canonical_json_bytes(
                row.action).decode("utf-8")
            for row in candidates)

    def event_payload(self):
        return {
            "legal_actions_digest":
                self.legal_actions_digest,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }


def _candidate(target=1, utility=2.0):
    return ImpactCandidate(
        {
            "action_type": "unit_move",
            "actor_id": 7,
            "target": target,
        },
        "exploration_move", utility,
        "grounded move")


def _query(candidate=None):
    candidate = candidate or _candidate()
    adapter = ImpactControlAdapter()
    snapshot = _Snapshot(candidates=(candidate,))
    query = adapter.build_query(
        snapshot=snapshot,
        candidates=(candidate,),
        expansion_city_target=5,
        horizon_turn=40,
        survival_threat_radius=6,
        goal_facts={"exploration": {}},
        lifecycle_clone_generation=3,
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")
    return query, snapshot, candidate


def _reservation(candidate, state="complete"):
    cost = PacketCost(ResourceKind.ACTION, 1)
    return PacketReservation(
        operation_id=candidate.action_key,
        costs=(cost,),
        reserved=(cost,),
        state=state)


def _resource_ledger(candidate):
    resource = ResourceRef(
        GameResourceKind.ACTOR,
        "unit:7", "whole_actor",
        "player:1")
    claim = ResourceClaim(
        resource, 1,
        TurnWindow(5, 6),
        ClaimHardness.HARD_CURRENT,
        True, candidate.action_key,
        "move")
    request = OperationResourceRequest(
        candidate.action_key, 1.0,
        (claim,))
    capacity = ResourceCapacity(
        resource, 1,
        TurnWindow(5, 6),
        "snapshot-1",
        "authoritative-own-unit")
    schedule = GreedyIdentityScheduler().schedule(
        (request,), (capacity,))
    ledger = ResourceReservationLedger(
        "commit-validator-test")
    ledger.reserve_schedule(
        schedule)
    return ledger


def test_stale_candidate_is_revalidated_before_materialization():
    query, _, candidate = _query()
    current = _Snapshot(
        "snapshot-2", "legal-2", (candidate,))
    result = ImpactCommitValidator().validate(
        query, candidate.action_key,
        current, (candidate,),
        reservation=_reservation(candidate),
        current_clone_generation=3)

    assert result.disposition == (
        ValidationDisposition.REGENERATE)
    assert result.reason == (
        "stale-snapshot-or-legal-actions")
    assert result.released_packets


def test_retired_action_releases_reserved_packets():
    query, _, candidate = _query()
    current = _Snapshot(
        "snapshot-2", "legal-2", ())
    result = ImpactCommitValidator().validate(
        query, candidate.action_key,
        current, (),
        reservation=_reservation(candidate),
        accepted_refresh=True,
        current_clone_generation=3)

    assert result.disposition == ValidationDisposition.REJECT
    assert result.reason == (
        "action-retired-or-not-authoritative")
    assert result.released_packets == (
        PacketCost(ResourceKind.ACTION, 1),)


def test_changed_cost_requests_regeneration():
    query, snapshot, candidate = _query()
    result = ImpactCommitValidator().validate(
        query, candidate.action_key,
        snapshot, (candidate,),
        reservation=_reservation(candidate),
        current_clone_generation=3,
        source_predicted_cost=1.0,
        current_predicted_cost=1.2)

    assert result.disposition == (
        ValidationDisposition.REGENERATE)
    assert result.reason == (
        "predicted-cost-materially-changed")
    assert result.released_packets


def test_clone_generation_change_rejects_stale_candidate():
    query, snapshot, candidate = _query()
    result = ImpactCommitValidator().validate(
        query, candidate.action_key,
        snapshot, (candidate,),
        reservation=_reservation(candidate),
        current_clone_generation=4)

    assert result.disposition == ValidationDisposition.REJECT
    assert result.reason == (
        "lifecycle-clone-generation-changed")


def test_current_legal_candidate_survives_bounded_stale_view():
    query, _, candidate = _query()
    current = _Snapshot(
        "snapshot-2", "legal-2", (candidate,))
    result = ImpactCommitValidator().validate(
        query, candidate.action_key,
        current, (candidate,),
        reservation=_reservation(candidate),
        accepted_refresh=True,
        current_clone_generation=3,
        exact_guard=lambda row, snapshot: (
            row.action_key == candidate.action_key))

    assert result.disposition == ValidationDisposition.COMMIT
    assert result.refreshed_candidate_key == (
        candidate.action_key)
    assert result.plan_materialization_authorized
    assert not result.execution_authority


def test_commit_validator_cannot_create_new_action():
    query, snapshot, candidate = _query()
    new = _candidate(target=99)
    current = _Snapshot(
        snapshot.snapshot_id,
        snapshot.legal_actions_digest,
        (candidate, new))
    result = ImpactCommitValidator().validate(
        query, new.action_key,
        current, (candidate, new),
        reservation=_reservation(new),
        current_clone_generation=3)

    assert result.disposition == ValidationDisposition.REJECT
    assert result.reason == "candidate-not-in-source-query"
    assert result.refreshed_candidate_key is None


def test_quarantine_or_double_spend_fails_closed():
    query, snapshot, candidate = _query()
    quarantined = ImpactCommitValidator().validate(
        query, candidate.action_key,
        snapshot, (candidate,),
        reservation=_reservation(candidate),
        current_clone_generation=3,
        quarantined=True)
    spent = ImpactCommitValidator().validate(
        query, candidate.action_key,
        snapshot, (candidate,),
        reservation=_reservation(candidate),
        current_clone_generation=3,
        consumed_operation_ids=(
            candidate.action_key,))

    assert quarantined.reason == "candidate-quarantined"
    assert spent.reason == (
        "packet-reservation-double-spend")


def test_packetless_canonical_validation_can_be_declared():
    query, snapshot, candidate = _query()
    result = ImpactCommitValidator(
        require_packet_reservation=False).validate(
            query, candidate.action_key,
            snapshot, (candidate,),
            current_clone_generation=3)

    assert result.disposition == ValidationDisposition.COMMIT
    assert result.released_packets == ()


def test_v2_resource_reservation_commits_with_exact_validation():
    query, snapshot, candidate = _query()
    ledger = _resource_ledger(
        candidate)

    result, resource_reservation = (
        ImpactCommitValidator()
        .validate_with_resource_ledger(
            ledger,
            candidate.action_key,
            query, candidate.action_key,
            snapshot, (candidate,),
            reservation=(
                _reservation(candidate)),
            current_clone_generation=3))

    assert result.disposition == (
        ValidationDisposition.COMMIT)
    assert resource_reservation.state == (
        ResourceReservationState.COMMITTED)


def test_v2_resource_reservation_releases_on_commit_rejection():
    query, _, candidate = _query()
    ledger = _resource_ledger(
        candidate)
    current = _Snapshot(
        "snapshot-2", "legal-2", ())

    result, resource_reservation = (
        ImpactCommitValidator()
        .validate_with_resource_ledger(
            ledger,
            candidate.action_key,
            query, candidate.action_key,
            current, (),
            reservation=(
                _reservation(candidate)),
            accepted_refresh=True,
            current_clone_generation=3))

    assert result.disposition == (
        ValidationDisposition.REJECT)
    assert resource_reservation.state == (
        ResourceReservationState.RELEASED)
    assert resource_reservation.reason == (
        "commit-validation:"
        "action-retired-or-not-authoritative")
