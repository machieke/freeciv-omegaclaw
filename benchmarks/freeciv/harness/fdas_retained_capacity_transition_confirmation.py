"""Fixed-cohort confirmation of the frozen PR99 transition model."""

import hashlib
import json
import os
import random

from freeciv_agent.events.schema import canonical_json_bytes, structural_hash
from freeciv_agent.planning.fdas_capacity_query_episode_dataset import (
    FdasRetainedCapacityQueryEpisodeRow,
)
from freeciv_agent.planning.fdas_capacity_transition_model import (
    FdasRetainedCapacityTransitionModel,
    FdasRetainedCapacityTransitionPrediction,
    RETAINED_CAPACITY_PRODUCT_TARGET,
    RETAINED_CAPACITY_RELIEF_TARGET,
)

from .fdas_retained_capacity_query_episode_dataset import (
    export_fdas_retained_capacity_query_episode_dataset,
)
from .fdas_retained_capacity_transition_discovery import (
    FROZEN_DISCOVERY_GAMES,
    retained_capacity_transition_discovery_adequacy,
)
from .statistics import wilson


TRANSITION_CONFIRMATION_IDENTITY = (
    "fdas-retained-capacity-transition-confirmation/1.0")
PR99_FIT_REPORT_HASH = (
    "a6ad5fea69cbc62bb136350942334ac77cf7505006a66551de2308f7fd82065a")
PR99_FIT_REPORT_SHA256 = (
    "73a08cc72101fe82ba26bc0636a740a090767935bf4285d91e7195bd1203893d")
PR99_MODEL_HASH = (
    "909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f")
CONFIRMATION_BOOTSTRAP_SAMPLES = 10000
CONFIRMATION_BOOTSTRAP_SEED = 1000301
ROOT_COMPARATORS = {
    RETAINED_CAPACITY_PRODUCT_TARGET: 0.37638888888888894,
    RETAINED_CAPACITY_RELIEF_TARGET: 0.2,
}
_TARGETS = (
    RETAINED_CAPACITY_PRODUCT_TARGET, RETAINED_CAPACITY_RELIEF_TARGET)
_STATUS_TARGETS = {
    "no-effect-observed": (0, 0),
    "effect-without-goal-relief": (1, 0),
    "goal-relief-observed": (1, 1),
}


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _bootstrap_mean(values):
    values = tuple(float(value) for value in values)
    if not values:
        return {
            "estimate": None, "lower": None, "upper": None, "n": 0,
            "method": "deterministic-game-cluster-bootstrap",
            "samples": CONFIRMATION_BOOTSTRAP_SAMPLES,
            "seed": CONFIRMATION_BOOTSTRAP_SEED,
        }
    randomizer = random.Random(CONFIRMATION_BOOTSTRAP_SEED)
    count = len(values)
    estimates = []
    for _sample in range(CONFIRMATION_BOOTSTRAP_SAMPLES):
        estimates.append(sum(
            values[randomizer.randrange(count)] for _value in values
        ) / float(count))
    estimates.sort()
    return {
        "estimate": sum(values) / float(count),
        "lower": estimates[250],
        "method": "deterministic-game-cluster-bootstrap",
        "n": count,
        "samples": CONFIRMATION_BOOTSTRAP_SAMPLES,
        "seed": CONFIRMATION_BOOTSTRAP_SEED,
        "upper": estimates[9750],
    }


def _target_value(status, target):
    values = _STATUS_TARGETS[status]
    return values[_TARGETS.index(target)]


def _frozen_model(model_report):
    report_sha = hashlib.sha256(
        canonical_json_bytes(model_report) + b"\n").hexdigest()
    if (report_sha != PR99_FIT_REPORT_SHA256
            or model_report.get("structural_hash") != PR99_FIT_REPORT_HASH
            or structural_hash(dict(
                (key, value) for key, value in model_report.items()
                if key != "structural_hash")) != PR99_FIT_REPORT_HASH
            or model_report.get("acceptance", {}).get("accepted") is not True
            or model_report.get("model", {}).get("result_hash")
            != PR99_MODEL_HASH):
        raise ValueError("retained capacity frozen PR99 model differs")
    model = FdasRetainedCapacityTransitionModel.from_dict(
        model_report["model"])
    if model.result_hash != PR99_MODEL_HASH:
        raise ValueError("retained capacity frozen model hash differs")
    return model


