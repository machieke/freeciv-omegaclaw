"""Live Impact shadow integration without policy authority."""

import json
import os
import sys
import tempfile
from dataclasses import replace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ControlDecision,
    ControlEventEmitter,
    ControlQuery,
    GroundedImpactPlanner,
)
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateShadowExecutor,
)
from freeciv_agent.pressure import ImpactPressureRankerV2  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _fixture():
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "domain-estimate-shadow", 1,
            json.load(stream)).to_snapshot()
    candidates = GroundedImpactPlanner({
        "pressure_enabled": False}).candidates(snapshot)
    return snapshot, candidates


def _rank(ranker, snapshot, candidates):
    return ranker.rank(
        snapshot, candidates,
        expansion_city_target=5,
        horizon_turn=int(snapshot.turn) + 200)


def _rank_and_complete(ranker, snapshot, candidates):
    ordered, artifact = _rank(
        ranker, snapshot, candidates)
    domain = artifact["domain_estimates"]
    completed = ranker.wait_for_domain_estimates(
        domain["dispatch_batch_id"], timeout=5.0)
    assert completed is not None
    assert completed["status"] == "completed"
    return ordered, artifact, completed


def test_shadow_estimates_cover_candidates_without_changing_live_order():
    snapshot, candidates = _fixture()
    baseline_order, baseline = _rank(
        ImpactPressureRankerV2(),
        snapshot, candidates)
    ranker = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest="ruleset-test")
    try:
        shadow_order, shadow, domain = (
            _rank_and_complete(
                ranker, snapshot, candidates))

        assert shadow_order == baseline_order
        assert shadow["schedule"] == baseline["schedule"]
        assert domain["shadow_only"]
        assert not domain["authority_active"]
        assert domain["live_ordering_unchanged"]
        assert domain["estimate_count"] == len(candidates)
        assert all(
            row["estimate"]["authority"] == "legacy_proxy"
            for row in domain["estimates"])
    finally:
        ranker.close_domain_estimates()


def test_shadow_estimate_payloads_are_valid_versioned_events():
    snapshot, candidates = _fixture()
    ranker = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest="ruleset-test")
    try:
        _, _, domain = _rank_and_complete(
            ranker, snapshot, candidates)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.jsonl")
            writer = EventWriter(
                path, "domain-estimate-events",
                durable=False)
            parent = writer.emit(
                "run_started", 0, {
                    "condition_id": "domain-shadow",
                    "manifest_identity": "test",
                })
            for row in domain["estimates"]:
                parent = writer.emit(
                    row["event_type"], snapshot.turn,
                    row["event_payload"],
                    caused_by=[parent["event_id"]])
            writer.emit(
                "run_completed", snapshot.turn, {
                    "status": "completed",
                    "summary": {
                        "estimate_count": len(candidates),
                    },
                }, caused_by=[parent["event_id"]])

            report = validate_file(path)
    finally:
        ranker.close_domain_estimates()

    assert report.valid, [
        row.to_dict() for row in report.errors]


def test_live_shadow_estimate_is_invariant_to_unrelated_candidates_and_utility():
    snapshot, candidates = _fixture()
    target = candidates[0]
    unrelated = next(
        row for row in candidates[1:]
        if row.category != target.category)
    ranker = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest="ruleset-test")

    try:
        artifacts = tuple(
            _rank_and_complete(
                ranker, snapshot, rows)[2]
            for rows in (
                (target,),
                (target, unrelated),
                (unrelated, target),
                (replace(
                    target,
                    utility=target.utility * 1000.0),
                 unrelated),
            ))
        target_action_id = next(
            row["candidate_action_id"]
            for row in artifacts[0]["estimates"])
        estimates = tuple(
            next(
                row["estimate"]
                for row in artifact["estimates"]
                if row["candidate_action_id"]
                == target_action_id)
            for artifact in artifacts)

        assert all(
            row == estimates[0]
            for row in estimates)
    finally:
        ranker.close_domain_estimates()


def test_shadow_semantic_hash_excludes_wall_timing():
    snapshot, candidates = _fixture()
    ranker = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest="ruleset-test")

    try:
        _, _, first = _rank_and_complete(
            ranker, snapshot, candidates)
        second = _rank(
            ranker, snapshot, candidates)[1][
                "domain_estimates"]

        assert second["status"] == "completed"
        assert (
            first["artifact_hash"]
            == second["artifact_hash"])
        assert [
            row["estimate"]
            for row in first["estimates"]
        ] == [
            row["estimate"]
            for row in second["estimates"]
        ]
    finally:
        ranker.close_domain_estimates()


