"""Reconstruct scaling trial identities and claim inputs from raw artifacts."""

import json
import os

from freeciv_agent.events.schema import structural_hash

from .analysis import build_report, required_correctness_keys
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


def audit_engine_shadow_report(report, minimum_pairs=20):
    """Validate an existing paired engine-shadow cohort as the G8 input."""
    if report is None:
        return {
            "gate": "not-entered", "pair_count": 0,
            "valid": None, "errors": [],
        }
    errors = []
    material = dict(report)
    claimed_hash = material.get("structural_hash")
    material["structural_hash"] = None
    if claimed_hash != structural_hash(material):
        errors.append("engine shadow report structural hash mismatch")
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
    return {
        "errors": errors,
        "gate": "pass" if entered and not errors else (
            "fail" if entered else "not-entered"),
        "maximum_volume": report.get(
            "aggregate", {}).get("maximum_volume"),
        "pair_count": len(pairs),
        "source_report_hash": claimed_hash,
        "valid": not errors,
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
    engine_shadow = audit_engine_shadow_report(engine_report)
    report["engine_shadow"] = engine_shadow
    report["gates"]["engine"] = engine_shadow["gate"]
    errors.extend(engine_shadow["errors"])
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
