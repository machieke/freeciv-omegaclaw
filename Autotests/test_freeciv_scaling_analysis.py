"""Robust-fit and audit reconstruction gates for scaling evidence."""

import math
import os
import random
import statistics
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
for candidate in (REPO, SRC):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from benchmarks.freeciv.scaling.analysis import (  # noqa: E402
    analyze_combined,
    analyze_captured,
    analyze_surface,
    build_report,
    cluster_bootstrap_interval,
    percentile,
    robust_log_slope,
)
from benchmarks.freeciv.scaling.audit import (  # noqa: E402
    audit_engine_shadow_report,
    audit_results,
)
from benchmarks.freeciv.scaling.runner import run_isolated, smoke_payloads  # noqa: E402
from benchmarks.freeciv.scaling.claims import build_claim_manifest  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def test_robust_log_fit_recovers_known_power_law():
    points = [(value, 3.0 * value ** 1.25) for value in (10, 20, 40, 80)]
    assert abs(robust_log_slope(points) - 1.25) < 1e-12
    clusters = dict((str(index), [point]) for index, point in enumerate(points))
    interval = cluster_bootstrap_interval(clusters, resamples=500, seed=1)
    assert interval == pytest.approx((1.25, 1.25))
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def _reference_cluster_bootstrap(clusters, resamples, seed):
    names = sorted(clusters)
    rng = random.Random(seed)
    medians = []
    for _ in range(resamples):
        sampled = [names[rng.randrange(len(names))] for _name in names]
        points = sorted(
            point for name in sampled for point in clusters[name])
        slopes = []
        for index, (left_x, left_y) in enumerate(points):
            for right_x, right_y in points[index + 1:]:
                if right_x != left_x:
                    slopes.append(
                        (math.log(right_y) - math.log(left_y))
                        / (math.log(right_x) - math.log(left_x)))
        if slopes:
            medians.append(statistics.median(slopes))
    return percentile(medians, 0.025), percentile(medians, 0.975)


def test_cluster_bootstrap_weighting_is_exactly_reference_equivalent():
    clusters = {
        "seed-a": [(10, 3.1), (20, 6.4), (40, 12.2)],
        "seed-b": [(10, 2.8), (20, 5.7), (40, 12.0)],
        "seed-c": [(10, 3.3), (20, 6.1), (40, 13.1)],
    }

    expected = _reference_cluster_bootstrap(clusters, 250, 919)
    actual = cluster_bootstrap_interval(clusters, resamples=250, seed=919)

    assert actual == expected


def test_audit_reconstructs_trial_and_result_hashes():
    results = [run_isolated(
        smoke_payloads(seed=91)[0], "test-source", wall_seconds=30).to_dict()]
    audit = audit_results(results, resamples=10)
    assert audit["valid"], audit["errors"]
    assert audit["result_count"] == 1
    assert audit["report"]["gates"]["atomspace"] == "not-entered"


def test_audit_rejects_tampered_work_count():
    result = run_isolated(
        smoke_payloads(seed=92)[3], "test-source", wall_seconds=30).to_dict()
    result["actual_work"]["edge_updates"] += 1
    audit = audit_results([result], resamples=10)
    assert not audit["valid"]
    assert any("hash mismatch" in row for row in audit["errors"])


def test_audit_requires_reported_retention_invariants():
    result = run_isolated({
        "surface": "atomspace",
        "tier": "A0-retention-audit",
        "seed": 31,
        "parameters": {
            "atom_count": 20,
            "scope_count": 2,
            "support_multiplicity": 1,
            "topology": "local",
            "churn_fraction": 0.1,
            "retention_cycles": 3,
            "revision_retention": 2,
        },
    }, "test-source", wall_seconds=30).to_dict()
    result["correctness"]["revision_retention_no_leak"] = False
    result["result_hash"] = structural_hash({
        key: value for key, value in result.items() if key != "result_hash"
    })

    audit = audit_results([result], resamples=10)

    assert audit["valid"]
    assert any(
        "revision_retention_no_leak" in error
        for error in audit["semantic_failures"])
    assert audit["report"]["gates"]["atomspace"] == "fail"


