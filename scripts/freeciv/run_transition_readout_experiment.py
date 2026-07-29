#!/usr/bin/env python3
"""Run the calibrated transition/readout ablation and write its report."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
for candidate in (
        REPO,
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks"),
):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.pf_unified.transition_readout_experiment import (  # noqa: E402
    run_transition_readout_experiment,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--readout-cases", type=int, default=300)
    parser.add_argument(
        "--persistence-traces", type=int, default=64)
    parser.add_argument(
        "--persistence-steps", type=int, default=80)
    parser.add_argument("--out")
    arguments = parser.parse_args(argv)
    result = run_transition_readout_experiment(
        arguments.readout_cases,
        arguments.persistence_traces,
        arguments.persistence_steps)
    encoded = json.dumps(
        result, indent=2, sort_keys=True) + "\n"
    if arguments.out:
        with open(
                arguments.out, "w",
                encoding="utf-8") as stream:
            stream.write(encoded)
    sys.stdout.write(encoded)
    return 0 if result["offline_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