def _query():
    return ControlQuery(
        query_id="domain-event-query",
        snapshot_id="snapshot",
        semantic_epoch=1,
        legal_actions_digest="legal",
        current_turn=1,
        horizon_turn=2,
        active_goals=(),
        grounded_candidates=(),
        truth_summaries=(),
        evidence_summaries=(),
        context_digest="context",
        config_digest="config",
        ruleset_digest="ruleset",
        expansion_city_target=1,
        survival_threat_radius=1,
        pressure_generation=1,
        lifecycle_clone_generation=1,
        normalization_contract_hash="normalization")


def _decision(domain_estimates):
    return ControlDecision(
        ordered_candidate_keys=(),
        selected_candidate_key=None,
        packet_schedule=None,
        controller_mode="scalar_v2",
        artifact={
            "ranker_artifact": {
                "domain_estimates": domain_estimates,
            },
        },
        health="healthy",
        fallback_chain=())


def test_async_domain_readout_cannot_change_decision_hash():
    pending = _decision({
        "batch_id": "batch",
        "estimate_count": 0,
        "estimates": [],
        "status": "pending",
    })
    completed = _decision({
        "batch_id": "batch",
        "estimate_count": 1,
        "estimates": [{
            "request_id": "request",
        }],
        "status": "completed",
        "worker_latency_ms": 99.0,
    })

    assert pending.decision_hash == completed.decision_hash


def test_completed_domain_events_are_emitted_once_per_run():
    payload = {
        "action_category": "test",
        "action_type": "test",
        "actor_id": None,
        "adverse_risk": 0.0,
        "authority": "legacy_proxy",
        "candidate_action_id": "a" * 64,
        "confidence": 0.0,
        "context_key": {},
        "estimator_id": "test",
        "estimator_version": "1",
        "expected_relief": {},
        "latency_ms": 0.0,
        "operation_id": "operation",
        "provenance": ["test"],
        "request_id": "request-once",
        "target_id": None,
        "transition": {},
        "validity": {},
    }
    decision = _decision({
        "batch_id": "batch",
        "estimate_count": 1,
        "estimates": [{
            "event_payload": payload,
            "event_type": "domain_estimate_emitted",
            "request_id": "request-once",
        }],
        "status": "completed",
    })
    emitter = ControlEventEmitter()
    with tempfile.TemporaryDirectory() as directory:
        writer = EventWriter(
            os.path.join(directory, "events.jsonl"),
            "domain-dedup-events",
            durable=False)
        first = emitter.emit_decision(
            writer, 1, _query(), decision)
        second = emitter.emit_decision(
            writer, 2, _query(), decision)

    assert [
        row["type"] for row in first
    ] == ["domain_estimate_emitted"]
    assert second == ()


def test_planner_final_drain_emits_the_last_shadow_batch():
    snapshot, candidates = _fixture()
    planner = GroundedImpactPlanner({
        "pressure_controller_mode": "scalar_v2",
        "pressure_domain_estimates_enabled": True,
        "pressure_enabled": True,
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_semantics_version": "v2",
    })
    try:
        assert planner.plan(snapshot) is not None
        artifacts = planner.flush_domain_estimates(
            timeout=5.0)
        assert artifacts
        assert sum(
            row.get("estimate_count", 0)
            for row in artifacts) >= len(candidates)

        emitter = ControlEventEmitter()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(
                directory, "events.jsonl")
            writer = EventWriter(
                path, "domain-final-drain",
                durable=False)
            events = (
                emitter.emit_domain_estimate_artifacts(
                    writer, snapshot.turn,
                    artifacts))
            duplicate = (
                emitter.emit_domain_estimate_artifacts(
                    writer, snapshot.turn,
                    artifacts))
            report = validate_file(path)

        assert len(events) >= len(candidates)
        assert duplicate == ()
        assert report.valid, [
            row.to_dict()
            for row in report.errors]
    finally:
        planner.close_domain_estimates()


def test_shadow_executor_is_bounded_and_failure_is_observational():
    import threading

    release = threading.Event()
    executor = DomainEstimateShadowExecutor(
        maximum_pending=2,
        maximum_cached=2)

    def blocked(value):
        release.wait(timeout=2.0)
        return {
            "batch_id": value,
            "estimate_count": 1,
            "estimates": [],
        }

    try:
        assert executor.submit(
            "one", blocked, ("one",)) == "submitted"
        assert executor.submit(
            "two", blocked, ("two",)) == "submitted"
        assert executor.submit(
            "three", blocked, ("three",)) == "capacity"
        release.set()
        assert executor.wait(
            "one", timeout=2.0)["status"] == "completed"
        assert executor.wait(
            "two", timeout=2.0)["status"] == "completed"

        def fail():
            raise RuntimeError("shadow failure")

        assert executor.submit(
            "failure", fail,
            failure_artifact={
                "batch_id": "failure",
                "shadow_only": True,
            }) == "submitted"
        failed = executor.wait(
            "failure", timeout=2.0)
        assert failed["status"] == "failed"
        assert failed["error_type"] == "RuntimeError"
        assert failed["estimate_count"] == 0
    finally:
        release.set()
        executor.close()
