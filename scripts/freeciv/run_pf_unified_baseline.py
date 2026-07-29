#!/usr/bin/env python3
"""Capture, verify, replay, compare, or time the unified PF-PLN baseline."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.baseline import (  # noqa: E402
    assert_comparable,
    load_baseline_manifest,
    verify_baseline,
)
from freeciv.pf_unified.golden import (  # noqa: E402
    capture_golden,
    controller_timings,
    reproduce_golden,
)


def _parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("verify")
    capture = commands.add_parser("capture")
    capture.add_argument("--out")
    commands.add_parser("replay")
    timing = commands.add_parser("timing")
    timing.add_argument("--repetitions", type=int, default=20)
    compare = commands.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--allow-cross-version", action="store_true")
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    command = arguments.command or "verify"
    if command == "verify":
        result = verify_baseline()
        status = 0 if result["valid"] else 1
    elif command == "capture":
        result = {"artifacts": capture_golden(arguments.out)}
        status = 0
    elif command == "replay":
        result = reproduce_golden()
        status = 0 if result["byte_exact"] else 1
    elif command == "timing":
        result = controller_timings(arguments.repetitions)
        status = 0
    else:
        result = assert_comparable(
            load_baseline_manifest(arguments.left),
            load_baseline_manifest(arguments.right),
            allow_cross_version=arguments.allow_cross_version)
        status = 0
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
