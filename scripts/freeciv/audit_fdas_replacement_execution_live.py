#!/usr/bin/env python3
"""Audit the bounded coordinated-replacement execution pilot."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_execution_live import (  # noqa: E402
    audit_fdas_replacement_execution_live,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit_fdas_replacement_execution_live(
        args.game_dir, repo=REPO,
        expected_source_commit=args.expected_source_commit)
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
