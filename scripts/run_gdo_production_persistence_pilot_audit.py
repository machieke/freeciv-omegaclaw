#!/usr/bin/env python3
"""Audit the bounded GDO-7A production-persistence engine pilot."""

import argparse
from collections import Counter
import glob
import hashlib
import json
import math
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.config import load as load_harness_config  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402


COHORT = "grounded_production_persistence_pilot_v1"
MECHANISM = "gdo7a-production-enabling"
GUARD_REASON = "bounded-production-persistence-authority"
DIVERGENCE_REASON = (
    "production-target-diverged-before-product-observation")


def _fraction(numerator, denominator):
    return (
        None if not denominator
        else float(numerator) / float(denominator))


def _mean(values):
    return (
        None if not values
        else sum(values) / float(len(values)))


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(
            json.loads(line)
            for line in stream
            if line.strip())


def _event_paths(root, cohort, arm):
    return sorted(glob.glob(os.path.join(
        root, "games", "impact_pair",
        cohort, arm, "e_full_loop",
        "*", "events.jsonl")))


def _metric(events, name):
    values = [
        row.get("payload", {}).get("value")
        for row in events
        if (
            row.get("type") == "metric_sample"
            and row.get("payload", {}).get("name") == name)
    ]
    return values[-1] if values else None


def _guard_scope_violation(event, previous):
    payload = event.get("payload", {})
    operation_id = payload.get("operation_id")
    safety = payload.get(
        "production_persistence_safety", {})
    maximum = payload.get(
        "persistence_maximum_remaining_turns")
    remaining = safety.get("remaining_turns")
    future_upkeep = safety.get(
        "future_gold_upkeep")
    gold = safety.get("gold")
    operating = safety.get(
        "operating_gold_per_turn")
    protected_city_id = payload.get(
        "protected_city_id")
    protected_action = payload.get(
        "next_action")
    excluded_actions = payload.get(
        "excluded_actions")
    excluded_ids = payload.get(
        "excluded_action_ids")
    deadline = payload.get("deadline_turn")
    projected = payload.get(
        "projected_completion_turn")
    reasons = []
    if payload.get("policy_authority") is not True:
        reasons.append("policy-authority-not-true")
    if payload.get("shadow_only") is not False:
        reasons.append("authority-row-still-shadow")
    if payload.get("authority_effect") != (
            "exclude-competing-city-production-switches"):
        reasons.append("unexpected-authority-effect")
    if not excluded_ids:
        reasons.append("no-competing-action-excluded")
    if (
            not isinstance(protected_city_id, int)
            or isinstance(protected_city_id, bool)
            or not isinstance(protected_action, dict)
            or protected_action.get("action_type") != "city_production"
            or protected_action.get("city_id") != protected_city_id
            or payload.get("actor_id") != "city:{}".format(
                protected_city_id)):
        reasons.append("protected-production-identity-invalid")
    if (
            not isinstance(previous, dict)
            or previous.get("next_action") != protected_action):
        reasons.append("protected-action-changed-from-operation")
    if (
            not isinstance(excluded_actions, list)
            or not excluded_actions
            or any(
                not isinstance(action, dict)
                or action.get("action_type") != "city_production"
                or action.get("city_id") != protected_city_id
                or action == protected_action
                for action in excluded_actions)):
        reasons.append("excluded-action-outside-city-production-slot")
    if (
            isinstance(excluded_actions, list)
            and isinstance(excluded_ids, list)
            and [
                hashlib.sha256(
                    canonical_json_bytes(action)).hexdigest()
                for action in excluded_actions
            ] != excluded_ids):
        reasons.append("excluded-action-hash-mismatch")
    if (
            not isinstance(previous, dict)
            or previous.get("step_index") != 1
            or previous.get("state") not in (
                "activated", "repaired",
                "step_revalidated",
                "step_committed")):
        reasons.append("operation-not-active-observation-step")
    if safety.get("competing_active_operation_count") != 1:
        reasons.append("ambiguous-production-slot")
    if safety.get("city_disorder") is not False:
        reasons.append("city-in-disorder")
    if safety.get("city_had_famine") is not False:
        reasons.append("city-had-famine")
    if (
            not isinstance(
                safety.get("food_surplus"),
                (int, float))
            or isinstance(safety.get("food_surplus"), bool)
            or not math.isfinite(safety.get("food_surplus"))
            or safety.get("food_surplus") < 0):
        reasons.append("negative-or-missing-food")
    if (
            not isinstance(
                safety.get("shield_surplus"),
                (int, float))
            or isinstance(safety.get("shield_surplus"), bool)
            or not math.isfinite(safety.get("shield_surplus"))
            or safety.get("shield_surplus") <= 0):
        reasons.append("nonpositive-or-missing-shields")
    if (
            not isinstance(protected_action, dict)
            or safety.get("current_production_kind")
            != protected_action.get("production_kind")
            or safety.get("current_production_value")
            != protected_action.get("production_value")):
        reasons.append("current-queue-identity-not-protected")
    if safety.get("visible_threat_count") != 0:
        reasons.append("visible-threat-in-radius")
    if (
            not isinstance(maximum, int)
            or not isinstance(remaining, int)
            or remaining < 1
            or remaining > maximum):
        reasons.append("remaining-turn-bound-violated")
    if (
            not isinstance(projected, int)
            or not isinstance(deadline, int)
            or projected > deadline
            or projected != int(event.get("turn", 0)) + remaining):
        reasons.append("completion-deadline-violated")
    if (
            not isinstance(future_upkeep, int)
            or isinstance(future_upkeep, bool)
            or future_upkeep < 0):
        reasons.append("future-upkeep-invalid")
    elif (
            future_upkeep > 0
            and (
                not isinstance(gold, int)
                or isinstance(gold, bool)
                or gold < future_upkeep
                or not isinstance(operating, int)
                or isinstance(operating, bool)
                or operating < 0)):
        reasons.append("upkeep-affordability-violated")
    return (
        None if not reasons else {
            "operation_id": operation_id,
            "reasons": reasons,
            "snapshot_id": payload.get("snapshot_id"),
            "turn": event.get("turn"),
        })


def analyze_trace(events):
    proposals = set()
    committed = set()
    completed = set()
    terminal = set()
    diverged = set()
    guarded = set()
    authority_rows = 0
    previous_by_operation = {}
    scope_violations = []
    maximum_remaining_turns = set()
    threat_radii = set()
    for event in events:
        event_type = str(event.get("type", ""))
        payload = event.get("payload", {})
        if payload.get("mechanism") != MECHANISM:
            continue
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str):
            continue
        if (
                event_type == "operation_step_selected"
                and payload.get("reason_code") == GUARD_REASON):
            authority_rows += 1
            guarded.add(operation_id)
            maximum_remaining_turns.add(payload.get(
                "persistence_maximum_remaining_turns"))
            threat_radii.add(payload.get(
                "persistence_threat_radius"))
            violation = _guard_scope_violation(
                event,
                previous_by_operation.get(operation_id))
            if violation is not None:
                scope_violations.append(violation)
        if event_type == "operation_proposed":
            proposals.add(operation_id)
        elif event_type == "operation_step_committed":
            committed.add(operation_id)
        elif event_type == "operation_completed":
            completed.add(operation_id)
            terminal.add(operation_id)
        elif event_type in (
                "operation_failed", "operation_abandoned",
                "operation_expired"):
            terminal.add(operation_id)
        elif (
                event_type == "operation_blocked"
                and payload.get("reason_code")
                == DIVERGENCE_REASON):
            diverged.add(operation_id)
        previous_by_operation[operation_id] = dict(payload)
    return {
        "authority_rows": authority_rows,
        "committed_unique": len(committed),
        "completed_unique": len(completed),
        "diverged_unique": len(diverged),
        "guarded_diverged_unique": len(
            guarded & diverged),
        "guarded_unique": len(guarded),
        "nonterminal_unique": len(
            proposals - terminal),
        "proposed_unique": len(proposals),
        "scope_violations": scope_violations,
        "authority_parameters": {
            "maximum_remaining_turns": sorted(
                maximum_remaining_turns,
                key=lambda value: str(value)),
            "visible_threat_radius": sorted(
                threat_radii,
                key=lambda value: str(value)),
        },
        "metrics": {
            "engine_rejected_action_rate": _metric(
                events, "engine_rejected_action_rate"),
            "score_lead_turn_n": _metric(
                events, "score_lead_turn_n"),
            "score_turn_n": _metric(
                events, "score_turn_n"),
        },
    }


def _combine(rows):
    counts = Counter()
    scope_violations = []
    maximum_remaining_turns = set()
    threat_radii = set()
    for row in rows:
        counts.update({
            key: row[key]
            for key in (
                "authority_rows", "committed_unique",
                "completed_unique", "diverged_unique",
                "guarded_diverged_unique", "guarded_unique",
                "nonterminal_unique", "proposed_unique")
        })
        scope_violations.extend(
            row["scope_violations"])
        maximum_remaining_turns.update(
            row["authority_parameters"][
                "maximum_remaining_turns"])
        threat_radii.update(
            row["authority_parameters"][
                "visible_threat_radius"])
    return {
        **dict(counts),
        "completed_products_per_game": _mean([
            row["completed_unique"] for row in rows]),
        "completion_rate_per_commit": _fraction(
            counts["completed_unique"],
            counts["committed_unique"]),
        "queue_divergence_rate_per_commit": _fraction(
            counts["diverged_unique"],
            counts["committed_unique"]),
        "scope_violations": scope_violations,
        "authority_parameters": {
            "maximum_remaining_turns": sorted(
                maximum_remaining_turns,
                key=lambda value: str(value)),
            "visible_threat_radius": sorted(
                threat_radii,
                key=lambda value: str(value)),
        },
    }


def _delta(treatment, baseline):
    if treatment is None or baseline is None:
        return None
    return float(treatment) - float(baseline)


