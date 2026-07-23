#!/usr/bin/env python3
"""Emit the deterministic PF-PLN pressure-concentration benchmark artifact."""

import argparse
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

from freeciv.pf_pressure_benchmark import (  # noqa: E402
    run_pressure_concentration_benchmark,
)
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--irrelevant-branches", type=int, default=128)
    parser.add_argument("--branch-depth", type=int, default=4)
    parser.add_argument("--max-routes", type=int, default=32)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run_pressure_concentration_benchmark(
        args.irrelevant_branches, args.branch_depth, args.max_routes)
    encoded = canonical_json_bytes(result.to_dict()) + b"\n"
    if args.output:
        with open(args.output, "wb") as stream:
            stream.write(encoded)
    else:
        sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
