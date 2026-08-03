"""Held-out validation for grounded move-transition calibration."""

import json
import math
import random

from ..events.schema import structural_hash
from ..pressure.induction import InductionFeatureQuery
from .fdas_candidate_transition_calibration import (
    FdasCandidateTransitionCalibrationModel,
    TRANSITION_CALIBRATION_LEVELS,
)
from .fdas_candidate_transition_features import (
    CANDIDATE_TRANSITION_OPERATION_TYPE,
)
from .fdas_candidate_choices import FdasCandidateChoiceCalibrationExport


TRANSITION_VALIDATION_IDENTITY = (
    "fdas-candidate-transition-calibration-validation/1.0")
DEFAULT_TRANSITION_VALIDATION_THRESHOLDS = {
    "maximum_brier_score": 0.30,
    "maximum_calibration_error": 0.20,
    "maximum_log_loss": 0.85,
    "minimum_candidate_specific_prediction_fraction": 0.25,
    "minimum_distinct_prediction_values": 2,
    "minimum_game_cluster_brier_improvement_ci_lower": -0.05,
    "minimum_heldout_lineages": 12,
    "minimum_prediction_coverage": 0.80,
}


def load_candidate_transition_calibration_model(path):
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    report_hash = raw.get("report_hash")
    semantic = dict(raw)
    semantic.pop("report_hash", None)
    if (not isinstance(report_hash, str)
            or report_hash != structural_hash(semantic)):
        raise ValueError("transition calibration artifact hash differs")
    if raw.get("schema_version") != (
            "fdas-candidate-transition-calibration-fit/1.0"):
        raise ValueError("transition calibration fit schema differs")
    if any(raw.get(name) is not False for name in (
            "policy_authority", "readout_authority", "truth_mutated")):
        raise ValueError("transition calibration artifact grants authority")
    return FdasCandidateTransitionCalibrationModel.from_dict(
        raw["calibration_model"]), report_hash


def load_candidate_transition_calibration_confirmation(path):
    """Load a passing audit-2.0 transition confirmation artifact."""
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    report_hash = raw.get("report_hash")
    semantic = dict(raw)
    semantic.pop("report_hash", None)
    if (not isinstance(report_hash, str)
            or report_hash != structural_hash(semantic)):
        raise ValueError("transition confirmation artifact hash differs")
    if raw.get("schema_version") != (
            "fdas-candidate-transition-calibration-confirmation/2.0"):
        raise ValueError("transition confirmation artifact schema differs")
    if (raw.get("passed") is not True
            or any(raw.get(name) is not False for name in (
                "policy_authority", "readout_authority", "truth_mutated"))):
        raise ValueError("transition confirmation is not passing shadow evidence")
    validation = raw.get("validation")
    validation_hash = (
        None if not isinstance(validation, dict)
        else validation.get("report_hash"))
    validation_semantic = (
        {} if not isinstance(validation, dict) else dict(validation))
    validation_semantic.pop("report_hash", None)
    if (not isinstance(validation_hash, str)
            or validation_hash != structural_hash(validation_semantic)
            or validation.get("passed") is not True
            or validation.get("model_result_hash")
            != raw.get("model_result_hash")
            or validation.get("claim_scope") != raw.get("claim_scope")
            or any(validation.get(name) is not False for name in (
                "policy_authority", "readout_authority", "truth_mutated"))):
        raise ValueError("transition confirmation validation differs")
    if (not isinstance(raw.get("yield"), dict)
            or raw["yield"].get("passed") is not True):
        raise ValueError("transition confirmation yield did not pass")
    for name in (
            "calibration_artifact_hash", "feature_audit_hash",
            "model_result_hash"):
        if not isinstance(raw.get(name), str) or not raw[name]:
            raise ValueError(
                "transition confirmation lacks {}".format(name))
    return raw, report_hash


def _single_prefixed(values, prefix, name):
    matches = tuple(
        value[len(prefix):] for value in values if value.startswith(prefix))
    if len(matches) != 1 or not matches[0]:
        raise ValueError("transition validation requires exact {}".format(name))
    return matches[0]


def _mean(values):
    values = tuple(values)
    if not values:
        raise ValueError("transition validation metric has no rows")
    return sum(values) / float(len(values))


