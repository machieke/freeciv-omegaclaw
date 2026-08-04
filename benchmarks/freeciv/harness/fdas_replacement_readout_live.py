"""Audit grounded coordinated-replacement candidate recall in one live run."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_live import audit_fdas_replacement_live


_COMPONENT_ID = "fdas-coordinated-replacement-candidate-readout"
_IDENTITY = "fdas-coordinated-replacement-candidate-readout/1.0"


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


def _hash_valid(value):
    material = dict(value)
    claimed = material.pop("result_hash", None)
    return isinstance(claimed, str) and claimed == structural_hash(material)


def audit_fdas_replacement_readout_live(
        game_dir, repo=None, require_grounded_pair=True):
    """Verify real safe-chain recall with no transition-value assertion."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_live(game_dir, repo=repo)
    paths = {
        name: os.path.join(game_dir, name)
        for name in (
            "events.jsonl", "fdas-coordinated-replacement-operations.json",
            "manifest.json", "status.json")}
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    store = _load(paths["fdas-coordinated-replacement-operations.json"])
    records = {
        row["spec"]["operation_id"]: row for row in store.get("records", ())}
    readout_events = tuple(
        row for row in events
        if (row.get("type") == "atomspace_shadow_decision"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    details = tuple(row["payload"]["details"] for row in readout_events)
    pairs = tuple(pair for detail in details for pair in detail.get("pairs", ()))
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0]["payload"].get("summary", {}) if len(final) == 1 else {})
    expected = {
        "fdas_replacement_readout_abstentions": sum(
            detail.get("status") == "abstained" for detail in details),
        "fdas_replacement_readout_candidates": sum(
            detail.get("replacement_candidate_count", 0) for detail in details),
        "fdas_replacement_readout_direct_controls": sum(
            detail.get("direct_candidate_count", 0) for detail in details),
        "fdas_replacement_readout_evaluations": len(details),
        "fdas_replacement_readout_grounded_pairs": len(pairs),
        "fdas_replacement_readout_rejections": sum(
            len(detail.get("rejected", ())) for detail in details),
    }
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    diagnostic = declaration.get(
        "coordinated_replacement_candidate_readout_diagnostic", {})
    pair_valid = all(
        pair.get("safe_chain_grounded") is True
        and pair.get("direct_unsafe_reason") == "protected-source-garrison"
        and pair.get("lifecycle_operation_id") in records
        and pair.get("combined_estimated_turns")
        == pair.get("replacement_estimated_turns")
        + pair.get("reinforcement_estimated_turns")
        and pair.get("combined_movement_cost")
        == pair.get("replacement_movement_cost")
        + pair.get("reinforcement_movement_cost")
        and _hash_valid(pair)
        for pair in pairs)
    checks = {
        "parent_replacement_lifecycle_audit_passes": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_non_authorizing_grounded_recall": (
            declaration.get("capabilities", {}).get(
                "coordinated_replacement_candidate_readout") == "shadow-live"
            and diagnostic == {
                "action_selection_changed": False,
                "combined_native_route_grounding_required": True,
                "direct_control_semantics": (
                    "protected-source-garrison-direct-move"),
                "policy_authority": False,
                "readout_authority": False,
                "transition_value_estimated": False,
                "truth_mutated": False,
            }),
        "readout_events_are_revision_current_and_non_authorizing": (
            (bool(details) or not require_grounded_pair) and all(
                row["payload"].get("snapshot_id")
                == detail.get("snapshot_id")
                and row["payload"].get("revision_id")
                == detail.get("revision_id")
                and detail.get("identity") == _IDENTITY
                and detail.get("action_selection_changed") is False
                and detail.get("policy_authority") is False
                and detail.get("readout_authority") is False
                and detail.get("transition_value_estimated") is False
                and detail.get("truth_mutated") is False
                and _hash_valid(detail)
                for row, detail in zip(readout_events, details))),
        "at_least_one_grounded_safe_chain_is_recalled": (
            bool(pairs) if require_grounded_pair else True),
        "pair_routes_and_lifecycle_references_are_exact": pair_valid,
        "status_and_terminal_counters_match_readout_events": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected.items()),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "known-seed grounded recall of a protected two-step replacement "
            "chain only; no transition value, preference, action, outcome, "
            "score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "abstentions": expected[
                "fdas_replacement_readout_abstentions"],
            "direct_candidates": expected[
                "fdas_replacement_readout_direct_controls"],
            "evaluations": len(details),
            "grounded_pairs": len(pairs),
            "rejections": expected[
                "fdas_replacement_readout_rejections"],
            "replacement_candidates": expected[
                "fdas_replacement_readout_candidates"],
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
