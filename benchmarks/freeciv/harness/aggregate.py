"""Metric-event-only deterministic aggregation and equal-fidelity report."""

import json
import math
import os

import jsonschema

from freeciv_agent.events.schema import canonical_json_bytes
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.events.validator import validate_file
from freeciv_agent.paths import repo_path

from .config import load
from .statistics import bootstrap_mean, paired_delta, wilson


METRICS = (
    "game_win", "score_lead_turn_n", "score_turn_n",
    "opponent_score_turn_n", "score_margin_turn_n",
    "engine_rejected_action_rate",
    "confabulation_write_through", "calibration_absolute_error",
    "plan_eta_absolute_error_turns", "replan_latency_ms", "loop_latency_ms",
    "induction_prediction_accuracy", "model_latency_ms",
    "turn_full_loop_latency_ms", "full_loop_under_30s_rate",
    "zombie_action_attempt_blocked", "abduction_truth_accuracy",
    "planned_engine_actions", "meaningful_actions_per_turn",
    "decision_impact_actions", "decision_impact_turn_rate",
    "decision_effect_observed_rate", "decision_no_effect_actions",
    "decision_effect_confirmation_latency_ms",
    "decision_effect_confirmation_timeouts",
    "decision_effect_confirmation_deferred",
    "decision_effect_confirmation_recovered",
    "decision_effect_confirmation_expired",
    "decision_effect_confirmation_pending",
    "decision_no_effect_retries_blocked",
    "decision_no_effect_failover_attempts",
    "decision_no_effect_failover_recoveries",
    "decision_no_effect_failover_recovery_rate",
    "model_safe_fallback_rate", "model_corrections_per_turn",
    "action_type_diversity", "cities_gained", "cities_founded", "technologies_acquired",
    "positions_explored", "production_changes", "tactical_actions",
    "founder_production_changes", "settlement_attempts",
    "production_repurpose_changes", "production_preexpansion_growth_changes",
    "production_military_score_changes",
    "settlement_completions", "planner_capability_pruned_worker_moves",
    "planner_nonprogress_moves_pruned", "planner_founder_unreachable_moves_pruned",
    "planner_repeated_failed_destination_moves_pruned",
    "planner_founder_route_successes", "planner_founder_route_failures",
    "planner_founder_route_success_rate",
    "planner_founder_cardinal_corridor_attempts",
    "planner_founder_cardinal_corridor_successes",
    "planner_founder_cardinal_corridor_success_rate",
    "planner_founder_capable_unit_types",
    "population_recovery_route_attempts", "population_recovery_route_successes",
    "population_recovery_route_success_rate",
    "population_recovery_attempts", "population_recovery_completions",
    "population_recovered",
    "production_projected_completion_eta_turns",
    "production_projected_score_value",
    "production_projected_unit_completions",
    "production_projected_unit_score_progress",
    "production_guaranteed_unit_score_points",
    "production_batch_incremental_unit_completions",
    "production_batch_guaranteed_unit_score_points",
    "production_projected_build_cost", "production_projected_shield_surplus",
    "production_projected_pop_cost", "production_projection_ruleset_source_rate",
    "production_projected_population_ready_eta_turns",
    "production_projected_settlement_eta_turns",
    "production_projected_settlement_runway_turns",
    "production_projected_founder_route_eta_turns",
    "production_projection_route_observed_source_rate",
    "production_projection_growth_ruleset_source_rate",
    "production_founder_deficit_before",
    "production_repurpose_avoided_population_cost",
    "production_repurpose_discarded_shield_stock",
    "production_repurpose_target_completion_rate",
    "production_preexpansion_sequence_settlement_eta_turns",
    "production_preexpansion_sequence_settlement_runway_turns",
    "score_component_citizens_turn_n", "score_component_technology_turn_n",
    "score_component_residual_turn_n", "score_component_citizen_delta",
    "score_component_technology_delta", "score_gain",
)


def _game_rows(out):
    root = os.path.join(os.path.abspath(out), "games")
    for directory, _, files in os.walk(root):
        if "manifest.json" not in files or "status.json" not in files:
            continue
        manifest = json.load(open(os.path.join(directory, "manifest.json"), encoding="utf-8"))
        status = json.load(open(os.path.join(directory, "status.json"), encoding="utf-8"))
        yield directory, manifest, status


