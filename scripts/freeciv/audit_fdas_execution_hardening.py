#!/usr/bin/env python3
"""Audit canonical spatial actions and stale-unit replay protection."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_execution_hardening import (  # noqa: E402
    audit_execution_hardening,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("randomized_audit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--historical-seed", type=int, required=True)
    parser.add_argument("--historical-turn", type=int, required=True)
    args = parser.parse_args()
    report = audit_execution_hardening(
        args.run_dir,
        args.randomized_audit,
        expected_seeds=args.expected_seed,
        historical_seed=args.historical_seed,
        historical_turn=args.historical_turn)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
