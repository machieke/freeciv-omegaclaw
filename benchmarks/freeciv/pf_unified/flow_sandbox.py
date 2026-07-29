"""Gate-G4 synthetic scientific-risk sandbox and flow decision."""

import math
import random
import time

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.flow_control import (
    CapacityKind,
    CapacityRecord,
    CommodityFlowRequest,
    FlowHealthMonitor,
    FlowHealthSample,
    FlowRepairPlanner,
    MultiCommodityCapacitySolver,
    default_normalization_contract,
)
from freeciv_agent.pressure import ResourceKind
from research.flow_control import (
    ABLATION_NAMES,
    BASELINE_NAMES,
    SYNTHETIC_FAMILIES,
    build_cohort,
    evaluate_selector,
    reference_invariants,
    selector_registry,
    stability_map,
    transport_latency,
)


def _compact_metrics(cases, selector):
    metrics = evaluate_selector(cases, selector)
    route_ids = metrics.pop("selected_route_ids")
    metrics["selected_route_hash"] = structural_hash(
        list(route_ids))
    return metrics


def _paired_interval(cases, left, right, seed=4401):
    differences = [
        int(left(case).actual_complete)
        - int(right(case).actual_complete)
        for case in cases]
    rng = random.Random(seed)
    bootstrap = []
    for _ in range(4000):
        bootstrap.append(sum(
            differences[rng.randrange(len(differences))]
            for _ in differences) / float(len(differences)))
    bootstrap.sort()
    wins = sum(value > 0 for value in differences)
    losses = sum(value < 0 for value in differences)
    discordant = wins + losses
    if discordant:
        tail = sum(
            math.comb(discordant, index)
            for index in range(min(wins, losses) + 1))
        probability = min(
            1.0, 2.0 * tail / float(2 ** discordant))
    else:
        probability = 1.0
    return {
        "bootstrap_95_ci": [
            bootstrap[int(0.025 * len(bootstrap))],
            bootstrap[int(0.975 * len(bootstrap))],
        ],
        "losses": losses,
        "mean_paired_completion_lift": (
            sum(differences) / float(len(differences))),
        "two_sided_exact_sign_p": probability,
        "wins": wins,
    }


