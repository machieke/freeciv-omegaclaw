"""Gate-G4 scientific-risk sandbox and decision checks."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        REPO,
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.flow_sandbox import (  # noqa: E402
    run_g4_flow_sandbox,
)
from research.flow_control import (  # noqa: E402
    ABLATION_NAMES,
    BASELINE_NAMES,
    SYNTHETIC_FAMILIES,
)


def test_g4_covers_preregistered_families_baselines_and_ablations():
    report = run_g4_flow_sandbox(8, 8, 1)

    assert set(report["synthetic_families"]) == set(
        SYNTHETIC_FAMILIES)
    assert set(report["baseline_metrics"]) == set(
        BASELINE_NAMES)
    assert set(report["ablation_ladder"]) == set(
        ABLATION_NAMES)
    assert report["training"]["cohort_hash"] != (
        report["heldout"]["cohort_hash"])
    assert report["training"]["seed_range"][1] < (
        report["heldout"]["seed_range"][0])


def test_g4_flow_earns_cost_on_heldout_synthetic_gate():
    report = run_g4_flow_sandbox(8, 16, 1)

    assert report["valid"], report["gate_conditions"]
    assert report["decision"] == (
        "proceed-to-shadow-live-integration")
    assert all(report["gate_conditions"].values())
    primary = report["comparisons"][
        "flow_vs_strong_scalar"]
    assert primary["bootstrap_95_ci"][0] > 0.0
    assert primary["two_sided_exact_sign_p"] < 0.05
    assert report["comparisons"][
        "bridge_vs_strong_scalar"][
            "mean_paired_completion_lift"] > 0.0
    assert report["comparisons"][
        "flow_vs_bridge_packet"][
            "mean_paired_completion_lift"] > 0.0


def test_g4_publishes_instability_and_claim_boundary():
    report = run_g4_flow_sandbox(4, 4, 1)

    assert "not-a-FreeCiv-gameplay-score-or-win-rate-claim" in (
        report["claim_status"])
    assert report["stability_map"]["stable_count"] > 0
    assert report["stability_map"]["unstable_count"] > 0
    assert len(report["stability_map"]["rows"]) == 256
    assert report["transport_latency"]["rows"]
    assert report["fallback_verification"]["valid"]
    assert not report["fallback_verification"][
        "truth_mutation_allowed"]


def test_g4_semantic_hash_excludes_wall_clock_timing():
    first = run_g4_flow_sandbox(4, 4, 1)
    second = run_g4_flow_sandbox(4, 4, 2)

    assert first["verification_hash"] == (
        second["verification_hash"])
    assert first["controller_inclusive_timing"] != (
        second["controller_inclusive_timing"])
