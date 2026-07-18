#!/usr/bin/env python3
"""Run the 100-turn authoritative packet/state/action comparator."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.state.parity import run_state_action_parity  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--seed", type=int, default=4202)
    parser.add_argument("--output")
    args = parser.parse_args()
    fixture = os.path.join(REPO, "contracts", "freeciv-proxy", "v2",
                           "authoritative-state.fixture.json")
    with open(fixture, encoding="utf-8") as stream:
        report = run_state_action_parity(json.load(stream), args.turns, args.seed)
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
