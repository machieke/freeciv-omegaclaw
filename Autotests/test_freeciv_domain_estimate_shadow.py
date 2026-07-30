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
from freeciv_agent.planning import GroundedImpactPlanner  # noqa: E402
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


def test_shadow_estimates_cover_candidates_without_changing_live_order():
    snapshot, candidates = _fixture()
    baseline_order, baseline = _rank(
        ImpactPressureRankerV2(),
        snapshot, candidates)
    shadow_order, shadow = _rank(
        ImpactPressureRankerV2(
            domain_estimates_enabled=True,
            ruleset_digest="ruleset-test"),
        snapshot, candidates)

    assert shadow_order == baseline_order
    assert shadow["schedule"] == baseline["schedule"]
    domain = shadow["domain_estimates"]
    assert domain["shadow_only"]
    assert not domain["authority_active"]
    assert domain["live_ordering_unchanged"]
    assert domain["estimate_count"] == len(candidates)
    assert all(
        row["estimate"]["authority"] == "legacy_proxy"
        for row in domain["estimates"])


def test_shadow_estimate_payloads_are_valid_versioned_events():
    snapshot, candidates = _fixture()
    _, artifact = _rank(
        ImpactPressureRankerV2(
            domain_estimates_enabled=True,
            ruleset_digest="ruleset-test"),
        snapshot, candidates)

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
        for row in artifact[
                "domain_estimates"]["estimates"]:
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

    artifacts = tuple(
        _rank(ranker, snapshot, rows)[1][
            "domain_estimates"]
        for rows in (
            (target,),
            (target, unrelated),
            (unrelated, target),
            (replace(target, utility=target.utility * 1000.0), unrelated),
        ))
    target_action_id = next(
        row["candidate_action_id"]
        for row in artifacts[0]["estimates"])
    estimates = tuple(
        next(
            row["estimate"]
            for row in artifact["estimates"]
            if row["candidate_action_id"] == target_action_id)
        for artifact in artifacts)

    assert all(row == estimates[0] for row in estimates)


def test_shadow_semantic_hash_excludes_wall_timing():
    snapshot, candidates = _fixture()
    ranker = ImpactPressureRankerV2(
        domain_estimates_enabled=True,
        ruleset_digest="ruleset-test")

    first = _rank(
        ranker, snapshot, candidates)[1][
            "domain_estimates"]
    second = _rank(
        ranker, snapshot, candidates)[1][
            "domain_estimates"]

    assert first["artifact_hash"] == second["artifact_hash"]
    assert [
        row["estimate"] for row in first["estimates"]
    ] == [
        row["estimate"] for row in second["estimates"]
    ]
