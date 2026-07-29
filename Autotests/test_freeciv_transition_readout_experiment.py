from freeciv.pf_unified.transition_readout_experiment import (
    run_transition_readout_experiment,
)


def test_transition_readout_experiment_passes_only_offline_gates():
    report = run_transition_readout_experiment(
        readout_cases=120,
        persistence_traces=12,
        persistence_steps=40)
    assert report["offline_valid"]
    assert report[
        "ct1_calibrated_scalar"][
            "mechanism_gate_pass"]
    assert report[
        "ct1_calibrated_scalar"][
            "mae_improvement"] >= 0.02
    assert report[
        "ct1_calibrated_scalar"][
            "interval_coverage"] >= 0.90
    recall = report[
        "ct2_ct3_candidate_recall"]
    assert recall["ct2_mechanism_gate_pass"]
    assert recall["ct3_mechanism_gate_pass"]
    assert recall[
        "historical_founding_candidate_protected"]
    persistence = report[
        "ct4_path_persistence"]
    assert persistence[
        "offline_mechanism_gate_pass"]
    assert not persistence[
        "engine_gameplay_gate_pass"]
    assert not report[
        "ct5_source_sink_entry"][
            "entry_gate_pass"]
    assert "claim-ineligible" in report[
        "evaluation_scope"]


def test_transition_readout_semantics_are_deterministic():
    left = run_transition_readout_experiment(
        readout_cases=60,
        persistence_traces=8,
        persistence_steps=30)
    right = run_transition_readout_experiment(
        readout_cases=60,
        persistence_traces=8,
        persistence_steps=30)
    # Latency is intentionally excluded from gate semantics by comparing
    # stable decision/calibration fields rather than wall-clock values.
    for report in (left, right):
        report[
            "ct2_ct3_candidate_recall"].pop(
                "mean_case_latency_ms")
        report[
            "ct4_path_persistence"].pop(
                "mean_decision_latency_ms")
        report.pop("semantic_hash")
    assert left == right
