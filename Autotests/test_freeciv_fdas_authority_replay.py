import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPT_DIR = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atomspace import load_runtime_declaration  # noqa: E402
from run_fdas_bounded_authority_replay import (  # noqa: E402
    implementation_identity,
)


REPORT = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-bounded-city-authority-replay.json")


def test_bounded_city_authority_evidence_is_current_and_fail_closed():
    with open(REPORT, encoding="utf-8") as stream:
        report = json.load(stream)
    semantic = dict(report)
    semantic.pop("generated_at")
    claimed_hash = semantic.pop("report_hash")

    assert claimed_hash == structural_hash(semantic)
    assert report["result"] == {
        "authorized_count": 4,
        "fallback_count": 34,
        "passed": True,
        "policy_winner_change_count": 0,
    }
    assert all(report["gates"].values())
    assert report["failures"] == []
    assert report["source"] == implementation_identity()

    declaration = load_runtime_declaration(
        os.path.join(
            REPO, "profile",
            "dependent_atomspace_city_stability_authority.yaml"),
        os.path.join(
            REPO, "profile",
            "fdas_manifest_city_stability_authority.json"),
    )
    assert report["config"]["declaration_hash"] == (
        declaration["declaration_hash"])

    authorized = tuple(
        row for row in report["readouts"]
        if row["readout"]["status"] == "authorized")
    assert len(authorized) == 4
    for row in authorized:
        readout = row["readout"]
        assert row["action_key"] == row["legacy_action_key"]
        assert readout["authority_pressure"][
            "selected_operation_id"] == readout["operation_id"]
        assert readout["operation_id"] in readout["scheduling"][
            "joint_selected_operation_ids"]
        assert readout["commit_validation"][
            "plan_materialization_authorized"] is True
        assert readout["commit_validation"][
            "execution_authority"] is False