def _read_events(path):
    report = validate_file(path)
    if not report.valid:
        raise ValueError("invalid event log {}: {}".format(path, report.to_dict()))
    values = {}
    calibration = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            if event["type"] == "metric_sample":
                payload = event["payload"]
                values.setdefault(payload["name"], []).append(payload["value"])
                if payload["name"] == "belief_calibration_sample":
                    labels = payload.get("labels", {})
                    truth = str(labels.get("truth", ""))
                    if truth not in ("0", "1"):
                        raise ValueError("calibration sample has non-binary truth in {}".format(path))
                    strength = float(payload["value"])
                    if not 0.0 <= strength <= 1.0:
                        raise ValueError("calibration strength outside [0,1] in {}".format(path))
                    calibration.append({
                        "atom_id": str(labels.get("atom_id", "unknown")),
                        "opponent": str(labels.get("opponent", "unknown")),
                        "strength": strength, "truth": int(truth),
                    })
    metrics = {name: sum(rows) / len(rows) for name, rows in values.items()
               if name != "belief_calibration_sample"}
    return metrics, calibration


def _calibration_group(samples, calibration):
    width = float(calibration["bucket_width"])
    buckets = {}
    for sample in samples:
        lower = math.floor(min(0.999999999, sample["strength"]) / width) * width
        name = "{:.1f}".format(lower)
        row = buckets.setdefault(name, {
            "bucket": name, "bucket_strength": round(lower + width / 2.0, 12),
            "samples": 0, "true": 0,
        })
        row["samples"] += 1
        row["true"] += int(sample["truth"])
    result = []
    for name in sorted(buckets):
        row = buckets[name]
        empirical = float(row["true"]) / row["samples"]
        error = abs(empirical - row["bucket_strength"])
        sufficient = row["samples"] >= calibration["minimum_bucket_samples"]
        result.append(dict(
            row, empirical_frequency=empirical, absolute_error=error,
            sufficient_sample=sufficient,
            within_tolerance=(error <= calibration["tolerance"]) if sufficient else None))
    return {"buckets": result, "samples": len(samples)}


def _calibration_report(rows, calibration=None):
    calibration = calibration or {
        "bucket_width": 0.1, "minimum_bucket_samples": 10, "tolerance": 0.15}
    samples = []
    for row in rows:
        for sample in row["calibration"]:
            samples.append(dict(
                sample, condition=row["manifest"]["condition_id"]))
    conditions = sorted(set(sample["condition"] for sample in samples))
    opponents = sorted(set(sample["opponent"] for sample in samples))
    return {
        "bucket_width": calibration["bucket_width"],
        "minimum_bucket_samples": calibration["minimum_bucket_samples"],
        "tolerance": calibration["tolerance"],
        "pooled": _calibration_group(samples, calibration),
        "per_condition": {
            condition: _calibration_group([
                sample for sample in samples if sample["condition"] == condition], calibration)
            for condition in conditions},
        "per_opponent": {
            opponent: _calibration_group([
                sample for sample in samples if sample["opponent"] == opponent], calibration)
            for opponent in opponents},
    }


def _summary(values, metric, statistics):
    if metric in ("game_win", "score_lead_turn_n"):
        return wilson(sum(value[metric] for value in values if metric in value),
                      sum(metric in value for value in values))
    return bootstrap_mean(
        [value[metric] for value in values if metric in value],
        samples=statistics["bootstrap_samples"], seed=statistics["bootstrap_seed"],
        confidence=statistics["confidence"])


