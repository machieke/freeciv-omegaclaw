#!/usr/bin/env python3
"""Run M1 unsatisfied-frontier properties through the native engine."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.oracle import (DependencyOracle, NativeResearchOracle,  # noqa: E402
                                  check_leaf_properties)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", default="civ2civ3", choices=("civ2civ3", "classic"))
    parser.add_argument("--image", default=os.environ.get(
        "FREECIV_PARITY_IMAGE", "freeciv-research-parity:local"))
    parser.add_argument("--pairs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    ir = compile_ruleset(args.ruleset_root, args.ruleset)
    report = check_leaf_properties(ir, DependencyOracle(ir),
                                   NativeResearchOracle(args.image),
                                   pair_count=args.pairs, seed=args.seed)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
