#!/usr/bin/env python3
"""Audit the disjoint engine-backed GDO-8 calibration bundle."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


TRAINING = (
    "docs/freeciv/evidence/"
    "gdo8-contextual-transition-training-v1-report.json")
HOLDOUT = (
    "docs/freeciv/evidence/"
    "gdo8-contextual-transition-holdout-v1-approval.json")
MODEL = (
    "docs/freeciv/evidence/"
    "gdo8-contextual-transition-training-v1-model.json")


def _json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(
                lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run():
    paths = {
        "training": os.path.join(REPO, TRAINING),
        "holdout": os.path.join(REPO, HOLDOUT),
        "model": os.path.join(REPO, MODEL),
    }
    training = _json(paths["training"])
    holdout = _json(paths["holdout"])
    training_seeds = set(
        int(row["seed"])
        for row in training["event_files"])
    holdout_seeds = set(
        int(row["seed"])
        for row in holdout["event_files"])
    model_sha256 = _sha256(paths["model"])
    gates = {
        "all_holdout_gates_passed": bool(
            holdout.get("gates")
            and all(
                value is True
                for value in holdout[
                    "gates"].values())),
        "authority_bundle_approved":
            holdout.get(
                "authority_approved")
            is True,
        "clean_source_identity_matches": (
            training.get(
                "source_identity")
            == holdout.get(
                "source_identity")),
        "disjoint_seed_sets":
            not training_seeds.intersection(
                holdout_seeds),
        "frozen_model_hash_matches": (
            training.get(
                "model_sha256")
            == holdout.get(
                "model_sha256")
            == model_sha256),
        "model_state_hash_matches": (
            training.get(
                "model_state_hash")
            == holdout.get(
                "model_state_hash")),
        "predeclared_sample_sizes_met": (
            len(training_seeds) == 30
            and len(holdout_seeds) == 30),
    }
    passed = all(gates.values())
    report = {
        "claim_boundary": {
            "gameplay_score_claim": False,
            "off_policy_value_claim": False,
            "prediction_calibration_claim":
                passed,
        },
        "gates": gates,
        "holdout": holdout[
            "aggregate"],
        "inputs": {
            "holdout": {
                "path": HOLDOUT,
                "sha256":
                    _sha256(paths["holdout"]),
            },
            "model": {
                "path": MODEL,
                "sha256": model_sha256,
            },
            "training": {
                "path": TRAINING,
                "sha256":
                    _sha256(paths["training"]),
            },
        },
        "result": {
            "engine_holdout_approved":
                passed,
            "holdout_outcomes":
                holdout["aggregate"][
                    "total_holdout_count"],
            "supported_training_keys":
                training[
                    "supported_key_count"],
            "total_training_keys":
                training["total_key_count"],
            "training_outcomes":
                training["outcome_count"],
        },
        "schema_version": "1.0",
        "scope": {
            "engine_backed": True,
            "live_authority_eligible":
                passed,
            "policy_authority_exercised":
                False,
            "target": (
                "selected-action realized "
                "goal-relief prediction"),
        },
        "seeds": {
            "holdout_count":
                len(holdout_seeds),
            "training_count":
                len(training_seeds),
        },
    }
    report["report_hash"] = structural_hash(
        report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=os.path.join(
            REPO, "benchmarks", "gdo",
            "gdo8_contextual_engine_confirmation.json"))
    arguments = parser.parse_args()
    report = run()
    output = os.path.abspath(
        arguments.output)
    os.makedirs(
        os.path.dirname(output),
        exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(
            canonical_json_bytes(report))
        stream.write(b"\n")
    print(json.dumps({
        "gates": report["gates"],
        "output": os.path.relpath(
            output, REPO),
        "report_hash":
            report["report_hash"],
        "result": report["result"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
