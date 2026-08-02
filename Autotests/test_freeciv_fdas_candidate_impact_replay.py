import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atomspace import load_runtime_declaration  # noqa: E402


REPORT = os.path.join(
    REPO, "docs", "freeciv", "evidence",
    "fdas-pr32-candidate-impact-replay.json")
RUNNER = os.path.join(
    REPO, "scripts", "freeciv",
    "evaluate_fdas_candidate_impact_replay.py")
CONFIG = os.path.join(
    REPO, "profile",
    "dependent_atomspace_defense_actor_persistence_causal_induction_shadow.yaml")
MANIFEST = os.path.join(
    REPO, "profile",
    "fdas_manifest_defense_actor_persistence_candidate_impact_shadow.json")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_candidate_impact_replay_evidence_is_current_and_non_authorizing():
    with open(REPORT, encoding="utf-8") as stream:
        report = json.load(stream)
    material = dict(report)
    claimed_hash = material.pop("structural_hash")

    assert claimed_hash == structural_hash(material)
    assert report["acceptance"]["accepted"] is True
    assert all(report["acceptance"]["checks"].values())
    assert report["failures"] == []
    assert report["source"]["dirty"] is False
    assert report["source"]["runner_sha256"] == _sha256(RUNNER)
    declaration = load_runtime_declaration(CONFIG, MANIFEST)
    assert report["config"]["declaration_hash"] == (
        declaration["declaration_hash"])
    assert report["summary"] == {
        "candidate_rows": 101,
        "complete_prediction_coverage_count": 21,
        "contextual_priority_delta_count": 80,
        "counterfactual_winner_change_count": 0,
        "evaluated_count": 38,
        "evaluation_reason_counts": {
            "approved_category_candidate_impact_available": 13,
            ("approved_category_candidate_impact_available_"
             "global_winner_outside_category"): 25,
        },
        "multi_candidate_evaluation_count": 29,
        "readout_reason_counts": {
            "approved_shadow_prediction_available": 53,
            ("compatible_maximal_predictions_conservative_"
             "above_baseline"): 27,
            "no_approved_rule_matches": 21,
        },
        "replay_count": 38,
    }
    evaluations = tuple(
        row["evaluation"] for row in report["readouts"])
    assert all(
        value["truth_mutated"] is False
        and value["policy_authority"] is False
        and value["readout_authority"] is False
        and value["action_selection_changed"] is False
        for value in evaluations)
    impacts = tuple(value["impact"] for value in evaluations)
    assert all(value is not None for value in impacts)
    assert all(
        value["truth_mutated"] is False
        and value["policy_authority"] is False
        and value["readout_authority"] is False
        and value["action_selection_changed"] is False
        for value in impacts)