def _wilson(positive_mass, sample_count, z=1.959963984540054):
    n = float(sample_count)
    p = float(positive_mass) / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(
        p * (1.0 - p) / n + z * z / (4.0 * n * n))
    radius /= denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _metrics(rows):
    predictions = tuple(value["prediction"] for value in rows)
    baselines = tuple(value["action_prediction"] for value in rows)
    outcomes = tuple(value["outcome"] for value in rows)
    brier = _mean(
        (prediction - outcome) ** 2
        for prediction, outcome in zip(predictions, outcomes))
    action_brier = _mean(
        (prediction - outcome) ** 2
        for prediction, outcome in zip(baselines, outcomes))
    log_loss = _mean(
        -(outcome * math.log(prediction)
          + (1.0 - outcome) * math.log(1.0 - prediction))
        for prediction, outcome in zip(predictions, outcomes))
    predicted = _mean(predictions)
    observed = _mean(outcomes)
    lower, upper = _wilson(sum(outcomes), len(outcomes))
    return {
        "action_only_brier_score": action_brier,
        "brier_improvement_over_action_only": action_brier - brier,
        "brier_score": brier,
        "calibration_error": abs(predicted - observed),
        "empirical_interval_lower": lower,
        "empirical_interval_upper": upper,
        "lineages": len(rows),
        "log_loss": log_loss,
        "observed_mean": observed,
        "predicted_mean": predicted,
        "prediction_mean_in_empirical_interval": (
            lower <= predicted <= upper),
    }


def _quantile(values, probability):
    values = tuple(sorted(float(value) for value in values))
    if not values:
        raise ValueError("transition validation bootstrap is empty")
    position = (len(values) - 1) * float(probability)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _game_cluster_bootstrap(rows, samples, seed):
    games = tuple(sorted({value["game_id"] for value in rows}))
    if len(games) < 2:
        raise ValueError("transition validation needs two game clusters")
    by_game = {
        game_id: tuple(value for value in rows
                       if value["game_id"] == game_id)
        for game_id in games}
    randomizer = random.Random(int(seed))
    improvements = []
    for _index in range(int(samples)):
        selected = tuple(
            randomizer.choice(games) for _unused in range(len(games)))
        replicated = tuple(
            row for game_id in selected for row in by_game[game_id])
        improvements.append(
            _metrics(replicated)["brier_improvement_over_action_only"])
    return {
        "cluster_count": len(games),
        "interval_lower": _quantile(improvements, 0.025),
        "interval_upper": _quantile(improvements, 0.975),
        "samples": int(samples),
        "seed": int(seed),
    }


