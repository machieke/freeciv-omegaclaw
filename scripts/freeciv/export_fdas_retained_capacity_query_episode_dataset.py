#!/usr/bin/env python3
"""Export retained-capacity proposal queries and later observations."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv.harness.fdas_retained_capacity_query_episode_dataset import (  # noqa: E402
    export_fdas_retained_capacity_query_episode_dataset,
)


def _hashes(value):
    if value is None:
        return None
    result = {}
    for item in value.split(","):
        seed, digest = item.split(":", 1)
        result[int(seed)] = digest
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seeds", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument(
        "--expected-parent-report-hashes",
        help="comma-separated seed:structural-hash bindings")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = export_fdas_retained_capacity_query_episode_dataset(
        args.run_dir,
        tuple(int(value) for value in args.expected_seeds.split(",")),
        args.expected_source_commit, repo=REPO,
        expected_parent_report_hashes=_hashes(
            args.expected_parent_report_hashes))
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "dataset_hash": report["dataset_hash"],
        "output": output,
        "query_rows": report["summary"]["query_rows"],
        "right_censored_rows": report["summary"]["right_censored_rows"],
        "terminal_rows": report["summary"]["terminal_rows"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
