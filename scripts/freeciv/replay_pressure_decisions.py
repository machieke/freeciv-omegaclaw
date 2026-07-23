#!/usr/bin/env python3
"""Compare recorded PF choices with exact unpressured candidate ordering."""

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

from freeciv.pf_pressure_replay import replay_paths  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--maximum-files", type=int)
    parser.add_argument("--output")
    parser.add_argument("--relative-to", default=REPO)
    args = parser.parse_args()
    result = replay_paths(
        args.paths, args.maximum_files, args.relative_to)
    encoded = canonical_json_bytes(result) + b"\n"
    if args.output:
        with open(args.output, "wb") as stream:
            stream.write(encoded)
    else:
        sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
