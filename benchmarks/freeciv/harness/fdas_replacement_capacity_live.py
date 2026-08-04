"""Audit typed replacement-capacity demand in one engine-backed run."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_opportunity_live import (
    audit_fdas_replacement_opportunity_live,
)


_COMPONENT_ID = "fdas-goal-pressure-shadow"
_DEFICIT_PREDICATE = "city-replacement-capacity-deficit"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "candidate_authority": False,
    "policy_authority": False,
    "precondition": "cross-city-critical-reinforcement-without-spare",
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


def audit_fdas_replacement_capacity_live(game_dir, repo=None):
    """Verify live demand/candidate recall without granting authority."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_opportunity_live(game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in ("events.jsonl", "manifest.json", "status.json")}
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    evaluations = tuple(
        row for row in events
        if (row.get("type") == "atomspace_shadow_decision"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    goals = tuple(
        row for row in events
        if (row.get("type") == "goal_instantiated"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID
            and row.get("payload", {}).get("details", {}).get(
                "deficit_predicate") == _DEFICIT_PREDICATE))
    candidates = tuple(
        row for row in events
        if (row.get("type") in (
                "operation_candidate_instantiated",
                "operation_candidate_rejected")
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID
            and row.get("payload", {}).get("details", {}).get(
                "operation_type") == _OPERATION_TYPE))
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})
    expected = {
        "fdas_replacement_capacity_evaluations": len(evaluations),
        "fdas_replacement_capacity_deficit_goals": len(goals),
        "fdas_replacement_capacity_production_candidates": len(candidates),
    }
    evaluation_revisions = frozenset(
        (row.get("payload", {}).get("snapshot_id"),
         row.get("payload", {}).get("revision_id"))
        for row in evaluations)
    capacity_rows = goals + candidates
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    candidate_details = tuple(
        row.get("payload", {}).get("details", {}) for row in candidates)
    checks = {
        "parent_lifecycle_readout_and_opportunity_audits_pass": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_non_authorizing_capacity_demand": (
            declaration.get("capabilities", {}).get(
                "replacement_capacity_demand") == "shadow-live"
            and declaration.get("replacement_capacity_demand_diagnostic")
            == _DIAGNOSTIC),
        "every_capacity_event_is_revision_current": all(
            (row.get("payload", {}).get("snapshot_id"),
             row.get("payload", {}).get("revision_id"))
            in evaluation_revisions for row in capacity_rows),
        "capacity_candidates_are_legal_bound_hash_identified_and_shadow_only": (
            all(
                detail.get("authority_eligible") is False
                and detail.get("legal_bound") is True
                and isinstance(detail.get("candidate_hash"), str)
                and bool(detail.get("candidate_hash"))
                and isinstance(detail.get("action_key"), str)
                and bool(detail.get("action_key"))
                and detail.get("operation_type") == _OPERATION_TYPE
                for detail in candidate_details)),
        "status_and_terminal_counters_match_event_ledger": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected.items()),
        "shadow_evaluation_counter_is_nonzero": len(evaluations) > 0,
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "typed source-city replacement-capacity demand and legal shadow "
            "production-candidate recall only; no production completion, "
            "replacement relation, value, action, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "capacity_deficit_goals": len(goals),
            "capacity_production_candidates": len(candidates),
            "evaluations": len(evaluations),
            "rejected_capacity_candidates": sum(
                row.get("type") == "operation_candidate_rejected"
                for row in candidates),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
