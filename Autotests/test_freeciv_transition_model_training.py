import json

from freeciv.pf_unified.transition_model_training import (
    evaluate_contextual_transition_value_model,
    fit_contextual_transition_value_model,
    fit_transition_value_model,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import GroundedImpactPlanner
from freeciv_agent.pressure import (
    CONTEXTUAL_TRANSITION_VALUE_MODEL_ID,
    ContextualTransitionValueModel,
    TransitionValueModel,
    validate_contextual_calibration_bundle,
)


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


def _contextual_observation(index):
    return {
        "action_id": "action-{}".format(index),
        "adverse_loss": 0.0,
        "adverse_loss_status": "observed",
        "causal_status": "eligible",
        "eligibility_trace": [
            "authoritative-next-snapshot",
            "selected-action-identity-matched",
        ],
        "estimator_version":
            CONTEXTUAL_TRANSITION_VALUE_MODEL_ID,
        "key": {
            "context": {
                "action_category": "movement",
                "action_type": "unit_move",
                "actor_class": "unit:settlers",
                "exact_context_digest": "plains-route",
                "horizon_bucket": "medium:4-10",
                "lifecycle_state": "route-progress",
                "ruleset_digest": "ruleset-a",
                "ruleset_family": "civ2civ3",
                "target_class": "tile:land",
                "threat_bucket": "distant:4+",
            },
            "estimator_version":
                CONTEXTUAL_TRANSITION_VALUE_MODEL_ID,
            "goal_id": "pf-impact:expansion",
            "policy_version": "scalar-v2/1.0",
            "schema_version": "2.0",
        },
        "observation_id": "contextual-{}".format(
            index),
        "operation_id": "operation-{}".format(
            index),
        "outcome_status": "terminal",
        "policy_version": "scalar-v2/1.0",
        "predicted_relief": 0.8,
        "predicted_transition_digest":
            "prediction-{}".format(index),
        "realized_goal_relief": 0.2,
        "realized_outcome_digest":
            "realized-{}".format(index),
        "relief_source": "authoritative:test",
        "selected_policy_id": "scalar-v2",
        "selection_policy_kind": "deterministic",
        "selection_propensity": None,
        "update_scope": "control-model-only",
    }


def _write_contextual_cohort(
        root, cohort, indexes):
    run = (
        root / "artifacts" / "games"
        / "impact_pair" / cohort
        / "treatment" / "e_full_loop"
        / "123-00")
    run.mkdir(parents=True)
    source = {
        "commit": "contextual-source",
        "dirty": False,
        "implementation_sha256": "e" * 64,
        "source_files": 5,
    }
    _write_json(run / "manifest.json", {
        "impact_pair": {
            "arm": "treatment",
            "claim_eligible": False,
            "cohort": cohort,
            "cohort_purpose": "diagnostic",
        },
        "seed": 123,
        "source": source,
    })
    _write_json(run / "status.json", {
        "completed": True,
        "status": "completed",
    })
    with open(
            run / "events.jsonl", "w",
            encoding="utf-8") as stream:
        for index in indexes:
            stream.write(json.dumps({
                "type": "transition_value_updated",
                "payload": {
                    "summary": {
                        "observation":
                            _contextual_observation(
                                index),
                    },
                },
            }) + "\n")


def test_contextual_fit_and_disjoint_holdout_write_approved_bundle(
        tmp_path):
    _write_contextual_cohort(
        tmp_path, "contextual-training",
        range(4))
    _write_contextual_cohort(
        tmp_path, "contextual-holdout",
        range(100, 108))
    model_path = tmp_path / "contextual-model.json"
    fit = fit_contextual_transition_value_model(
        str(tmp_path / "artifacts"),
        str(model_path),
        "contextual-fit",
        "contextual-training",
        minimum_samples=2,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0)

    assert fit["schema_version"] == "2.0"
    assert fit["outcome_count"] == 4
    assert fit["supported_key_count"] == 1
    approval_path = (
        tmp_path / "contextual-approval.json")
    approval = (
        evaluate_contextual_transition_value_model(
            str(tmp_path / "artifacts"),
            str(model_path),
            "contextual-fit",
            "contextual-holdout",
            str(approval_path),
            minimum_samples=2,
            maximum_half_width=1.0,
            shrinkage_kappa=0.0,
            bootstrap_iterations=200))
    frozen = ContextualTransitionValueModel(
        str(model_path),
        identity="contextual-fit",
        minimum_samples=2,
        maximum_half_width=1.0,
        shrinkage_kappa=0.0,
        read_only=True)

    assert approval["authority_approved"]
    assert approval["claim_eligible"] is False
    assert approval["cohort"] == (
        "contextual-holdout")
    assert approval["seed_count"] == 1
    assert len(approval["event_files"]) == 1
    assert approval["model_identity"] == (
        "contextual-fit")
    assert approval["aggregate"][
        "coverage"] == 1.0
    assert validate_contextual_calibration_bundle(
        str(approval_path), frozen)[
            "report_hash"] == approval[
                "report_hash"]

    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_contextual_conductance_enabled": True,
        "pressure_contextual_conductance_authority_enabled": True,
        "pressure_contextual_conductance_model_path":
            str(model_path),
        "pressure_contextual_conductance_model_identity":
            "contextual-fit",
        "pressure_contextual_conductance_read_only": True,
        "pressure_contextual_conductance_approval_path":
            str(approval_path),
        "pressure_contextual_minimum_samples": 2,
        "pressure_contextual_maximum_half_width": 1.0,
        "pressure_contextual_shrinkage_kappa": 0.0,
    })
    assert planner.controller_activation[
        "layers"]["contextual_conductance"][
            "enabled"]
