"""Gate-G3 held-out conductance-versus-bridge experiment checks."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.bridge_experiment import (  # noqa: E402
    ARM_NAMES,
    GRAPH_FAMILIES,
    run_g3_bridge_experiment,
)


def test_g3_bridge_experiment_is_seed_disjoint_and_falsifiable():
    report = run_g3_bridge_experiment(
        train_seeds_per_family=16,
        heldout_seeds_per_family=16,
        timing_repetitions=1)

    assert report["valid"]
    assert set(report["arms"]) == set(ARM_NAMES)
    assert set(report["graph_families"]) == set(GRAPH_FAMILIES)
    assert report["training"]["cohort_hash"] != (
        report["heldout"]["cohort_hash"])
    assert report["training"]["seed_range"][1] < (
        report["heldout"]["seed_range"][0])
    primary = report["comparisons"][
        "bridge_vs_context_conductance"]
    assert primary["bootstrap_95_ci"][0] > 0.0
    assert primary["two_sided_exact_sign_p"] < 0.05
    assert report["comparisons"][
        "bridge_vs_shuffled_forward"][
            "mean_paired_completion_lift"] > 0.0
    assert report["comparisons"][
        "bridge_vs_shuffled_backward"][
            "mean_paired_completion_lift"] > 0.0


def test_g3_claim_boundary_and_strong_scalar_contract_are_explicit():
    report = run_g3_bridge_experiment(
        train_seeds_per_family=8,
        heldout_seeds_per_family=8,
        timing_repetitions=1)

    assert "not-a-FreeCiv-gameplay-score-claim" in (
        report["claim_status"])
    assert not report["bridge_calibration"]["claim_eligible"]
    assert report["bridge_calibration"][
        "synthetic_gate_eligible"]
    assert report["strong_smoothed_scalar_baseline"][
        "first_step_selection_equivalent"]
    assert report["fixed_compute_contract"][
        "candidate_sets_identical"]
    assert report["arms"]["explicit_bridge"][
        "mean_verified_goal_loss_relief"] > (
            report["arms"]["bridge_only_without_pf_typing"][
                "mean_verified_goal_loss_relief"])


def test_g3_semantic_hash_excludes_nondeterministic_wall_timing():
    first = run_g3_bridge_experiment(8, 8, 1)
    second = run_g3_bridge_experiment(8, 8, 2)

    assert first["verification_hash"] == (
        second["verification_hash"])
    assert first["controller_inclusive_timing"] != (
        second["controller_inclusive_timing"])