def retained_capacity_transition_confirmation_metrics(
        evaluation_rows, model):
    """Evaluate frozen predictions with independent-game aggregation."""
    if not isinstance(model, FdasRetainedCapacityTransitionModel):
        raise TypeError("transition confirmation requires typed frozen model")
    terminal = tuple(
        value for value in evaluation_rows
        if value["observation_status"] == "terminal-observed")
    bins = dict((value.bin_id, value) for value in model.bins)
    overall = {}
    bin_results = []
    target_checks = {}
    for target in _TARGETS:
        predicted = []
        for value in terminal:
            prediction = getattr(value["prediction"], (
                "product_effect" if target == RETAINED_CAPACITY_PRODUCT_TARGET
                else "goal_relief"))
            if prediction.status == "estimated":
                predicted.append((value, prediction))
        coverage = len(predicted) / float(len(terminal)) if terminal else 0.0
        games = {}
        for value, prediction in predicted:
            outcome = _target_value(value["outcome_status"], target)
            root = ROOT_COMPARATORS[target]
            games.setdefault(value["seed"], []).append({
                "brier": (prediction.estimate - outcome) ** 2,
                "calibration": prediction.estimate - outcome,
                "delta": ((prediction.estimate - outcome) ** 2
                          - (root - outcome) ** 2),
            })
        game_values = []
        for seed, rows in sorted(games.items()):
            game_values.append({
                "brier": sum(row["brier"] for row in rows) / len(rows),
                "calibration": (
                    sum(row["calibration"] for row in rows) / len(rows)),
                "delta": sum(row["delta"] for row in rows) / len(rows),
                "seed": seed,
            })
        brier = _bootstrap_mean(tuple(row["brier"] for row in game_values))
        calibration = _bootstrap_mean(tuple(
            row["calibration"] for row in game_values))
        delta = _bootstrap_mean(tuple(row["delta"] for row in game_values))
        overall[target] = {
            "brier_score": brier,
            "calibration_difference": calibration,
            "model_minus_root_brier": delta,
            "numerical_coverage": {
                "estimated_terminal_rows": len(predicted),
                "rate": coverage,
                "terminal_rows": len(terminal),
            },
            "root_comparator": ROOT_COMPARATORS[target],
        }
        target_checks[target + "_numerical_coverage_at_least_90_percent"] = (
            coverage >= 0.90)
        target_checks[target + "_brier_score_no_greater_than_0_25"] = (
            brier["estimate"] is not None and brier["estimate"] <= 0.25)
        target_checks[target + "_calibration_interval_within_0_10"] = (
            calibration["lower"] is not None
            and calibration["lower"] >= -0.10
            and calibration["upper"] <= 0.10)
        target_checks[target + "_root_brier_noninferiority"] = (
            delta["upper"] is not None and delta["upper"] <= 0.02)
        if target == RETAINED_CAPACITY_RELIEF_TARGET:
            target_checks[
                target + "_point_brier_improves_on_root"] = (
                    delta["estimate"] is not None
                    and delta["estimate"] < 0.0)

        grouped = {}
        for value, prediction in predicted:
            grouped.setdefault(prediction.bin_id, {}).setdefault(
                value["seed"], []).append(
                    _target_value(value["outcome_status"], target))
        for bin_id, by_game in sorted(grouped.items()):
            if len(by_game) < 20:
                continue
            bin_value = bins.get(bin_id)
            if bin_value is None or bin_value.target != target:
                raise ValueError("transition confirmation bin lineage differs")
            per_game_outcome = tuple(
                sum(values) / float(len(values))
                for _seed, values in sorted(by_game.items()))
            outcome = _bootstrap_mean(per_game_outcome)
            calibration = _bootstrap_mean(tuple(
                bin_value.estimate - value for value in per_game_outcome))
            bin_results.append({
                "bin_id": bin_id,
                "confirmation_calibration_difference": calibration,
                "confirmation_outcome_mean": outcome,
                "frozen_estimate": bin_value.estimate,
                "frozen_interval_lower": bin_value.interval_lower,
                "frozen_interval_upper": bin_value.interval_upper,
                "independent_confirmation_games": len(by_game),
                "level": bin_value.level,
                "outcome_mean_inside_frozen_interval": (
                    bin_value.interval_lower <= outcome["estimate"]
                    <= bin_value.interval_upper),
                "target": target,
            })
    bin_results.sort(key=lambda value: (
        value["target"], value["level"], value["bin_id"]))
    bin_point_checks = [
        abs(value["confirmation_calibration_difference"]["estimate"]) <= 0.15
        for value in bin_results]
    contained = sum(
        value["outcome_mean_inside_frozen_interval"] for value in bin_results)
    containment_rate = contained / float(len(bin_results)) if bin_results else 0.0
    shared_checks = {
        "at_least_four_selected_target_bins_have_20_confirmation_games": (
            len(bin_results) >= 4),
        "all_qualifying_bin_absolute_point_calibration_within_0_15": (
            bool(bin_results) and all(bin_point_checks)),
        "at_least_80_percent_of_qualifying_outcome_means_inside_frozen_interval": (
            containment_rate >= 0.80),
    }
    checks = {**target_checks, **shared_checks}
    return {
        "bin_confirmation": {
            "contained_groups": contained,
            "containment_rate": containment_rate,
            "groups": bin_results,
            "qualifying_groups": len(bin_results),
        },
        "checks": dict(sorted(checks.items())),
        "decision": "confirmed" if all(checks.values()) else "not-confirmed",
        "overall": overall,
    }


