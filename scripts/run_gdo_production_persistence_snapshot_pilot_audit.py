#!/usr/bin/env python3
"""Audit the corrected snapshot-local GDO-7A persistence pilot."""

import argparse
from collections import Counter
import glob
import hashlib
import json
import math
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.config import load as load_harness_config  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from run_gdo_production_persistence_pilot_audit import (  # noqa: E402
    DIVERGENCE_REASON,
    GUARD_REASON,
    MECHANISM,
    _combine,
    _delta,
    _events,
    _load,
    _mean,
    _sha256_file,
    analyze_trace,
)


COHORT = "grounded_production_persistence_snapshot_pilot_v2"


def _event_paths(root, cohort, arm):
    return sorted(glob.glob(os.path.join(
        root, "games", "impact_pair", cohort, arm,
        "e_full_loop", "*", "events.jsonl")))


def _distance(city, unit, state):
    coordinates = (
        city.get("x"), city.get("y"),
        unit.get("x"), unit.get("y"))
    if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in coordinates):
        return None
    map_state = state.get("payload", {}).get("map", {})
    topology = state.get("payload", {}).get(
        "grounded_context", {}).get("map_topology", {})
    width = map_state.get("width")
    height = map_state.get("height")
    if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in (width, height)):
        return None
    wrap_x = topology.get("wrap_x")
    wrap_y = topology.get("wrap_y")
    if not isinstance(wrap_x, bool) or not isinstance(wrap_y, bool):
        return None
    dx = abs(coordinates[0] - coordinates[2])
    dy = abs(coordinates[1] - coordinates[3])
    if wrap_x:
        dx = min(dx, width - dx)
    if wrap_y:
        dy = min(dy, height - dy)
    return max(dx, dy)


def _relinquishment_reasons(state, guard_payload, switch_action):
    if not isinstance(state, dict):
        return ["missing_authoritative_state"]
    own_state = state.get("payload", {}).get("own_state", {})
    city_id = guard_payload.get("protected_city_id")
    city = next((
        row for row in own_state.get("cities", ())
        if row.get("city_id") == city_id
    ), None)
    if city is None:
        return ["city_removed"]
    reasons = []
    protected = guard_payload.get("next_action", {})
    if (
            city.get("production_kind")
            != protected.get("production_kind")
            or city.get("production_value")
            != protected.get("production_value")):
        reasons.append("current_queue_identity_changed")
    if city.get("disorder") is True or city.get("had_famine") is True:
        reasons.append("disorder_or_famine")
    surplus = city.get("surplus")
    if not isinstance(surplus, list) or len(surplus) < 2:
        reasons.append("missing_output_state")
    else:
        food = surplus[0]
        shields = surplus[1]
        if (
                isinstance(food, bool)
                or not isinstance(food, (int, float))
                or not math.isfinite(food)
                or food < 0):
            reasons.append("negative_food")
        if (
                isinstance(shields, bool)
                or not isinstance(shields, (int, float))
                or not math.isfinite(shields)
                or shields <= 0):
            reasons.append("nonpositive_shields")
        safety = guard_payload.get("production_persistence_safety", {})
        build_cost = safety.get("build_cost")
        stock = city.get("shield_stock")
        maximum = guard_payload.get("persistence_maximum_remaining_turns")
        deadline = guard_payload.get("deadline_turn")
        if all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (build_cost, stock, maximum, deadline)
        ) and isinstance(shields, (int, float)) and shields > 0:
            remaining = max(1, int(math.ceil(
                max(0, build_cost - stock) / float(shields))))
            if (
                    remaining > maximum
                    or int(state.get("turn", 0)) + remaining > deadline):
                reasons.append("completion_bound_exceeded")
        elif "nonpositive_shields" not in reasons:
            reasons.append("missing_completion_bound_state")
    safety = guard_payload.get("production_persistence_safety", {})
    upkeep = safety.get("future_gold_upkeep")
    if isinstance(upkeep, int) and not isinstance(upkeep, bool) and upkeep > 0:
        economy = own_state.get("economy", {})
        gold = economy.get("gold")
        operating = economy.get("operating_gold_per_turn")
        if (
                economy.get("available") is not True
                or not isinstance(gold, int)
                or isinstance(gold, bool)
                or gold < upkeep
                or not isinstance(operating, int)
                or isinstance(operating, bool)
                or operating < 0):
            reasons.append("upkeep_unaffordable")
    enemies = state.get("payload", {}).get(
        "grounded_context", {}).get("visible_enemy_units")
    radius = guard_payload.get("persistence_threat_radius")
    if not isinstance(enemies, list) or not isinstance(radius, int):
        reasons.append("missing_threat_state")
    else:
        distances = [_distance(city, unit, state) for unit in enemies]
        if any(value is None for value in distances):
            reasons.append("missing_threat_state")
        elif any(value <= radius for value in distances):
            reasons.append("visible_threat")
    if (
            not isinstance(switch_action, dict)
            or switch_action.get("action_type") != "city_production"
            or switch_action.get("city_id") != city_id):
        reasons.append("missing_competing_switch")
    return sorted(set(reasons))