def test_analysis_never_pools_different_source_identities():
    rows = []
    for seed, source, atoms in (
            (1, "source-a", 100), (2, "source-b", 1000)):
        result = run_isolated(
            {"surface": "atomspace", "tier": "test", "seed": seed,
             "parameters": {"atom_count": atoms, "scope_count": 2,
                            "topology": "local"}},
            source, wall_seconds=30).to_dict()
        rows.append(result)
    report = build_report(rows, resamples=10)
    surface = report["surfaces"]["atomspace"]
    assert len(surface["versions"]) == 2
    assert surface["distinct_work_values"] == 1
    assert surface["gate"] == "not-entered"


def test_phase_reports_never_pool_discovery_with_heldout():
    rows = []
    for phase, tier, work in (
            ("discovery", "A0", 100), ("heldout", "A1", 1000)):
        rows.append({
            "actual_work": {"live_revision_atoms": work},
            "correctness": {},
            "metrics": {"incremental_ms": float(work),
                        "peak_rss_bytes": float(work)},
            "status": "completed",
            "trial": {"arm": "kernel", "phase": phase,
                      "cell": {"parameters": {}, "seed": 1,
                               "surface": "atomspace", "tier": tier},
                      "source_identity": "same-source"},
        })

    report = build_report(rows, resamples=10)

    assert report["surfaces"]["atomspace"]["distinct_work_values"] == 2
    assert report["phase_reports"]["discovery"][
        "surfaces"]["atomspace"]["distinct_work_values"] == 1
    assert report["phase_reports"]["heldout"][
        "surfaces"]["atomspace"]["distinct_work_values"] == 1


def test_fit_gate_is_independent_from_absolute_label_sample_eligibility():
    rows = []
    for seed in (1, 2):
        for work, elapsed, rss in ((100, 1.0, 1000), (1000, 10.0, 1500)):
            rows.append({
                "actual_work": {"live_revision_atoms": work},
                "correctness": {
                    "cold_incremental_equivalent": True,
                    "count_exact": True,
                    "synthetic_namespace_only": True,
                },
                "metrics": {
                    "incremental_ms": elapsed,
                    "peak_rss_bytes": rss,
                },
                "status": "completed",
                "trial": {
                    "cell": {
                        "seed": seed,
                        "surface": "atomspace",
                        "tier": "synthetic-fit",
                    },
                    "source_identity": "same-source",
                },
            })

    surface = analyze_surface(
        rows, "atomspace", resamples=100, source_identity="same-source")

    assert surface["fit_eligible"]
    assert surface["gate"] == "pass"
    assert surface["secondary_fits"][
        "peak-rss-vs-live-atoms"]["gate"] == "pass"
    assert all(
        label["status"] == "not-entered"
        for label in surface["absolute_labels"].values())


def test_parallel_semantic_screening_never_enters_timing_fits():
    rows = []
    for seed, work in ((1, 100), (2, 1000)):
        rows.append({
            "actual_work": {"live_revision_atoms": work},
            "correctness": {
                "cold_incremental_equivalent": True,
                "count_exact": True,
                "synthetic_namespace_only": True,
            },
            "metrics": {
                "incremental_ms": float(work),
                "peak_rss_bytes": float(work),
            },
            "status": "completed",
            "trial": {
                "cell": {
                    "parameters": {
                        "churn_fraction": 0.01,
                        "support_multiplicity": 1,
                        "topology": "local",
                    },
                    "seed": seed,
                    "surface": "atomspace",
                    "tier": "screening",
                },
                "source_identity": "same-source",
                "telemetry_mode": "semantic-screening",
            },
        })

    surface = analyze_surface(
        rows, "atomspace", resamples=100, source_identity="same-source")

    assert surface["completed_trials"] == 2
    assert surface["excluded_non_timing_trials"] == 2
    assert surface["fit_completed_trials"] == 0
    assert surface["gate"] == "not-entered"


