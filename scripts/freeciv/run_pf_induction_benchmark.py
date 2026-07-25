#!/usr/bin/env python3
"""Deterministic contextual-rule replay benchmark for PF-PLN Phase 6."""

import argparse
import hashlib
import json
import os
import platform
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    ContextGeneralizer,
    CostVector,
    ExpansionGate,
    GoalState,
    InductionEpisode,
    PatternMiner,
    PressureEngine,
    PressureGraph,
    ReplayValidator,
    Resolvability,
    TruthState,
)


def _context(opponent):
    return (
        ("diplomacy", "peace"),
        ("era", "ancient"),
        ("geometry", "land-border"),
        ("opponent", opponent),
        ("ruleset", "classic"),
    )


def _population(opponent, cohort, episodes, invert_attack=False):
    patterns = (
        (("border-road", "military-spike"), True),
        (("border-road",), False),
        (("military-spike",), False),
        (("settler-seen",), False),
    )
    result = []
    for index in range(int(episodes)):
        features, outcome = patterns[index % len(patterns)]
        if invert_attack and features == (
                "border-road", "military-spike"):
            outcome = False
        episode_id = "{}-{}-{:04d}".format(cohort, opponent, index)
        result.append(InductionEpisode(
            episode_id, _context(opponent), features, outcome,
            ("observation-" + episode_id,)))
    return tuple(result)


def _candidate(opponent, training_episodes):
    rows = PatternMiner(
        minimum_support=8, maximum_antecedents=2).mine(
            _population(opponent, "training", training_episodes),
            "attack-within-six")
    return next(
        row for row in rows
        if row.antecedent == ("border-road", "military-spike"))


def _pressure(expand):
    graph = PressureGraph()
    graph.add_atom(
        AtomState("attack-risk", TruthState(0.0, 1.0, crisp=True)),
        Resolvability(expand=expand, infer=1.0 - expand))
    return PressureEngine().propagate(
        graph, (GoalState("survive", "attack-risk"),))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def run(training_episodes=64, validation_episodes=256):
    training_episodes = int(training_episodes)
    validation_episodes = int(validation_episodes)
    if training_episodes < 32 or validation_episodes < 64:
        raise ValueError("benchmark cohorts are too small")

    alpha = _candidate("alpha", training_episodes)
    bravo = _candidate("bravo", training_episodes)
    validator = ReplayValidator(
        minimum_samples=validation_episodes,
        minimum_activations=validation_episodes // 8)
    held_out = _population(
        "alpha", "held-out", validation_episodes)
    contextual = validator.validate(alpha, held_out)
    repeat = validator.validate(alpha, tuple(reversed(held_out)))

    generalized = ContextGeneralizer.propose(
        (alpha, bravo), ("opponent",))
    per_population = validation_episodes // 4
    generalization_replay = (
        _population("alpha", "generalization", per_population)
        + _population("bravo", "generalization", per_population)
        + _population(
            "charlie", "generalization", per_population, True)
        + _population(
            "delta", "generalization", per_population, True)
        + _population(
            "echo", "generalization", per_population, True)
        + _population(
            "foxtrot", "generalization", per_population, True))
    generalization_validation = ReplayValidator(
        minimum_samples=len(generalization_replay),
        minimum_activations=per_population).validate(
            generalized, generalization_replay)

    gate = ExpansionGate(
        minimum_expand_pressure=0.05, minimum_value_cost_ratio=0.01)
    without_pressure = gate.decide(
        alpha, _pressure(0.0), "survive", "attack-risk",
        CostVector(compute=0.1))
    with_pressure = gate.decide(
        alpha, _pressure(1.0), "survive", "attack-risk",
        CostVector(compute=0.1))

    report = {
        "benchmark": "pf-pln-phase-6-contextual-induction",
        "configuration": {
            "deterministic_pattern_schedule": True,
            "generalization_validation_episodes": len(
                generalization_replay),
            "random_seed": None,
            "training_episodes_per_context": training_episodes,
            "validation_episodes": validation_episodes,
        },
        "implementation": {
            "benchmark_sha256": _sha256(__file__),
            "induction_sha256": _sha256(os.path.join(
                SRC, "freeciv_agent", "pressure", "induction.py")),
            "python_version": platform.python_version(),
        },
        "contextual_rule": {
            "metrics": contextual.metrics.to_dict(),
            "proposal": alpha.to_dict(),
            "replay_order_invariant": (
                contextual.to_dict() == repeat.to_dict()),
            "verdict": contextual.verdict,
        },
        "expansion_gate": {
            "with_expand_pressure": with_pressure.to_dict(),
            "without_expand_pressure": without_pressure.to_dict(),
        },
        "overgeneralized_rule": {
            "metrics": generalization_validation.metrics.to_dict(),
            "proposal": generalized.to_dict(),
            "reason": generalization_validation.reason,
            "verdict": generalization_validation.verdict,
        },
        "schema_version": "1.0",
    }
    report["acceptance"] = {
        "contextual_calibration_improved": (
            contextual.metrics.calibration_improvement > 0),
        "contextual_contradiction_not_increased": (
            contextual.metrics.candidate_contradiction_rate
            <= contextual.metrics.baseline_contradiction_rate),
        "contextual_rule_promoted": contextual.verdict == "promoted",
        "expansion_pressure_required": (
            not without_pressure.accepted and with_pressure.accepted),
        "overgeneralized_rule_demoted": (
            generalization_validation.verdict == "demoted"),
        "replay_order_invariant": (
            contextual.to_dict() == repeat.to_dict()),
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-episodes", type=int, default=64)
    parser.add_argument("--validation-episodes", type=int, default=256)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = run(args.training_episodes, args.validation_episodes)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if all(report["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
