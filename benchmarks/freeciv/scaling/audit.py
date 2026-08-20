"""Reconstruct scaling trial identities and claim inputs from raw artifacts."""

import json
import math
import os

from freeciv_agent.events.schema import structural_hash

from .analysis import build_report, percentile, required_correctness_keys
from .model import ScaleCell, TrialSpec


def load_results(root):
    results = []
    for phase in ("discovery", "heldout"):
        path = os.path.join(root, phase, "trials.json")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            material = json.load(handle)
        if material.get("artifact_type") != "freeciv-scalability-trials":
            raise ValueError("wrong trial artifact type: {}".format(path))
        results.extend(material["results"])
    return results


def _trial_identity(material):
    cell_row = material["trial"]["cell"]
    cell = ScaleCell(
        cell_row["surface"], cell_row["tier"], cell_row["seed"],
        tuple(cell_row["parameters"].items()),
        tuple(cell_row["budgets"].items()),
    )
    trial_row = material["trial"]
    return TrialSpec(
        trial_row["experiment_id"], trial_row["phase"], cell,
        trial_row["arm"], trial_row["telemetry_mode"],
        trial_row["source_identity"],
    ).trial_id


def _engine_synthetic_transfer(report, results):
    """Build the preregistered descriptive G8 nearest-work transfer ratios."""
    achieved_atoms = int(report.get(
        "aggregate", {}).get(
            "maximum_volume", {}).get("atoms", 0) or 0)
    rows = []
    for row in results or ():
        trial = row.get("trial", {})
        cell = trial.get("cell", {})
        parameters = cell.get("parameters", {})
        if (row.get("status") != "completed"
                or trial.get("phase") != "heldout"
                or trial.get("telemetry_mode", "aggregate") != "aggregate"
                or cell.get("surface") != "atomspace"
                or parameters.get("topology", "local") != "local"
                or float(parameters.get("churn_fraction", 0.01)) != 0.01
                or int(parameters.get("support_multiplicity", 1)) != 1
                or int(parameters.get("retention_cycles", 0)) != 0):
            continue
        work = int(row.get("actual_work", {}).get(
            "live_revision_atoms", 0))
        latency = row.get("metrics", {}).get("incremental_ms")
        rss = row.get("metrics", {}).get("peak_rss_bytes")
        if work > 0 and latency is not None and rss is not None:
            rows.append((work, float(latency), int(rss), cell.get("tier")))
    work_values = sorted(set(row[0] for row in rows))
    if achieved_atoms <= 0 or not work_values:
        return {
            "entered": False,
            "reason": "engine or canonical synthetic work is unavailable",
        }
    nearest_work = min(
        work_values,
        key=lambda work: (abs(math.log(work) - math.log(achieved_atoms)), work))
    selected = [row for row in rows if row[0] == nearest_work]
    synthetic_latency = percentile(
        [row[1] for row in selected], 0.95)
    synthetic_rss = percentile([row[2] for row in selected], 0.95)
    aggregate = report.get("aggregate", {})
    engine_latency = aggregate.get(
        "fdas_projection_latency_ms", {}).get("p95_ms")
    engine_rss = aggregate.get(
        "controller_process_peak_rss_bytes", {}).get("p95_bytes")
    complete = all(value is not None and float(value) > 0.0 for value in (
        synthetic_latency, synthetic_rss, engine_latency, engine_rss))
    return {
        "engine_achieved_atoms": achieved_atoms,
        "engine_point_inside_synthetic_work_range": bool(
            min(work_values) <= achieved_atoms <= max(work_values)),
        "entered": complete,
        "interpretation": (
            "descriptive integration/shape ratios; workloads are not exact "
            "equivalents and no acceptance threshold is applied"),
        "latency_ratio_engine_fdas_projection_p95_to_synthetic_incremental_p95": (
            float(engine_latency) / float(synthetic_latency)
            if complete else None),
        "memory_ratio_engine_controller_rss_p95_to_synthetic_process_rss_p95": (
            float(engine_rss) / float(synthetic_rss)
            if complete else None),
        "nearest_synthetic_tier": selected[0][3],
        "nearest_synthetic_work_atoms": nearest_work,
        "synthetic_latency_p95_ms": synthetic_latency,
        "synthetic_rss_p95_bytes": synthetic_rss,
        "synthetic_sample_count": len(selected),
    }