def test_parallel_semantic_screening_never_enters_combined_ratios():
    source = "screening-source"
    rows = []
    for surface, tier, metric in (
            ("atomspace", "A2", {"wall_ms": 10.0}),
            ("proof", "P1", {"wall_ms": 20.0}),
            ("bridge", "B1", {"wall_ms": 30.0})):
        rows.append({
            "actual_work": {}, "correctness": {}, "metrics": metric,
            "status": "completed",
            "trial": {
                "cell": {"parameters": {}, "seed": 1,
                         "surface": surface, "tier": tier},
                "source_identity": source,
                "telemetry_mode": "semantic-screening",
            },
        })
    rows.append({
        "actual_work": {},
        "correctness": {
            "bridge_candidate_safe": True,
            "cold_incremental_equivalent": True,
            "fluid_healthy": True,
            "fluid_mass_within_1e_9": True,
            "proof_matches_reference": True,
            "truth_hash_unchanged": True,
        },
        "metrics": {"combined_elapsed_ms": 40.0},
        "status": "completed",
        "trial": {
            "cell": {"parameters": {
                "atom_tier": "A2", "bridge_tier": "B1",
                "fluid_tier": "none", "proof_tier": "P1",
            }, "seed": 1, "surface": "combined", "tier": "C00"},
            "source_identity": source,
            "telemetry_mode": "semantic-screening",
        },
    })

    combined = analyze_combined(rows, source_identity=source)

    assert combined["completed_trials"] == 1
    assert combined["semantic_screening_trials"] == 1
    assert combined["timing_completed_trials"] == 0
    assert combined["paired_trials"] == 0
    assert combined["maximum_ratio"] is None
    assert combined["gate"] == "not-entered"


def test_combined_stop_fails_gate_without_timing_claim():
    row = {
        "actual_work": {}, "correctness": {
            "stop_rule": "wall-time"}, "errors": ["wall limit exceeded"],
        "metrics": {}, "status": "stopped",
        "trial": {
            "cell": {"parameters": {}, "seed": 1,
                     "surface": "combined", "tier": "C15"},
            "source_identity": "screening-source",
            "telemetry_mode": "semantic-screening",
        },
    }

    combined = analyze_combined(
        [row], source_identity="screening-source")

    assert combined["gate"] == "fail"
    assert combined["status_counts"]["stopped"] == 1
    assert combined["paired_trials"] == 0


def test_primary_fit_excludes_atomspace_stress_dimensions():
    rows = []
    for seed in (1, 2):
        for tier, work in (("A1", 10000), ("A2", 25000)):
            rows.append({
                "actual_work": {"live_revision_atoms": work},
                "metrics": {"incremental_ms": work / 100.0,
                            "peak_rss_bytes": work * 100.0},
                "status": "completed",
                "trial": {"cell": {"parameters": {
                    "churn_fraction": 0.01,
                    "support_multiplicity": 1,
                    "topology": "local",
                }, "seed": seed, "surface": "atomspace", "tier": tier},
                    "source_identity": "same-source"},
            })
    stress = dict(rows[-1])
    stress["trial"] = {
        "cell": {"parameters": {
            "churn_fraction": 0.01,
            "support_multiplicity": 1,
            "topology": "hub",
        }, "seed": 3, "surface": "atomspace", "tier": "A2"},
        "source_identity": "same-source",
    }
    stress["metrics"] = {
        "incremental_ms": 999999.0, "peak_rss_bytes": 999999999.0}
    rows.append(stress)

    surface = analyze_surface(
        rows, "atomspace", resamples=100,
        source_identity="same-source")

    assert surface["completed_trials"] == 5
    assert surface["fit_completed_trials"] == 4
    assert surface["excluded_stress_trials"] == 1
    assert [point[1] for point in surface["points"]] == [
        100.0, 250.0, 100.0, 250.0]


