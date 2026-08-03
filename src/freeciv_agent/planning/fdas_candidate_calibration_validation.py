"""Held-out validation for non-authorizing FDAS candidate calibration."""

import json
import math
import random

from ..events.schema import structural_hash
from ..pressure.induction import InductionFeatureQuery
from .fdas_candidate_calibration import FdasCandidateCalibrationModel
from .fdas_candidate_choices import (
    DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES,
    FdasCandidateChoiceCalibrationExport,
)


VALIDATION_IDENTITY = "fdas-candidate-calibration-validation/1.0"
DEFAULT_VALIDATION_THRESHOLDS = {
    "maximum_action_calibration_error": 0.25,
    "maximum_brier_score": 0.25,
    "maximum_calibration_error": 0.15,
    "maximum_log_loss": 0.75,
    "minimum_lifecycle_brier_improvement_ci_lower": -0.05,
    "minimum_prediction_coverage": 0.95,
}


def load_candidate_calibration_model(path):
    """Load and hash-check a discovery artifact plus its nested model."""
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    claimed_hash = raw.get("report_hash")
    semantic = dict(raw)
    semantic.pop("report_hash", None)
    if not isinstance(claimed_hash, str) or (
            claimed_hash != structural_hash(semantic)):
        raise ValueError("candidate calibration artifact hash differs")
    if any(raw.get(name) is not False for name in (
            "policy_authority", "readout_authority", "truth_mutated")):
        raise ValueError("candidate calibration artifact grants authority")
    return FdasCandidateCalibrationModel.from_dict(
        raw["calibration_model"]), claimed_hash


def _single_prefixed(values, prefix, name):
    matches = tuple(
        value[len(prefix):] for value in values if value.startswith(prefix))
    if len(matches) != 1 or not matches[0]:
        raise ValueError("validation row requires exact {}".format(name))
    return matches[0]


def _mean(values):
    values = tuple(values)
    if not values:
        raise ValueError("validation metric requires observations")
    return sum(values) / float(len(values))


def _wilson(positive_mass, sample_count, z=1.959963984540054):
    n = float(sample_count)
    p = float(positive_mass) / n
    denominator = 1.0 + (z * z / n)
    center = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(
        (p * (1.0 - p) / n) + (z * z / (4.0 * n * n)))
    radius /= denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _metrics(rows):
    predictions = tuple(value["prediction"] for value in rows)
    outcomes = tuple(value["outcome"] for value in rows)
    baseline = tuple(value["action_prediction"] for value in rows)
    brier = _mean(
        (prediction - outcome) ** 2
        for prediction, outcome in zip(predictions, outcomes))
    action_brier = _mean(
        (prediction - outcome) ** 2
        for prediction, outcome in zip(baseline, outcomes))
    log_loss = _mean(
        -(outcome * math.log(prediction)
          + (1.0 - outcome) * math.log(1.0 - prediction))
        for prediction, outcome in zip(predictions, outcomes))
    prediction_mean = _mean(predictions)
    outcome_mean = _mean(outcomes)
    lower, upper = _wilson(sum(outcomes), len(outcomes))
    return {
        "action_only_brier_score": action_brier,
        "brier_improvement_over_action_only": action_brier - brier,
        "brier_score": brier,
        "calibration_error": abs(prediction_mean - outcome_mean),
        "empirical_interval_lower": lower,
        "empirical_interval_upper": upper,
        "lineages": len(rows),
        "log_loss": log_loss,
        "observed_mean": outcome_mean,
        "predicted_mean": prediction_mean,
        "prediction_mean_in_empirical_interval": (
            lower <= prediction_mean <= upper),
    }


def _quantile(values, probability):
    values = tuple(sorted(float(value) for value in values))
    if not values:
        raise ValueError("validation bootstrap is empty")
    position = (len(values) - 1) * float(probability)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _game_cluster_bootstrap(rows, samples, seed):
    games = tuple(sorted(set(value["game_id"] for value in rows)))
    if len(games) < 2:
        raise ValueError("validation requires at least two game clusters")
    by_game = dict(
        (game_id, tuple(value for value in rows
                        if value["game_id"] == game_id))
        for game_id in games)
    randomizer = random.Random(int(seed))
    improvements = []
    for _index in range(int(samples)):
        sampled = tuple(
            randomizer.choice(games) for _unused in range(len(games)))
        replicated = tuple(
            value for game_id in sampled for value in by_game[game_id])
        improvements.append(_metrics(
            replicated)["brier_improvement_over_action_only"])
    return {
        "cluster_count": len(games),
        "interval_lower": _quantile(improvements, 0.025),
        "interval_upper": _quantile(improvements, 0.975),
        "samples": int(samples),
        "seed": int(seed),
    }