def audit_engine_shadow_report(
        report, minimum_pairs=20, synthetic_results=None):
    """Validate an existing paired engine-shadow cohort as the G8 input."""
    if report is None:
        return {
            "gate": "not-entered", "pair_count": 0,
            "valid": None, "errors": [], "integrity_errors": [],
            "synthetic_transfer": {
                "entered": False,
                "reason": "engine shadow report is unavailable",
            },
        }
    errors = []
    integrity_errors = []
    material = dict(report)
    claimed_hash = material.get("structural_hash")
    material["structural_hash"] = None
    if claimed_hash != structural_hash(material):
        message = "engine shadow report structural hash mismatch"
        errors.append(message)
        integrity_errors.append(message)
    pairs = report.get("pairs", ())
    if len(pairs) < int(minimum_pairs):
        errors.append(
            "engine shadow cohort has {} pairs; {} required".format(
                len(pairs), int(minimum_pairs)))
    for index, pair in enumerate(pairs):
        for key in (
                "action_trace_match", "result_trace_match",
                "behavioral_completion_match"):
            if pair.get(key) is not True:
                errors.append(
                    "engine pair {} failed {}".format(index, key))
        if pair.get("failures"):
            errors.append(
                "engine pair {} contains failures".format(index))
        shadow = pair.get("shadow", {})
        diagnostics = shadow.get("shadow", {})
        for key in (
                "authority_eligible_count", "authority_violation_count",
                "detail_omission_count", "legal_binding_failure_count",
                "missing_legacy_count", "safety_downgrade_count"):
            if int(diagnostics.get(key, 0)) != 0:
                errors.append(
                    "engine pair {} has nonzero {}".format(index, key))
        if shadow.get("event_validation_valid") is not True:
            errors.append(
                "engine pair {} event ledger is invalid".format(index))
    if report.get("acceptance", {}).get("accepted") is not True:
        errors.append("engine shadow source report was not accepted")
    entered = len(pairs) >= int(minimum_pairs)
    aggregate = report.get("aggregate", {})
    return {
        "engine_shadow_scenario": report.get("engine_shadow_scenario"),
        "errors": errors,
        "gate": "pass" if entered and not errors else (
            "fail" if entered else "not-entered"),
        "maximum_volume": report.get(
            "aggregate", {}).get("maximum_volume"),
        "pair_count": len(pairs),
        "performance": {
            "controller_latency_ms": aggregate.get(
                "controller_latency_ms"),
            "controller_process_peak_rss_bytes": aggregate.get(
                "controller_process_peak_rss_bytes"),
            "fdas_projection_latency_ms": aggregate.get(
                "fdas_projection_latency_ms"),
            "fdas_shadow_latency_ms": aggregate.get(
                "fdas_shadow_latency_ms"),
            "fdas_turn_contribution_ms": aggregate.get(
                "fdas_turn_contribution_ms"),
        },
        "source_report_hash": claimed_hash,
        "synthetic_transfer": _engine_synthetic_transfer(
            report, synthetic_results),
        "integrity_errors": integrity_errors,
        "totals": aggregate.get("totals"),
        "valid": not errors,
        "volume_expansion": aggregate.get("volume_expansion"),
    }


def audit_results(results, resamples=10000, engine_report=None):
    errors = []
    semantic_failures = []
    status_counts = {}
    surfaces = {}
    for index, row in enumerate(results):
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        surface = row["trial"]["cell"]["surface"]
        surfaces[surface] = surfaces.get(surface, 0) + 1
        material = dict(row)
        claimed_hash = material.pop("result_hash", None)
        actual_hash = structural_hash(material)
        if claimed_hash != actual_hash:
            errors.append("result {} hash mismatch".format(index))
        if row.get("trial_id") != _trial_identity(row):
            errors.append("result {} trial identity mismatch".format(index))
        if row["status"] == "completed" and row.get("errors"):
            errors.append("result {} completed with errors".format(index))
        correctness = row.get("correctness", {})
        required_true = required_correctness_keys(row)
        if surface == "combined":
            required_true = (
                "bridge_candidate_safe", "cold_incremental_equivalent",
                "fluid_healthy", "fluid_mass_within_1e_9",
                "proof_matches_reference", "truth_hash_unchanged")
        elif surface == "captured":
            required_true = (
                "at_least_target_atoms", "clone_authority_quarantined",
                "original_subgraph_invariant", "source_hash_verified")
        if row["status"] == "completed":
            for key in required_true:
                if correctness.get(key) is not True:
                    semantic_failures.append(
                        "result {} correctness failure: {}".format(index, key))
    report = build_report(results, resamples=resamples)
    engine_shadow = audit_engine_shadow_report(
        engine_report, synthetic_results=results)
    report["engine_shadow"] = engine_shadow
    report["gates"]["engine"] = engine_shadow["gate"]
    # A negative G8 result is an empirical gate failure, not a corrupt G9
    # reconstruction. Only a broken source-report identity invalidates audit
    # integrity; semantic and scale failures remain visible in the G8 gate.
    errors.extend(engine_shadow.get("integrity_errors", ()))
    return {
        "artifact_type": "freeciv-scalability-audit",
        "errors": errors,
        "report": report,
        "result_count": len(results),
        "schema_version": "1.0",
        "semantic_failures": semantic_failures,
        "status_counts": status_counts,
        "surface_counts": surfaces,
        "valid": not errors,
    }
