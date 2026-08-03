from copy import deepcopy

from freeciv.harness.fdas_randomized_candidate_value import (
    analyze_randomized_candidate_value,
)


def _audit(treatment_outcome):
    games = []
    for index in range(40):
        arm = "control" if index < 20 else "treatment"
        outcome = False if arm == "control" else treatment_outcome
        games.append({
            "assignments": [{
                "assigned_arm": arm,
                "game_id": "game-{}".format(index),
                "label_outcome": outcome,
                "label_status": "observed",
                "selection_propensity": 0.5,
            }],
            "game_id": "game-{}".format(index),
        })
    return {
        "audit_identity": "fdas-randomized-alternative-live-audit/1.5",
        "games": games,
        "passed": True,
        "report_hash": "source-audit",
    }


def test_candidate_value_discovery_advances_only_positive_clustered_interval():
    report = analyze_randomized_candidate_value(
        _audit(True), minimum_assignments_per_arm=20,
        minimum_game_clusters_per_arm=20, bootstrap_samples=500)

    assert report["mechanically_valid"] is True
    assert report["discovery_risk_difference"] == 1.0
    assert report["bootstrap"]["interval"] == [1.0, 1.0]
    assert report["passed"] is True
    assert report["disposition"] == "advance-positive-confirmation"


def test_candidate_value_discovery_freezes_null_without_mechanical_failure():
    audit = _audit(False)
    report = analyze_randomized_candidate_value(
        audit, minimum_assignments_per_arm=20,
        minimum_game_clusters_per_arm=20, bootstrap_samples=500)

    assert report["mechanically_valid"] is True
    assert report["discovery_positive_gate"] is False
    assert report["passed"] is False
    assert report["disposition"] == "freeze-no-positive-value"

    changed = deepcopy(audit)
    changed["games"] = changed["games"][:-1]
    incomplete = analyze_randomized_candidate_value(
        changed, minimum_assignments_per_arm=20,
        minimum_game_clusters_per_arm=20, bootstrap_samples=500)
    assert incomplete["mechanically_valid"] is False
    assert incomplete["disposition"] == "mechanically-incomplete"