def aggregate_runs(out, config_path=None):
    config = load(config_path)
    rows = []
    failures = []
    for directory, manifest, status in _game_rows(out):
        if status.get("status") != "completed":
            failures.append({
                "condition": manifest["condition_id"], "error": status.get("error"),
                "game_id": manifest["game_id"], "seed": manifest["seed"],
                "status": status.get("status"), "track": manifest["track"],
            })
            continue
        metrics, calibration = _read_events(os.path.join(directory, "events.jsonl"))
        rows.append(dict(manifest=manifest, metrics=metrics,
                         calibration=calibration, status=status))
    conditions = {}
    main = [row for row in rows if row["manifest"]["track"] == "main"]
    calibration = _calibration_report(main, config["calibration"])
    for condition in config["conditions"]:
        selected = [row for row in main if row["manifest"]["condition_id"] == condition]
        conditions[condition] = {
            "completed_games": len(selected),
            "losses": sum(bool(row["status"].get("loss")) for row in selected),
            "metrics": {metric: _summary([row["metrics"] for row in selected], metric,
                                         config["statistics"]) for metric in METRICS},
            "seeds": sorted(row["manifest"]["seed"] for row in selected),
        }
    marginal = {}
    for left, right in zip(config["conditions"], config["conditions"][1:]):
        name = "{}__to__{}".format(left, right)
        marginal[name] = {}
        left_rows = [row for row in main if row["manifest"]["condition_id"] == left]
        right_rows = [row for row in main if row["manifest"]["condition_id"] == right]
        for metric in METRICS:
            left_by_seed = {row["manifest"]["seed"]: row["metrics"][metric]
                            for row in left_rows if metric in row["metrics"]}
            right_by_seed = {row["manifest"]["seed"]: row["metrics"][metric]
                             for row in right_rows if metric in row["metrics"]}
            marginal[name][metric] = paired_delta(
                left_by_seed, right_by_seed,
                samples=config["statistics"]["bootstrap_samples"],
                seed=config["statistics"]["bootstrap_seed"],
                confidence=config["statistics"]["confidence"])
    induction_rows = [row for row in rows if row["manifest"]["track"] == "induction"]
    induction = {
        condition: {
            "games": len([row for row in induction_rows
                          if row["manifest"]["condition_id"] == condition]),
            "accuracy": _summary([
                row["metrics"] for row in induction_rows
                if row["manifest"]["condition_id"] == condition],
                "induction_prediction_accuracy", config["statistics"]),
        } for condition in ("d_uncertain_monitor", "e_full_loop")}
    oracle_delta = marginal["a_stock_llm__to__b_state_oracle"]["score_turn_n"]
    induction_delta = paired_delta(
        {row["manifest"]["sequence"]: 0.5 for row in induction_rows
         if row["manifest"]["condition_id"] == "e_full_loop"},
        {row["manifest"]["sequence"]: row["metrics"]["induction_prediction_accuracy"]
         for row in induction_rows if row["manifest"]["condition_id"] == "e_full_loop"},
        samples=config["statistics"]["bootstrap_samples"],
        seed=config["statistics"]["bootstrap_seed"],
        confidence=config["statistics"]["confidence"])
    induction["oracle_vs_induction"] = {
        "induction_accuracy_delta": induction_delta,
        "oracle_score_delta": oracle_delta,
        "prediction_assumed": False,
    }
    grading = {}
    grading_rows = [row for row in rows if row["manifest"]["track"].startswith("grading_")]
    for metric in ("game_win", "score_turn_n"):
        left = {row["manifest"]["seed"]: row["metrics"][metric] for row in grading_rows
                if row["manifest"]["track"] == "grading_ungraded"}
        right = {row["manifest"]["seed"]: row["metrics"][metric] for row in grading_rows
                 if row["manifest"]["track"] == "grading_graded"}
        grading[metric] = paired_delta(
            left, right, samples=config["statistics"]["bootstrap_samples"],
            seed=config["statistics"]["bootstrap_seed"],
            confidence=config["statistics"]["confidence"])
    grading["games_per_arm"] = min(
        sum(row["manifest"]["track"] == "grading_ungraded" for row in grading_rows),
        sum(row["manifest"]["track"] == "grading_graded" for row in grading_rows))
    aggregate = {
        "schema_version": "1.0", "configuration_hash": config["configuration_hash"],
        "conditions": conditions, "failures": sorted(
            failures, key=lambda row: (row["track"], row["condition"], row["seed"])),
        "grading_ab": grading, "induction": induction, "marginal_deltas": marginal,
        "calibration": calibration,
        "methods": {
            "binary": "Wilson score interval", "confidence": config["statistics"]["confidence"],
            "continuous": "deterministic percentile bootstrap of paired seed deltas",
            "bootstrap_samples": config["statistics"]["bootstrap_samples"],
            "bootstrap_seed": config["statistics"]["bootstrap_seed"],
        },
    }
    schema = json.load(open(repo_path(
        "schemas", "freeciv-harness", "v1", "aggregate.schema.json"), encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(aggregate)
    return aggregate


def write_report(out, aggregate):
    out = os.path.abspath(out)
    aggregate_path = os.path.join(out, "aggregate.json")
    with open(aggregate_path, "wb") as stream:
        stream.write(canonical_json_bytes(aggregate) + b"\n")
    lines = [
        "# PLN-FreeCiv five-condition evaluation", "",
        "Configuration: `{}`".format(aggregate["configuration_hash"]), "",
        "Statistical methods: {} for binary metrics; {}.".format(
            aggregate["methods"]["binary"], aggregate["methods"]["continuous"]), "",
        "## Conditions", "",
        "| Condition | Games | Losses | Win rate (95% CI) | Score at N (95% CI) |", "|---|---:|---:|---:|---:|",
    ]
    def interval(result, digits):
        if result["estimate"] is None:
            return "n/a (n=0)"
        template = "{{:.{0}f}} [{{:.{0}f}}, {{:.{0}f}}]".format(digits)
        return template.format(result["estimate"], result["lower"], result["upper"])

    for condition, row in aggregate["conditions"].items():
        win = row["metrics"]["game_win"]; score = row["metrics"]["score_turn_n"]
        lines.append("| {} | {} | {} | {} | {} |".format(
            condition, row["completed_games"], row["losses"],
            interval(win, 3), interval(score, 2)))
    lines.extend([
        "", "## Decision impact", "",
        "| Condition | Meaningful actions/turn | Impact actions | Impact-turn rate | "
        "Effect-observed rate | Failover recovery rate | No-effect retries blocked | "
        "Model fallback rate | "
        "Cities founded | "
        "Technologies acquired | Score gain |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for condition, row in aggregate["conditions"].items():
        metrics = row["metrics"]
        values = [metrics[name]["estimate"] for name in (
            "meaningful_actions_per_turn", "decision_impact_actions",
            "decision_impact_turn_rate", "decision_effect_observed_rate",
            "decision_no_effect_failover_recovery_rate",
            "decision_no_effect_retries_blocked", "model_safe_fallback_rate",
            "cities_founded",
            "technologies_acquired", "score_gain")]
        rendered = ["n/a" if value is None else "{:.3f}".format(value)
                    for value in values]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            condition, *rendered))
    lines.extend(["", "## Marginal effects", ""])
    for transition, metrics in aggregate["marginal_deltas"].items():
        lines.append("### {}".format(transition)); lines.append("")
        for metric, result in metrics.items():
            lines.append("- {}: delta={} CI=[{}, {}], n={}".format(
                metric, result["estimate"], result["lower"], result["upper"], result["n"]))
        lines.append("")
    lines.extend([
        "## Belief calibration", "",
        "Buckets use width `0.1`; a bucket needs at least `{}` samples and passes at "
        "absolute error at most `{}`.".format(
            aggregate["calibration"]["minimum_bucket_samples"],
            aggregate["calibration"]["tolerance"]), "",
        "| Bucket | Samples | Predicted | Empirical | Absolute error | Result |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for row in aggregate["calibration"]["pooled"]["buckets"]:
        result = ("insufficient-sample" if not row["sufficient_sample"] else
                  "pass" if row["within_tolerance"] else "fail")
        lines.append("| {} | {} | {:.2f} | {:.3f} | {:.3f} | {} |".format(
            row["bucket"], row["samples"], row["bucket_strength"],
            row["empirical_frequency"], row["absolute_error"], result))
    lines.append("")
    comparison = aggregate["induction"]["oracle_vs_induction"]
    lines.extend([
        "## Oracle versus induction prediction", "",
        "The prediction was tested, not assumed. Oracle score delta: `{}`. "
        "Induction accuracy delta: `{}`.".format(
            comparison["oracle_score_delta"]["estimate"],
            comparison["induction_accuracy_delta"]["estimate"]), "",
        "## Failures, losses, null and negative results", "",
        "Infrastructure failures: `{}`. Loss counts remain in the condition table; every "
        "negative or null marginal delta above is retained without relabeling.".format(
            len(aggregate["failures"])), "",
    ])
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    event_path = os.path.join(out, "aggregate-events.jsonl")
    if os.path.exists(event_path):
        os.remove(event_path)
    writer = EventWriter(event_path, "m7-aggregate", durable=False)
    root = writer.emit("run_started", 0, {
        "condition_id": "m7_aggregate", "manifest_identity": aggregate["configuration_hash"]})
    parent = root["event_id"]
    turn = 1
    for condition, row in aggregate["conditions"].items():
        for metric, result in row["metrics"].items():
            for statistic in ("estimate", "lower", "upper", "n"):
                value = result.get(statistic)
                if value is None:
                    continue
                event = writer.emit("metric_sample", turn, {
                    "labels": {"condition": condition, "statistic": statistic,
                               "source": "harness_aggregate"},
                    "name": metric if statistic == "estimate" else "{}__{}".format(metric, statistic),
                    "unit": "count" if statistic == "n" else "aggregate",
                    "value": float(value),
                }, caused_by=[parent])
                parent = event["event_id"]
    writer.emit("run_completed", turn, {
        "status": "completed", "summary": {"conditions": len(aggregate["conditions"])}},
        caused_by=[parent])
    return aggregate_path
