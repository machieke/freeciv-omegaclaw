#!/usr/bin/env python3
"""Validate transition calibration with cohort-scoped opportunity auditing."""

import argparse
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for path in (SRC, SCRIPT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_candidate_transition_features_cohort import (  # noqa: E402
    audit as audit_features_cohort,
)
from fit_fdas_candidate_transition_calibration import (  # noqa: E402
    DEFAULT_DISCOVERY_THRESHOLDS,
)
from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    DEFAULT_TRANSITION_VALIDATION_THRESHOLDS,
)
from validate_fdas_candidate_transition_calibration import (  # noqa: E402
    confirmation_report,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--confirmation-id", required=True)
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=16061)
    for name, value in sorted(DEFAULT_DISCOVERY_THRESHOLDS.items()):
        parser.add_argument(
            "--minimum-yield-" + name.replace("_", "-"),
            dest="yield_" + name, type=int, default=value)
    for name, value in sorted(
            DEFAULT_TRANSITION_VALIDATION_THRESHOLDS.items()):
        value_type = int if name in (
            "minimum_distinct_prediction_values",
            "minimum_heldout_lineages") else float
        parser.add_argument(
            "--" + name.replace("_", "-"), dest=name,
            type=value_type, default=value)
    args = parser.parse_args(argv)
    report = confirmation_report(
        args.run_root, args.model, args.confirmation_id,
        tuple(args.expected_seed), args.expected_source_commit,
        yield_thresholds={
            name: getattr(args, "yield_" + name)
            for name in DEFAULT_DISCOVERY_THRESHOLDS},
        validation_thresholds={
            name: getattr(args, name)
            for name in DEFAULT_TRANSITION_VALIDATION_THRESHOLDS},
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        feature_auditor=audit_features_cohort,
        report_schema_version=(
            "fdas-candidate-transition-calibration-confirmation/2.0"))
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "validation": report["validation"],
        "yield": report["yield"],
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
