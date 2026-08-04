"""Audit exact-match replacement-capacity production lifecycle evidence."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_production_live import (
    audit_fdas_replacement_capacity_production_live,
)


_MECHANISM = "fdas-replacement-capacity-production-lifecycle"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "candidate_authority": False,
    "match_semantics": (
        "exactly-one-grounded-candidate-matches-existing-policy-action"),
    "observation_authority": "later-authoritative-snapshot",
    "policy_authority": False,
    "queue_acceptance_separate_from_product_observation": True,
    "truth_mutated": False,
}
_COUNTERS = (
    "fdas_replacement_capacity_lifecycle_match_evaluations",
    "fdas_replacement_capacity_lifecycle_exact_matches",
    "fdas_replacement_capacity_lifecycle_no_matches",
    "fdas_replacement_capacity_lifecycle_ambiguous_matches",
    "fdas_replacement_capacity_lifecycle_operations_registered",
    "fdas_replacement_capacity_lifecycle_queue_acceptances",
    "fdas_replacement_capacity_lifecycle_queue_observations",
    "fdas_replacement_capacity_lifecycle_product_observations",
    "fdas_replacement_capacity_lifecycle_terminal_failures",
)


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


def audit_fdas_replacement_capacity_production_lifecycle_live(
        game_dir, repo=None):
    """Verify selected-action matching and delayed observation stay separate."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_production_live(
        game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in ("events.jsonl", "manifest.json", "status.json")
    }
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    completed = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        completed[0].get("payload", {}).get("summary", {})
        if len(completed) == 1 else {})
    lifecycle = tuple(
        row for row in events
        if row.get("payload", {}).get("mechanism") == _MECHANISM)
    proposals = tuple(
        row for row in lifecycle if row.get("type") == "operation_proposed")
    queue_acceptances = tuple(
        row for row in lifecycle
        if row.get("type") == "operation_step_committed")
    queue_observations = tuple(
        row for row in lifecycle
        if (row.get("type") == "operation_step_revalidated"
            and row.get("payload", {}).get("reason_code") ==
            "queue-target-observed-awaiting-product"))
    products = tuple(
        row for row in lifecycle if row.get("type") == "operation_completed")
    failures = tuple(
        row for row in lifecycle
        if row.get("type") in (
            "operation_failed", "operation_abandoned", "operation_expired"))
    event_counts = {
        "fdas_replacement_capacity_lifecycle_operations_registered":
            len(proposals),
        "fdas_replacement_capacity_lifecycle_queue_acceptances":
            len(queue_acceptances),
        "fdas_replacement_capacity_lifecycle_queue_observations":
            len(queue_observations),
        "fdas_replacement_capacity_lifecycle_product_observations":
            len(products),
        "fdas_replacement_capacity_lifecycle_terminal_failures":
            len(failures),
    }
    declared = manifest.get("dependent_atomspace", {}).get("manifest", {})
    operation_ids = tuple(
        row.get("payload", {}).get("operation_id") for row in proposals)
    proposal_by_id = {
        row.get("payload", {}).get("operation_id"): row for row in proposals}
    checks = {
        "parent_grounded_production_audit_passes": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_exact_non_authorizing_lifecycle": (
            declared.get("capabilities", {}).get(
                "replacement_capacity_production_lifecycle") == "shadow-live"
            and declared.get(
                "replacement_capacity_production_lifecycle_diagnostic")
            == _DIAGNOSTIC),
        "match_outcomes_partition_every_evaluation": (
            status.get(_COUNTERS[0]) ==
            status.get(_COUNTERS[1], 0)
            + status.get(_COUNTERS[2], 0)
            + status.get(_COUNTERS[3], 0)),
        "exact_matches_bound_registration_without_forcing_yield": (
            status.get(_COUNTERS[1], 0) >= len(proposals)),
        "lifecycle_event_counters_match_status_and_terminal": all(
            status.get(name) == count and terminal.get(name) == count
            for name, count in event_counts.items()),
        "all_match_counters_match_terminal": all(
            status.get(name) == terminal.get(name)
            for name in _COUNTERS[:4]),
        "operation_proposals_are_unique": (
            all(isinstance(value, str) and value for value in operation_ids)
            and len(operation_ids) == len(set(operation_ids))),
        "proposals_preserve_exact_match_zero_relief_contract": all(
            row.get("payload", {}).get("operation_type") == _OPERATION_TYPE
            and row["payload"].get("policy_authority") is False
            and row["payload"].get("shadow_only") is True
            and row["payload"].get("expected_prevented_loss") == 0.0
            and "domain_estimate_request_id" not in row["payload"]
            and isinstance(row["payload"].get("requirement_set"), dict)
            and bool(row["payload"].get("claims"))
            and "legacy-selected-action-byte-exact-match"
                in row["payload"].get("provenance", ())
            and "queue-acceptance-is-not-product-observation"
                in row["payload"].get("provenance", ())
            and "zero-immediate-capacity-goal-relief"
                in row["payload"].get("provenance", ())
            for row in proposals),
        "all_lifecycle_events_remain_shadow_and_non_authorizing": all(
            row.get("payload", {}).get("policy_authority") is False
            and row.get("payload", {}).get("shadow_only") is True
            for row in lifecycle),
        "product_observation_is_later_authoritative_resolution": all(
            isinstance(row.get("payload", {}).get("product_ref"), str)
            and row["payload"].get("resolution_status") == "resolved_success"
            and row["payload"].get("resolution_snapshot_id") !=
                proposal_by_id.get(
                    row["payload"].get("operation_id"), {})
                .get("payload", {}).get("snapshot_id")
            for row in products),
        "queue_acceptance_and_product_observation_are_distinct_events": (
            not set(row.get("event_id") for row in queue_acceptances)
            .intersection(row.get("event_id") for row in products)),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "exact matching of an unchanged existing-policy production action "
            "to one grounded replacement-capacity operation, engine queue "
            "acceptance, and later authoritative product observation only; "
            "no candidate, policy, action, relief, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "ambiguous_matches": status.get(_COUNTERS[3], 0),
            "exact_matches": status.get(_COUNTERS[1], 0),
            "match_evaluations": status.get(_COUNTERS[0], 0),
            "no_matches": status.get(_COUNTERS[2], 0),
            "operations_registered": len(proposals),
            "product_observations": len(products),
            "queue_acceptances": len(queue_acceptances),
            "queue_observations": len(queue_observations),
            "terminal_failures": len(failures),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