def _correlation(left, right):
    if len(left) != len(right) or not left:
        return 0.0
    left_mean = sum(left) / float(len(left))
    right_mean = sum(right) / float(len(right))
    covariance = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left, right))
    left_scale = math.sqrt(sum(
        (value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum(
        (value - right_mean) ** 2 for value in right))
    if left_scale == 0.0 or right_scale == 0.0:
        return 0.0
    return covariance / (left_scale * right_scale)


def _predictive_diagnostics(cases, selector):
    # Prediction validity is evaluated over all held-out opportunities,
    # including incomplete ones; using only the full controller's selected
    # packets can collapse completion variance after a strong gate.
    selected = tuple(
        route for case in cases for route in case.routes)
    packet = tuple(
        float(row.actual_complete) for row in selected)
    relaxed = tuple(
        row.corrected_forward
        * row.backward_relevance
        for row in selected)
    realized = tuple(
        row.realized_value for row in selected)
    return {
        "packet_completion_realized_value_correlation": (
            _correlation(packet, realized)),
        "relaxed_mass_realized_value_correlation": (
            _correlation(relaxed, realized)),
        "packet_completion_is_stronger_predictor": (
            abs(_correlation(packet, realized))
            > abs(_correlation(relaxed, realized))),
        "scope": "held-out synthetic operation packets",
    }


def _controller_timing(cases, selectors, repetitions):
    rows = {}
    repetitions = max(1, int(repetitions))
    names = (
        "strong_smoothed_scalar",
        "bridge_scoring_without_flow",
        "pf_bridge_scalar_packet_scheduler",
        "full_multi_goal_controller",
    )
    checksum = 0
    for name in names:
        started = time.perf_counter()
        for _ in range(repetitions):
            for case in cases:
                checksum += int(
                    selectors[name](case).actual_complete)
        elapsed = time.perf_counter() - started
        rows[name] = {
            "case_evaluations": repetitions * len(cases),
            "mean_microseconds_per_case": (
                elapsed * 1000000.0
                / repetitions / len(cases)),
            "total_seconds": elapsed,
        }
    return {
        "checksum": checksum,
        "controllers": rows,
    }


def _capacity_provenance_verification():
    requests = (
        CommodityFlowRequest(
            "goal-a:cpu", ResourceKind.CPU,
            ("service",), (1.0,)),
        CommodityFlowRequest(
            "goal-b:cpu", ResourceKind.CPU,
            ("service",), (1.0,)),
    )
    rows = {}
    for kind in (
            CapacityKind.MEASURED,
            CapacityKind.ALLOCATED,
            CapacityKind.SHAPING):
        record = CapacityRecord(
            edge_or_node_id="service",
            resource=ResourceKind.CPU,
            value=1.0,
            kind=kind,
            provenance_id="g4:{}".format(kind.value),
            measured_window=(
                ("turn-0", "turn-20")
                if kind == CapacityKind.MEASURED else None),
            confidence=0.9)
        result = MultiCommodityCapacitySolver().solve(
            requests, (record,))
        dual = result.capacity_duals[0]
        rows[kind.value] = {
            "converged": result.converged,
            "dual": dual.value,
            "economic_price": dual.economic_price,
            "permitted_response": dual.permitted_response,
            "provenance_id": dual.provenance_id,
        }
    valid = all((
        rows["measured"]["economic_price"],
        rows["measured"]["permitted_response"]
        == "structural_bottleneck_candidate",
        not rows["allocated"]["economic_price"],
        rows["allocated"]["permitted_response"]
        == "request_arbiter_reconsideration",
        not rows["shaping"]["economic_price"],
        rows["shaping"]["permitted_response"]
        == "numerical_shaping_only",
    ))
    return {"records": rows, "valid": valid}


def _fallback_verification():
    sample = FlowHealthSample(
        forward_total_mass=0.9,
        backward_total_mass=1.0,
        mass_error=0.1,
        balance_residual=0.2,
        projection_healthy=False,
        local_cfl=3.0,
        cfl_rescaled=False,
        advection_healthy=False,
        bridge_overlap=0.0,
        probe_meet_rate=0.0,
        ess_fraction=0.01,
        clipped_fraction=0.9,
        path_diversity=0.0,
        probes_healthy=False,
        feedback_ratio=0.9,
        pressure_peak=20.0,
        dual_converged=False,
        integrality_gap=9.0,
        relaxed_value=10.0,
        packet_starvation_count=2,
        stale_view_lag=2,
        relief_mae=1.0,
        expected_normalization_hash="expected",
        observed_normalization_hash="changed",
        controller_overhead_ms=1000.0)
    report = FlowHealthMonitor().evaluate(
        sample, require_complete=True)
    planner = FlowRepairPlanner()
    attempted = []
    actions = []
    while True:
        decision = planner.decide(
            report, tuple(attempted))
        if decision.selected_action is None:
            break
        actions.append(decision.selected_action)
        attempted.append(decision.selected_action)
    return {
        "actions": actions,
        "candidate_authority": False,
        "report_hash": report.report_hash,
        "truth_mutation_allowed": False,
        "valid": (
            actions[:4] == [
                "local_numerical_repair",
                "adjust_exploration_or_feedback",
                "apply_pending_topology_patches",
                "rebuild_affected_view",
            ]
            and actions[-4:] == [
                "fallback_bridge_scalar",
                "fallback_scalar_v2",
                "fallback_legacy_scalar",
                "fallback_canonical_impact",
            ]),
    }


def _stability_verification():
    report = stability_map()
    selected = report["selected_region"]
    neighborhood = [
        row for row in report["rows"]
        if all(
            row[name] == selected[name]
            for name in (
                "deposit_gain",
                "current_following_gain",
                "decay", "temperature",
                "diffusion", "turnover"))
    ]
    rate = sum(
        row["recovered"] for row in neighborhood
    ) / float(len(neighborhood))
    report["selected_region_neighborhood"] = {
        "case_count": len(neighborhood),
        "recovery_rate": rate,
        "varied": [
            "packet_quantum", "corridor_length"],
    }
    return report


def run_g4_flow_sandbox(
        train_seeds_per_family=32,
        heldout_seeds_per_family=64,
        timing_repetitions=10):
    train = build_cohort(
        "train", train_seeds_per_family)
    heldout = build_cohort(
        "heldout", heldout_seeds_per_family)
    selectors = selector_registry()
    metrics = {}
    for name in BASELINE_NAMES + ABLATION_NAMES:
        metrics[name] = _compact_metrics(
            heldout, selectors[name])
    comparisons = {
        "flow_vs_strong_scalar": _paired_interval(
            heldout,
            selectors["full_multi_goal_controller"],
            selectors["strong_smoothed_scalar"]),
        "bridge_vs_strong_scalar": _paired_interval(
            heldout,
            selectors["bridge_scoring_without_flow"],
            selectors["strong_smoothed_scalar"],
            seed=4402),
        "flow_vs_bridge_packet": _paired_interval(
            heldout,
            selectors["full_multi_goal_controller"],
            selectors[
                "pf_bridge_scalar_packet_scheduler"],
            seed=4403),
    }
    family_metrics = {}
    for family in SYNTHETIC_FAMILIES:
        subset = tuple(
            row for row in heldout
            if row.family == family)
        family_metrics[family] = {
            "bridge_packet_completion_rate": (
                _compact_metrics(
                    subset,
                    selectors[
                        "pf_bridge_scalar_packet_scheduler"])[
                            "completion_rate"]),
            "flow_completion_rate": _compact_metrics(
                subset,
                selectors["full_multi_goal_controller"])[
                    "completion_rate"],
            "strong_scalar_completion_rate": (
                _compact_metrics(
                    subset,
                    selectors["strong_smoothed_scalar"])[
                        "completion_rate"]),
        }
    train_flow = _compact_metrics(
        train, selectors["full_multi_goal_controller"])
    heldout_flow = metrics["full_multi_goal_controller"]
    stability = _stability_verification()
    invariants = reference_invariants()
    capacity = _capacity_provenance_verification()
    fallback = _fallback_verification()
    predictive = _predictive_diagnostics(
        heldout,
        selectors["full_multi_goal_controller"])
    timing = _controller_timing(
        heldout, selectors, timing_repetitions)
    transport = transport_latency(
        timing_repetitions)
    scalar_us = timing["controllers"][
        "strong_smoothed_scalar"][
            "mean_microseconds_per_case"]
    flow_us = timing["controllers"][
        "full_multi_goal_controller"][
            "mean_microseconds_per_case"]
    overhead_penalty = max(
        0.0, flow_us - scalar_us) / 1000000.0
    net_flow = (
        heldout_flow["mean_realized_value"]
        - overhead_penalty)
    net_scalar = (
        metrics["strong_smoothed_scalar"][
            "mean_realized_value"])
    primary = comparisons["flow_vs_strong_scalar"]
    bridge_incremental = comparisons[
        "bridge_vs_strong_scalar"]
    flow_incremental = comparisons[
        "flow_vs_bridge_packet"]
    dynamic_survival = all(
        family_metrics[name]["flow_completion_rate"]
        > family_metrics[name][
            "strong_scalar_completion_rate"]
        for name in (
            "long_path_changing",
            "dynamic_edge_failures",
            "stale_topology"))
    transfer_gap = abs(
        train_flow["completion_rate"]
        - heldout_flow["completion_rate"])
    report = {
        "ablation_ladder": {
            name: metrics[name]
            for name in ABLATION_NAMES
        },
        "baseline_metrics": {
            name: metrics[name]
            for name in BASELINE_NAMES
        },
        "capacity_provenance": capacity,
        "claim_status": (
            "G4-synthetic-control-gate;"
            "not-a-FreeCiv-gameplay-score-or-win-rate-claim"),
        "comparisons": comparisons,
        "controller_inclusive_timing": timing,
        "fallback_verification": fallback,
        "family_metrics": family_metrics,
        "gate_conditions": {
            "bridge_incremental_value": (
                bridge_incremental[
                    "mean_paired_completion_lift"] > 0.0),
            "capacity_provenance_valid": capacity["valid"],
            "dynamic_and_corridor_failure_survival": (
                dynamic_survival),
            "fallback_ladder_valid": fallback["valid"],
            "flow_incremental_value": (
                flow_incremental[
                    "mean_paired_completion_lift"] > 0.0),
            "flow_net_value_after_measured_overhead": (
                net_flow > net_scalar),
            "flow_vs_scalar_heldout_significant": (
                primary["bootstrap_95_ci"][0] > 0.0
                and primary[
                    "two_sided_exact_sign_p"] < 0.05),
            "mass_and_projection_invariants": (
                invariants["valid"]),
            "normalization_transfers": transfer_gap <= 0.05,
            "packet_completion_predicts_useful_work": (
                predictive[
                    "packet_completion_is_stronger_predictor"]),
            "selected_region_recovery_reliable": (
                stability[
                    "selected_region_neighborhood"][
                        "recovery_rate"] >= 0.75),
            "transport_latency_included": bool(
                transport["rows"]),
            "unstable_regions_published": (
                stability["unstable_count"] > 0),
        },
        "heldout": {
            "case_count": len(heldout),
            "cohort_hash": structural_hash([
                row.case_id for row in heldout]),
            "seed_range": [
                min(row.seed for row in heldout),
                max(row.seed for row in heldout),
            ],
        },
        "invariants": invariants,
        "net_value_after_controller_overhead": {
            "flow": net_flow,
            "measured_incremental_overhead_penalty": (
                overhead_penalty),
            "strong_scalar": net_scalar,
        },
        "normalization_transfer": {
            "contract_hash": (
                default_normalization_contract().contract_hash),
            "heldout_completion_rate": (
                heldout_flow["completion_rate"]),
            "same_contract_used": True,
            "train_completion_rate": (
                train_flow["completion_rate"]),
            "transfer_gap": transfer_gap,
        },
        "predictive_diagnostics": predictive,
        "preregistered_primary_comparison": (
            "full_multi_goal_controller versus "
            "strong_smoothed_scalar"),
        "primary_metric": (
            "complete operation packets before deadline"),
        "schema_version": "1.0",
        "stability_map": stability,
        "synthetic_families": list(
            SYNTHETIC_FAMILIES),
        "training": {
            "case_count": len(train),
            "cohort_hash": structural_hash([
                row.case_id for row in train]),
            "seed_range": [
                min(row.seed for row in train),
                max(row.seed for row in train),
            ],
        },
        "transport_latency": transport,
    }
    report["valid"] = all(
        report["gate_conditions"].values())
    report["decision"] = (
        "proceed-to-shadow-live-integration"
        if report["valid"]
        else "retain-best-scalar-bridge-packet-subset;"
             "stop-fluid-live-integration")
    semantic = dict(report)
    semantic.pop("controller_inclusive_timing")
    semantic.pop("transport_latency")
    semantic.pop("net_value_after_controller_overhead")
    report["verification_hash"] = structural_hash(
        semantic)
    return report
