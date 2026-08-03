import json
import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    FdasCandidateChoiceCalibrationExport,
    evaluate_candidate_calibration,
    fit_candidate_calibration,
    load_candidate_calibration_confirmation,
    load_candidate_calibration_model,
)
from freeciv_agent.pressure import InductionEpisode  # noqa: E402


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"
FORTIFY = "fdas-shadow:unit-fortification-opportunity:unit_fortify"


def _episode(game, index, operation_type, outcome, lineage=None,
             lifecycle="0-31"):
    lineage = lineage or "{}-{}-{}".format(
        game, operation_type.rsplit(":", 1)[-1], index)
    return InductionEpisode(
        "episode-{}-{}".format(game, index),
        (
            ("induction_feature_schema", "defense-episode-features/3.0"),
            ("operation_type", operation_type),
            ("outcome_target",
             DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET),
        ),
        ("context:turn_phase_band={}".format(lifecycle),),
        outcome,
        (
            "candidate-lineage:" + lineage,
            "game-id:" + game,
            "source-event:{}".format(index),
        ),
    )


def _export(store_digest, episodes):
    episodes = tuple(episodes)
    semantic = {
        "choice_set_count": len(episodes),
        "examples": [value.to_dict() for value in episodes],
        "no_in_scope_selection_count": 0,
        "nonselected_censored_count": len(episodes),
        "operation_type": DEFENSE_CANDIDATE_CHOICE_SURFACE,
        "outcome_target": DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        "policy_authority": False,
        "readout_authority": False,
        "selected_observed_count": len(episodes),
        "selected_pending_or_censored_count": 0,
        "source_store_digest": store_digest,
        "truth_mutated": False,
    }
    return FdasCandidateChoiceCalibrationExport(
        DEFENSE_CANDIDATE_CHOICE_SURFACE,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
        store_digest, episodes, len(episodes), len(episodes), 0, 0,
        structural_hash(semantic))


def _discovery():
    return (
        _export("discovery-store-a", tuple(
            _episode("d1", index, MOVE, index < 3)
            for index in range(5))),
        _export("discovery-store-b", tuple(
            _episode("d2", index, FORTIFY, index < 9)
            for index in range(5, 10))),
    )


def _confirmation():
    shared = "c1-shared-move"
    return (
        _export("confirmation-store-a", (
            _episode("c1", 0, MOVE, True, shared),
            _episode("c1", 1, MOVE, False, shared),
            _episode("c1", 2, MOVE, True),
            _episode("c1", 3, FORTIFY, True),
            _episode("c1", 4, FORTIFY, False),
        )),
        _export("confirmation-store-b", (
            _episode("c2", 5, MOVE, False),
            _episode("c2", 6, MOVE, True),
            _episode("c2", 7, FORTIFY, True),
            _episode("c2", 8, FORTIFY, True),
        )),
    )


def _thresholds():
    return {
        "maximum_action_calibration_error": 1.0,
        "maximum_brier_score": 1.0,
        "maximum_calibration_error": 1.0,
        "maximum_log_loss": 2.0,
        "minimum_lifecycle_brier_improvement_ci_lower": -1.0,
        "minimum_prediction_coverage": 1.0,
    }


def test_heldout_validation_clusters_lineages_and_denies_authority():
    model = fit_candidate_calibration(
        _discovery(), "validation-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    report = evaluate_candidate_calibration(
        model, _confirmation(), "confirmation-test", _thresholds(),
        bootstrap_samples=200, bootstrap_seed=91)

    assert report["passed"] is True
    assert report["raw_observed_rows"] == 9
    assert report["selected_effective_lineages"] == 8
    assert report["prediction_coverage"] == 1.0
    assert report["overall_metrics"]["lineages"] == 8
    assert report["bootstrap_brier_improvement_over_action_only"][
        "cluster_count"] == 2
    assert report["policy_authority"] is False
    assert report["readout_authority"] is False
    assert report["truth_mutated"] is False
    semantic = dict(report)
    claimed = semantic.pop("report_hash")
    assert claimed == structural_hash(semantic)


def test_heldout_validation_rejects_discovery_overlap():
    discovery = _discovery()
    model = fit_candidate_calibration(
        discovery, "validation-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)

    with pytest.raises(ValueError, match="overlaps calibration discovery"):
        evaluate_candidate_calibration(
            model, discovery, "overlap-test", _thresholds(),
            bootstrap_samples=200)


def test_calibration_artifact_loader_rejects_wrapper_and_model_tampering():
    model = fit_candidate_calibration(
        _discovery(), "validation-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    semantic = {
        "calibration_model": model.to_dict(),
        "policy_authority": False,
        "readout_authority": False,
        "truth_mutated": False,
    }
    artifact = dict(semantic)
    artifact["report_hash"] = structural_hash(semantic)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "model.json")
        with open(path, "wb") as stream:
            stream.write(canonical_json_bytes(artifact) + b"\n")
        loaded, artifact_hash = load_candidate_calibration_model(path)
        assert loaded == model
        assert artifact_hash == artifact["report_hash"]

        artifact["policy_authority"] = True
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(artifact, stream)
        with pytest.raises(ValueError, match="artifact hash differs"):
            load_candidate_calibration_model(path)


def test_confirmation_loader_binds_passing_nested_validation():
    model = fit_candidate_calibration(
        _discovery(), "validation-model",
        minimum_action_lineages=5, minimum_lifecycle_lineages=3)
    validation = evaluate_candidate_calibration(
        model, _confirmation(), "confirmation-test", _thresholds(),
        bootstrap_samples=200, bootstrap_seed=91)
    semantic = {
        "calibration_artifact_hash": "discovery-artifact-hash",
        "claim_scope": validation["claim_scope"],
        "model_result_hash": model.result_hash,
        "passed": True,
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": "fdas-candidate-calibration-confirmation/1.0",
        "truth_mutated": False,
        "validation": validation,
    }
    artifact = dict(semantic)
    artifact["report_hash"] = structural_hash(semantic)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "confirmation.json")
        with open(path, "wb") as stream:
            stream.write(canonical_json_bytes(artifact) + b"\n")
        loaded, artifact_hash = load_candidate_calibration_confirmation(path)
        assert loaded == artifact
        assert artifact_hash == artifact["report_hash"]

        artifact["validation"]["passed"] = False
        artifact_semantic = dict(artifact)
        artifact_semantic.pop("report_hash")
        artifact["report_hash"] = structural_hash(artifact_semantic)
        with open(path, "wb") as stream:
            stream.write(canonical_json_bytes(artifact) + b"\n")
        with pytest.raises(ValueError, match="validation hash differs"):
            load_candidate_calibration_confirmation(path)
