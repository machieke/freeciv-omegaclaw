#!/usr/bin/env python3
"""Replay grounded GDO-7C city-worker macros on retained engine captures."""

import argparse
import glob
import hashlib
import json
import math
import os
import statistics
import sys
import time
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    CityWorkerMacroAssembler,
    CityWorkerMacroIntent,
    ImpactCandidate,
)
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedCityWorkerTransitionModel,
)


DEFAULT_CAPTURE_GLOBS = (
    "benchmarks/gdo/captured_snapshots/city_defense/*.json",
    "benchmarks/gdo/captured_snapshots/city_defense_grounded_160/*.json",
)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--capture-glob", action="append",
        dest="capture_globs")
    parser.add_argument(
        "--iterations", type=int, default=20)
    parser.add_argument(
        "--output",
        default=(
            "benchmarks/gdo/"
            "gdo7c_city_worker_macro_diagnostic.json"))
    return parser.parse_args()


def _city(row):
    governor = row.get("governor") or {}
    return SimpleNamespace(
        city_id=row["city_id"],
        owner=row["owner"],
        name=row["name"],
        governor_available=governor.get(
            "available"),
        governor_enabled=governor.get(
            "enabled"),
        governor_minimal_surplus=tuple(
            governor.get(
                "minimal_surplus", ())),
        governor_require_happy=governor.get(
            "require_happy"),
        was_happy=row.get("was_happy"),
        disorder=row.get("disorder"),
        surplus=tuple(row.get("surplus", ())),
        production=tuple(
            row.get("production", ())),
        usage=tuple(row.get("usage", ())))


def _snapshot(captured):
    event = captured["snapshot_event"]
    payload = event["payload"]
    cities = tuple(
        _city(row)
        for row in payload[
            "own_state"]["cities"])
    city_by_id = {
        city.city_id: city
        for city in cities}
    grounded = payload.get(
        "grounded_context") or {}
    actions = tuple(
        grounded.get("legal_actions") or ())
    if not actions:
        actions = tuple(
            row["action"]
            for row in captured.get(
                "candidates", ())
            if isinstance(
                row.get("action"), dict))
    legal_action_json = tuple(sorted(set(
        canonical_json_bytes(
            action).decode("utf-8")
        for action in actions)))
    return SimpleNamespace(
        game_id=event["game_id"],
        player_id=payload["player_id"],
        turn=event["turn"],
        snapshot_id=payload["snapshot_id"],
        legal_actions_digest=payload[
            "legal_actions_digest"],
        legal_action_json=legal_action_json,
        cities=cities,
        units=(),
        city=lambda city_id: city_by_id.get(
            city_id))


def _intent(candidate):
    action = candidate["action"]
    target = action.get("target") or {}
    return CityWorkerMacroIntent(
        city_id=action["city_id"],
        food_surplus_minimum=target[
            "food_surplus_reserve"],
        require_happy=bool(
            target.get("require_happy", False)),
        scheduling_bid=max(
            0.0, float(candidate["utility"])))


