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

from freeciv.pf_pressure_replay import (  # noqa: E402
    direct_completion_counterfactual_paths,
    opportunity_counterfactual_paths,
    replay_paths,
    score_alignment_counterfactual_paths,
)
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--maximum-files", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--direct-completion-counterfactual", action="store_true")
    mode.add_argument(
        "--opportunity-counterfactual", action="store_true")
    mode.add_argument(
        "--score-alignment-counterfactual", action="store_true")
    parser.add_argument(
        "--exploration-information-enabled", action="store_true",
        help=(
            "retain grounded positional exploration pressure in "
            "score-alignment replay"))
    parser.add_argument(
        "--score-alignment-utility-tolerance", type=float, default=0.0,
        help="relative utility uncertainty band for score-alignment replay")
    parser.add_argument("--output")
    parser.add_argument("--relative-to", default=REPO)
    args = parser.parse_args()
    if (not args.score_alignment_counterfactual
            and (args.exploration_information_enabled
                 or args.score_alignment_utility_tolerance)):
        parser.error(
            "score-alignment replay settings require "
            "--score-alignment-counterfactual")
    if args.score_alignment_counterfactual:
        result = score_alignment_counterfactual_paths(
            args.paths, args.maximum_files, args.relative_to,
            exploration_information_enabled=(
                args.exploration_information_enabled),
            score_alignment_utility_tolerance=(
                args.score_alignment_utility_tolerance))
    else:
        replay = (
            direct_completion_counterfactual_paths
            if args.direct_completion_counterfactual
            else opportunity_counterfactual_paths
            if args.opportunity_counterfactual
            else replay_paths)
        result = replay(args.paths, args.maximum_files, args.relative_to)
    encoded = canonical_json_bytes(result) + b"\n"
    if args.output:
        with open(args.output, "wb") as stream:
            stream.write(encoded)
    else:
        sys.stdout.buffer.write(encoded)


if __name__ == "__main__":
    main()