def analyze_snapshot_contract(events):
    accepted = {
        event.get("payload", {}).get("action_id")
        for event in events
        if (
            event.get("type") == "action_result"
            and event.get("payload", {}).get("status") == "accepted")
    }
    guards = []
    divergences = {}
    for index, event in enumerate(events):
        payload = event.get("payload", {})
        operation_id = payload.get("operation_id")
        if (
                event.get("type") == "operation_step_selected"
                and payload.get("mechanism") == MECHANISM
                and payload.get("reason_code") == GUARD_REASON):
            guards.append((index, event))
        if (
                event.get("type") == "operation_blocked"
                and payload.get("mechanism") == MECHANISM
                and payload.get("reason_code") == DIVERGENCE_REASON
                and operation_id not in divergences):
            divergences[operation_id] = (index, event)

    protected_violations = []
    guard_rows_by_operation = {}
    for index, event in guards:
        payload = event["payload"]
        operation_id = payload["operation_id"]
        guard_rows_by_operation.setdefault(operation_id, []).append(
            (index, event))
        boundary = next((
            offset for offset in range(index + 1, len(events))
            if events[offset].get("type") == "state_snapshot"
        ), len(events))
        excluded = set(payload.get("excluded_action_ids", ()))
        for candidate in events[index + 1:boundary]:
            candidate_payload = candidate.get("payload", {})
            action = candidate_payload.get("action")
            if (
                    candidate.get("type") == "action_sent"
                    and candidate_payload.get("action_id") in accepted
                    and isinstance(action, dict)
                    and hashlib.sha256(
                        canonical_json_bytes(action)).hexdigest() in excluded):
                protected_violations.append({
                    "action_id": candidate_payload.get("action_id"),
                    "operation_id": operation_id,
                    "snapshot_id": payload.get("snapshot_id"),
                    "turn": candidate.get("turn"),
                })

    reason_counts = Counter()
    unattributed = []
    attributed = []
    for operation_id, (divergence_index, divergence) in divergences.items():
        prior_guards = [
            row for row in guard_rows_by_operation.get(operation_id, ())
            if row[0] < divergence_index
        ]
        if not prior_guards:
            continue
        guard_index, guard_event = prior_guards[-1]
        protected = guard_event["payload"].get("next_action", {})
        city_id = guard_event["payload"].get("protected_city_id")
        switch_index = None
        switch_action = None
        for offset in range(guard_index + 1, divergence_index):
            candidate = events[offset]
            action = candidate.get("payload", {}).get("action")
            if (
                    candidate.get("type") == "action_sent"
                    and isinstance(action, dict)
                    and action.get("action_type") == "city_production"
                    and action.get("city_id") == city_id
                    and action != protected):
                switch_index = offset
                switch_action = action
        state_boundary = switch_index or divergence_index
        state = next((
            events[offset]
            for offset in range(state_boundary - 1, guard_index, -1)
            if events[offset].get("type") == "state_snapshot"
        ), None)
        reasons = _relinquishment_reasons(
            state, guard_event["payload"], switch_action)
        allowed = {
            "visible_threat", "disorder_or_famine", "negative_food",
            "nonpositive_shields", "completion_bound_exceeded",
            "upkeep_unaffordable", "current_queue_identity_changed",
            "city_removed",
        }
        accepted_reasons = sorted(set(reasons) & allowed)
        row = {
            "divergence_turn": divergence.get("turn"),
            "last_guard_snapshot_id": guard_event["payload"].get(
                "snapshot_id"),
            "last_guard_turn": guard_event.get("turn"),
            "operation_id": operation_id,
            "reasons": accepted_reasons,
        }
        if accepted_reasons:
            attributed.append(row)
            reason_counts.update(accepted_reasons)
        else:
            row["diagnostics"] = reasons
            unattributed.append(row)
    return {
        "attributed_relinquishments": attributed,
        "guard_rows": len(guards),
        "protected_snapshot_switches": protected_violations,
        "relinquishment_reason_counts": dict(sorted(reason_counts.items())),
        "unattributed_relinquishments": unattributed,
    }


