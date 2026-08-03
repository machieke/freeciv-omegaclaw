#!/usr/bin/env python3
"""Audit a frozen engine-backed FDAS randomized-alternative run."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_randomized_alternative_live import (  # noqa: E402
    audit_randomized_alternative_run,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--output")
    parser.add_argument("--expected-seed", action="append", type=int,
                        default=[])
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-implementation-sha256")
    parser.add_argument("--require-treatment", action="store_true")
    args = parser.parse_args()
    report = audit_randomized_alternative_run(
        args.run_dir,
        expected_seeds=args.expected_seed,
        expected_source_commit=args.expected_source_commit,
        expected_implementation_sha256=(
            args.expected_implementation_sha256),
        require_treatment=args.require_treatment)
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
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
