"""Audit the frozen PR99 retained-capacity shadow-model fit."""

from collections import Counter

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    FdasRetainedCapacityQueryEpisodeRow,
    FdasRetainedCapacityTransitionModel,
    FdasRetainedCapacityTransitionPrediction,
    RETAINED_CAPACITY_PRODUCT_TARGET,
    RETAINED_CAPACITY_RELIEF_TARGET,
    RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS,
    fit_retained_capacity_transition_model,
)


TRANSITION_MODEL_FIT_IDENTITY = (
    "fdas-retained-capacity-transition-model-fit/1.0")


def _target_counts(predictions, name):
    values = [getattr(value, name) for value in predictions]
    return {
        "abstained": sum(value.status == "abstained" for value in values),
        "estimated": sum(value.status == "estimated" for value in values),
    }


def audit_fdas_retained_capacity_transition_model_fit(source_report):
    """Fit, roundtrip, predict, and audit without granting authority."""
    model = fit_retained_capacity_transition_model(source_report)
    reparsed_model = FdasRetainedCapacityTransitionModel.from_dict(
        model.to_dict())
    prediction_rows = []
    predictions = []
    for value in source_report["dataset"]["rows"]:
        row = FdasRetainedCapacityQueryEpisodeRow.from_dict(value["row"])
        prediction = model.predict(row.query)
        reparsed = FdasRetainedCapacityTransitionPrediction.from_dict(
            prediction.to_dict())
        if reparsed != prediction:
            raise ValueError("retained capacity prediction roundtrip differs")
        predictions.append(prediction)
        prediction_rows.append({
            "observation_status": row.observation_status,
            "outcome_status": row.outcome_status,
            "prediction": prediction.to_dict(),
            "row_id": row.row_id,
            "seed": value["seed"],
        })
    prediction_rows.sort(key=lambda value: (value["seed"], value["row_id"]))
    by_level = Counter(
        value.selected_level or "no-eligible-root" for value in predictions)
    bins_by_scope = Counter(
        (value.level, value.target, "sample-eligible"
         if value.sample_eligible else "sample-ineligible",
         "numerically-usable" if value.numerically_usable
         else "numerically-abstained")
        for value in model.bins)
    bin_scope_rows = [{
        "bins": count,
        "level": level,
        "numerical_status": numerical,
        "sample_status": sample,
        "target": target,
    } for (level, target, sample, numerical), count
        in sorted(bins_by_scope.items(), key=lambda item: (
            RETAINED_CAPACITY_TRANSITION_MODEL_LEVELS.index(item[0][0]),
            item[0][1:]))]
    paired = {}
    for value in model.bins:
        paired.setdefault(
            (value.level, value.feature_values), {})[value.target] = value
    target_pairs_are_nested = True
    for targets in paired.values():
        product = targets.get(RETAINED_CAPACITY_PRODUCT_TARGET)
        relief = targets.get(RETAINED_CAPACITY_RELIEF_TARGET)
        if (product is None or relief is None
                or product.sample_eligible != relief.sample_eligible
                or product.independent_games != relief.independent_games
                or tuple(row.row_ids for row in product.game_outcomes)
                != tuple(row.row_ids for row in relief.game_outcomes)
                or (product.estimate is not None
                    and product.estimate < relief.estimate)):
            target_pairs_are_nested = False
            break
    model_material = model.to_dict()
    authority_names = (
        "action_authority", "calibrated", "learning_write_through",
        "policy_authority", "readout_authority", "truth_mutated")
    checks = {
        "all_301_source_games_are_listed_once": (
            len(model.source_games) == 301
            and len({value.seed for value in model.source_games}) == 301),
        "all_163_query_rows_are_partitioned_once": (
            len(model.training_rows) == 162
            and len(model.excluded_rows) == 1
            and len({value.row_id for value in (
                model.training_rows + model.excluded_rows)}) == 163),
        "all_model_and_prediction_authority_remains_disabled": (
            all(model_material.get(name) is False for name in authority_names)
            and all(all(value.to_dict().get(name) is False
                        for name in authority_names)
                    for value in predictions)),
        "all_source_queries_receive_one_shadow_prediction": (
            len(predictions) == 163
            and len({value.query_id for value in predictions}) == 163),
        "censored_row_is_retained_but_excluded_from_fitting": (
            len(model.excluded_rows) == 1
            and model.excluded_rows[0].exclusion_reason
            == "right-censored-no-terminal-target"
            and model.excluded_rows[0].row_id not in {
                value.row_id for value in model.training_rows}),
        "exact_product_and_goal_relief_bins_preserve_target_nesting": (
            target_pairs_are_nested),
        "model_roundtrip_and_bin_recomputation_are_exact": (
            reparsed_model == model),
        "source_report_mechanics_and_adequacy_pass": (
            source_report["acceptance"]["accepted"] is True
            and source_report["discovery_ready"] is True),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "bin_scopes": bin_scope_rows,
        "claim_scope": (
            "deterministic in-sample discovery fit and numerical coverage "
            "for a shadow retained-capacity transition model; no calibration, "
            "validation, causal, readout, policy, action, gameplay, score, or "
            "win-rate claim"),
        "identity": TRANSITION_MODEL_FIT_IDENTITY,
        "model": model_material,
        "prediction_rows": prediction_rows,
        "schema_version": "1.0",
        "source": {
            "cohort_structural_hash": source_report["structural_hash"],
            "dataset_hash": source_report["dataset"]["dataset_hash"],
        },
        "summary": {
            "excluded_censored_rows": len(model.excluded_rows),
            "fitted_bins": len(model.bins),
            "goal_relief_predictions": _target_counts(
                predictions, "goal_relief"),
            "prediction_selected_levels": dict(sorted(by_level.items())),
            "product_effect_predictions": _target_counts(
                predictions, "product_effect"),
            "sample_eligible_bins": sum(
                value.sample_eligible for value in model.bins),
            "source_games": len(model.source_games),
            "source_query_rows": len(predictions),
            "training_terminal_rows": len(model.training_rows),
            "numerically_usable_bins": sum(
                value.numerically_usable for value in model.bins),
        },
        "action_authority": False,
        "calibrated": False,
        "learning_write_through": False,
        "policy_authority": False,
        "readout_authority": False,
        "truth_mutated": False,
    }
    report["structural_hash"] = structural_hash(report)
    return report