def evaluate_candidate_transition_calibration(
        model, exports, confirmation_id, thresholds=None,
        bootstrap_samples=2000, bootstrap_seed=16061):
    if not isinstance(model, FdasCandidateTransitionCalibrationModel):
        raise TypeError("transition validation requires typed model")
    exports = tuple(exports)
    if (not exports or any(
            not isinstance(value, FdasCandidateChoiceCalibrationExport)
            for value in exports)):
        raise TypeError("transition validation requires typed exports")
    if not isinstance(confirmation_id, str) or not confirmation_id:
        raise ValueError("transition validation confirmation ID is required")
    if len({value.source_store_digest for value in exports}) != len(exports):
        raise ValueError("transition validation source stores overlap")
    if set(model.source_store_digests).intersection(
            value.source_store_digest for value in exports):
        raise ValueError("transition validation overlaps discovery sources")
    thresholds = dict(
        DEFAULT_TRANSITION_VALIDATION_THRESHOLDS
        if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_TRANSITION_VALIDATION_THRESHOLDS):
        raise ValueError("transition validation thresholds are incomplete")
    if any(not math.isfinite(float(value))
           for value in thresholds.values()):
        raise ValueError("transition validation thresholds must be finite")
    if (not 0.0 <= thresholds["minimum_prediction_coverage"] <= 1.0
            or not 0.0 <= thresholds[
                "minimum_candidate_specific_prediction_fraction"] <= 1.0
            or not -1.0 <= thresholds[
                "minimum_game_cluster_brier_improvement_ci_lower"] <= 1.0
            or any(thresholds[name] < 0.0 for name in (
                "maximum_brier_score", "maximum_calibration_error",
                "maximum_log_loss"))
            or any(isinstance(thresholds[name], bool)
                   or not isinstance(thresholds[name], int)
                   or thresholds[name] < 1 for name in (
                       "minimum_distinct_prediction_values",
                       "minimum_heldout_lineages"))):
        raise ValueError("transition validation thresholds are outside range")
    if (isinstance(bootstrap_samples, bool)
            or not isinstance(bootstrap_samples, int)
            or bootstrap_samples < 100):
        raise ValueError("transition validation bootstrap is too small")

    action_bin = next((
        value for value in model.bins if value.level == "action"), None)
    if action_bin is None:
        raise ValueError("transition validation model lacks action bin")
    raw_rows = []
    episode_ids = set()
    for export in exports:
        for episode in export.examples:
            if episode.episode_id in episode_ids:
                raise ValueError("transition validation episodes overlap")
            episode_ids.add(episode.episode_id)
            query = InductionFeatureQuery(
                episode.episode_id, episode.context, episode.features,
                episode.provenance_ids)
            if dict(query.context).get("operation_type") != (
                    CANDIDATE_TRANSITION_OPERATION_TYPE):
                continue
            prediction = model.predict(query)
            raw_rows.append({
                "action_prediction": action_bin.estimate,
                "episode_id": episode.episode_id,
                "game_id": _single_prefixed(
                    episode.provenance_ids, "game-id:", "game identity"),
                "level": prediction.level,
                "lineage_id": _single_prefixed(
                    episode.provenance_ids, "candidate-lineage:",
                    "candidate lineage"),
                "outcome": 1.0 if episode.outcome else 0.0,
                "prediction": prediction.estimate,
                "prediction_status": prediction.status,
                "source_store_digest": export.source_store_digest,
            })
    if not raw_rows:
        raise ValueError("transition validation has no selected move rows")
    estimated = tuple(
        value for value in raw_rows
        if value["prediction_status"] == "estimated"
        and value["prediction"] is not None)
    coverage = len(estimated) / float(len(raw_rows))
    grouped = {}
    for row in estimated:
        grouped.setdefault(row["lineage_id"], []).append(row)
    lineage_rows = []
    for lineage_id, rows in sorted(grouped.items()):
        if (len({value["game_id"] for value in rows}) != 1
                or len({value["source_store_digest"] for value in rows}) != 1):
            raise ValueError("transition lineage crosses game or source")
        lineage_rows.append({
            "action_prediction": _mean(
                value["action_prediction"] for value in rows),
            "game_id": rows[0]["game_id"],
            "level": sorted(
                {value["level"] for value in rows},
                key=lambda value: (
                    -1 if value is None else
                    TRANSITION_CALIBRATION_LEVELS.index(value)))[-1],
            "lineage_id": lineage_id,
            "outcome": _mean(value["outcome"] for value in rows),
            "prediction": _mean(value["prediction"] for value in rows),
            "raw_rows": len(rows),
        })
    lineage_rows = tuple(lineage_rows)
    metrics = _metrics(lineage_rows)
    bootstrap = _game_cluster_bootstrap(
        lineage_rows, bootstrap_samples, bootstrap_seed)
    candidate_specific = tuple(
        value for value in lineage_rows
        if value["level"] not in (None, "action", "lifecycle"))
    fraction = len(candidate_specific) / float(len(lineage_rows))
    distinct = len({value["prediction"] for value in lineage_rows})
    gates = {
        "brier_score_bounded": (
            metrics["brier_score"] <= thresholds["maximum_brier_score"]),
        "calibration_error_bounded": (
            metrics["calibration_error"]
            <= thresholds["maximum_calibration_error"]),
        "candidate_specific_prediction_fraction_sufficient": (
            fraction >= thresholds[
                "minimum_candidate_specific_prediction_fraction"]),
        "distinct_prediction_values_sufficient": (
            distinct >= thresholds["minimum_distinct_prediction_values"]),
        "game_cluster_brier_noninferior": (
            bootstrap["interval_lower"] >= thresholds[
                "minimum_game_cluster_brier_improvement_ci_lower"]),
        "heldout_lineages_sufficient": (
            len(lineage_rows) >= thresholds["minimum_heldout_lineages"]),
        "log_loss_bounded": (
            metrics["log_loss"] <= thresholds["maximum_log_loss"]),
        "prediction_coverage_sufficient": (
            coverage >= thresholds["minimum_prediction_coverage"]),
        "prediction_mean_inside_empirical_interval": (
            metrics["prediction_mean_in_empirical_interval"]),
    }
    semantic = {
        "bootstrap_brier_improvement_over_action_only": bootstrap,
        "candidate_specific_prediction_fraction": fraction,
        "claim_scope": (
            "held-out selected-only grounded move-transition predictive "
            "calibration; no censored counterfactual, ranking, policy, "
            "readout, gameplay, score, or win-rate claim"),
        "confirmation_id": confirmation_id,
        "distinct_prediction_values": distinct,
        "gates": gates,
        "model_result_hash": model.result_hash,
        "overall_metrics": metrics,
        "passed": all(gates.values()),
        "policy_authority": False,
        "prediction_coverage": coverage,
        "readout_authority": False,
        "schema_version": (
            "fdas-candidate-transition-calibration-validation/1.0"),
        "thresholds": thresholds,
        "truth_mutated": False,
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic
