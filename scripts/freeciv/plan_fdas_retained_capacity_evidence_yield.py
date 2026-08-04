#!/usr/bin/env python3
"""Write the frozen retained-capacity evidence-yield plan."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv.harness.fdas_retained_capacity_evidence_yield import (  # noqa: E402
    retained_capacity_evidence_yield_plan,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = retained_capacity_evidence_yield_plan()
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    os.replace(temporary, output)
    print(json.dumps({
        "conservative_sensitivity_games": report["planning"][
            "conservative_wilson_lower_sensitivity_games"],
        "output": output,
        "plan_hash": report["plan_hash"],
        "provisional_games": report["planning"][
            "provisional_games_per_discovery_or_confirmation_cohort"],
        "yield_pilot_games": report["planning"][
            "query_enabled_yield_pilot_games"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
