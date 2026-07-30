#!/usr/bin/env python3
"""Replay grounded GDO-7A production semantics on retained engine captures."""

import argparse
import json
import math
import os
import statistics
import sys
import time
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedProductionTransitionModel,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=(
            "benchmarks/gdo/captured_snapshots/"
            "city_defense_grounded_160_manifest.json"))
    parser.add_argument(
        "--ruleset-root",
        default=(
            "build/freeciv/ruleset-source"))
    parser.add_argument(
        "--output",
        default=(
            "benchmarks/gdo/"
            "gdo7a_production_grounding_diagnostic.json"))
    parser.add_argument(
        "--iterations",
        type=int, default=20)
    return parser.parse_args()


def _snapshot(event):
    payload = event["payload"]
    cities = []
    for row in payload[
            "own_state"]["cities"]:
        cities.append(
            SimpleNamespace(
                city_id=row["city_id"],
                owner=row["owner"],
                name=row["name"],
                production_kind=(
                    row[
                        "production_kind"]),
                production_value=(
                    row[
                        "production_value"]),
                shield_stock=(
                    row["shield_stock"]),
                surplus=tuple(
                    row["surplus"]),
                buildability_available=(
                    row[
                        "buildability_available"]),
                buildable=tuple(
                    tuple(value)
                    for value in
                    row["buildable"]),
                buildings=tuple(
                    SimpleNamespace(
                        improvement_id=(
                            building[
                                "improvement_id"]),
                        name=building[
                            "name"])
                    for building in
                    row.get(
                        "buildings", ()))))
    by_city = {
        row.city_id: row
        for row in cities}
    legal_actions = payload[
        "grounded_context"][
            "legal_actions"]
    return SimpleNamespace(
        player_id=payload[
            "player_id"],
        turn=event["turn"],
        snapshot_id=payload[
            "snapshot_id"],
        legal_actions_digest=payload[
            "legal_actions_digest"],
        legal_action_json=tuple(
            canonical_json_bytes(
                row).decode("utf-8")
            for row in legal_actions),
        cities=tuple(cities),
        units=(),
        city=lambda city_id: (
            by_city.get(city_id)))


