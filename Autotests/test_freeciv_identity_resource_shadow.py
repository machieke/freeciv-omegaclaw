"""Default-off resource scheduling shadow integration."""

import json
import os
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ControlEventEmitter,
    GroundedImpactPlanner,
)
from freeciv_agent.pressure import ImpactPressureRankerV2  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _fixture():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "identity-resource-shadow", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False,
    }).candidates(snapshot)
    return snapshot, candidates


def _rank(ranker, snapshot, candidates):
    return ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 200)


def _rank_and_complete(
        ranker, snapshot, candidates):
    ordered, artifact = _rank(
        ranker, snapshot, candidates)
    pending = artifact[
        "identity_resource_schedule"]
    ranker.dispatch_resource_schedule()
    completed = (
        ranker.wait_for_resource_schedule(
            pending[
                "dispatch_batch_id"],
            timeout=5.0))
    assert completed is not None
    assert completed["status"] == (
        "completed")
    return ordered, artifact, completed


def test_identity_resource_shadow_preserves_scalar_v2_decision():
    snapshot, candidates = _fixture()
    baseline_order, baseline = _rank(
        ImpactPressureRankerV2(),
        snapshot, candidates)
    ranker = ImpactPressureRankerV2(
        resource_scheduler_enabled=True)
    try:
        shadow_order, shadow, resource = (
            _rank_and_complete(
                ranker, snapshot,
                candidates))
        assert shadow_order == baseline_order
        assert shadow["schedule"] == baseline["schedule"]
        assert resource["shadow_only"]
        assert not resource["policy_authority"]
        assert resource["live_ordering_unchanged"]
        assert resource[
            "packet_exact_selection_equal"]
        assert resource[
            "packet_committed_operation_ids"] == (
                resource["exact"][
                    "selected_operation_ids"])
        assert resource["exact"]["status"] == "exact"
        assert "latency_ms" not in resource["exact"]
        assert resource["greedy"] is None
    finally:
        ranker.close_resource_schedules()


def test_identity_resource_shadow_is_byte_deterministic():
    snapshot, candidates = _fixture()
    first_ranker = ImpactPressureRankerV2(
        resource_scheduler_enabled=True)
    second_ranker = ImpactPressureRankerV2(
        resource_scheduler_enabled=True)
    try:
        _, _, first_resource = (
            _rank_and_complete(
                first_ranker, snapshot,
                candidates))
        _, _, second_resource = (
            _rank_and_complete(
                second_ranker, snapshot,
                candidates))
        assert first_resource[
            "artifact_hash"] == second_resource[
                "artifact_hash"]
        assert first_resource["exact"] == (
            second_resource["exact"])
        assert first_resource["exact"][
            "decision_digest"] == second_resource[
                "exact"]["decision_digest"]
    finally:
        first_ranker.close_resource_schedules()
        second_ranker.close_resource_schedules()


def test_normal_planner_configuration_wires_resource_shadow():
    snapshot, _ = _fixture()
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
    })

    result = planner.plan(snapshot)

    assert result is not None
    artifact = planner.last_control_decision.artifact[
        "ranker_artifact"]
    assert "identity_resource_schedule" in artifact
    assert artifact[
        "identity_resource_schedule"][
            "shadow_only"]
    assert artifact[
        "identity_resource_schedule"][
            "status"] == "pending"
    planner.close_domain_estimates()


def test_resource_shadow_emits_attributable_valid_events():
    snapshot, _ = _fixture()
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
    })
    assert planner.plan(snapshot) is not None
    planner.dispatch_resource_schedules()
    artifacts = planner.flush_resource_schedules(
        timeout=5.0)
    assert artifacts

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "events.jsonl")
        writer = EventWriter(
            path, "resource-shadow-events",
            durable=False)
        emitter = ControlEventEmitter()
        decision_events = emitter.emit_decision(
            writer, snapshot.turn,
            planner.last_control_query,
            planner.last_control_decision)
        events = (
            decision_events
            + emitter
            .emit_resource_schedule_results(
                writer, snapshot.turn,
                artifacts,
                caused_by=(
                    (decision_events[-1][
                        "event_id"],)
                    if decision_events
                    else ())))
        report = validate_file(path)
    planner.close_domain_estimates()

    event_types = [
        row["type"] for row in events]
    assert "resource_schedule_decided" in event_types
    assert "resource_capacity_changed" in event_types
    assert "resource_claim_requested" in event_types
    assert "resource_claim_reserved" in event_types
    assert "resource_claim_rejected" in event_types
    rejected = next(
        row for row in events
        if row["type"]
        == "resource_claim_rejected")
    assert rejected["payload"]["reason"]
    assert rejected["payload"][
        "conflict_resource_ids"]
    assert report.valid, [
        row.to_dict()
        for row in report.errors]
