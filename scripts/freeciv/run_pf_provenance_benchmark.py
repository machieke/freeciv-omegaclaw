#!/usr/bin/env python3
"""Deterministic PF-PLN Phase 2 duplicate-evidence and cycle benchmark."""

import argparse
import json
import os
import random
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.beliefs import (  # noqa: E402
    BeliefKey,
    BeliefStore,
    Evidence,
    SelfSupportingProof,
    UncertainInference,
)
from freeciv_agent.config import belief_config  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402


def _evidence(provenance_id, key, strength=1.0, game_id="benchmark"):
    return Evidence(
        provenance_id=provenance_id,
        game_id=game_id,
        turn=1,
        location=(3, 4),
        source_sensor="phase-2-benchmark",
        key=key,
        strength=strength,
        confidence=0.8,
        opponent_id="fixed-ai",
        ruleset="civ2civ3",
        model_version="opponent-model/1.0",
    )


def run(duplicate_seeds=64, paths_per_seed=128, cycle_trials=256):
    config = belief_config()
    duplicate_errors = 0
    duplicate_conflicts = 0
    reference_state = None
    for seed in range(int(duplicate_seeds)):
        store = BeliefStore(config)
        source = _evidence(
            "duplicate-root", BeliefKey("observed-unit", ("enemy", "Phalanx")))
        store.observe(source)
        target = BeliefKey("has-tech", ("enemy", "Bronze Working"))
        paths = [
            "duplicate-path-{:04d}".format(index)
            for index in range(int(paths_per_seed))]
        random.Random(seed).shuffle(paths)
        for path in paths:
            store.derive(
                target, (source.provenance_id,), 1, 0.9, 0.8, path,
                dampening_lambda=config["dampening_lambda"])
        belief = store.get(target)
        state = (belief.tv, belief.provenance_ids, belief.support_paths)
        reference_state = reference_state or state
        if state != reference_state or len(belief.provenance_ids) != 1:
            duplicate_errors += 1
        duplicate_conflicts += len(store.conflicts())

    cycles_rejected = 0
    cycles_accepted = 0
    for trial in range(int(cycle_trials)):
        store = BeliefStore(config)
        inference = UncertainInference(SimpleNamespace(rules=()), store)
        source, _ = store.observe(_evidence(
            "cycle-root-{:04d}".format(trial),
            BeliefKey("route-seed", ("enemy", trial))))
        route_a, _ = inference.deduce(
            "route-a", ("enemy", trial), (source,), 1, "seed-to-a")
        route_b, _ = inference.deduce(
            "route-b", ("enemy", trial), (route_a,), 1, "a-to-b")
        try:
            inference.deduce(
                "route-a", ("enemy", trial), (route_b,), 1, "b-to-a")
        except SelfSupportingProof:
            cycles_rejected += 1
        else:
            cycles_accepted += 1

    context_store = BeliefStore(config)
    context_key = BeliefKey("enemy-route", ("enemy", "north"))
    left = _evidence("context-left", context_key, 1.0, "context-game-left")
    right = Evidence(
        "context-right", "context-game-right", 1, (8, 9),
        "phase-2-benchmark", context_key, 0.0, 0.8, "fixed-ai",
        "civ2civ3", "opponent-model/1.0")
    context_store.observe(left)
    context_store.observe(right)
    conflict = context_store.conflicts()[0]
    operation = next(
        row for row in context_store.context_quarantine_operations(
            conflict.conflict_id, 1)
        if row.context_id == left.context_id)
    context_store.apply_context_quarantine(operation)
    contextual = context_store.get_in_context(context_key, left.context_id, 1)

    report = {
        "schema_version": "1.0",
        "benchmark": "pf-pln-phase-2-provenance-contradiction",
        "configuration": {
            "conflict_min_confidence": config["conflict_min_confidence"],
            "conflict_severity_threshold": config[
                "conflict_severity_threshold"],
            "cycle_trials": int(cycle_trials),
            "duplicate_seeds": int(duplicate_seeds),
            "paths_per_seed": int(paths_per_seed),
        },
        "duplicate_evidence": {
            "conflicts_materialized": duplicate_conflicts,
            "overlap_errors": duplicate_errors,
            "paths_replayed": int(duplicate_seeds) * int(paths_per_seed),
            "unique_tokens_per_result": 1,
        },
        "proof_cycles": {
            "accepted": cycles_accepted,
            "rejected": cycles_rejected,
        },
        "context_quarantine": {
            "aggregate_strength": 0.5,
            "conflict_severity": conflict.severity,
            "contextual_provenance_ids": list(contextual.provenance_ids),
            "contextual_strength": contextual.strength,
            "operations_materialized": len(
                context_store.context_quarantine_operations(
                    conflict.conflict_id, 1)),
        },
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--duplicate-seeds", type=int, default=64)
    parser.add_argument("--paths-per-seed", type=int, default=128)
    parser.add_argument("--cycle-trials", type=int, default=256)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if min(args.duplicate_seeds, args.paths_per_seed, args.cycle_trials) < 1:
        parser.error("benchmark counts must be positive")
    report = run(
        args.duplicate_seeds, args.paths_per_seed, args.cycle_trials)
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if (
        report["duplicate_evidence"]["overlap_errors"] == 0
        and report["duplicate_evidence"]["conflicts_materialized"] == 0
        and report["proof_cycles"]["accepted"] == 0
        and report["context_quarantine"]["contextual_strength"] == 1.0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
