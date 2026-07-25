#!/usr/bin/env python3
"""AND/threshold characterization benchmark for PF-PLN Phase 8."""

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
    DifferentiableTruthRule,
    LearnableRuleParameter,
    adjoint_pressure,
    characterize_threshold,
    counterfactual_pressure,
    finite_difference_adjoint,
    learn_rule_parameter,
    requirement_pressure,
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def run(grid_steps=19, learning_steps=20):
    grid_steps = int(grid_steps)
    learning_steps = int(learning_steps)
    if grid_steps < 5 or learning_steps < 1:
        raise ValueError("benchmark bounds are too small")

    maximum_error = 0.0
    comparisons = 0
    per_rule = {}
    values = [
        float(index + 1) / (grid_steps + 1)
        for index in range(grid_steps)]
    for kind in ("product-and", "probabilistic-or"):
        rule = DifferentiableTruthRule("benchmark:" + kind, kind)
        rule_error = 0.0
        for left in values:
            for right in values:
                premises = (("left", left), ("right", right))
                exact = dict(adjoint_pressure(
                    rule, premises).premise_rows)
                numerical = dict(finite_difference_adjoint(
                    rule, premises, epsilon=1e-6))
                for premise_id in exact:
                    error = abs(exact[premise_id] - numerical[premise_id])
                    maximum_error = max(maximum_error, error)
                    rule_error = max(rule_error, error)
                    comparisons += 1
        per_rule[kind] = {
            "comparisons": grid_steps * grid_steps * 2,
            "maximum_absolute_error": rule_error,
        }

    and_rule = DifferentiableTruthRule(
        "benchmark:dead-and", "product-and")
    dead_values = (("left", 0.0), ("right", 0.0))
    dead_adjoint = adjoint_pressure(and_rule, dead_values)
    dead_requirement = requirement_pressure(dead_values)
    dead_counterfactual = counterfactual_pressure(and_rule, dead_values)

    threshold_rows = [
        characterize_threshold(value, 5, min(10, value + 1)).to_dict()
        for value in range(0, 11)]
    decisive = next(row for row in threshold_rows if row["value"] == 4)

    examples = (
        (0.2, 0.16), (0.5, 0.4), (0.8, 0.64), (1.0, 0.8))
    parameter = LearnableRuleParameter("benchmark:reliability", 0.2)
    updates = []
    for _ in range(learning_steps):
        parameter, update = learn_rule_parameter(
            parameter, examples, learning_rate=0.2)
        updates.append(update)

    report = {
        "acceptance": {
            "dead_and_coalition_detected": (
                dead_counterfactual.coalition_gain == 1.0),
            "dead_and_requirement_nonzero": (
                abs(sum(value for _, value in dead_requirement) - 1.0)
                < 1e-12),
            "learned_parameter_loss_reduced": (
                updates[-1].posterior_loss < updates[0].prior_loss),
            "smooth_adjoint_matches_finite_difference": (
                maximum_error < 1e-8),
            "threshold_counterfactual_detects_final_unit": (
                not decisive["adjoint_available"]
                and decisive["requirement"] == 1.0
                and decisive["counterfactual_gain"] == 1.0),
        },
        "benchmark": "pf-pln-phase-8-differentiable-execution",
        "characterization": {
            "dead_product_and": {
                "adjoint": dead_adjoint.to_dict(),
                "conclusion": (
                    "pure adjoint is insufficient when all required "
                    "premises have zero local derivative"),
                "counterfactual": dead_counterfactual.to_dict(),
                "requirement_pressure": dict(dead_requirement),
            },
            "smooth_truth_functions": {
                "comparisons": comparisons,
                "conclusion": (
                    "adjoint suffices for local leverage on smooth active "
                    "truth paths"),
                "maximum_absolute_error": maximum_error,
                "rules": per_rule,
            },
            "threshold": {
                "conclusion": (
                    "thresholds are outside autodiff; requirement pressure "
                    "tracks deficits and counterfactual pressure detects "
                    "decisive boundary crossings"),
                "rows": threshold_rows,
            },
        },
        "configuration": {
            "finite_difference_epsilon": 1e-6,
            "grid_steps": grid_steps,
            "learning_steps": learning_steps,
            "random_seed": None,
        },
        "implementation": {
            "benchmark_sha256": _sha256(__file__),
            "differentiable_sha256": _sha256(os.path.join(
                SRC, "freeciv_agent", "pressure", "differentiable.py")),
            "python_version": platform.python_version(),
        },
        "parameter_learning": {
            "examples": len(examples),
            "final_loss": updates[-1].posterior_loss,
            "final_value": parameter.value,
            "initial_loss": updates[0].prior_loss,
            "initial_value": updates[0].prior_value,
            "updates": learning_steps,
        },
        "schema_version": "1.0",
    }
    report["artifact_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-steps", type=int, default=19)
    parser.add_argument("--learning-steps", type=int, default=20)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = run(args.grid_steps, args.learning_steps)
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
