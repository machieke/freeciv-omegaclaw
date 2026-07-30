"""Retained GDO-4 diagnostic runner contract."""

import json
import os
import subprocess
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    REPO, "scripts",
    "run_gdo_city_defense_diagnostic.py")


def test_city_defense_diagnostic_proves_exact_small_graph_mechanism():
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(
            directory, "report.json")
        process = subprocess.run(
            [
                sys.executable,
                SCRIPT,
                "--timing-iterations",
                "1",
                "--output", output,
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=30)
        assert process.returncode == 0, (
            process.stderr)
        with open(
                output,
                encoding="utf-8") as stream:
            report = json.load(
                stream)

    assert report["passed"]
    assert report["claim_status"] == (
        "synthetic-mechanism-diagnostic-only")
    assert report["scenario_count"] == 64
    assert report["gates"][
        "all_exact_results_match_brute_force"]
    assert report["gates"][
        "known_greedy_counterexample_improved"]
    assert report[
        "exact_beats_greedy_scenario_count"] > 0
    assert report["arms"]["B4"][
        "uncovered_threat_slots"] < (
            report["arms"]["B3"][
                "uncovered_threat_slots"])
    assert not report[
        "policy_authority"]
