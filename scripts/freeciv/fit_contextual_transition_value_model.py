#!/usr/bin/env python3
"""Fit or evaluate a frozen contextual transition-value model."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
for candidate in (
        REPO,
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.transition_model_training import (  # noqa: E402
    evaluate_contextual_transition_value_model,
    fit_contextual_transition_value_model,
)


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    fit = subparsers.add_parser(
        "fit", help="fit a mutable training cohort and freeze the model")
    fit.add_argument("--artifacts", required=True)
    fit.add_argument("--out", required=True)
    fit.add_argument("--identity", required=True)
    fit.add_argument("--cohort", required=True)
    fit.add_argument("--arm", default="treatment")
    fit.add_argument("--minimum-samples", type=int, default=30)
    fit.add_argument("--maximum-half-width", type=float, default=0.50)
    fit.add_argument("--alpha", type=float, default=0.05)
    fit.add_argument("--shrinkage-kappa", type=float, default=10.0)
    fit.add_argument("--legacy-v1-path")
    fit.add_argument("--legacy-ruleset-family")
    fit.add_argument("--report")
    fit.add_argument("--overwrite", action="store_true")

    evaluate = subparsers.add_parser(
        "evaluate", help="evaluate a disjoint holdout and write approval")
    evaluate.add_argument("--artifacts", required=True)
    evaluate.add_argument("--model", required=True)
    evaluate.add_argument("--out", required=True)
    evaluate.add_argument("--identity", required=True)
    evaluate.add_argument("--cohort", required=True)
    evaluate.add_argument("--arm", default="treatment")
    evaluate.add_argument("--minimum-samples", type=int, default=30)
    evaluate.add_argument("--maximum-half-width", type=float, default=0.50)
    evaluate.add_argument("--alpha", type=float, default=0.05)
    evaluate.add_argument("--shrinkage-kappa", type=float, default=10.0)
    evaluate.add_argument("--minimum-coverage", type=float, default=0.80)
    evaluate.add_argument(
        "--maximum-context-brier-regression", type=float, default=0.02)
    evaluate.add_argument("--bootstrap-iterations", type=int, default=2000)
    evaluate.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    if arguments.command == "fit":
        report = fit_contextual_transition_value_model(
            arguments.artifacts,
            arguments.out,
            arguments.identity,
            arguments.cohort,
            arm=arguments.arm,
            minimum_samples=arguments.minimum_samples,
            maximum_half_width=arguments.maximum_half_width,
            alpha=arguments.alpha,
            shrinkage_kappa=arguments.shrinkage_kappa,
            legacy_v1_path=arguments.legacy_v1_path,
            legacy_ruleset_family=arguments.legacy_ruleset_family,
            overwrite=arguments.overwrite)
        if arguments.report:
            with open(arguments.report, "w", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, sort_keys=True)
                stream.write("\n")
    else:
        report = evaluate_contextual_transition_value_model(
            arguments.artifacts,
            arguments.model,
            arguments.identity,
            arguments.cohort,
            arguments.out,
            arm=arguments.arm,
            minimum_samples=arguments.minimum_samples,
            maximum_half_width=arguments.maximum_half_width,
            alpha=arguments.alpha,
            shrinkage_kappa=arguments.shrinkage_kappa,
            minimum_coverage=arguments.minimum_coverage,
            maximum_context_brier_regression=(
                arguments.maximum_context_brier_regression),
            bootstrap_iterations=arguments.bootstrap_iterations,
            overwrite=arguments.overwrite)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
