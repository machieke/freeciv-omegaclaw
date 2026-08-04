#!/usr/bin/env python3
"""Export and audit the offline retained-capacity episode dataset."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv.harness.fdas_retained_capacity_episode_dataset import (  # noqa: E402
    DEFAULT_ADEQUACY_THRESHOLDS,
    export_fdas_retained_capacity_episode_dataset,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--expected-seeds", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-parent-report-hash", required=True)
    parser.add_argument("--output", required=True)
    for name, value in sorted(DEFAULT_ADEQUACY_THRESHOLDS.items()):
        parser.add_argument(
            "--minimum-" + name.replace("_", "-"),
            dest=name, type=int, default=value)
    args = parser.parse_args(argv)
    thresholds = {
        name: getattr(args, name) for name in DEFAULT_ADEQUACY_THRESHOLDS}
    report = export_fdas_retained_capacity_episode_dataset(
        args.run_dir,
        tuple(int(value) for value in args.expected_seeds.split(",")),
        args.expected_source_commit, args.expected_parent_report_hash,
        repo=REPO, adequacy_thresholds=thresholds)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "adequacy": report["adequacy"]["decision"],
        "dataset_hash": report["dataset_hash"],
        "output": output,
        "terminal_episodes": report["summary"]["terminal_episodes"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
