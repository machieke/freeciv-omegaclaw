"""Predeclared paired-policy aggregation, power planning, and fidelity report."""

import copy
import json
import os

import jsonschema

from freeciv_agent.events.schema import canonical_json_bytes
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.paths import repo_path

from .aggregate import METRICS, _game_rows, _read_events, _summary
from .config import load
from .statistics import (paired_binary_discordance, paired_binary_effect,
                         paired_delta, paired_power, paired_score_randomization,
                         paired_win_design_power)


def _interval(result, digits=3):
    if result["estimate"] is None:
        return "n/a (n=0)"
    template = "{{:.{0}f}} [{{:.{0}f}}, {{:.{0}f}}]".format(digits)
    return template.format(result["estimate"], result["lower"], result["upper"])


def _historical_failures(out, cohort):
    root = os.path.join(os.path.abspath(out), "attempt-history")
    result = []
    for directory, _, files in os.walk(root):
        if "manifest.json" not in files or "status.json" not in files:
            continue
        manifest = json.load(open(
            os.path.join(directory, "manifest.json"), encoding="utf-8"))
        status = json.load(open(
            os.path.join(directory, "status.json"), encoding="utf-8"))
        if (manifest.get("track") != "impact_pair"
                or status.get("status") == "completed"):
            continue
        pair = manifest.get("impact_pair", {})
        if pair.get("cohort", "development") != cohort:
            continue
        result.append({
            "arm": pair.get("arm"), "attempt_id": manifest.get("attempt_id"),
            "error": status.get("error"), "game_id": manifest.get("game_id"),
            "historical": True, "pair_index": pair.get("pair_index"),
            "seed": manifest.get("seed"), "status": status.get("status"),
            "within_pair_order": pair.get("within_pair_order"),
        })
    return result


def _source_freeze(source_rows, cohort, run_summary):
    commits = sorted(set(
        row["source"].get("commit") for row in source_rows
        if row["source"].get("commit")))
    implementation_sha256s = sorted(set(
        row["source"].get("implementation_sha256") for row in source_rows
        if row["source"].get("implementation_sha256")))
    dirty_games = sorted(
        row["game_id"] for row in source_rows if row["source"].get("dirty") is not False)
    unavailable_games = sorted(
        row["game_id"] for row in source_rows
        if row["source"].get("commit") in (None, "", "unavailable"))
    required = cohort["require_clean_source"]
    run_source_stable = run_summary.get("source_stable") if run_summary else None
    passed = (not required or (
        bool(source_rows) and not dirty_games and not unavailable_games
        and len(commits) == 1 and len(implementation_sha256s) == 1
        and run_source_stable is True))
    return {
        "commits": commits, "dirty_games": dirty_games,
        "implementation_sha256s": implementation_sha256s,
        "required": required, "passed": passed,
        "run_source_stable": run_source_stable,
        "unavailable_games": unavailable_games,
    }


def _claim_evaluation(design, cohort, complete_pairs, incomplete_pairs,
                      active_failures, order_violations, safety, source_freeze,
                      primary, score_test, meaningful_score_test,
                      win_effect, binary, power):
    endpoints = set(cohort["endpoints"])
    outcomes = design["outcomes"]
    claims = design["claims"]
    common_reasons = []
    if complete_pairs != cohort["planned_pairs"]:
        common_reasons.append("all {} predeclared pairs must complete".format(
            cohort["planned_pairs"]))
    if incomplete_pairs:
        common_reasons.append("incomplete pairs remain")
    if active_failures:
        common_reasons.append("active infrastructure failures remain")
    if order_violations:
        common_reasons.append("within-pair order violations remain")
    if not safety["overall_passed"]:
        common_reasons.append("absolute safety gates did not pass")
    if not source_freeze["passed"]:
        common_reasons.append("source-freeze gate did not pass")

    result = {
        "alpha": design["power"]["alpha"],
        "claim_eligible_cohort": cohort["claim_eligible"],
        "claimable": [], "common_reasons": common_reasons,
        "multiplicity": claims["multiplicity"],
    }
    score_declared = outcomes["score_metric"] in endpoints
    if not score_declared:
        score = {"status": "not_declared"}
    elif not cohort["claim_eligible"]:
        score = {"status": "ineligible"}
    elif common_reasons:
        score = {"status": "not_ready"}
    elif not power["ready"]:
        score = {"status": "not_ready", "reason": power["reason"]}
    elif not score_test["ready"]:
        score = {"status": "not_ready", "reason": score_test["reason"]}
    else:
        margin = claims["score_superiority_margin"]
        meaningful = claims["meaningful_score_delta"]
        interval_passed = primary["lower"] is not None and primary["lower"] > margin
        randomization_passed = score_test["p_value"] <= design["power"]["alpha"]
        passed = interval_passed and randomization_passed
        meaningful_interval_passed = bool(
            primary["lower"] is not None and primary["lower"] > meaningful)
        meaningful_randomization_passed = bool(
            meaningful_score_test["ready"]
            and meaningful_score_test["observed_mean_difference"] > 0
            and meaningful_score_test["p_value"] <= design["power"]["alpha"])
        meaningful_passed = (
            passed and meaningful_interval_passed
            and meaningful_randomization_passed)
        score = {
            "estimate": primary["estimate"], "lower": primary["lower"],
            "interval_passed": bool(interval_passed),
            "meaningful_margin": meaningful,
            "meaningful_interval_passed": meaningful_interval_passed,
            "meaningful_passed": bool(meaningful_passed),
            "meaningful_randomization_p": meaningful_score_test["p_value"],
            "meaningful_randomization_passed": meaningful_randomization_passed,
            "passed": bool(passed), "status": "passed" if passed else "failed",
            "randomization_p": score_test["p_value"],
            "randomization_passed": bool(randomization_passed),
            "superiority_margin": margin, "upper": primary["upper"],
        }
        if passed:
            result["claimable"].append("score_improvement")
        if meaningful_passed:
            result["claimable"].append("meaningful_score_improvement")
    result["score"] = score

    win_declared = outcomes["win_metric"] in endpoints
    if not win_declared:
        win = {"status": "not_declared"}
    elif not cohort["claim_eligible"]:
        win = {"status": "ineligible"}
    elif common_reasons:
        win = {"status": "not_ready"}
    elif score_declared and score.get("status") != "passed":
        win = {
            "reason": "hierarchical score gate did not pass",
            "status": "gated",
        }
    else:
        margin = claims["win_superiority_margin"]
        meaningful = claims["meaningful_win_rate_delta"]
        passed = (
            win_effect["lower"] is not None and win_effect["lower"] > margin
            and binary["exact_mcnemar_p"] <= design["power"]["alpha"])
        win = {
            "estimate": win_effect["estimate"],
            "exact_mcnemar_p": binary["exact_mcnemar_p"],
            "lower": win_effect["lower"], "meaningful_margin": meaningful,
            "meaningful_passed": bool(
                win_effect["lower"] is not None and win_effect["lower"] > meaningful),
            "passed": bool(passed), "status": "passed" if passed else "failed",
            "superiority_margin": margin, "upper": win_effect["upper"],
        }
        if passed:
            result["claimable"].append("fixed_horizon_score_lead_rate_improvement")
    result["win_rate"] = win
    if not cohort["claim_eligible"]:
        result["status"] = "ineligible"
    elif common_reasons:
        result["status"] = "not_ready"
    elif result["claimable"]:
        result["status"] = "claim_supported"
    else:
        result["status"] = "no_claim"
    return result


