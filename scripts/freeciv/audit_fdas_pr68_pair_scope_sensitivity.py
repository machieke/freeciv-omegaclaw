#!/usr/bin/env python3
"""Reconstruct exact PR68 pair-scope evidence from immutable event parents."""

import argparse
import glob
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_grounded_transition_candidate_readout import (  # noqa: E402
    UNION_COMPONENT_ID,
)
from audit_fdas_safe_filtered_scalar_readout import (  # noqa: E402
    FILTER_COMPONENT_ID,
)
from audit_fdas_safe_filtered_scalar_readout_cohort import (  # noqa: E402
    audit as audit_pr68,
)
from audit_fdas_scalar_baseline_candidate_readout import (  # noqa: E402
    READOUT_COMPONENT_ID,
)
from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)


AUDIT_IDENTITY = "fdas-pr68-pair-scope-sensitivity/1.0"
PR68_PRIMARY_REPORT_HASH = (
    "9364021e5f06684b836ebb5ffcea22a15c4af1e7ec5a6b4e200287d1a2bbde1c")
GENERIC_REASON = ":pair-scope-mismatch"


def _unit_resources(action):
    if (not isinstance(action, dict)
            or not str(action.get("action_type", "")).startswith("unit_")
            or isinstance(action.get("actor_id"), bool)
            or not isinstance(action.get("actor_id"), int)):
        return None
    return ("unit-action:{}".format(action["actor_id"]),)


