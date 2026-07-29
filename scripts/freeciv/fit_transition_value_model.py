#!/usr/bin/env python3
"""Fit a frozen transition-value model from engine diagnostic artifacts."""

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
    fit_transition_value_model,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--arm", default="treatment")
    parser.add_argument(
        "--minimum-samples", type=int, default=30)
    parser.add_argument(
        "--maximum-half-width",
        type=float, default=0.50)
    parser.add_argument(
        "--alpha", type=float, default=0.05)
    parser.add_argument("--report")
    parser.add_argument(
        "--overwrite", action="store_true")
    arguments = parser.parse_args(argv)
    report = fit_transition_value_model(
        arguments.artifacts,
        arguments.out,
        arguments.identity,
        arguments.cohort,
        arm=arguments.arm,
        minimum_samples=arguments.minimum_samples,
        maximum_half_width=(
            arguments.maximum_half_width),
        alpha=arguments.alpha,
        overwrite=arguments.overwrite)
    encoded = json.dumps(
        report, indent=2,
        sort_keys=True) + "\n"
    if arguments.report:
        with open(
                arguments.report, "w",
                encoding="utf-8") as stream:
            stream.write(encoded)
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