def aggregate_impact_pairs(out, config_path=None, cohort=None):
    config = load(config_path)
    design = config.get("paired_impact")
    if design is None:
        raise ValueError("configuration does not declare paired_impact")
    cohort_name = cohort or design["default_cohort"]
    if cohort_name not in design["cohorts"]:
        raise ValueError("unknown paired impact cohort {}".format(cohort_name))
    design = copy.deepcopy(design)
    cohort_design = design["cohorts"][cohort_name]
    design["arms"] = copy.deepcopy(
        cohort_design.get("arms", design["arms"]))
    design["outcomes"]["horizon_turn"] = cohort_design.get(
        "horizon_turn", design["outcomes"]["horizon_turn"])
    if "score_design" in cohort_design:
        design["power"]["score"] = dict(
            cohort_design["score_design"],
            planned_pairs=cohort_design["planned_pairs"])
    declared_seeds = set(cohort_design["seeds"])
    records = []
    failures = []
    seen = set()
    source_rows = []
    for directory, manifest, status in _game_rows(out):
        if manifest.get("track") != "impact_pair":
            continue
        pair = manifest.get("impact_pair", {})
        if pair.get("cohort", "development") != cohort_name:
            continue
        if manifest.get("configuration_hash") != config["configuration_hash"]:
            raise ValueError(
                "impact pair manifest {} belongs to another configuration".format(
                    manifest.get("game_id")))
        arm = pair.get("arm")
        if manifest["seed"] not in declared_seeds:
            raise ValueError("impact pair seed {} is not declared for cohort {}".format(
                manifest["seed"], cohort_name))
        key = (manifest["seed"], arm)
        if arm not in ("baseline", "treatment") or key in seen:
            raise ValueError("invalid or duplicate impact pair arm {}".format(key))
        expected_policy = dict(
            config["impact_policy"], **design["arms"][arm])
        expected_policy["horizon_turn"] = design["outcomes"]["horizon_turn"]
        if manifest.get("impact_policy") != expected_policy:
            raise ValueError(
                "impact pair arm {} does not match its isolated policy"
                .format(key))
        seen.add(key)
        source_rows.append({
            "arm": arm, "game_id": manifest["game_id"],
            "seed": manifest["seed"], "source": manifest.get("source", {}),
        })
        base = {
            "arm": arm, "error": status.get("error"),
            "game_id": manifest["game_id"], "pair_index": pair.get("pair_index"),
            "historical": False, "seed": manifest["seed"],
            "status": status.get("status"),
            "within_pair_order": pair.get("within_pair_order"),
        }
        if status.get("status") != "completed":
            failures.append(base)
            continue
        metrics, _ = _read_events(os.path.join(directory, "events.jsonl"))
        records.append(dict(base, manifest=manifest, metrics=metrics, status_row=status))

    by_seed = {}
    for row in records:
        by_seed.setdefault(row["seed"], {})[row["arm"]] = row
    complete_seeds = sorted(
        seed for seed, arms in by_seed.items()
        if set(arms) == {"baseline", "treatment"})
    attempted_seeds = sorted(set(seed for seed, _ in seen))
    incomplete = []
    for seed in attempted_seeds:
        completed = sorted(by_seed.get(seed, {}))
        if len(completed) != 2:
            incomplete.append({"completed_arms": completed, "seed": seed})

    statistics = config["statistics"]
    paired_rows = [row for row in records if row["seed"] in complete_seeds]
    arms = {}
    for arm in ("baseline", "treatment"):
        all_arm = [row for row in records if row["arm"] == arm]
        selected = [row for row in paired_rows if row["arm"] == arm]
        arms[arm] = {
            "completed_games": len(all_arm), "paired_games": len(selected),
            "metrics": {metric: _summary(
                [row["metrics"] for row in selected], metric, statistics)
                for metric in METRICS},
            "seeds": sorted(row["seed"] for row in selected),
        }

    paired_deltas = {}
    for metric in METRICS:
        left = {row["seed"]: row["metrics"][metric] for row in paired_rows
                if row["arm"] == "baseline" and metric in row["metrics"]}
        right = {row["seed"]: row["metrics"][metric] for row in paired_rows
                 if row["arm"] == "treatment" and metric in row["metrics"]}
        paired_deltas[metric] = paired_delta(
            left, right, samples=(
                design["power"]["primary_bootstrap_samples"]
                if metric in (design["outcomes"]["score_metric"],
                              design["outcomes"]["win_metric"])
                else statistics["bootstrap_samples"]),
            seed=statistics["bootstrap_seed"],
            confidence=statistics["confidence"])

    win_metric = design["outcomes"]["win_metric"]

    def win_value(row):
        # Pre-hardening development artifacts used ``game_win`` for this same
        # fixed-horizon score comparison. New manifests always emit the explicit
        # endpoint; the fallback keeps old development evidence re-aggregatable.
        return row["metrics"].get(win_metric, row["metrics"].get("game_win"))

    left_wins = {row["seed"]: win_value(row) for row in paired_rows
                 if row["arm"] == "baseline" and win_value(row) is not None}
    right_wins = {row["seed"]: win_value(row) for row in paired_rows
                  if row["arm"] == "treatment" and win_value(row) is not None}
    binary = paired_binary_discordance(left_wins, right_wins)
    win_effect = paired_binary_effect(
        left_wins, right_wins,
        samples=design["power"]["primary_bootstrap_samples"],
        seed=statistics["bootstrap_seed"], confidence=statistics["confidence"])
    score_metric = design["outcomes"]["score_metric"]
    score_left = {row["seed"]: row["metrics"][score_metric] for row in paired_rows
                  if row["arm"] == "baseline" and score_metric in row["metrics"]}
    score_right = {row["seed"]: row["metrics"][score_metric] for row in paired_rows
                   if row["arm"] == "treatment" and score_metric in row["metrics"]}
    score_differences = [score_right[seed] - score_left[seed]
                         for seed in sorted(set(score_left) & set(score_right))]
    score_test_config = design["claims"]["score_test"]
    score_randomization = paired_score_randomization(
        score_differences,
        margin=design["claims"]["score_superiority_margin"],
        maximum_states=score_test_config["maximum_states"])
    score_meaningful_randomization = paired_score_randomization(
        score_differences,
        margin=design["claims"]["meaningful_score_delta"],
        maximum_states=design["claims"]["meaningful_score_test"]["maximum_states"],
        alternative=design["claims"]["meaningful_score_test"]["alternative"])
    power = paired_power(
        score_differences, alpha=design["power"]["alpha"],
        target_power=design["power"]["target_power"],
        minimum_detectable_delta=design["power"]["score"][
            "minimum_detectable_delta"],
        minimum_pairs=design["power"]["minimum_variance_pairs"])
    if not power["ready"]:
        power["recommendation"] = power["reason"]
    elif cohort_design["purpose"] == "pilot":
        power["recommendation"] = "freeze a fresh confirmatory sample of at least {} pairs".format(
            power["required_pairs"])
    elif power["required_pairs"] <= cohort_design["planned_pairs"]:
        power["recommendation"] = "predeclared cohort meets the variance-based planning target"
    else:
        power["recommendation"] = (
            "predeclared cohort is smaller than the variance-based planning estimate of {}"
            .format(power["required_pairs"]))
    win_power = paired_win_design_power(
        design["power"]["win"]["planned_pairs"],
        design["power"]["win"]["minimum_detectable_delta"],
        design["power"]["win"]["planned_discordance"],
        alpha=design["power"]["alpha"],
        target_power=design["power"]["target_power"])

    order_counts = {"baseline_first": 0, "treatment_first": 0}
    order_violations = []
    for seed in complete_seeds:
        rows = by_seed[seed]
        first = min(rows.values(), key=lambda row: row["within_pair_order"])["arm"]
        order_counts["{}_first".format(first)] += 1
        pair_index = rows["baseline"]["pair_index"]
        expected = "baseline" if pair_index % 2 == 0 else "treatment"
        if first != expected:
            order_violations.append(seed)

    safety = {}
    for metric, expected in (
            ("engine_rejected_action_rate", 0.0),
            ("model_safe_fallback_rate", 0.0),
            ("full_loop_under_30s_rate", 1.0)):
        values = {arm: arms[arm]["metrics"][metric]["estimate"]
                  for arm in ("baseline", "treatment")}
        evaluated = all(value is not None for value in values.values())
        safety[metric] = {
            "arms": values, "evaluated": evaluated,
            "expected": expected,
            "passed": (all(value == expected for value in values.values())
                       if evaluated else None),
        }
    initial_state_mismatches = []
    initial_state_unavailable = []
    for seed in complete_seeds:
        rows = by_seed[seed]
        fingerprints = {
            arm: rows[arm]["status_row"].get("initial_state_fingerprint")
            for arm in ("baseline", "treatment")}
        if not all(fingerprints.values()):
            initial_state_unavailable.append(seed)
        elif fingerprints["baseline"] != fingerprints["treatment"]:
            initial_state_mismatches.append(seed)
    fidelity_evaluated = bool(complete_seeds) and not initial_state_unavailable
    safety["paired_initial_state_fidelity"] = {
        "evaluated": fidelity_evaluated,
        "mismatch_count": len(initial_state_mismatches),
        "mismatch_seeds": initial_state_mismatches,
        "passed": bool(fidelity_evaluated and not initial_state_mismatches),
        "unavailable_seeds": initial_state_unavailable,
    }
    active_failures = [row for row in failures if not row["historical"]]
    safety["overall_passed"] = (
        not active_failures and not order_violations
        and all(row["passed"] is not False for row in safety.values()
                if isinstance(row, dict)))

    summary_path = os.path.join(os.path.abspath(out), "impact-run-summary.json")
    run_summary = (json.load(open(summary_path, encoding="utf-8"))
                   if os.path.isfile(summary_path) else None)
    if (run_summary is not None
            and run_summary.get("cohort", cohort_name) != cohort_name):
        run_summary = None
    source_freeze = _source_freeze(source_rows, cohort_design, run_summary)
    claim_evaluation = _claim_evaluation(
        design, cohort_design, len(complete_seeds), incomplete,
        active_failures, order_violations, safety, source_freeze,
        paired_deltas[design["primary_metric"]], score_randomization,
        score_meaningful_randomization, win_effect, binary, power)
    failures.extend(_historical_failures(out, cohort_name))
    aggregate = {
        "schema_version": "1.0", "configuration_hash": config["configuration_hash"],
        "design": {
            "arms": design["arms"], "condition": design["condition"],
            "experimental_unit": design["experimental_unit"],
            "cohort": cohort_name,
            "cohort_purpose": cohort_design["purpose"],
            "claim_eligible": cohort_design["claim_eligible"],
            "isolated_policy_keys": cohort_design.get(
                "isolated_policy_keys"),
            "endpoints": cohort_design["endpoints"],
            "outcomes": design["outcomes"],
            "order": design["order"], "order_counts": order_counts,
            "order_violations": order_violations,
            "predeclared_pairs": cohort_design["planned_pairs"],
            "primary_metric": design["primary_metric"],
        },
        "attempted_pairs": len(attempted_seeds), "complete_pairs": len(complete_seeds),
        "complete_seeds": complete_seeds, "incomplete_pairs": incomplete,
        "arms": arms, "paired_deltas": paired_deltas,
        "primary_outcome": paired_deltas[design["primary_metric"]],
        "score_randomization": score_randomization,
        "score_meaningful_randomization": score_meaningful_randomization,
        "win_discordance": binary, "win_rate_difference": win_effect,
        "power_analysis": power, "win_power_analysis": win_power,
        "source_freeze": source_freeze,
        "claim_evaluation": claim_evaluation,
        "safety_gates": safety,
        "failures": sorted(failures, key=lambda row: (
            row["seed"], row["arm"], row["historical"])),
        "methods": {
            "binary": (
                "paired seed bootstrap risk-difference interval plus exact two-sided McNemar"),
            "confidence": statistics["confidence"],
            "continuous": "deterministic percentile bootstrap of paired seed deltas",
            "score_test": (
                "exact two-sided paired sign-flip test for superiority and exact "
                "one-sided greater-than sign-flip test for the meaningful margin; "
                "both fail closed above the predeclared state bound"),
            "bootstrap_samples": statistics["bootstrap_samples"],
            "primary_bootstrap_samples": design["power"]["primary_bootstrap_samples"],
            "bootstrap_seed": statistics["bootstrap_seed"],
            "power": "paired normal approximation for planning, not a stopping rule",
            "multiplicity": design["claims"]["multiplicity"],
        },
    }
    schema = json.load(open(repo_path(
        "schemas", "freeciv-harness", "v1", "impact-paired.schema.json"),
        encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(aggregate)
    return aggregate


def write_impact_report(out, aggregate):
    out = os.path.abspath(out)
    path = os.path.join(out, "impact-aggregate.json")
    with open(path, "wb") as stream:
        stream.write(canonical_json_bytes(aggregate) + b"\n")
    primary = aggregate["primary_outcome"]
    score_randomization = aggregate["score_randomization"]
    meaningful_score_randomization = aggregate["score_meaningful_randomization"]
    binary = aggregate["win_discordance"]
    win_effect = aggregate["win_rate_difference"]
    power = aggregate["power_analysis"]
    win_power = aggregate["win_power_analysis"]
    claims = aggregate["claim_evaluation"]
    lines = [
        "# FreeCiv paired impact-policy evaluation", "",
        "Configuration: `{}`".format(aggregate["configuration_hash"]), "",
        "Cohort: `{}` (`{}`); confirmatory-claim eligible: `{}`.".format(
            aggregate["design"]["cohort"], aggregate["design"]["cohort_purpose"],
            aggregate["design"]["claim_eligible"]), "",
        "Experimental unit: `{}`; primary outcome: `{}`; predeclared pairs: `{}`.".format(
            aggregate["design"]["experimental_unit"],
            aggregate["design"]["primary_metric"],
            aggregate["design"]["predeclared_pairs"]), "",
        "Completed pairs: `{}` of `{}` attempted. Retained infrastructure failures: `{}`.".format(
            aggregate["complete_pairs"], aggregate["attempted_pairs"],
            len(aggregate["failures"])), "",
        "## Primary outcome", "",
        "Treatment minus baseline score: `{}`. This interval uses games/seeds as the "
        "experimental units, not actions.".format(_interval(primary, 2)), "",
        "Exact two-sided paired sign-flip test against the zero-point superiority "
        "margin: ready `{}`, p `{}`, states `{}`. The one-sided greater-than test "
        "against the declared meaningful margin of `{}` points is ready `{}`, p `{}`."
        .format(
            score_randomization["ready"], score_randomization["p_value"],
            score_randomization["states_evaluated"],
            meaningful_score_randomization["margin"],
            meaningful_score_randomization["ready"],
            meaningful_score_randomization["p_value"]), "",
        "## Fixed-horizon score-lead rate", "",
        "This endpoint means player score > opponent score at turn `{}`; ties are "
        "non-wins. It is not labeled as an engine-reported terminal victory.".format(
            aggregate["design"]["outcomes"]["horizon_turn"]), "",
        "Treatment minus baseline score-lead rate: `{}`.".format(
            _interval(win_effect, 3)), "",
        "| Neither leads | Baseline only leads | Treatment only leads | Both lead | Discordant | Exact p |",
        "|---:|---:|---:|---:|---:|---:|",
        "| {} | {} | {} | {} | {} | {:.6f} |".format(
            binary["both_lose"], binary["baseline_only_win"],
            binary["treatment_only_win"], binary["both_win"],
            binary["discordant_pairs"], binary["exact_mcnemar_p"]), "",
        "## Mechanism deltas", "",
        "| Metric | Treatment - baseline (95% CI) | Pairs |", "|---|---:|---:|",
    ]
    for metric in (
            "opponent_score_turn_n", "score_margin_turn_n",
            "decision_effect_observed_rate", "decision_effect_confirmation_latency_ms",
            "decision_effect_confirmation_timeouts",
            "decision_effect_confirmation_deferred",
            "decision_effect_confirmation_recovered",
            "decision_effect_confirmation_expired",
            "decision_effect_confirmation_pending",
            "decision_no_effect_failover_recovery_rate",
            "positions_explored", "tactical_actions", "cities_gained", "cities_founded",
            "founder_production_changes", "settlement_attempts",
            "production_repurpose_changes",
            "production_preexpansion_growth_changes",
            "production_preexpansion_founder_changes",
            "production_military_score_changes",
            "settlement_completions", "planner_capability_pruned_worker_moves",
            "planner_nonprogress_moves_pruned",
            "planner_repeated_failed_destination_moves_pruned",
            "planner_founder_unreachable_moves_pruned",
            "planner_founder_cycle_moves_pruned",
            "planner_founder_attrition_moves_pruned",
            "planner_failed_settlement_sites_pruned",
            "planner_founder_route_successes",
            "planner_founder_route_failures",
            "planner_founder_route_success_rate",
            "planner_founder_cardinal_corridor_attempts",
            "planner_founder_cardinal_corridor_successes",
            "planner_founder_cardinal_corridor_success_rate",
            "planner_founder_settlement_site_preference_attempts",
            "planner_founder_settlement_site_preference_successes",
            "planner_founder_settlement_site_preference_success_rate",
            "planner_founder_escort_deferral_snapshots",
            "planner_founder_escort_defense_production_attempts",
            "planner_founder_escort_defense_production_successes",
            "planner_founder_escort_defense_production_success_rate",
            "planner_founder_escort_move_attempts",
            "planner_founder_escort_move_successes",
            "planner_founder_escort_move_success_rate",
            "planner_founder_escorted_settlement_attempts",
            "planner_founder_escorted_settlement_completions",
            "planner_founder_escorted_settlement_completion_rate",
            "planner_founder_capable_unit_types",
            "population_recovery_route_attempts",
            "population_recovery_route_successes",
            "population_recovery_route_success_rate",
            "population_recovery_attempts",
            "population_recovery_completions",
            "population_recovered",
            "technologies_acquired", "engine_rejected_action_rate",
            "production_projected_completion_eta_turns",
            "production_projected_score_value",
            "production_projected_unit_completions",
            "production_projected_unit_score_progress",
            "production_guaranteed_unit_score_points",
            "production_batch_incremental_unit_completions",
            "production_batch_guaranteed_unit_score_points",
            "production_projected_build_cost",
            "production_projected_shield_surplus",
            "production_projected_pop_cost",
            "production_projection_ruleset_source_rate",
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
            "score_component_citizen_delta", "score_component_technology_delta",
            "score_component_residual_turn_n",
            "full_loop_under_30s_rate", "model_safe_fallback_rate"):
        result = aggregate["paired_deltas"][metric]
        lines.append("| {} | {} | {} |".format(metric, _interval(result), result["n"]))
    lines.extend([
        "", "## Absolute safety gates", "",
        "| Gate | Baseline | Treatment | Expected | Result |", "|---|---:|---:|---:|---|",
    ])
    for metric in (
            "engine_rejected_action_rate", "model_safe_fallback_rate",
            "full_loop_under_30s_rate"):
        gate = aggregate["safety_gates"][metric]
        result = ("not evaluated" if not gate["evaluated"] else
                  "pass" if gate["passed"] else "fail")
        lines.append("| {} | {} | {} | {} | {} |".format(
            metric, gate["arms"]["baseline"], gate["arms"]["treatment"],
            gate["expected"], result))
    fidelity = aggregate["safety_gates"]["paired_initial_state_fidelity"]
    lines.extend([
        "", "Paired initial-state fidelity: `{}`; mismatches: `{}`; "
        "unavailable: `{}`.".format(
            "pass" if fidelity["passed"] else (
                "fail" if fidelity["passed"] is False else "not evaluated"),
            fidelity["mismatch_count"], len(fidelity["unavailable_seeds"])),
        "", "## Power planning", "",
        "Score planning ready: `{}`. Observed paired SD: `{}`. "
        "Minimum detectable score delta: `{}`. "
        "Required pairs at target power `{}`: `{}`. {}.".format(
            power["ready"], power["observed_paired_sd"],
            power["minimum_detectable_delta"],
            power["target_power"], power["required_pairs"], power["recommendation"]), "",
        "The predeclared McNemar design uses `{}` pairs, discordance `{}`, and a "
        "minimum absolute score-lead-rate delta of `{}`; exact planned power is `{:.3f}` "
        "(target met: `{}`).".format(
            win_power["planned_pairs"], win_power["planned_discordance"],
            win_power["minimum_detectable_delta"], win_power["planned_power"],
            win_power["target_met"]), "",
        "This calculation is planning guidance and must not be used to stop early after a "
        "favorable result.", "", "## Confirmatory claim gate", "",
        "Overall status: `{}`. Multiplicity procedure: `{}`. Claimable results: `{}`.".format(
            claims["status"], claims["multiplicity"], claims["claimable"]), "",
        "Score gate: `{}`; fixed-horizon score-lead-rate gate: `{}`.".format(
            claims["score"]["status"], claims["win_rate"]["status"]), "",
        "An eligible score claim requires both its confidence-interval lower bound "
        "above the declared margin and its exact paired-randomization p-value at or "
        "below alpha. A meaningful-score claim applies both checks again at the "
        "meaningful margin.", "",
        "Readiness blockers: `{}`.".format(claims["common_reasons"]), "",
        "## Source freeze", "",
        "Required: `{}`; passed: `{}`; run source stable: `{}`; commits: `{}`; "
        "implementation hashes: `{}`; dirty games: `{}`; "
        "unavailable identities: `{}`.".format(
            aggregate["source_freeze"]["required"],
            aggregate["source_freeze"]["passed"],
            aggregate["source_freeze"]["run_source_stable"],
            aggregate["source_freeze"]["commits"],
            aggregate["source_freeze"]["implementation_sha256s"],
            len(aggregate["source_freeze"]["dirty_games"]),
            len(aggregate["source_freeze"]["unavailable_games"])), "",
        "## Ordering and exclusions", "",
        "Baseline-first pairs: `{}`; treatment-first pairs: `{}`; order violations: `{}`.".format(
            aggregate["design"]["order_counts"]["baseline_first"],
            aggregate["design"]["order_counts"]["treatment_first"],
            len(aggregate["design"]["order_violations"])), "",
        "Incomplete active pairs: `{}`. Every failed arm remains in `failures`; active "
        "failures exclude both sides from paired estimates, while archived failures remain "
        "visible after a successful retry.".format(
            len(aggregate["incomplete_pairs"])), "",
    ])
    with open(os.path.join(out, "impact-report.md"), "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines))

    event_path = os.path.join(out, "impact-aggregate-events.jsonl")
    if os.path.exists(event_path):
        os.remove(event_path)
    writer = EventWriter(event_path, "impact-pair-aggregate", durable=False)
    root = writer.emit("run_started", 0, {
        "condition_id": "impact_pair_aggregate",
        "manifest_identity": aggregate["configuration_hash"]})
    parent = root["event_id"]
    for metric, result in aggregate["paired_deltas"].items():
        if result["estimate"] is None:
            continue
        event = writer.emit("metric_sample", 1, {
            "labels": {"source": "paired_impact_aggregate", "statistic": "delta"},
            "name": "{}__paired_delta".format(metric), "unit": "aggregate",
            "value": float(result["estimate"]),
        }, caused_by=[parent])
        parent = event["event_id"]
    writer.emit("run_completed", 1, {
        "status": "completed", "summary": {
            "claim_status": aggregate["claim_evaluation"]["status"],
            "claimable": aggregate["claim_evaluation"]["claimable"],
            "cohort": aggregate["design"]["cohort"],
            "pairs": aggregate["complete_pairs"]}},
        caused_by=[parent])
    return path