def evaluate_candidate_calibration(
        model, exports, confirmation_id, thresholds=None,
        bootstrap_samples=2000, bootstrap_seed=7751):
    """Evaluate selected-only holdout outcomes without granting readout."""
    if not isinstance(model, FdasCandidateCalibrationModel):
        raise TypeError("validation requires typed calibration model")
    exports = tuple(exports)
    if (not exports or any(
            not isinstance(value, FdasCandidateChoiceCalibrationExport)
            for value in exports)):
        raise TypeError("validation requires typed calibration exports")
    if not isinstance(confirmation_id, str) or not confirmation_id:
        raise ValueError("validation confirmation identity is required")
    if len({value.source_store_digest for value in exports}) != len(exports):
        raise ValueError("validation source stores overlap")
    if set(model.source_store_digests).intersection(
            value.source_store_digest for value in exports):
        raise ValueError("validation overlaps calibration discovery sources")
    thresholds = dict(
        DEFAULT_VALIDATION_THRESHOLDS if thresholds is None else thresholds)
    if set(thresholds) != set(DEFAULT_VALIDATION_THRESHOLDS):
        raise ValueError("validation thresholds are incomplete or unknown")
    if any(not math.isfinite(float(value)) for value in thresholds.values()):
        raise ValueError("validation thresholds must be finite")
    if (not 0.0 <= thresholds["minimum_prediction_coverage"] <= 1.0
            or any(thresholds[name] < 0.0 for name in (
                "maximum_action_calibration_error",
                "maximum_brier_score", "maximum_calibration_error",
                "maximum_log_loss"))
            or not -1.0 <= thresholds[
                "minimum_lifecycle_brier_improvement_ci_lower"] <= 1.0):
        raise ValueError("validation thresholds are outside metric ranges")
    if (isinstance(bootstrap_samples, bool)
            or not isinstance(bootstrap_samples, int)
            or bootstrap_samples < 100):
        raise ValueError("validation bootstrap sample count is too small")

    raw_rows = []
    episode_ids = set()
    action_bins = dict(
        (value.operation_type, value)
        for value in model.bins if value.level == "action")
    for export in exports:
        for episode in export.examples:
            if episode.episode_id in episode_ids:
                raise ValueError("validation episodes overlap")
            episode_ids.add(episode.episode_id)
            query = InductionFeatureQuery(
                episode.episode_id, episode.context, episode.features,
                episode.provenance_ids)
            operation_type = dict(query.context).get("operation_type")
            if operation_type not in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES:
                raise ValueError("validation action stratum differs")
            prediction = model.predict(query)
            action_bin = action_bins.get(operation_type)
            raw_rows.append({
                "action_prediction": (
                    None if action_bin is None else action_bin.estimate),
                "episode_id": episode.episode_id,
                "game_id": _single_prefixed(
                    episode.provenance_ids, "game-id:", "game identity"),
                "lineage_id": _single_prefixed(
                    episode.provenance_ids, "candidate-lineage:",
                    "candidate lineage"),
                "operation_type": operation_type,
                "outcome": 1.0 if episode.outcome else 0.0,
                "prediction": prediction.estimate,
                "prediction_reason": prediction.reason,
                "prediction_status": prediction.status,
                "source_store_digest": export.source_store_digest,
            })
    if not raw_rows:
        raise ValueError("validation has no observed selected rows")
    estimated = tuple(
        value for value in raw_rows
        if value["prediction_status"] == "estimated"
        and value["prediction"] is not None
        and value["action_prediction"] is not None)
    coverage = len(estimated) / float(len(raw_rows))

    grouped = {}
    for row in estimated:
        grouped.setdefault(row["lineage_id"], []).append(row)
    lineage_rows = []
    for lineage_id, rows in sorted(grouped.items()):
        if (len({value["game_id"] for value in rows}) != 1
                or len({value["operation_type"] for value in rows}) != 1
                or len({value["source_store_digest"]
                        for value in rows}) != 1):
            raise ValueError(
                "validation lineage crosses game, action, or source")
        lineage_rows.append({
            "action_prediction": _mean(
                value["action_prediction"] for value in rows),
            "game_id": rows[0]["game_id"],
            "lineage_id": lineage_id,
            "operation_type": rows[0]["operation_type"],
            "outcome": _mean(value["outcome"] for value in rows),
            "prediction": _mean(value["prediction"] for value in rows),
            "raw_rows": len(rows),
        })
    lineage_rows = tuple(lineage_rows)
    overall = _metrics(lineage_rows)
    action_metrics = dict(
        (operation_type, _metrics(tuple(
            value for value in lineage_rows
            if value["operation_type"] == operation_type)))
        for operation_type in DEFENSE_CANDIDATE_CHOICE_OPERATION_TYPES)
    bootstrap = _game_cluster_bootstrap(
        lineage_rows, bootstrap_samples, bootstrap_seed)
    gates = {
        "action_calibration_error_bounded": all(
            value["calibration_error"]
            <= thresholds["maximum_action_calibration_error"]
            for value in action_metrics.values()),
        "action_prediction_means_inside_empirical_intervals": all(
            value["prediction_mean_in_empirical_interval"]
            for value in action_metrics.values()),
        "brier_score_bounded": (
            overall["brier_score"]
            <= thresholds["maximum_brier_score"]),
        "calibration_error_bounded": (
            overall["calibration_error"]
            <= thresholds["maximum_calibration_error"]),
        "lifecycle_model_game_cluster_noninferior": (
            bootstrap["interval_lower"] >= thresholds[
                "minimum_lifecycle_brier_improvement_ci_lower"]),
        "log_loss_bounded": (
            overall["log_loss"] <= thresholds["maximum_log_loss"]),
        "prediction_coverage_sufficient": (
            coverage >= thresholds["minimum_prediction_coverage"]),
    }
    semantic = {
        "action_metrics": action_metrics,
        "bootstrap_brier_improvement_over_action_only": bootstrap,
        "claim_scope": (
            "held-out selected-only predictive calibration; no censored "
            "counterfactual, ranking, policy, readout, gameplay, score, or "
            "win-rate claim"),
        "confirmation_id": confirmation_id,
        "gates": gates,
        "model_result_hash": model.result_hash,
        "overall_metrics": overall,
        "passed": all(gates.values()),
        "policy_authority": False,
        "prediction_coverage": coverage,
        "readout_authority": False,
        "raw_observed_rows": len(raw_rows),
        "schema_version": "fdas-candidate-calibration-validation/1.0",
        "selected_effective_lineages": len(lineage_rows),
        "source_export_hashes": sorted(
            value.result_hash for value in exports),
        "source_store_digests": sorted(
            value.source_store_digest for value in exports),
        "thresholds": thresholds,
        "truth_mutated": False,
        "validation_identity": VALIDATION_IDENTITY,
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic
