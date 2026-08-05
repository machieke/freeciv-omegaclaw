#!/usr/bin/env python3
"""Fit and audit the frozen PR99 retained-capacity shadow model."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv.harness.fdas_retained_capacity_transition_model_fit import (  # noqa: E402
    audit_fdas_retained_capacity_transition_model_fit,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source_report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with open(args.source_report, encoding="utf-8") as stream:
        source = json.load(stream)
    report = audit_fdas_retained_capacity_transition_model_fit(source)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    temporary = output + ".tmp.{}".format(os.getpid())
    with open(temporary, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    os.replace(temporary, output)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "model_hash": report["model"]["result_hash"],
        "output": output,
        "structural_hash": report["structural_hash"],
        "summary": report["summary"],
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
