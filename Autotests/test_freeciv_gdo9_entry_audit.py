"""Conditional GDO-9 bridge/flow re-entry and live evidence tests."""

import importlib.util
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _audit_module():
    path = os.path.join(
        REPO, "scripts",
        "run_gdo_bridge_flow_entry_audit.py")
    specification = (
        importlib.util.spec_from_file_location(
            "gdo9_entry_audit", path))
    module = importlib.util.module_from_spec(
        specification)
    specification.loader.exec_module(module)
    return module


def test_gdo9_entry_audit_is_deterministic_and_fail_closed():
    module = _audit_module()
    first = module.run()
    second = module.run()
    artifact_path = os.path.join(
        REPO, "benchmarks", "gdo",
        "gdo9_bridge_flow_entry_audit.json")
    with open(
            artifact_path,
            encoding="utf-8") as stream:
        artifact = json.load(stream)

    assert first == second == artifact
    assert not artifact["entry_approved"]
    assert artifact["decision"][
        "result"] == "entry-gate-closed"
    assert not artifact["decision"][
        "bridge_reentry_allowed"]
    assert not artifact["decision"][
        "flow_reentry_allowed"]
    assert sum(
        row["passed"]
        for row in
        artifact["conditions"].values()) == 3
    assert artifact["conditions"][
        "1_candidate_invariant_calibrated_target_slice"][
            "passed"]
    assert artifact["conditions"][
        "2_zero_hard_identity_overallocation"][
            "passed"]
    assert artifact["conditions"][
        "4_bounded_exact_scheduler_is_comparison_baseline"][
            "passed"]
