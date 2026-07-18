#!/usr/bin/env python3
"""Measure warm M1 proof latency independently of compiler/import startup."""

import argparse
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.oracle import CrispStateView, DependencyOracle, Goal  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def percentile(values, fraction):
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", default="civ2civ3", choices=("civ2civ3", "classic"))
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    ir = compile_ruleset(args.ruleset_root, args.ruleset)
    oracle = DependencyOracle(ir)
    state = CrispStateView("benchmark-empty", known_techs=(), player="benchmark")
    techs = sorted(rule.rule_name for rule in ir.rules if rule.target_kind == "tech")
    samples = []
    largest = {"chain_depth": -1}
    for round_index in range(args.rounds):
        for tech in techs:
            # Snapshot IDs vary by round so each measurement exercises proof traversal;
            # compiler import and service startup remain outside this hot path.
            round_state = CrispStateView("benchmark-{}".format(round_index),
                                         known_techs=(), player="benchmark")
            started = time.perf_counter()
            result = oracle.deps(Goal.researchable("benchmark", tech), round_state)
            elapsed = (time.perf_counter() - started) * 1000.0
            samples.append(elapsed)
            if result.chain_depth > largest["chain_depth"]:
                largest = {"chain_depth": result.chain_depth, "latency_ms": elapsed,
                           "tech": tech, "tree_size": len(result.proof["nodes"])}
    output = {
        "cache_status": "miss",
        "count": len(samples),
        "maximum_ms": max(samples),
        "mean_ms": statistics.mean(samples),
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "ruleset": args.ruleset,
        "longest_full_depth": largest,
    }
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0 if largest["latency_ms"] < 500.0 else 1


if __name__ == "__main__":
    sys.exit(main())
