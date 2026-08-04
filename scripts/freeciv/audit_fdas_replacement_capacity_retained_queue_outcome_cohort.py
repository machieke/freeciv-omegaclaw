#!/usr/bin/env python3
"""Audit a fixed retained-capacity delayed-outcome cohort."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_capacity_retained_queue_outcome_cohort import (  # noqa: E402
    audit_fdas_replacement_capacity_retained_queue_outcome_cohort,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seeds", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--minimum-games-with-label", type=int, default=2)
    parser.add_argument("--minimum-games-with-product", type=int, default=1)
    parser.add_argument("--minimum-games-with-relief", type=int, default=1)
    parser.add_argument("--minimum-positive-relief", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit_fdas_replacement_capacity_retained_queue_outcome_cohort(
        args.run_dir,
        tuple(int(value) for value in args.expected_seeds.split(",")),
        args.expected_source_commit, repo=REPO,
        minimum_games_with_label=args.minimum_games_with_label,
        minimum_games_with_product=args.minimum_games_with_product,
        minimum_games_with_relief=args.minimum_games_with_relief,
        minimum_positive_relief=args.minimum_positive_relief)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "games_with_label": report["summary"]["games_with_label"],
        "games_with_product": report["summary"]["games_with_product"],
        "games_with_relief": report["summary"]["games_with_relief"],
        "relief_positive": report["summary"]["relief_positive"],
        "output": output,
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
