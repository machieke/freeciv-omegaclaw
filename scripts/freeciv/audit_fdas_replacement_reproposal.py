#!/usr/bin/env python3
"""Audit PR80 coordinated-replacement terminal reproposal hardening."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_reproposal import (  # noqa: E402
    audit_fdas_replacement_reproposal,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--maximum-events", type=int, default=300000)
    parser.add_argument("--maximum-operations", type=int, default=80)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit_fdas_replacement_reproposal(
        args.game_dir, repo=REPO,
        expected_source_commit=args.expected_source_commit,
        maximum_events=args.maximum_events,
        maximum_operations=args.maximum_operations)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "output": output,
        "structural_hash": report["structural_hash"],
        "summary": report["summary"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
