#!/usr/bin/env python3
"""Audit a paired legacy-control and FDAS-shadow engine cohort."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_shadow_cohort import (  # noqa: E402
    audit_fdas_shadow_cohort,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True)
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--minimum-pairs", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit_fdas_shadow_cohort(
        args.control, args.shadow, minimum_pairs=args.minimum_pairs)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "failure_count": report["acceptance"]["failure_count"],
        "output": output,
        "pairs": len(report["pairs"]),
        "structural_hash": report["structural_hash"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())

