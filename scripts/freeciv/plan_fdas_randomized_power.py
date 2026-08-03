#!/usr/bin/env python3
"""Create an outcome-blind powered FDAS candidate-value design."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_randomized_power import (  # noqa: E402
    plan_randomized_candidate_value,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("yield_report")
    parser.add_argument("--output")
    parser.add_argument("--minimum-detectable-risk-difference", type=float,
                        default=0.35)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--target-power", type=float, default=0.80)
    parser.add_argument("--planning-icc", type=float, default=0.25)
    parser.add_argument("--yield-safety-multiplier", type=float, default=1.25)
    parser.add_argument("--minimum-game-clusters-per-arm", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--mean-engine-seconds-per-game", type=float)
    args = parser.parse_args()
    with open(args.yield_report, encoding="utf-8") as stream:
        report = json.load(stream)
    plan = plan_randomized_candidate_value(
        report,
        minimum_detectable_risk_difference=(
            args.minimum_detectable_risk_difference),
        alpha=args.alpha,
        target_power=args.target_power,
        planning_icc=args.planning_icc,
        yield_safety_multiplier=args.yield_safety_multiplier,
        minimum_game_clusters_per_arm=args.minimum_game_clusters_per_arm,
        workers=args.workers,
        mean_engine_seconds_per_game=args.mean_engine_seconds_per_game)
    payload = json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        temporary = output + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, output)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
