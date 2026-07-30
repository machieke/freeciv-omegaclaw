#!/usr/bin/env python3
"""Run the deterministic GDO-8 contextual calibration mechanism diagnostic."""

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
import time


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.pressure import (  # noqa: E402
    ContextualCalibrationGate,
    ContextualOutcomeRecord,
    ContextualTransitionValueKey,
    ContextualTransitionValueModel,
    TransitionContextKey,
    TransitionValueKey,
    TransitionValueModel,
    TransitionValueObservation,
)


ESTIMATOR_VERSION = "synthetic-grounded-transition/1.0"
POLICY_VERSION = "scalar-v2/1.0"
CONTEXTS = (
    {
        "action_category": "movement",
        "action_type": "unit_move",
        "actor_class": "unit:settlers",
        "exact": "movement-settler-distant",
        "predicted": 0.80,
        "realized": 0.20,
        "target_class": "tile:land",
        "threat": "distant:4+",
    },
    {
        "action_category": "movement",
        "action_type": "unit_move",
        "actor_class": "unit:warriors",
        "exact": "movement-warrior-immediate",
        "predicted": 0.20,
        "realized": 0.80,
        "target_class": "tile:land",
        "threat": "immediate:0-1",
    },
    {
        "action_category": "combat",
        "action_type": "unit_attack",
        "actor_class": "unit:warriors",
        "exact": "combat-warrior-immediate",
        "predicted": 0.75,
        "realized": 0.25,
        "target_class": "unit",
        "threat": "immediate:0-1",
    },
    {
        "action_category": "combat",
        "action_type": "unit_attack",
        "actor_class": "unit:riflemen",
        "exact": "combat-rifle-near",
        "predicted": 0.25,
        "realized": 0.75,
        "target_class": "unit",
        "threat": "near:2-3",
    },
)


def _key(specification):
    return ContextualTransitionValueKey(
        goal_id=(
            "pf-impact:expansion"
            if specification[
                "action_category"]
            == "movement"
            else "pf-impact:survival"),
        context=TransitionContextKey(
            exact_context_digest=(
                specification["exact"]),
            action_type=(
                specification["action_type"]),
            action_category=(
                specification[
                    "action_category"]),
            actor_class=(
                specification["actor_class"]),
            target_class=(
                specification["target_class"]),
            threat_bucket=(
                specification["threat"]),
            horizon_bucket="medium:4-10",
            lifecycle_state=(
                "route-progress"
                if specification[
                    "action_category"]
                == "movement"
                else "tactical-execution"),
            ruleset_digest="synthetic-ruleset-a",
            ruleset_family="civ2civ3"),
        estimator_version=ESTIMATOR_VERSION,
        policy_version=POLICY_VERSION)


def _outcome(
        specification, index,
        split, unknown=False):
    jitter = (
        0.02
        if index % 2 == 0 else -0.02)
    realized = min(
        1.0, max(
            0.0,
            specification["realized"]
            + jitter))
    return ContextualOutcomeRecord(
        observation_id=(
            "{}-{}-{:03d}".format(
                split,
                specification["exact"],
                index)),
        key=_key(specification),
        selected_policy_id="scalar-v2",
        selection_policy_kind=(
            "stochastic"
            if index % 5 == 0
            else "deterministic"),
        selection_propensity=(
            0.5 if index % 5 == 0
            else None),
        action_id="action-{}-{:03d}".format(
            specification["exact"],
            index),
        operation_id=(
            "operation-{}-{:03d}".format(
                specification["exact"],
                index)),
        predicted_transition_digest=(
            "prediction-{}-{:03d}".format(
                specification["exact"],
                index)),
        predicted_relief=float(
            specification["predicted"]),
        realized_outcome_digest=(
            None if unknown
            else "realized-{}-{:03d}".format(
                specification["exact"],
                index)),
        realized_goal_relief=(
            None if unknown else realized),
        adverse_loss=(
            None if unknown
            else (
                0.10
                if specification[
                    "action_category"]
                == "combat" else 0.0)),
        adverse_loss_status=(
            "unknown"
            if unknown else "observed"),
        eligibility_trace=(
            "authoritative-next-snapshot",
            "selected-action-identity-matched",
        ),
        causal_status=(
            "unknown"
            if unknown else "eligible"),
        outcome_status=(
            "unknown"
            if unknown else "terminal"),
        estimator_version=ESTIMATOR_VERSION,
        policy_version=POLICY_VERSION,
        relief_source=(
            None if unknown
            else "authoritative:synthetic-ground-truth"))


def _legacy_model(path):
    model = TransitionValueModel(
        path=path,
        identity="gdo8-legacy-prior",
        minimum_samples=1,
        maximum_half_width=1.0)
    key = TransitionValueKey(
        "movement", "route-progress",
        "pf-impact:expansion")
    model.observe_many(tuple(
        TransitionValueObservation(
            observation_id=(
                "legacy-prior-{:02d}".format(
                    index)),
            key=key,
            predicted_relief=0.8,
            realized_relief=0.3,
            effect_observed=True,
            relief_source=(
                "authoritative:synthetic-legacy"),
            context_digest=(
                "legacy-context-{:02d}".format(
                    index)))
        for index in range(10)))