def test_proof_distractor_fit_is_stratified_by_relevant_tier():
    rows = []
    relevant = {"P1": 1000, "P2": 10000, "P3": 100000}
    for seed in (1, 2):
        for tier, rules in relevant.items():
            rows.append({
                "actual_work": {
                    "indexed_distractor_rules": 0,
                    "relevant_rules": rules,
                },
                "metrics": {"kernel_elapsed_ms": rules / 100.0},
                "status": "completed",
                "trial": {"cell": {"parameters": {
                    "distractor_count": 0, "shape": "shared_dag",
                }, "seed": seed, "surface": "proof", "tier": tier},
                    "source_identity": "same-source"},
            })
            for distractors in (100, 400, 1600):
                rows.append({
                    "actual_work": {
                        "indexed_distractor_rules": distractors,
                        "relevant_rules": rules,
                    },
                    "metrics": {
                        "kernel_elapsed_ms": distractors ** 0.5},
                    "status": "completed",
                    "trial": {"cell": {"parameters": {
                        "distractor_count": distractors,
                        "shape": "shared_dag",
                    }, "seed": seed, "surface": "proof", "tier": tier},
                        "source_identity": "same-source"},
                })

    surface = analyze_surface(
        rows, "proof", resamples=100, source_identity="same-source")
    secondary = surface["secondary_fits"][
        "time-vs-indexed-distractors"]

    assert surface["fit_completed_trials"] == 6
    assert secondary["gate"] == "pass"
    assert secondary["eligible"]
    assert all(row["gate"] == "pass"
               for row in secondary["tier_fits"].values())


def test_combined_interaction_pairs_only_same_source_seed_and_tiers():
    source = "frozen-source"
    seed = 7
    isolated = []
    for surface, tier in (
            ("atomspace", "A2"), ("proof", "P1"), ("bridge", "B1")):
        isolated.append({
            "actual_work": {},
            "correctness": {},
            "metrics": {"wall_ms": 10.0},
            "status": "completed",
            "trial": {"cell": {"parameters": {}, "seed": seed,
                                "surface": surface, "tier": tier},
                      "source_identity": source},
        })
    combined = {
        "actual_work": {},
        "correctness": {
            "bridge_candidate_safe": True,
            "cold_incremental_equivalent": True,
            "fluid_healthy": True,
            "fluid_mass_within_1e_9": True,
            "proof_matches_reference": True,
            "truth_hash_unchanged": True,
        },
        "metrics": {"combined_elapsed_ms": 45.0},
        "status": "completed",
        "trial": {"cell": {
            "parameters": {"atom_tier": "A2", "proof_tier": "P1",
                           "bridge_tier": "B1", "fluid_tier": "none"},
            "seed": seed, "surface": "combined", "tier": "C00"},
            "source_identity": source},
    }

    report = analyze_combined(isolated + [combined], source_identity=source)

    assert report["paired_trials"] == 1
    assert report["maximum_ratio"] == pytest.approx(1.5)
    assert report["gate"] == "pass"
    isolated[0]["trial"]["source_identity"] = "different-source"
    assert analyze_combined(
        isolated + [combined], source_identity=source)["gate"] == "not-entered"


def test_captured_gate_requires_full_cohort_and_same_source_reference():
    source = "captured-source"
    rows = []
    for tier in ("A2", "A4"):
        rows.append({
            "actual_work": {}, "correctness": {},
            "metrics": {"generator_ms": 100.0, "peak_rss_bytes": 1000},
            "status": "completed",
            "trial": {"cell": {"parameters": {}, "seed": 1,
                                "surface": "atomspace", "tier": tier},
                      "source_identity": source},
        })
    for index in range(20):
        for captured_tier, synthetic_tier in (("CA2", "A2"), ("CA4", "A4")):
            rows.append({
                "actual_work": {"turn": index + 1},
                "correctness": {
                    "at_least_target_atoms": True,
                    "clone_authority_quarantined": True,
                    "original_subgraph_invariant": True,
                    "source_hash_verified": True,
                },
                "metrics": {"amplification_ms": 150.0,
                            "peak_rss_bytes": 1500},
                "status": "completed",
                "trial": {"cell": {
                    "parameters": {"synthetic_tier": synthetic_tier},
                    "seed": index, "surface": "captured",
                    "tier": captured_tier},
                    "source_identity": source},
            })

    report = analyze_captured(rows, source_identity=source)

    assert report["cohort_complete"]
    assert report["paired_trials"] == 40
    assert report["maximum_timing_ratio"] == pytest.approx(1.5)
    assert report["gate"] == "pass"