def _combine_snapshot_contract(rows):
    counts = Counter()
    protected = []
    unattributed = []
    attributed = []
    for row in rows:
        counts["guard_rows"] += row["guard_rows"]
        counts.update(row["relinquishment_reason_counts"])
        protected.extend(row["protected_snapshot_switches"])
        unattributed.extend(row["unattributed_relinquishments"])
        attributed.extend(row["attributed_relinquishments"])
    return {
        "attributed_relinquishment_count": len(attributed),
        "guard_rows": counts.pop("guard_rows", 0),
        "protected_snapshot_switch_count": len(protected),
        "protected_snapshot_switches": protected,
        "relinquishment_reason_counts": dict(sorted(counts.items())),
        "unattributed_relinquishment_count": len(unattributed),
        "unattributed_relinquishments": unattributed,
    }


def run(root, profile, cohort=COHORT):
    aggregate_path = os.path.join(root, "impact-aggregate.json")
    aggregate = _load(aggregate_path)
    if aggregate.get("design", {}).get("cohort") != cohort:
        raise ValueError("aggregate cohort does not match requested audit")
    config = load_harness_config(profile)
    cohort_config = config["paired_impact"]["cohorts"][cohort]
    design = cohort_config["production_persistence_snapshot_design"]
    expected = int(aggregate.get("complete_pairs", 0))
    paths = {
        arm: _event_paths(root, cohort, arm)
        for arm in ("baseline", "treatment")
    }
    if any(len(value) != expected for value in paths.values()):
        raise ValueError("cohort trace counts do not match complete pairs")
    arms = {}
    contracts = {}
    paired_metrics = {}
    trace_sources = []
    validation = Counter()
    for arm in ("baseline", "treatment"):
        analyses = []
        contract_rows = []
        for path in paths[arm]:
            report = validate_file(path)
            validation["event_count"] += report.event_count
            validation["error_count"] += len(report.errors)
            validation["warning_count"] += len(report.warnings)
            events = _events(path)
            analysis = analyze_trace(events)
            analyses.append(analysis)
            contract_rows.append(analyze_snapshot_contract(events))
            manifest = _load(os.path.join(os.path.dirname(path), "manifest.json"))
            seed = int(manifest["seed"])
            paired_metrics.setdefault(seed, {})[arm] = analysis["metrics"]
            trace_sources.append({
                "arm": arm,
                "path": os.path.relpath(path, root),
                "seed": seed,
                "sha256": _sha256_file(path),
            })
        arms[arm] = _combine(analyses)
        contracts[arm] = _combine_snapshot_contract(contract_rows)
    baseline = arms["baseline"]
    treatment = arms["treatment"]
    divergence_delta = _delta(
        treatment["queue_divergence_rate_per_commit"],
        baseline["queue_divergence_rate_per_commit"])
    completion_delta = _delta(
        treatment["completion_rate_per_commit"],
        baseline["completion_rate_per_commit"])
    products_delta = _delta(
        treatment["completed_products_per_game"],
        baseline["completed_products_per_game"])
    score_deltas = [
        values["treatment"]["score_turn_n"]
        - values["baseline"]["score_turn_n"]
        for values in paired_metrics.values()
        if (
            set(values) == {"baseline", "treatment"}
            and all(isinstance(
                values[arm]["score_turn_n"], (int, float))
                for arm in ("baseline", "treatment")))
    ]
    score_delta = _mean(score_deltas)
    engine_rejected = aggregate.get("safety_gates", {}).get(
        "engine_rejected_action_rate", {}).get("arms", {}).get("treatment")
    treatment_contract = contracts["treatment"]
    gates = {
        "all_predeclared_pairs_completed": (
            expected == cohort_config["planned_pairs"]),
        "baseline_has_no_persistence_authority": (
            baseline["authority_rows"] == 0),
        "completed_product_throughput_nonregression": (
            products_delta is not None and products_delta >= design[
                "minimum_completed_products_per_game_delta"]),
        "completion_rate_nonregression": (
            completion_delta is not None and completion_delta >= design[
                "minimum_completion_rate_delta"]),
        "engine_action_safety": (
            engine_rejected is not None and engine_rejected <= design[
                "maximum_engine_rejected_action_rate"]),
        "event_schema_valid": validation["error_count"] == 0,
        "later_relinquishments_attributed": (
            treatment_contract["unattributed_relinquishment_count"]
            <= design["maximum_unattributed_relinquishments"]),
        "persistence_authority_scope_valid": (
            len(treatment["scope_violations"])
            <= design["maximum_off_scope_authority_rows"]),
        "protected_snapshots_not_overridden": (
            treatment_contract["protected_snapshot_switch_count"]
            <= design["maximum_protected_snapshot_switches"]),
        "queue_divergence_reduced": (
            divergence_delta is not None
            and divergence_delta <= -design[
                "minimum_absolute_divergence_reduction"]),
        "score_mean_above_safety_floor": (
            score_delta is not None
            and score_delta >= design["minimum_mean_score_delta"]),
        "source_freeze_passed": (
            aggregate.get("source_freeze", {}).get("passed") is True),
        "treatment_persistence_authority_active": (
            treatment["authority_rows"] > 0
            and treatment["guarded_unique"] > 0),
    }
    ordered_sources = sorted(
        trace_sources, key=lambda row: (row["seed"], row["arm"]))
    return {
        "schema_version": "1.0",
        "cohort": cohort,
        "claim_eligible": False,
        "complete_pairs": expected,
        "planned_pairs": cohort_config["planned_pairs"],
        "design": design,
        "arms": arms,
        "snapshot_contract": contracts,
        "paired_deltas": {
            "completed_products_per_game": products_delta,
            "completion_rate_per_commit": completion_delta,
            "mean_score": score_delta,
            "queue_divergence_rate_per_commit": divergence_delta,
        },
        "gates": gates,
        "overall_passed": all(gates.values()),
        "validation": dict(sorted(validation.items())),
        "trace_sources": ordered_sources,
        "aggregate_source": {
            "path": os.path.relpath(aggregate_path, root),
            "sha256": _sha256_file(aggregate_path),
        },
        "audit_hash": hashlib.sha256(canonical_json_bytes({
            "cohort": cohort,
            "trace_sources": ordered_sources,
        })).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cohort_root")
    parser.add_argument(
        "--profile",
        default=os.path.join(REPO, "profile", "freeciv_harness.yaml"))
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