def run(
        train_per_context=40,
        holdout_per_context=25,
        bootstrap_iterations=2000):
    with tempfile.TemporaryDirectory() as directory:
        legacy_path = os.path.join(
            directory, "legacy-v1.json")
        model_path = os.path.join(
            directory, "contextual-v2.json")
        _legacy_model(legacy_path)
        model = ContextualTransitionValueModel(
            path=model_path,
            identity="gdo8-synthetic-fit",
            minimum_samples=30,
            maximum_half_width=0.50,
            alpha=0.05,
            shrinkage_kappa=10.0)
        model.import_legacy_v1(
            legacy_path, "civ2civ3")
        training = tuple(
            _outcome(
                specification,
                index, "training")
            for specification in CONTEXTS
            for index in range(
                train_per_context))
        unknown = tuple(
            _outcome(
                specification,
                1000 + index,
                "training-unknown",
                unknown=True)
            for specification in CONTEXTS
            for index in range(3))
        model.observe_many(
            training + unknown)
        frozen = ContextualTransitionValueModel(
            path=model_path,
            identity="gdo8-synthetic-fit",
            minimum_samples=30,
            maximum_half_width=0.50,
            alpha=0.05,
            shrinkage_kappa=10.0,
            read_only=True)
        holdout = tuple(
            _outcome(
                specification,
                2000 + index,
                "holdout")
            for specification in CONTEXTS
            for index in range(
                holdout_per_context))
        gate = ContextualCalibrationGate(
            minimum_coverage=0.80,
            maximum_context_brier_regression=0.02,
            bootstrap_iterations=(
                bootstrap_iterations))
        before_hash = frozen.state_hash
        started = time.perf_counter()
        report = gate.evaluate(
            frozen, holdout)
        gate_latency_ms = (
            time.perf_counter() - started
        ) * 1000.0
        repeated = gate.evaluate(
            frozen, holdout)
        estimate_latencies = []
        estimates = []
        for outcome in holdout:
            started = time.perf_counter()
            estimate = frozen.estimate(
                outcome.key,
                outcome.predicted_relief)
            estimate_latencies.append(
                (time.perf_counter() - started)
                * 1000.0)
            estimates.append(
                estimate.to_dict())
        ordered = sorted(
            estimate_latencies)
        p95_index = max(
            0, int(math.ceil(
                0.95 * len(ordered))) - 1)
        mechanism_gates = {
            "category_only_negative_transfer_corrected":
                report["aggregate"][
                    "mean_brier_improvement"]
                > 0.0,
            "conductance_has_causal_support":
                all(
                    row[
                        "conductance_supported"]
                    for row in estimates),
            "contextual_holdout_gate_passed":
                report[
                    "authority_approved"],
            "deterministic_holdout_report":
                report["report_hash"]
                == repeated[
                    "report_hash"],
            "frozen_model_unchanged":
                frozen.state_hash
                == before_hash,
            "legacy_rows_not_v2_outcomes":
                frozen.decision_snapshot()[
                    "outcome_count"]
                == len(training)
                + len(unknown),
            "unknown_outcomes_retained_but_excluded":
                frozen.decision_snapshot()[
                    "unknown_outcome_count"]
                == len(unknown)
                and frozen.decision_snapshot()[
                    "eligible_outcome_count"]
                == len(training),
        }
        return {
            "diagnostic":
                "gdo8-contextual-calibration",
            "holdout": report,
            "latency_ms": {
                "gate_evaluation":
                    gate_latency_ms,
                "mean_estimate":
                    statistics.mean(
                        estimate_latencies),
                "p95_estimate":
                    ordered[p95_index],
                "sample_count":
                    len(estimate_latencies),
            },
            "mechanism_gates":
                mechanism_gates,
            "model": frozen.decision_snapshot(),
            "passed": all(
                mechanism_gates.values()),
            "repeatability": {
                "estimate_set_hash":
                    structural_hash(estimates),
                "holdout_report_hash":
                    report["report_hash"],
            },
            "schema_version": "1.0",
            "scope": {
                "engine_backed": False,
                "live_authority_eligible":
                    False,
                "score_claim": False,
                "synthetic_context_regime":
                    True,
            },
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=os.path.join(
            REPO, "benchmarks", "gdo",
            "gdo8_contextual_calibration_diagnostic.json"))
    parser.add_argument(
        "--train-per-context",
        type=int, default=40)
    parser.add_argument(
        "--holdout-per-context",
        type=int, default=25)
    parser.add_argument(
        "--bootstrap-iterations",
        type=int, default=2000)
    arguments = parser.parse_args()
    result = run(
        arguments.train_per_context,
        arguments.holdout_per_context,
        arguments.bootstrap_iterations)
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(
            canonical_json_bytes(result))
        stream.write(b"\n")
    print(json.dumps({
        "holdout": result["holdout"][
            "aggregate"],
        "mechanism_gates":
            result["mechanism_gates"],
        "output": os.path.relpath(
            output, REPO),
        "passed": result["passed"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