def _request(snapshot, candidate, index):
    action = candidate["action"]
    return DomainEstimateRequest(
        request_id=structural_hash({
            "action": action,
            "candidate_index": index,
            "snapshot_id":
                snapshot.snapshot_id,
        }),
        snapshot=snapshot,
        ruleset_ir=SimpleNamespace(rules=()),
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category=candidate["category"],
            utility=float(candidate["utility"]),
            rationale=candidate["rationale"],
            projection=candidate.get("projection")),
        goal_losses=((
            "pf-impact:{}".format(
                candidate["category"]),
            1.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            "retained-civ2civ3",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=snapshot.turn + 1)


def _complete_output_vector(value):
    names = {
        "food", "shield", "trade",
        "gold", "luxury", "science",
    }
    return bool(
        isinstance(value, dict)
        and set(value) == {
            "produced", "used", "net"}
        and all(
            isinstance(value[field], dict)
            and set(value[field]) == names
            and all(
                isinstance(number, int)
                and not isinstance(number, bool)
                for number in
                value[field].values())
            for field in (
                "produced", "used", "net")))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(
                lambda: stream.read(1024 * 1024),
                b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    args = _arguments()
    if args.iterations < 1:
        raise SystemExit(
            "--iterations must be positive")
    patterns = tuple(
        args.capture_globs
        or DEFAULT_CAPTURE_GLOBS)
    paths = tuple(sorted(set(
        path
        for pattern in patterns
        for path in glob.glob(
            os.path.join(REPO, pattern)))))
    if not paths:
        raise SystemExit(
            "no retained captures matched")

    captures = []
    snapshots = {}
    for path in paths:
        with open(path, encoding="utf-8") as stream:
            captured = json.load(stream)
        snapshot = _snapshot(captured)
        captures.append((
            path, captured, snapshot))
        snapshots.setdefault(
            (snapshot.game_id, snapshot.turn),
            snapshot)

    model = GroundedCityWorkerTransitionModel()
    latencies = []
    rows = []
    results = []
    repeat_hashes = {}
    for path, captured, snapshot in captures:
        candidates = tuple(
            row for row in
            captured.get("candidates", ())
            if row.get("action", {}).get(
                "action_type")
            == "city_governor")
        for index, candidate in enumerate(
                candidates):
            request = _request(
                snapshot, candidate, index)
            estimates = []
            for _ in range(args.iterations):
                started = time.perf_counter()
                estimate = model.estimate(request)
                latencies.append(
                    (time.perf_counter() - started)
                    * 1000.0)
                estimates.append(estimate)
            repeat_hashes[
                request.request_id] = tuple(
                    sorted(set(
                        structural_hash(
                            estimate.to_dict())
                        for estimate in
                        estimates)))
            estimate = estimates[0]
            artifact = estimate.to_dict().get(
                "model_artifact") or {}
            intent = _intent(candidate)
            assembly = (
                CityWorkerMacroAssembler
                .assemble(
                    snapshot, intent,
                    estimate,
                    ("pf-impact:{}".format(
                        candidate["category"]),),
                    "retained-civ2civ3"))
            projection = (
                candidate.get("projection") or {})
            selected = bool(
                candidate.get("operation_id")
                == (
                    captured.get(
                        "source_control")
                    or {}).get(
                        "selected_operation_id"))
            row = {
                "action": candidate["action"],
                "assembly_created":
                    assembly is not None,
                "authority":
                    estimate.authority.value,
                "baseline_complete_output_vector":
                    _complete_output_vector(
                        projection.get(
                            "current_output_vector")),
                "capture": os.path.relpath(
                    path, REPO),
                "citizen_action_count": (
                    int(
                        artifact.get(
                            "assignment", {})
                        .get(
                            "citizen_actions_emitted")
                        is True)),
                "current_complete_output_vector":
                    _complete_output_vector(
                        artifact.get(
                            "current_output_vector")),
                "game_id": snapshot.game_id,
                "macro_step_count": (
                    len(assembly.spec.steps)
                    if assembly is not None
                    else 0),
                "optimality_gap_status": (
                    artifact.get("solver", {})
                    .get(
                        "optimality_gap_status")),
                "predicted_output_point_estimate":
                    (
                        artifact.get(
                            "predicted_output_vector", {})
                        .get("point_estimate")),
                "selected_by_source_controller":
                    selected,
                "snapshot_id":
                    snapshot.snapshot_id,
                "turn": snapshot.turn,
            }
            rows.append(row)
            after = snapshots.get((
                snapshot.game_id,
                snapshot.turn + 1))
            if (
                    selected
                    and assembly is not None
                    and after is not None
            ):
                result = (
                    CityWorkerMacroAssembler
                    .observe_result(
                        assembly, snapshot,
                        after, accepted=True))
                results.append({
                    "action":
                        candidate["action"],
                    "after_turn":
                        after.turn,
                    "before_turn":
                        snapshot.turn,
                    "capture":
                        os.path.relpath(
                            path, REPO),
                    "result":
                        result.to_dict(),
                })

    emitted = tuple(
        row for row in rows
        if row["authority"]
        != EstimateAuthority.ABSTAIN.value)
    sorted_latencies = sorted(latencies)
    p95_index = (
        max(
            0, int(math.ceil(
                0.95
                * len(sorted_latencies))) - 1)
        if sorted_latencies else 0)
    deterministic = bool(
        repeat_hashes
        and all(
            len(values) == 1
            for values in
            repeat_hashes.values()))
    metrics = {
        "adjacent_selected_outcome_count":
            len(results),
        "baseline_complete_output_vector_count":
            sum(
                row[
                    "baseline_complete_output_vector"]
                for row in rows),
        "candidate_count": len(rows),
        "citizen_action_count": sum(
            row["citizen_action_count"]
            for row in emitted),
        "confirmed_observed_result_count":
            sum(
                row["result"][
                    "configuration_observed"]
                is True
                for row in results),
        "confirmed_constraints_satisfied_count":
            sum(
                row["result"][
                    "constraints_met"] is True
                for row in results),
        "deterministic_repeated_estimates":
            deterministic,
        "emitted_count": len(emitted),
        "grounded_complete_output_vector_count":
            sum(
                row[
                    "current_complete_output_vector"]
                for row in emitted),
        "mean_latency_ms": (
            statistics.mean(latencies)
            if latencies else 0.0),
        "p95_latency_ms": (
            sorted_latencies[p95_index]
            if sorted_latencies else 0.0),
        "predicted_output_point_estimate_count":
            sum(
                row[
                    "predicted_output_point_estimate"]
                is not None
                for row in emitted),
        "single_macro_step_count":
            sum(
                row["macro_step_count"] == 1
                for row in emitted),
        "unknown_optimality_gap_count":
            sum(
                row["optimality_gap_status"]
                == (
                    "not-exposed-by-server-interface")
                for row in emitted),
    }
    gates = {
        "all_retained_city_worker_candidates_grounded":
            bool(rows)
            and len(emitted) == len(rows),
        "current_output_coverage_beats_simpler_baseline":
            metrics[
                "grounded_complete_output_vector_count"]
            == len(emitted)
            and metrics[
                "baseline_complete_output_vector_count"]
            < metrics[
                "grounded_complete_output_vector_count"],
        "deterministic": deterministic,
        "engine_observed_macro_result_confirmed":
            metrics[
                "confirmed_observed_result_count"]
            >= 1
            and metrics[
                "confirmed_constraints_satisfied_count"]
            >= 1,
        "no_invented_citizen_actions":
            metrics["citizen_action_count"] == 0,
        "no_invented_output_point_estimate":
            metrics[
                "predicted_output_point_estimate_count"]
            == 0,
        "one_atomic_macro_step_per_candidate":
            metrics[
                "single_macro_step_count"]
            == len(emitted),
        "unexposed_optimality_gap_remains_unknown":
            metrics[
                "unknown_optimality_gap_count"]
            == len(emitted),
    }
    report = {
        "authority": {
            "claim_status":
                "diagnostic-replay-only",
            "full_legal_action_set_available":
                False,
            "policy_authority_eligible":
                False,
            "score_claim": False,
        },
        "capture_globs": list(patterns),
        "fixture_count": len(paths),
        "fixture_hashes": {
            os.path.relpath(path, REPO):
                _sha256(path)
            for path in paths
        },
        "gates": gates,
        "iterations": args.iterations,
        "metrics": metrics,
        "observed_results": results,
        "passed": all(gates.values()),
        "rows": rows,
        "schema_version": "1.0",
    }
    report["report_hash"] = structural_hash(
        report)
    output_path = (
        args.output
        if os.path.isabs(args.output)
        else os.path.join(REPO, args.output))
    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True)
    with open(
            output_path, "wb") as stream:
        stream.write(
            canonical_json_bytes(report))
        stream.write(b"\n")
    print(json.dumps({
        "gates": gates,
        "metrics": metrics,
        "output": os.path.relpath(
            output_path, REPO),
        "passed": report["passed"],
        "report_hash":
            report["report_hash"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