def _request(
        snapshot, candidate,
        ruleset, index):
    action = candidate["action"]
    return DomainEstimateRequest(
        request_id=structural_hash({
            "action": action,
            "fixture":
                snapshot.snapshot_id,
            "index": index,
        }),
        snapshot=snapshot,
        ruleset_ir=ruleset,
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category=candidate[
                "category"],
            utility=float(
                candidate["utility"]),
            rationale=candidate[
                "rationale"],
            projection=candidate.get(
                "projection")),
        goal_losses=((
            "pf-impact:{}".format(
                candidate[
                    "category"]),
            1.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot
            .legal_actions_digest,
            "retained-civ2civ3",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=(
            snapshot.turn
            + int(
                (candidate.get(
                    "projection")
                 or {}).get(
                    "remaining_turns",
                    30))))


def main():
    args = _arguments()
    if args.iterations < 1:
        raise SystemExit(
            "--iterations must be positive")
    manifest_path = os.path.join(
        REPO, args.manifest)
    ruleset_root = os.path.join(
        REPO, args.ruleset_root)
    with open(
            manifest_path,
            encoding="utf-8") as stream:
        manifest = json.load(stream)
    ruleset = compile_ruleset(
        ruleset_root,
        manifest["ruleset"])
    model = (
        GroundedProductionTransitionModel())
    rows = []
    latencies = []
    repeated_digests = {}
    fixture_count = 0
    for fixture in manifest[
            "fixtures"]:
        fixture_count += 1
        path = os.path.join(
            REPO, fixture["path"])
        with open(
                path,
                encoding="utf-8") as stream:
            captured = json.load(stream)
        snapshot = _snapshot(
            captured[
                "snapshot_event"])
        candidates = tuple(
            row for row in
            captured.get(
                "candidates", ())
            if row.get(
                "action", {}).get(
                    "action_type")
                == "city_production")
        for index, candidate in enumerate(
                candidates):
            request = _request(
                snapshot, candidate,
                ruleset, index)
            estimates = []
            for _ in range(
                    args.iterations):
                started = (
                    time.perf_counter())
                estimate = model.estimate(
                    request)
                latencies.append(
                    (
                        time.perf_counter()
                        - started)
                    * 1000.0)
                estimates.append(
                    estimate.to_dict())
            digests = tuple(
                structural_hash(value)
                for value in estimates)
            repeated_digests[
                request.request_id] = (
                    tuple(sorted(set(
                        digests))))
            estimate = estimates[0]
            artifact = estimate.get(
                "model_artifact", {})
            city = snapshot.city(
                candidate["action"][
                    "city_id"])
            projection = (
                candidate.get(
                    "projection") or {})
            legacy_eta = projection.get(
                "completion_eta_turns")
            grounded_eta = artifact.get(
                "completion_eta") or {}
            rows.append({
                "action":
                    candidate["action"],
                "authority":
                    estimate["authority"],
                "build_cost_parity": (
                    projection.get(
                        "build_cost")
                    == (
                        artifact.get(
                            "target_profile")
                        or {}).get(
                            "build_cost")),
                "category":
                    candidate["category"],
                "fixture":
                    fixture["path"],
                "grounded_earliest_eta":
                    grounded_eta.get(
                        "earliest_turns"),
                "grounded_latest_eta":
                    grounded_eta.get(
                        "latest_turns"),
                "grounded_product_available_now":
                    (
                        artifact.get(
                            "availability")
                        or {}).get(
                            "product_available_now"),
                "legacy_eta":
                    legacy_eta,
                "same_target": bool(
                    city is not None
                    and city.production_kind
                        == candidate[
                            "action"].get(
                                "production_kind")
                    and city.production_value
                        == candidate[
                            "action"].get(
                                "production_value")),
                "switch_cost_status":
                    (
                        artifact.get(
                            "switch_cost")
                        or {}).get(
                            "status"),
            })
    emitted = [
        row for row in rows
        if row["authority"]
        != EstimateAuthority
        .ABSTAIN.value]
    legacy_zero = [
        row for row in rows
        if (
            row["legacy_eta"]
            is not None
            and float(
                row["legacy_eta"])
                <= 0.0)]
    legacy_zero_switches = [
        row for row in
        legacy_zero
        if not row["same_target"]]
    grounded_zero = [
        row for row in emitted
        if (
            row[
                "grounded_earliest_eta"]
            is not None
            and float(
                row[
                    "grounded_earliest_eta"])
                <= 0.0)]
    deterministic = all(
        len(digests) == 1
        for digests in
        repeated_digests.values())
    sorted_latencies = sorted(
        latencies)
    p95_index = max(
        0, int(math.ceil(
            0.95
            * len(sorted_latencies)))
        - 1) if sorted_latencies else 0
    metrics = {
        "build_cost_parity_count": sum(
            row["build_cost_parity"]
            for row in emitted),
        "candidate_count": len(rows),
        "deterministic_repeated_estimates":
            deterministic,
        "emitted_count": len(emitted),
        "grounded_immediate_product_claim_count":
            len(grounded_zero),
        "grounded_product_available_now_true_count":
            sum(
                row[
                    "grounded_product_available_now"]
                is True
                for row in emitted),
        "legacy_zero_turn_eta_count":
            len(legacy_zero),
        "legacy_zero_turn_switch_eta_count":
            len(legacy_zero_switches),
        "mean_latency_ms": (
            statistics.mean(
                latencies)
            if latencies else 0.0),
        "p95_latency_ms": (
            sorted_latencies[
                p95_index]
            if sorted_latencies else 0.0),
        "switch_history_uncertainty_exposed_count":
            sum(
                row[
                    "switch_cost_status"]
                == "unresolved"
                for row in emitted),
    }
    gates = {
        "all_retained_production_candidates_grounded":
            len(emitted) == len(rows)
            and bool(rows),
        "compiled_build_cost_parity":
            metrics[
                "build_cost_parity_count"]
            == len(emitted),
        "deterministic":
            deterministic,
        "no_immediate_product_availability":
            metrics[
                "grounded_product_available_now_true_count"]
            == 0,
        "no_zero_turn_completion_forecast":
            len(grounded_zero) == 0,
        "simpler_baseline_failure_observed":
            len(legacy_zero_switches) > 0,
    }
    report = {
        "authority": {
            "claim_status":
                "diagnostic-replay-only",
            "policy_authority_eligible":
                False,
        },
        "fixture_count": fixture_count,
        "gates": gates,
        "iterations": args.iterations,
        "manifest": args.manifest,
        "manifest_hash":
            manifest["manifest_hash"],
        "metrics": metrics,
        "passed": all(
            gates.values()),
        "rows": rows,
        "ruleset": manifest[
            "ruleset"],
        "schema_version": "1.0",
    }
    report["report_hash"] = (
        structural_hash(report))
    output_path = os.path.join(
        REPO, args.output)
    with open(
            output_path,
            "wb") as stream:
        stream.write(
            canonical_json_bytes(
                report))
        stream.write(b"\n")
    print(json.dumps({
        "metrics": metrics,
        "output": args.output,
        "passed": report["passed"],
        "report_hash":
            report["report_hash"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