def run(root, profile, cohort=COHORT):
    aggregate_path = os.path.join(
        root, "impact-aggregate.json")
    aggregate = _load(aggregate_path)
    if aggregate.get("design", {}).get("cohort") != cohort:
        raise ValueError(
            "aggregate cohort does not match requested audit")
    config = load_harness_config(profile)
    cohort_config = config[
        "paired_impact"]["cohorts"][cohort]
    design = cohort_config[
        "production_persistence_design"]
    expected = int(aggregate.get("complete_pairs", 0))
    paths = {
        arm: _event_paths(root, cohort, arm)
        for arm in ("baseline", "treatment")
    }
    if any(len(value) != expected for value in paths.values()):
        raise ValueError(
            "cohort trace counts do not match complete pairs")
    arms = {}
    trace_sources = []
    validation = Counter()
    paired_metrics = {}
    for arm in ("baseline", "treatment"):
        analyses = []
        for path in paths[arm]:
            report = validate_file(path)
            validation["event_count"] += report.event_count
            validation["error_count"] += len(report.errors)
            validation["warning_count"] += len(report.warnings)
            events = _events(path)
            analysis = analyze_trace(events)
            analyses.append(analysis)
            manifest = _load(os.path.join(
                os.path.dirname(path), "manifest.json"))
            seed = int(manifest["seed"])
            paired_metrics.setdefault(seed, {})[
                arm] = analysis["metrics"]
            trace_sources.append({
                "arm": arm,
                "path": os.path.relpath(path, root),
                "seed": seed,
                "sha256": _sha256_file(path),
            })
        arms[arm] = _combine(analyses)
    baseline = arms["baseline"]
    treatment = arms["treatment"]
    score_deltas = [
        values["treatment"]["score_turn_n"]
        - values["baseline"]["score_turn_n"]
        for _, values in sorted(paired_metrics.items())
        if (
            set(values) == {"baseline", "treatment"}
            and isinstance(
                values["baseline"]["score_turn_n"],
                (int, float))
            and isinstance(
                values["treatment"]["score_turn_n"],
                (int, float)))
    ]
    divergence_delta = _delta(
        treatment["queue_divergence_rate_per_commit"],
        baseline["queue_divergence_rate_per_commit"])
    completion_delta = _delta(
        treatment["completion_rate_per_commit"],
        baseline["completion_rate_per_commit"])
    products_delta = _delta(
        treatment["completed_products_per_game"],
        baseline["completed_products_per_game"])
    score_delta = _mean(score_deltas)
    safety = aggregate.get("safety_gates", {})
    engine_rejected = safety.get(
        "engine_rejected_action_rate", {}).get(
            "arms", {}).get("treatment")
    gates = {
        "all_predeclared_pairs_completed": (
            expected == cohort_config["planned_pairs"]),
        "baseline_has_no_persistence_authority": (
            baseline["authority_rows"] == 0),
        "completed_product_throughput_nonregression": (
            products_delta is not None
            and products_delta >= design[
                "minimum_completed_products_per_game_delta"]),
        "completion_rate_nonregression": (
            completion_delta is not None
            and completion_delta >= design[
                "minimum_completion_rate_delta"]),
        "engine_action_safety": (
            engine_rejected is not None
            and engine_rejected <= design[
                "maximum_engine_rejected_action_rate"]),
        "event_schema_valid": (
            validation["error_count"] == 0),
        "guarded_operations_do_not_diverge": (
            treatment["guarded_diverged_unique"]
            <= design["maximum_guarded_divergences"]),
        "persistence_authority_scope_valid": (
            len(treatment["scope_violations"])
            <= design["maximum_off_scope_authority_rows"]),
        "persistence_authority_parameters_frozen": (
            treatment["authority_parameters"] == {
                "maximum_remaining_turns": [
                    design["maximum_remaining_turns"]],
                "visible_threat_radius": [
                    design["visible_threat_radius"]],
            }),
        "queue_divergence_reduced": (
            divergence_delta is not None
            and divergence_delta <= -design[
                "minimum_absolute_divergence_reduction"]),
        "score_mean_above_safety_floor": (
            score_delta is not None
            and score_delta >= design[
                "minimum_mean_score_delta"]),
        "source_freeze_passed": (
            aggregate.get("source_freeze", {}).get("passed")
            is True),
        "treatment_persistence_authority_active": (
            treatment["authority_rows"] > 0
            and treatment["guarded_unique"] > 0),
    }
    return {
        "schema_version": "1.0",
        "cohort": cohort,
        "claim_eligible": False,
        "complete_pairs": expected,
        "planned_pairs": cohort_config["planned_pairs"],
        "design": design,
        "arms": arms,
        "paired_deltas": {
            "completed_products_per_game": products_delta,
            "completion_rate_per_commit": completion_delta,
            "mean_score": score_delta,
            "queue_divergence_rate_per_commit": divergence_delta,
        },
        "gates": gates,
        "overall_passed": all(gates.values()),
        "validation": dict(sorted(validation.items())),
        "trace_sources": sorted(
            trace_sources,
            key=lambda row: (row["seed"], row["arm"])),
        "aggregate_source": {
            "path": os.path.relpath(aggregate_path, root),
            "sha256": _sha256_file(aggregate_path),
        },
        "audit_hash": hashlib.sha256(
            canonical_json_bytes({
                "cohort": cohort,
                "trace_sources": sorted(
                    trace_sources,
                    key=lambda row: (
                        row["seed"], row["arm"])),
            })).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cohort_root")
    parser.add_argument(
        "--profile",
        default=os.path.join(
            REPO, "profile", "freeciv_harness.yaml"))
    parser.add_argument("--cohort", default=COHORT)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = run(
        os.path.abspath(args.cohort_root),
        os.path.abspath(args.profile),
        cohort=args.cohort)
    encoded = canonical_json_bytes(result) + b"\n"
    if args.out:
        path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(encoded)
    sys.stdout.buffer.write(encoded)
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
