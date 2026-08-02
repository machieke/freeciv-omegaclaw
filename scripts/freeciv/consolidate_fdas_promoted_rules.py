#!/usr/bin/env python3
"""Build a non-authorizing minimal basis from an FDAS holdout report."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
BENCHMARKS = os.path.join(REPO, "benchmarks")
for location in (SRC, BENCHMARKS):
    if location not in sys.path:
        sys.path.insert(0, location)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    InducedRuleProposal,
    InductionPromotionApproval,
    PromotedRuleConsolidator,
    ReplayValidation,
)
from freeciv.harness.runner import _source_identity  # noqa: E402


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path):
    absolute = os.path.abspath(path)
    relative = os.path.relpath(absolute, REPO)
    if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
        return relative.replace(os.sep, "/")
    return absolute


def _write(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    temporary = os.path.abspath(path) + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, os.path.abspath(path))


def _load_verified_report(path):
    with open(path, encoding="utf-8") as stream:
        report = json.load(stream)
    expected_hash = report.get("structural_hash")
    material = dict(report)
    material.pop("structural_hash", None)
    return report, expected_hash == structural_hash(material)


def run(arguments):
    source_report, source_hash_valid = _load_verified_report(arguments.input)
    source_result = source_report.get("result", {})
    promoted_ids = tuple(sorted(source_result.get("promoted_rule_ids", ())))
    promoted_id_set = set(promoted_ids)
    proposal_values = tuple(
        value for value in source_result.get("proposals", ())
        if value.get("proposal_id") in promoted_id_set)
    validation_values = tuple(
        value for value in source_result.get("validations", ())
        if value.get("proposal_id") in promoted_id_set)
    approval_values = tuple(source_result.get("approvals", ()))
    proposals = tuple(
        InducedRuleProposal.from_dict(value) for value in proposal_values)
    validations = tuple(
        ReplayValidation.from_dict(value) for value in validation_values)
    approvals = tuple(
        InductionPromotionApproval.from_dict(value)
        for value in approval_values)
    consolidation = PromotedRuleConsolidator().consolidate(
        proposals, validations, approvals)
    consolidation_value = consolidation.to_dict()
    retained_ids = set(consolidation.retained_rule_ids)
    retained_proposals = [
        value.to_dict() for value in sorted(
            proposals, key=lambda row: row.proposal_id)
        if value.proposal_id in retained_ids]
    execution_source = dict(
        _source_identity(), runner_sha256=_sha256(os.path.abspath(__file__)))
    input_sets_match = (
        promoted_id_set
        == set(value.proposal_id for value in proposals)
        == set(value.proposal_id for value in validations)
        == set(value.proposal_id for value in approvals))
    checks = {
        "all_promotions_have_exact_input_artifacts": input_sets_match,
        "consolidation_partitions_every_approved_rule": (
            len(consolidation.input_rule_ids)
            == len(consolidation.retained_rule_ids)
            + len(consolidation.suppressions)),
        "execution_source_requirement_met": (
            not arguments.require_clean_source
            or execution_source.get("dirty") is False),
        "no_truth_policy_or_readout_authority": (
            consolidation_value["truth_mutated"] is False
            and consolidation_value["policy_authority"] is False
            and consolidation_value["readout_authority"] is False),
        "source_acceptance_is_valid": (
            source_report.get("acceptance", {}).get("accepted") is True),
        "source_report_hash_is_valid": source_hash_valid,
        "source_report_has_no_authority": (
            source_result.get("truth_mutated") is False
            and source_result.get("policy_authority") is False
            and source_result.get("readout_authority") is False),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "retrospective, training-structure-only consolidation of exact "
            "held-out-approved FDAS rules into a minimal diagnostic basis; "
            "zero truth, policy, or readout authority and no gameplay, score, "
            "causal-intervention, or win-rate claim"),
        "consolidation": consolidation_value,
        "retained_proposals": retained_proposals,
        "schema_version": "1.0",
        "source": execution_source,
        "source_report": {
            "path": _logical(arguments.input),
            "sha256": _sha256(arguments.input),
            "structural_hash": source_report.get("structural_hash"),
        },
    }
    report["structural_hash"] = structural_hash(report)
    if arguments.output:
        _write(arguments.output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-clean-source", action="store_true")
    arguments = parser.parse_args(argv)
    report = run(arguments)
    print(json.dumps({
        "accepted": report["acceptance"]["accepted"],
        "input_rules": len(
            report["consolidation"]["input_rule_ids"]),
        "output": arguments.output,
        "retained_rules": len(
            report["consolidation"]["retained_rule_ids"]),
        "structural_hash": report["structural_hash"],
        "suppressed_rules": len(
            report["consolidation"]["suppressions"]),
    }, sort_keys=True))
    return 0 if report["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
