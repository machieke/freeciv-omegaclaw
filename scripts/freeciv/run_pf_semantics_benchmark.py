#!/usr/bin/env python3
"""Emit the deterministic PF-PLN Phase 0 executable-semantics artifact."""

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

from freeciv.pf_semantics_benchmark import (  # noqa: E402
    run_semantics_benchmark,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    report = run_semantics_benchmark()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0 if all(report["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
