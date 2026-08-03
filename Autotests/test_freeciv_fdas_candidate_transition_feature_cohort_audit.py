import copy
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_candidate_transition_features import (  # noqa: E402
    AUDIT_IDENTITY as LEGACY_AUDIT_IDENTITY,
)
from audit_fdas_candidate_transition_features_cohort import (  # noqa: E402
    reinterpret_feature_audit,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _game(seed, moves, *, multi=0, diverse=0, signatures=0):
    opportunity = bool(multi and diverse and signatures >= 2)
    return {
        "errors": [],
        "game_id": "game-{}".format(seed),
        "gates": {
            "candidate_choice_store_is_valid": True,
            "every_move_query_is_enriched": moves > 0,
            "fortify_queries_remain_frozen": True,
            "frozen_predictions_are_byte_identical": True,
            "grounded_transition_signatures_are_diverse": opportunity,
            "multi_move_choice_sets_are_observed": multi > 0,
            "zero_incomplete_move_groundings": True,
        },
        "incomplete_grounding_reasons": {},
        "measures": {
            "choice_sets": max(1, moves),
            "complete_move_choices": moves,
            "diverse_multi_move_choice_sets": diverse,
            "fortify_choices": int(moves == 0),
            "frozen_prediction_compatibility_checks": moves,
            "incomplete_move_choices": 0,
            "move_choice_sets": moves,
            "move_choices": moves,
            "multi_move_choice_sets": multi,
            "unique_transition_signatures": signatures,
        },
        "passed": opportunity,
        "seed": seed,
        "store_digest": "store-{}".format(seed),
    }


def _legacy(games):
    totals = {
        name: sum(game["measures"][name] for game in games)
        for name in games[0]["measures"]}
    semantic = {
        "audit_identity": LEGACY_AUDIT_IDENTITY,
        "calibration_artifact_hash": "calibration-hash",
        "claim_scope": "legacy",
        "decision_safe_parent_audit_hash": "parent-hash",
        "games": games,
        "gates": {
            "all_feature_game_gates_pass": all(
                game["passed"] for game in games),
            "decision_safe_parent_audit_passes": True,
            "exact_expected_seeds_completed": True,
        },
        "model_result_hash": "model-hash",
        "passed": all(game["passed"] for game in games),
        "policy_authority": False,
        "readout_authority": False,
        "totals": totals,
        "truth_mutated": False,
    }
    return dict(semantic, report_hash=structural_hash(semantic))


def test_cohort_audit_accepts_sparse_game_when_cohort_has_opportunity():
    report = reinterpret_feature_audit(_legacy((
        _game(1, 4, multi=2, diverse=1, signatures=3),
        _game(2, 0),
        _game(3, 2, signatures=1),
    )))

    assert report["passed"] is True
    assert all(game["passed"] for game in report["games"])
    assert report["games"][1]["gates"][
        "move_queries_are_enriched_when_present"] is True


def test_cohort_audit_rejects_present_unenriched_move():
    legacy = _legacy((
        _game(1, 4, multi=2, diverse=1, signatures=3),
        _game(2, 2, signatures=1),
    ))
    legacy["games"][1]["gates"]["every_move_query_is_enriched"] = False
    semantic = copy.deepcopy(legacy)
    semantic.pop("report_hash")
    legacy["report_hash"] = structural_hash(semantic)

    report = reinterpret_feature_audit(legacy)

    assert report["passed"] is False
    assert report["games"][1]["gates"][
        "move_queries_are_enriched_when_present"] is False


def test_cohort_audit_rejects_absent_cohort_competition():
    report = reinterpret_feature_audit(_legacy((
        _game(1, 2, signatures=1),
        _game(2, 0),
    )))

    assert report["passed"] is False
    assert report["gates"][
        "multi_move_choice_sets_are_observed"] is False
    assert report["gates"][
        "diverse_multi_move_choice_sets_are_observed"] is False
