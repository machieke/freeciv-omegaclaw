#!/usr/bin/env python3
"""Audit the fixed fresh-seed delayed replacement-production cohort."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_capacity_production_cohort import (  # noqa: E402
    audit_fdas_replacement_capacity_production_cohort,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seeds", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    seeds = tuple(int(value) for value in args.expected_seeds.split(","))
    report = audit_fdas_replacement_capacity_production_cohort(
        args.run_dir, seeds, args.expected_source_commit, repo=REPO)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "capacity_production_candidates": report["summary"][
            "capacity_production_candidate_count"],
        "grounded_production_operations": report["summary"][
            "grounded_production_operation_count"],
        "output": output,
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
