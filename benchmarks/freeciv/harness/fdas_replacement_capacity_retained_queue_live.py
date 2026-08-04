"""Audit PF-selected replacement-capacity queues already in production."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_capacity_production_lifecycle_live import (
    audit_fdas_replacement_capacity_production_lifecycle_live,
)


_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "candidate_authority": False,
    "match_semantics": (
        "pressure-selected-grounded-candidate-matches-current-authoritative-"
        "queue"),
    "no_queue_action_submitted": True,
    "observation_authority": "later-authoritative-snapshot",
    "policy_authority": False,
    "single_pressure_selected_operation_required": True,
    "truth_mutated": False,
}
_COUNTERS = (
    "fdas_replacement_retained_queue_lifecycle_evaluations",
    "fdas_replacement_retained_queue_lifecycle_selected_matches",
    "fdas_replacement_retained_queue_lifecycle_no_matches",
    "fdas_replacement_retained_queue_lifecycle_ambiguous_matches",
    "fdas_replacement_retained_queue_lifecycle_operations_registered",
    "fdas_replacement_retained_queue_lifecycle_queue_observations",
    "fdas_replacement_retained_queue_lifecycle_product_observations",
    "fdas_replacement_retained_queue_lifecycle_terminal_failures",
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


def audit_fdas_replacement_capacity_retained_queue_live(game_dir, repo=None):
    """Verify one current PF-selected queue is only observed, never submitted."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_capacity_production_lifecycle_live(
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
    queue_observations = tuple(
        row for row in lifecycle
        if (row.get("type") == "operation_step_revalidated"
            and row.get("payload", {}).get("reason_code") ==
            "queue-was-already-selected"))
    products = tuple(
        row for row in lifecycle if row.get("type") == "operation_completed")
    failures = tuple(
        row for row in lifecycle
        if row.get("type") in (
            "operation_failed", "operation_abandoned", "operation_expired"))
    commits = tuple(
        row for row in lifecycle
        if row.get("type") == "operation_step_committed")
    event_counts = {
        _COUNTERS[4]: len(proposals),
        _COUNTERS[5]: len(queue_observations),
        _COUNTERS[6]: len(products),
        _COUNTERS[7]: len(failures),
    }
    declared = manifest.get("dependent_atomspace", {}).get("manifest", {})
    proposal_ids = tuple(
        row.get("payload", {}).get("operation_id") for row in proposals)
    observation_ids = tuple(
        row.get("payload", {}).get("operation_id")
        for row in queue_observations)
    product_ids = set(
        row.get("payload", {}).get("operation_id") for row in products)
    failure_ids = set(
        row.get("payload", {}).get("operation_id") for row in failures)
    terminal_ids = product_ids.union(failure_ids)
    checks = {
        "parent_selected_action_lifecycle_audit_passes": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_selected_retained_queue_observation": (
            declared.get("capabilities", {}).get(
                "replacement_capacity_retained_queue_lifecycle")
            == "shadow-live"
            and declared.get(
                "replacement_capacity_retained_queue_lifecycle_diagnostic")
            == _DIAGNOSTIC),
        "match_outcomes_partition_every_shadow_evaluation": (
            status.get(_COUNTERS[0]) ==
            status.get(_COUNTERS[1], 0)
            + status.get(_COUNTERS[2], 0)
            + status.get(_COUNTERS[3], 0)),
        "selected_matches_bound_registration_without_forcing_yield": (
            status.get(_COUNTERS[1], 0) >= len(proposals)),
        "event_counters_match_status_and_terminal": all(
            status.get(name) == count and terminal.get(name) == count
            for name, count in event_counts.items()),
        "match_counters_match_terminal": all(
            status.get(name) == terminal.get(name) for name in _COUNTERS[:4]),
        "operation_and_queue_observation_identity_is_one_to_one": (
            len(proposal_ids) == len(set(proposal_ids))
            and sorted(proposal_ids) == sorted(observation_ids)),
        "every_terminal_identity_is_unique_and_registered": (
            len(products) == len(product_ids)
            and len(failures) == len(failure_ids)
            and not product_ids.intersection(failure_ids)
            and terminal_ids.issubset(set(proposal_ids))),
        "proposals_are_current_selected_queue_zero_relief_observers": all(
            row.get("payload", {}).get("operation_type") == _OPERATION_TYPE
            and row["payload"].get("policy_authority") is False
            and row["payload"].get("shadow_only") is True
            and row["payload"].get("expected_prevented_loss") == 0.0
            and "domain_estimate_request_id" not in row["payload"]
            and isinstance(row["payload"].get("requirement_set"), dict)
            and bool(row["payload"].get("claims"))
            and "pressure-selected-operation-exact-match"
                in row["payload"].get("provenance", ())
            and "current-authoritative-queue-byte-exact-match"
                in row["payload"].get("provenance", ())
            and "no-queue-action-submitted"
                in row["payload"].get("provenance", ())
            and "zero-immediate-capacity-goal-relief"
                in row["payload"].get("provenance", ())
            for row in proposals),
        "retained_queue_never_emits_action_commit": not commits,
        "all_lifecycle_events_remain_shadow_and_non_authorizing": all(
            row.get("payload", {}).get("policy_authority") is False
            and row.get("payload", {}).get("shadow_only") is True
            for row in lifecycle),
        "product_completion_is_later_authoritative_identity": all(
            isinstance(row.get("payload", {}).get("product_ref"), str)
            and row["payload"].get("resolution_status") == "resolved_success"
            for row in products),
        "queue_divergence_is_single_terminal_abandonment": all(
            row.get("payload", {}).get("reason_code") !=
                "production-target-diverged-before-product-observation"
            or row.get("type") == "operation_abandoned"
            for row in lifecycle),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "PF-selected grounded replacement-capacity operations whose exact "
            "queue was already authoritative, plus later product completion "
            "or terminal divergence; no submitted action, relief, policy, "
            "score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "ambiguous_matches": status.get(_COUNTERS[3], 0),
            "evaluations": status.get(_COUNTERS[0], 0),
            "no_matches": status.get(_COUNTERS[2], 0),
            "operations_registered": len(proposals),
            "product_observations": len(products),
            "queue_observations": len(queue_observations),
            "selected_matches": status.get(_COUNTERS[1], 0),
            "terminal_failures": len(failures),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