def audit_fdas_retained_capacity_transition_confirmation(
        run_dir, expected_seeds, expected_source_commit, model_report,
        repo=None, audit_workers=4):
    """Audit PR100 mechanics, diversity, and frozen-model calibration."""
    seeds = tuple(int(value) for value in expected_seeds)
    if (len(seeds) != FROZEN_DISCOVERY_GAMES
            or len(seeds) != len(set(seeds))):
        raise ValueError(
            "retained capacity transition confirmation requires 301 seeds")
    model = _frozen_model(model_report)
    dataset = export_fdas_retained_capacity_query_episode_dataset(
        run_dir, seeds, expected_source_commit, repo=repo,
        audit_workers=audit_workers)
    run_summary = _load(os.path.join(os.path.abspath(run_dir),
                                     "run-summary.json"))
    adequacy = retained_capacity_transition_discovery_adequacy(dataset)
    evaluation_rows = []
    for value in dataset["rows"]:
        row = FdasRetainedCapacityQueryEpisodeRow.from_dict(value["row"])
        prediction = model.predict(row.query)
        if (FdasRetainedCapacityTransitionPrediction.from_dict(
                prediction.to_dict()) != prediction):
            raise ValueError("transition confirmation prediction differs")
        evaluation_rows.append({
            "observation_status": row.observation_status,
            "outcome_status": row.outcome_status,
            "prediction": prediction,
            "row_id": row.row_id,
            "seed": value["seed"],
        })
    evaluation_rows.sort(key=lambda value: (value["seed"], value["row_id"]))
    calibration = retained_capacity_transition_confirmation_metrics(
        tuple(evaluation_rows), model)
    mechanics_checks = {
        "all_query_episode_dataset_gates_pass": (
            dataset["acceptance"]["accepted"]),
        "all_source_queries_receive_one_frozen_prediction": (
            len(evaluation_rows) == dataset["summary"]["query_rows"]
            and len({value["row_id"] for value in evaluation_rows})
            == len(evaluation_rows)
            and all(value["prediction"].model_result_hash == PR99_MODEL_HASH
                    for value in evaluation_rows)),
        "all_truth_learning_readout_policy_action_authority_disabled": all(
            value is False for value in (
                dataset["truth_mutated"], dataset["learning_authority"],
                dataset["policy_authority"], dataset["readout_authority"])),
        "exact_301_games_are_retained_once": (
            tuple(value["seed"] for value in dataset["games"]) == seeds),
        "frozen_pr99_model_is_loaded_without_refit": (
            model.result_hash == PR99_MODEL_HASH
            and model_report["structural_hash"] == PR99_FIT_REPORT_HASH),
        "run_completed_without_resume_or_infrastructure_failure": (
            run_summary.get("jobs") == FROZEN_DISCOVERY_GAMES
            and run_summary.get("completed") == FROZEN_DISCOVERY_GAMES
            and run_summary.get("resumed") == 0
            and run_summary.get("infrastructure_failures") == 0),
    }
    mechanics_accepted = all(mechanics_checks.values())
    diversity_eligible = adequacy["decision"] == (
        "eligible-for-preregistered-transition-model-fitting")
    report = {
        "acceptance": {
            "accepted": mechanics_accepted,
            "checks": mechanics_checks,
        },
        "adequacy": adequacy,
        "calibration": calibration,
        "claim_scope": (
            "disjoint fixed-cohort out-of-sample calibration of the exact "
            "frozen PR99 retained-capacity transition model; no causal, "
            "readout, policy, action, gameplay, score, or win-rate claim"),
        "confirmation_ready": (
            mechanics_accepted and diversity_eligible
            and calibration["decision"] == "confirmed"),
        "dataset": dataset,
        "evaluation_rows": [{
            **dict((key, value[key]) for key in (
                "observation_status", "outcome_status", "row_id", "seed")),
            "prediction": value["prediction"].to_dict(),
        } for value in evaluation_rows],
        "identity": TRANSITION_CONFIRMATION_IDENTITY,
        "model": {
            "fit_report_hash": PR99_FIT_REPORT_HASH,
            "fit_report_sha256": PR99_FIT_REPORT_SHA256,
            "model_result_hash": model.result_hash,
            "refitted": False,
        },
        "rates": {
            "games_with_queries": wilson(
                dataset["summary"]["games_with_queries"], len(seeds)),
            "terminal_bearing_games": wilson(
                adequacy["measures"]["terminal_bearing_games"], len(seeds)),
        },
        "run_summary": run_summary,
        "schema_version": "1.0",
        "source": {
            "expected_commit": expected_source_commit,
            "expected_seeds": list(seeds),
        },
        "summary": {
            **dataset["summary"],
            "status_bearing_games": dict((status, adequacy["measures"][
                status + "_games"]) for status in _STATUS_TARGETS),
            "terminal_bearing_games": adequacy["measures"][
                "terminal_bearing_games"],
        },
        "action_authority": False,
        "calibrated_authority": False,
        "learning_write_through": False,
        "policy_authority": False,
        "readout_authority": False,
        "truth_mutated": False,
    }
    report["structural_hash"] = structural_hash(report)
    return report
