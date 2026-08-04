"""Audit delayed grounded replacement-capacity production operations."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_live import (
    audit_fdas_replacement_capacity_live,
)


_COMPONENT_ID = "fdas-goal-pressure-shadow"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "candidate_authority": False,
    "completion_semantics": (
        "queue-selection-then-authoritative-product-observation"),
    "maximum_observation_horizon_turns": 64,
    "policy_authority": False,
    "queue_selection_is_goal_relief": False,
    "resource_semantics": "exact-current-and-conditional-future-claims",
    "truth_mutated": False,
}


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def audit_fdas_replacement_capacity_production_live(game_dir, repo=None):
    """Verify exact queue/observation semantics without granting relief."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_live(game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in ("events.jsonl", "manifest.json", "status.json")
    }
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    candidates = tuple(
        row for row in events
        if (row.get("type") in (
                "operation_candidate_instantiated",
                "operation_candidate_rejected")
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID
            and row.get("payload", {}).get("details", {}).get(
                "operation_type") == _OPERATION_TYPE))
    details = tuple(
        row.get("payload", {}).get("details", {}) for row in candidates)
    grounded = tuple(
        (row, detail, detail.get("grounded_production_operation"))
        for row, detail in zip(candidates, details)
        if isinstance(detail.get("grounded_production_operation"), dict))
    abstentions = tuple(
        detail for detail in details
        if not isinstance(detail.get("grounded_production_operation"), dict))
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})
    expected = {
        "fdas_replacement_capacity_grounded_production_operations": (
            len(grounded)),
        "fdas_replacement_capacity_production_model_abstentions": (
            len(abstentions)),
    }
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    allowed_abstention_blockers = frozenset((
        "grounded-production-action-shape-invalid",
        "grounded-production-model-abstained",
        "grounded-production-operation-unavailable",
        "production-completion-beyond-observation-horizon",
        "production-completion-eta-unavailable",
    ))
    checks = {
        "parent_replacement_capacity_audit_passes": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_delayed_non_authorizing_production": (
            declaration.get("capabilities", {}).get(
                "replacement_capacity_production_operation") == "shadow-live"
            and declaration.get(
                "replacement_capacity_production_operation_diagnostic")
            == _DIAGNOSTIC),
        "grounded_operations_are_two_step_delayed_and_shadow_only": all(
            row.get("type") == "operation_candidate_rejected"
            and "delayed-production-completion-unobserved"
                in detail.get("blockers", ())
            and operation.get("step_count") == 2
            and operation.get("queue_selection_is_goal_relief") is False
            and operation.get("policy_authority") is False
            and operation.get("shadow_only") is True
            and isinstance(operation.get("requirement_set_id"), str)
            and bool(operation.get("requirement_set_id"))
            and isinstance(operation.get("resource_claim_count"), int)
            and operation.get("resource_claim_count") >= 1
            for row, detail, operation in grounded),
        "grounded_completion_intervals_fit_declared_horizon": all(
            isinstance(operation.get("completion_eta"), dict)
            and isinstance(operation["completion_eta"].get(
                "earliest_completion_turn"), int)
            and isinstance(operation["completion_eta"].get(
                "latest_completion_turn"), int)
            and operation["completion_eta"]["earliest_completion_turn"]
                <= operation["completion_eta"]["latest_completion_turn"]
            and operation["completion_eta"]["latest_completion_turn"]
                <= int(row.get("turn")) + 64
            for row, _detail, operation in grounded),
        "ungrounded_candidates_fail_closed_with_typed_blockers": all(
            bool(set(detail.get("blockers", ())).intersection(
                allowed_abstention_blockers))
            and detail.get("authority_eligible") is False
            for detail in abstentions),
        "grounded_and_abstained_partition_all_capacity_candidates": (
            len(grounded) + len(abstentions) == len(candidates)),
        "status_and_terminal_counters_match_event_ledger": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected.items()),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "ruleset-grounded delayed replacement-defender production "
            "candidate mechanics, RequirementSet/resource evidence, and "
            "fail-closed abstention only; no completion, goal-relief, action, "
            "score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "capacity_production_candidates": len(candidates),
            "grounded_production_operations": len(grounded),
            "production_model_abstentions": len(abstentions),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
