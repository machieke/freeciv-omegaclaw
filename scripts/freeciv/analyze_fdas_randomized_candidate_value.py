#!/usr/bin/env python3
"""Analyze a powered randomized FDAS candidate-value discovery cohort."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_randomized_candidate_value import (  # noqa: E402
    analyze_randomized_candidate_value,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_report")
    parser.add_argument("--output")
    parser.add_argument("--minimum-assignments-per-arm", type=int, default=44)
    parser.add_argument("--minimum-game-clusters-per-arm", type=int, default=20)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=8113)
    args = parser.parse_args()
    with open(args.audit_report, encoding="utf-8") as stream:
        audit = json.load(stream)
    report = analyze_randomized_candidate_value(
        audit,
        minimum_assignments_per_arm=args.minimum_assignments_per_arm,
        minimum_game_clusters_per_arm=args.minimum_game_clusters_per_arm,
        confidence=args.confidence,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        temporary = output + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, output)
    else:
        sys.stdout.write(payload)
    return 0 if report["mechanically_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
