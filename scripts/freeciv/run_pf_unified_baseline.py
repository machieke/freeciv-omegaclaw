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
from freeciv.pf_unified.v2_benchmark import (  # noqa: E402
    run_v2_timing,
    run_v2_verification,
)
from freeciv.pf_unified.teleology_benchmark import (  # noqa: E402
    run_g2_timing,
    run_g2_verification,
)
from freeciv.pf_unified.bridge_experiment import (  # noqa: E402
    run_g3_bridge_experiment,
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
    v2_timing = commands.add_parser("v2-timing")
    v2_timing.add_argument("--repetitions", type=int, default=500)
    commands.add_parser("v2-verify")
    g2_timing = commands.add_parser("g2-timing")
    g2_timing.add_argument("--repetitions", type=int, default=50)
    commands.add_parser("g2-verify")
    g3_bridge = commands.add_parser("g3-bridge-experiment")
    g3_bridge.add_argument(
        "--train-seeds-per-family", type=int, default=64)
    g3_bridge.add_argument(
        "--heldout-seeds-per-family", type=int, default=64)
    g3_bridge.add_argument(
        "--timing-repetitions", type=int, default=20)
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
    elif command == "v2-timing":
        result = run_v2_timing(arguments.repetitions)
        status = 0
    elif command == "v2-verify":
        result = run_v2_verification()
        status = 0 if result["valid"] else 1
    elif command == "g2-timing":
        result = run_g2_timing(arguments.repetitions)
        status = 0
    elif command == "g2-verify":
        result = run_g2_verification()
        status = 0 if result["valid"] else 1
    elif command == "g3-bridge-experiment":
        result = run_g3_bridge_experiment(
            arguments.train_seeds_per_family,
            arguments.heldout_seeds_per_family,
            arguments.timing_repetitions)
        status = 0 if result["valid"] else 1
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
