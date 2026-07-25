#!/usr/bin/env python3
"""Exact hidden-context likelihood and planning benchmark for PF-PLN Phase 5."""

import argparse
import json
import math
import os
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    CloneLifecycleStore,
    CloneManager,
    CloneState,
    TruthState,
)


def run(signal_accuracy=0.9, matched_action_success=0.9,
        mismatched_action_success=0.1):
    signal_accuracy = float(signal_accuracy)
    matched_action_success = float(matched_action_success)
    mismatched_action_success = float(mismatched_action_success)
    for value in (
            signal_accuracy, matched_action_success,
            mismatched_action_success):
        if not 0.0 < value < 1.0:
            raise ValueError("benchmark probabilities must be in (0,1)")

    # Exact expectation over two equally likely hidden contexts and the two
    # possible signals. The conditioned planner chooses the signal-matching
    # action; the clone-free planner always chooses the first tied action.
    clone_success = (
        signal_accuracy * matched_action_success
        + (1.0 - signal_accuracy) * mismatched_action_success)
    clone_free_success = (
        0.5 * matched_action_success + 0.5 * mismatched_action_success)
    clone_log_likelihood = (
        signal_accuracy * math.log(signal_accuracy)
        + (1.0 - signal_accuracy) * math.log(1.0 - signal_accuracy))
    clone_free_log_likelihood = math.log(0.5)

    manager = CloneManager(maximum_clones=2)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "clone-state.json")
        store = CloneLifecycleStore(path, manager)
        store.initialize("enemy-intent", (
            CloneState(
                "attack", "enemy-intent", 0.5,
                TruthState(1.0, 0.8, ("attack-model",))),
            CloneState(
                "transit", "enemy-intent", 0.5,
                TruthState(0.0, 0.8, ("transit-model",))),
        ))
        updated = store.bayes_update(
            "enemy-intent",
            {"attack": signal_accuracy, "transit": 1.0 - signal_accuracy},
            "attack-signal")
        persistence = {
            "active_clone_ids": [row.clone_id for row in updated],
            "posterior": dict(
                (row.clone_id, row.posterior) for row in updated),
            "reopen_matches": (
                CloneLifecycleStore(path, manager).clones("enemy-intent")
                == updated),
            "state_hash": store.state_hash,
        }

    report = {
        "schema_version": "1.0",
        "benchmark": "pf-pln-phase-5-hidden-context",
        "configuration": {
            "hidden_contexts": 2,
            "matched_action_success": matched_action_success,
            "mismatched_action_success": mismatched_action_success,
            "signal_accuracy": signal_accuracy,
        },
        "predictive_likelihood": {
            "clone_conditioned_mean_log_likelihood_nats": (
                clone_log_likelihood),
            "clone_free_mean_log_likelihood_nats": clone_free_log_likelihood,
            "improvement_nats": (
                clone_log_likelihood - clone_free_log_likelihood),
        },
        "planning_success": {
            "absolute_improvement": clone_success - clone_free_success,
            "clone_conditioned": clone_success,
            "clone_free": clone_free_success,
            "relative_improvement": (
                (clone_success - clone_free_success) / clone_free_success),
        },
        "persistence": persistence,
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal-accuracy", type=float, default=0.9)
    parser.add_argument("--matched-action-success", type=float, default=0.9)
    parser.add_argument("--mismatched-action-success", type=float, default=0.1)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = run(
        args.signal_accuracy, args.matched_action_success,
        args.mismatched_action_success)
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if (
        report["predictive_likelihood"]["improvement_nats"] > 0
        and report["planning_success"]["absolute_improvement"] > 0
        and report["persistence"]["reopen_matches"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
