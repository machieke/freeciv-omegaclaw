"""GDO baseline and paired shadow diagnostic reproducibility."""

import importlib.util
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
        REPO):
    if path not in sys.path:
        sys.path.insert(0, path)


def _module(name, relative_path):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(REPO, relative_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_manifest_capture_has_stable_required_identity():
    module = _module(
        "run_gdo_baseline",
        "scripts/run_gdo_baseline.py")

    manifest = module.build_manifest(
        run_tests=False)

    assert manifest["schema_version"] == "1.0"
    assert len(manifest["source_commit"]) == 40
    assert len(manifest["manifest_identity"]) == 64
    assert manifest["comparators"] == {
        "B0": "canonical Impact",
        "B1": "scalar PF-v2 plus v1 packet scheduler",
    }


def test_frozen_grounded_baseline_records_complete_supported_scope():
    with open(os.path.join(
            REPO, "benchmarks", "gdo",
            "baseline_manifest.json"),
            encoding="utf-8") as stream:
        manifest = json.load(stream)

    assert manifest[
        "baseline_status"] == "frozen_complete"
    assert all(
        status.startswith("passed")
        for status in
        manifest["gates"].values())
    assert manifest[
        "engine_baseline"][
            "cohort_status"] == "passed"
    assert len(manifest[
        "engine_baseline"][
            "evidence"]) == 3
    assert manifest[
        "retained_inputs"][
            "transport_boundary"][
                "authority"] == (
                    "synthetic-contract-only")
    assert manifest[
        "retained_inputs"][
            "transport_boundary"][
                "fresh_engine_sequence_available"] is False


def test_paired_shadow_replay_preserves_policy_and_estimate_semantics():
    module = _module(
        "run_gdo_replay",
        "scripts/run_gdo_replay.py")

    report = module.run(
        module.DEFAULT_FIXTURE,
        iterations=10,
        warmup=1)

    assert report["coverage"]["minimum_fraction"] == 1.0
    assert report["gates"]["candidate_coverage"]
    assert report["gates"][
        "action_trace_byte_identical"]
    assert report["gates"]["live_order_identical"]
    assert report["gates"]["schedule_identical"]
    assert report["gates"][
        "semantic_estimates_deterministic"]
    assert not report["policy_authority"]
    assert report["claim_status"] == "diagnostic-only"
    assert report["domain_readout"][
        "authority_counts"]
    assert report["domain_readout"][
        "estimator_counts"]
