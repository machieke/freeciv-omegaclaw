"""The retained GDO-8 authority diagnostic stays fail-closed."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT / "benchmarks" / "gdo"
    / "gdo8_contextual_authority_diagnostic.json")


def test_contextual_authority_diagnostic_is_safe_but_not_a_score_claim():
    report = json.loads(
        ARTIFACT.read_text(
            encoding="utf-8"))

    assert all(report["gates"].values())
    assert report["result"][
        "runtime_authority_gate_passed"]
    assert not report["result"][
        "policy_benefit_gate_passed"]
    assert not report["result"][
        "live_authority_recommended"]
    assert report["policy_effect"][
        "score_delta"]["estimate"] == 0.0
    assert report["policy_effect"][
        "action_divergence_pairs"] == 4
    assert not report["claim_boundary"][
        "gameplay_score_claim"]
