"""GDO-8 engine calibration evidence remains reproducible and bounded."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_gdo_contextual_engine_audit.py"
SPEC = importlib.util.spec_from_file_location(
    "run_gdo_contextual_engine_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_gdo8_engine_audit_is_approved_and_deterministic():
    first = MODULE.run()
    second = MODULE.run()

    assert first == second
    assert all(first["gates"].values())
    assert first["result"][
        "engine_holdout_approved"]
    assert first["seeds"] == {
        "holdout_count": 30,
        "training_count": 30,
    }
    assert first["claim_boundary"] == {
        "gameplay_score_claim": False,
        "off_policy_value_claim": False,
        "prediction_calibration_claim": True,
    }
