#!/usr/bin/env python3
"""Audit raw scalability trials and emit reconstructed aggregate evidence."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for candidate in (REPO, os.path.join(REPO, "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from benchmarks.freeciv.scaling.audit import audit_results, load_results  # noqa: E402
from benchmarks.freeciv.scaling.claims import build_claim_manifest  # noqa: E402
from benchmarks.freeciv.scaling.runner import write_json  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-resamples", type=int, default=10000)
    arguments = parser.parse_args(argv)
    engine_path = os.path.join(
        arguments.root, "heldout", "engine", "report.json")
    engine_report = None
    if os.path.isfile(engine_path):
        with open(engine_path, "r", encoding="utf-8") as handle:
            engine_report = json.load(handle)
    results = load_results(arguments.root)
    audit = audit_results(
        results,
        resamples=arguments.bootstrap_resamples,
        engine_report=engine_report)
    frozen = None
    frozen_path = os.path.join(arguments.root, "frozen-preregistration.json")
    if os.path.isfile(frozen_path):
        with open(frozen_path, "r", encoding="utf-8") as handle:
            frozen = json.load(handle)
    claims = build_claim_manifest(results, audit, frozen=frozen)
    write_json(os.path.join(arguments.root, "aggregate.json"), audit["report"])
    write_json(os.path.join(arguments.root, "audit.json"), audit)
    write_json(os.path.join(arguments.root, "claim-manifest.json"), claims)
    write_json(arguments.output, audit)
    json.dump(audit, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if audit["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