def test_captured_semantic_screen_does_not_fail_unentered_transfer_gate():
    source = "captured-screening-source"
    rows = []
    for tier in ("A2", "A4"):
        rows.append({
            "actual_work": {}, "correctness": {},
            "metrics": {"generator_ms": 100.0, "peak_rss_bytes": 1000},
            "status": "completed",
            "trial": {"cell": {"parameters": {}, "seed": 1,
                                "surface": "atomspace", "tier": tier},
                      "source_identity": source,
                      "telemetry_mode": "aggregate"},
        })
    for index in range(20):
        for captured_tier, synthetic_tier in (("CA2", "A2"), ("CA4", "A4")):
            rows.append({
                "actual_work": {"turn": index + 1},
                "correctness": {
                    "at_least_target_atoms": True,
                    "clone_authority_quarantined": True,
                    "original_subgraph_invariant": True,
                    "source_hash_verified": True,
                },
                "metrics": {"amplification_ms": 150.0,
                            "peak_rss_bytes": 1500},
                "status": "completed",
                "trial": {"cell": {
                    "parameters": {"synthetic_tier": synthetic_tier},
                    "seed": index, "surface": "captured",
                    "tier": captured_tier},
                    "source_identity": source,
                    "telemetry_mode": "semantic-screening"},
            })

    report = analyze_captured(rows, source_identity=source)

    assert report["cohort_complete"]
    assert report["semantic_invariants_hold"]
    assert report["semantic_screening_trials"] == 40
    assert report["excluded_non_timing_trials"] == 40
    assert report["timing_completed_trials"] == 0
    assert not report["timing_cohort_complete"]
    assert report["paired_trials"] == 0
    assert report["gate"] == "not-entered"


def test_captured_version_selection_prefers_complete_semantic_cohort():
    screening_source = "captured-complete-screening"
    timing_source = "captured-two-pair-timing"
    rows = []
    for index in range(20):
        for captured_tier, synthetic_tier in (("CA2", "A2"), ("CA4", "A4")):
            rows.append({
                "actual_work": {"turn": index + 1},
                "correctness": {
                    "at_least_target_atoms": True,
                    "clone_authority_quarantined": True,
                    "original_subgraph_invariant": True,
                    "source_hash_verified": True,
                },
                "metrics": {"amplification_ms": 150.0,
                            "peak_rss_bytes": 1500},
                "status": "completed",
                "trial": {"cell": {
                    "parameters": {"synthetic_tier": synthetic_tier},
                    "seed": index, "surface": "captured",
                    "tier": captured_tier},
                    "source_identity": screening_source,
                    "phase": "discovery",
                    "telemetry_mode": "semantic-screening"},
            })
    for tier in ("A2", "A4"):
        rows.append({
            "actual_work": {}, "correctness": {},
            "metrics": {"generator_ms": 100.0, "peak_rss_bytes": 1000},
            "status": "completed",
            "trial": {"cell": {"parameters": {}, "seed": 1,
                                "surface": "atomspace", "tier": tier},
                      "source_identity": timing_source,
                      "phase": "discovery",
                      "telemetry_mode": "aggregate"},
        })
    for captured_tier, synthetic_tier in (("CA2", "A2"), ("CA4", "A4")):
        rows.append({
            "actual_work": {"turn": 250},
            "correctness": {
                "at_least_target_atoms": True,
                "clone_authority_quarantined": True,
                "original_subgraph_invariant": True,
                "source_hash_verified": True,
            },
            "metrics": {"amplification_ms": 150.0,
                        "peak_rss_bytes": 1500},
            "status": "completed",
            "trial": {"cell": {
                "parameters": {"synthetic_tier": synthetic_tier},
                "seed": 250, "surface": "captured", "tier": captured_tier},
                "source_identity": timing_source,
                "phase": "discovery",
                "telemetry_mode": "aggregate"},
        })

    captured = build_report(rows, resamples=10)["captured"]

    assert captured["selected_source_identity"] == screening_source
    assert captured["cohort_complete"]
    assert captured["completed_trials"] == 40
    assert captured["gate"] == "not-entered"


