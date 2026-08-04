#!/usr/bin/env python3
"""Write a deterministic PR84 paired replacement-intention audit."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_intention_live import (  # noqa: E402
    CORRECTED_EXPERIMENT_ID,
    CORRECTED_FIXED_SEEDS,
    EXPERIMENT_ID,
    FIXED_SEEDS,
    ISOLATED_EXPERIMENT_ID,
    ISOLATED_FIXED_SEEDS,
    audit_fdas_replacement_intention_cohort,
)


def _game_dirs(roots):
    rows = []
    for root in roots:
        base = os.path.join(
            os.path.abspath(root), "games", "main", "e_full_loop")
        if not os.path.isdir(base):
            raise ValueError("replacement intention root lacks games: {}".format(
                root))
        rows.extend(
            os.path.join(base, name) for name in sorted(os.listdir(base))
            if os.path.isdir(os.path.join(base, name)))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-root", action="append", required=True)
    parser.add_argument("--treatment-root", action="append", required=True)
    parser.add_argument("--expected-source-commit")
    parser.add_argument(
        "--experiment-id", choices=(
            EXPERIMENT_ID, CORRECTED_EXPERIMENT_ID, ISOLATED_EXPERIMENT_ID),
        default=EXPERIMENT_ID)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    report = audit_fdas_replacement_intention_cohort(
        _game_dirs(arguments.control_root),
        _game_dirs(arguments.treatment_root), repo=REPO,
        expected_source_commit=arguments.expected_source_commit,
        experiment_id=arguments.experiment_id,
        fixed_seeds={
            EXPERIMENT_ID: FIXED_SEEDS,
            CORRECTED_EXPERIMENT_ID: CORRECTED_FIXED_SEEDS,
            ISOLATED_EXPERIMENT_ID: ISOLATED_FIXED_SEEDS,
        }[arguments.experiment_id])
    output = os.path.abspath(arguments.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "matched_observed": report["analysis"]["classification_counts"][
            "matched-observed"],
        "output": output,
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
