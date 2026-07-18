#!/usr/bin/env python3
"""Run M1 prerequisite parity against native FreeCiv for every technology."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.oracle import (DependencyOracle, NativeResearchOracle,  # noqa: E402
                                  compare_all)
from freeciv_agent.rulesets.compiler import canonical_json, compile_ruleset  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", action="append", choices=("civ2civ3", "classic"))
    parser.add_argument("--image", default=os.environ.get(
        "FREECIV_PARITY_IMAGE", "freeciv-research-parity:local"))
    parser.add_argument("--states", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")
    if args.states < 1:
        parser.error("--states must be positive")
    rulesets = args.ruleset or ["civ2civ3", "classic"]
    native = NativeResearchOracle(args.image)
    reports = []
    os.makedirs(args.out, exist_ok=True)
    for ruleset in rulesets:
        ir = compile_ruleset(args.ruleset_root, ruleset)
        report = compare_all(ir, DependencyOracle(ir), native,
                             state_count=args.states, seed=args.seed)
        report["native_image"] = native.image_identity()
        report["ruleset_source_hashes"] = ir.source_hashes
        data = canonical_json(report)
        path = os.path.join(args.out, ruleset + "-parity.json")
        with open(path, "wb") as handle:
            handle.write(data)
        report["artifact"] = {"path": path, "sha256": hashlib.sha256(data).hexdigest()}
        reports.append(report)
    summary = {
        "comparisons": sum(item["comparisons"] for item in reports),
        "mismatches": sum(len(item["mismatches"]) for item in reports),
        "passed": all(item["passed"] for item in reports),
        "reports": reports,
        "seed": args.seed,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