def test_engine_shadow_gate_reconstructs_hash_and_requires_twenty_pairs():
    pairs = []
    for seed in range(20):
        pairs.append({
            "action_trace_match": True,
            "behavioral_completion_match": True,
            "failures": [],
            "result_trace_match": True,
            "seed": seed,
            "shadow": {
                "event_validation_valid": True,
                "shadow": {
                    "authority_eligible_count": 0,
                    "authority_violation_count": 0,
                    "detail_omission_count": 0,
                    "legal_binding_failure_count": 0,
                    "missing_legacy_count": 0,
                    "safety_downgrade_count": 0,
                },
            },
        })
    report = {
        "acceptance": {"accepted": True},
        "aggregate": {"maximum_volume": {"atoms": 1234}},
        "pairs": pairs,
        "schema_version": "fdas-engine-shadow-cohort/1.0",
        "structural_hash": None,
    }
    report["structural_hash"] = structural_hash(report)

    result = audit_engine_shadow_report(report)

    assert result["valid"]
    assert result["gate"] == "pass"
    assert result["pair_count"] == 20
    report["pairs"][0]["action_trace_match"] = False
    assert not audit_engine_shadow_report(report)["valid"]


def test_engine_shadow_transfer_uses_nearest_canonical_heldout_atom_tier():
    pairs = [{
        "action_trace_match": True,
        "behavioral_completion_match": True,
        "failures": [],
        "result_trace_match": True,
        "shadow": {"event_validation_valid": True, "shadow": {}},
    } for _ in range(20)]
    report = {
        "acceptance": {"accepted": True},
        "aggregate": {
            "controller_process_peak_rss_bytes": {"p95_bytes": 3000},
            "fdas_projection_latency_ms": {"p95_ms": 30.0},
            "maximum_volume": {"atoms": 3000},
        },
        "pairs": pairs,
        "schema_version": "fdas-engine-shadow-cohort/1.0",
        "structural_hash": None,
    }
    report["structural_hash"] = structural_hash(report)
    synthetic = []
    for work, latency, rss, tier in (
            (2500, 10.0, 1000, "A0"),
            (10000, 40.0, 4000, "A1")):
        synthetic.append({
            "actual_work": {"live_revision_atoms": work},
            "metrics": {
                "incremental_ms": latency, "peak_rss_bytes": rss},
            "status": "completed",
            "trial": {
                "cell": {"parameters": {
                    "churn_fraction": 0.01,
                    "support_multiplicity": 1,
                    "topology": "local",
                }, "surface": "atomspace", "tier": tier},
                "phase": "heldout", "telemetry_mode": "aggregate",
            },
        })

    transfer = audit_engine_shadow_report(
        report, synthetic_results=synthetic)["synthetic_transfer"]

    assert transfer["entered"]
    assert transfer["nearest_synthetic_tier"] == "A0"
    assert transfer["latency_ratio_engine_fdas_projection_p95_to_synthetic_incremental_p95"] == 3.0
    assert transfer["memory_ratio_engine_controller_rss_p95_to_synthetic_process_rss_p95"] == 3.0


def test_claim_manifest_never_promotes_discovery_rows():
    result = run_isolated(
        smoke_payloads(seed=301)[0], "claim-source",
        phase="discovery", wall_seconds=30).to_dict()
    audit = audit_results([result], resamples=10)

    claims = build_claim_manifest([result], audit, frozen=None)

    assert claims["heldout_result_count"] == 0
    assert not claims["g9_complete"]
    assert not any(
        row["correct_at_scale_tiers"]
        for row in claims["surface_claims"].values())
