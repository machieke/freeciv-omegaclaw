import json
import os

from freeciv.pf_unified.transition_model_training import (
    fit_transition_value_model,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import TransitionValueModel


def _write_json(path, value):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.write("\n")


def test_training_fit_accepts_only_clean_claim_ineligible_outcomes(
        tmp_path):
    run = (
        tmp_path / "artifacts" / "games"
        / "impact_pair" / "training-v1"
        / "treatment" / "e_full_loop"
        / "123-00")
    run.mkdir(parents=True)
    source = {
        "commit": "abc",
        "dirty": False,
        "implementation_sha256": "d" * 64,
        "source_files": 4,
    }
    _write_json(run / "manifest.json", {
        "impact_pair": {
            "arm": "treatment",
            "claim_eligible": False,
            "cohort": "training-v1",
            "cohort_purpose": "diagnostic",
        },
        "seed": 123,
        "source": source,
    })
    _write_json(run / "status.json", {
        "completed": True,
        "status": "completed",
    })
    events = []
    for index in range(3):
        observation = {
            "context_digest": "context-{}".format(index),
            "effect_observed": True,
            "key": {
                "action_category": "expansion",
                "goal_id": "pf-impact:expansion",
                "lifecycle_state": "route-progress",
            },
            "observation_id": "observation-{}".format(index),
            "predicted_relief": 0.2,
            "realized_relief": 0.4,
            "relief_source": "authoritative:test",
            "selection_propensity": None,
            "update_scope": "control-model-only",
        }
        events.append({
            "type": "transition_value_updated",
            "payload": {
                "summary": {
                    "observation": observation,
                },
            },
        })
    with open(
            run / "events.jsonl", "w",
            encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event) + "\n")

    model_path = tmp_path / "frozen-model.json"
    report = fit_transition_value_model(
        str(tmp_path / "artifacts"),
        str(model_path),
        "training-v1",
        "training-v1",
        minimum_samples=2,
        maximum_half_width=1.0)
    assert report["observation_count"] == 3
    assert report["supported_key_count"] == 1
    assert report["source_identity"] == (
        structural_hash(source))
    assert TransitionValueModel(
        str(model_path),
        identity="training-v1",
        minimum_samples=2,
        maximum_half_width=1.0,
        read_only=True).state_hash == (
            report["model_state_hash"])


def test_training_fit_rejects_claim_eligible_trace(tmp_path):
    run = (
        tmp_path / "artifacts" / "games"
        / "impact_pair" / "training-v1"
        / "treatment" / "e_full_loop"
        / "123-00")
    run.mkdir(parents=True)
    _write_json(run / "manifest.json", {
        "impact_pair": {
            "arm": "treatment",
            "claim_eligible": True,
            "cohort": "training-v1",
            "cohort_purpose": "confirmatory",
        },
        "seed": 123,
        "source": {"dirty": False},
    })
    _write_json(run / "status.json", {
        "completed": True,
        "status": "completed",
    })
    (run / "events.jsonl").write_text(
        "", encoding="utf-8")
    try:
        fit_transition_value_model(
            str(tmp_path / "artifacts"),
            str(tmp_path / "model.json"),
            "training-v1",
            "training-v1")
    except ValueError as error:
        assert "claim-ineligible" in str(error)
    else:
        raise AssertionError(
            "claim-eligible training trace was accepted")