def _reconstruct_pair(game_id, turn, readout, union_event, filter_event,
                      alternative_id):
    union = union_event["payload"]["details"]
    candidate_filter = filter_event["payload"]["details"]
    union_by_id = {
        value.get("operation_id"): value
        for value in union.get("readouts", ())
        if isinstance(value, dict)}
    filter_by_id = {
        value.get("operation_id"): value
        for value in candidate_filter.get("readouts", ())
        if isinstance(value, dict)}
    baseline_id = readout.get("baseline_operation_id")
    baseline_union = union_by_id.get(baseline_id)
    alternative_union = union_by_id.get(alternative_id)
    baseline_filter = filter_by_id.get(baseline_id)
    alternative_filter = filter_by_id.get(alternative_id)
    if any(value is None for value in (
            baseline_union, alternative_union,
            baseline_filter, alternative_filter)):
        raise ValueError("PR68 scope pair lacks a parent candidate row")
    try:
        baseline_action = json.loads(baseline_union["action_key"])
        alternative_action = json.loads(alternative_union["action_key"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("PR68 scope pair action is not canonical JSON")
    baseline_resources = _unit_resources(baseline_action)
    alternative_resources = _unit_resources(alternative_action)
    if baseline_resources is None or alternative_resources is None:
        raise ValueError("PR68 sensitivity supports ordinary unit resources")
    overlap = tuple(sorted(set(baseline_resources).intersection(
        alternative_resources)))
    predicates = {
        "bounded_target_support_matches": (
            baseline_filter.get("source_atom_id")
            == alternative_filter.get("source_atom_id")),
        "duplicate_action": (
            baseline_union.get("action_key")
            == alternative_union.get("action_key")),
        "identical_inferred_resource_set": (
            baseline_resources == alternative_resources),
        "operation_type_matches": (
            baseline_union.get("operation_type")
            == alternative_union.get("operation_type")),
        "shared_inferred_resources": list(overlap),
    }
    semantic = {
        "alternative": {
            "action_key": alternative_union.get("action_key"),
            "bounded_target_support_atom_id": alternative_filter.get(
                "source_atom_id"),
            "inferred_resources": list(alternative_resources),
            "operation_id": alternative_id,
            "operation_type": alternative_union.get("operation_type"),
        },
        "baseline": {
            "action_key": baseline_union.get("action_key"),
            "bounded_target_support_atom_id": baseline_filter.get(
                "source_atom_id"),
            "inferred_resources": list(baseline_resources),
            "operation_id": baseline_id,
            "operation_type": baseline_union.get("operation_type"),
        },
        "filter_event_id": filter_event.get("event_id"),
        "game_id": game_id,
        "inference_contract": (
            "CandidateOperationFactory._resource/unit-action-actor/1.0"),
        "predicates": predicates,
        "readout_result_hash": readout.get("result_hash"),
        "turn": turn,
        "union_event_id": union_event.get("event_id"),
    }
    return dict(semantic, row_hash=structural_hash(semantic))


def _sensitivity_rows(run_root):
    rows = []
    for event_path in sorted(glob.glob(os.path.join(
            os.path.abspath(run_root), "games", "main", "e_full_loop", "*",
            "events.jsonl"))):
        events = []
        with open(event_path, encoding="utf-8") as stream:
            events.extend(json.loads(line) for line in stream)
        by_id = {value.get("event_id"): value for value in events}
        unions = {
            value.get("payload", {}).get("details", {}).get("result_hash"):
            value for value in events
            if (value.get("type") == "atomspace_shadow_decision"
                and value.get("payload", {}).get("component_id")
                == UNION_COMPONENT_ID)}
        for event in events:
            payload = event.get("payload", {})
            details = payload.get("details", {})
            if (event.get("type") != "atomspace_shadow_decision"
                    or payload.get("component_id") != READOUT_COMPONENT_ID):
                continue
            alternatives = tuple(
                value[:-len(GENERIC_REASON)]
                for value in details.get("rejected", ())
                if isinstance(value, str) and value.endswith(GENERIC_REASON))
            if not alternatives:
                continue
            union_event = unions.get(
                details.get("protected_union_result_hash"))
            if union_event is None:
                raise ValueError("PR68 scope readout lacks union parent")
            parent_ids = tuple(union_event.get("caused_by", ()))
            filter_event = by_id.get(parent_ids[0]) if len(
                parent_ids) == 1 else None
            if (filter_event is None
                    or filter_event.get("payload", {}).get("component_id")
                    != FILTER_COMPONENT_ID):
                raise ValueError("PR68 scope union lacks filter parent")
            rows.extend(_reconstruct_pair(
                event.get("game_id"), event.get("turn"), details,
                union_event, filter_event, operation_id)
                for operation_id in alternatives)
    return tuple(rows)


def audit(run_root, expected_seeds, expected_source_commit):
    parent = audit_pr68(
        run_root, expected_seeds, expected_source_commit)
    rows = _sensitivity_rows(run_root)
    gates = {
        "all_pairs_are_distinct_actions": (
            bool(rows) and all(
                not value["predicates"]["duplicate_action"]
                for value in rows)),
        "all_pairs_have_identical_actor_resource": (
            bool(rows) and all(
                value["predicates"]["identical_inferred_resource_set"]
                and value["predicates"]["shared_inferred_resources"]
                for value in rows)),
        "all_pairs_have_matching_bounded_target_support": (
            bool(rows) and all(
                value["predicates"]["bounded_target_support_matches"]
                for value in rows)),
        "all_pairs_have_matching_operation_type": (
            bool(rows) and all(
                value["predicates"]["operation_type_matches"]
                for value in rows)),
        "exact_six_pr68_scope_pairs_reconstructed": len(rows) == 6,
        "pr68_primary_report_is_hash_bound": (
            parent["report_hash"] == PR68_PRIMARY_REPORT_HASH
            and parent["passed"] is False),
    }
    report = {
        "audit_identity": AUDIT_IDENTITY,
        "claim_scope": (
            "post-hoc deterministic PR68 scope sensitivity only; actor "
            "resources are reconstructed from the committed factory rule; "
            "no fresh confirmation, eligibility change, alternative value, "
            "ranking, gameplay, score, or win-rate claim"),
        "gates": gates,
        "parent_report_hash": parent["report_hash"],
        "passed": all(gates.values()),
        "rows": list(rows),
    }
    report["report_hash"] = structural_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("--expected-seed", action="append", type=int,
                        required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit(
        args.run_root, args.expected_seed, args.expected_source_commit)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as stream:
        stream.write(canonical_json_bytes(report) + b"\n")
    print(json.dumps({
        "gates": report["gates"],
        "output": output,
        "passed": report["passed"],
        "report_hash": report["report_hash"],
        "rows": len(report["rows"]),
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
