#!/usr/bin/env python3
"""Audit a fixed PF-selected retained replacement-capacity queue cohort."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_capacity_retained_queue_cohort import (  # noqa: E402
    audit_fdas_replacement_capacity_retained_queue_cohort,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seeds", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--minimum-games-with-selected-match", type=int,
                        default=2)
    parser.add_argument("--minimum-games-with-product-observation", type=int,
                        default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    seeds = tuple(int(value) for value in args.expected_seeds.split(","))
    report = audit_fdas_replacement_capacity_retained_queue_cohort(
        args.run_dir, seeds, args.expected_source_commit, repo=REPO,
        minimum_games_with_selected_match=(
            args.minimum_games_with_selected_match),
        minimum_games_with_product_observation=(
            args.minimum_games_with_product_observation))
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "games_with_product_observation": report["summary"][
            "games_with_product_observation"],
        "games_with_selected_match": report["summary"][
            "games_with_selected_match"],
        "operations_registered": report["summary"]["operations_registered"],
        "output": output,
        "product_observations": report["summary"]["product_observations"],
        "selected_matches": report["summary"]["selected_matches"],
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
