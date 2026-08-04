"""Audit one revision-bound coordinated-replacement why-not funnel."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import FdasReplacementOpportunityFunnel

from .fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
)


_COMPONENT_ID = "fdas-coordinated-replacement-opportunity-funnel"
_READOUT_COMPONENT_ID = "fdas-coordinated-replacement-candidate-readout"
_DIAGNOSTIC = {
    "action_selection_changed": False,
    "blocker_taxonomy": "coordinated-replacement-opportunity-blockers/1.0",
    "policy_authority": False,
    "readout_authority": False,
    "transition_value_estimated": False,
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


def audit_fdas_replacement_opportunity_live(game_dir, repo=None):
    """Verify exhaustive diagnostic staging without policy/value authority."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_readout_live(
        game_dir, repo=repo, require_grounded_pair=False)
    paths = {
        name: os.path.join(game_dir, name)
        for name in ("events.jsonl", "manifest.json", "status.json")}
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    by_id = {row.get("event_id"): row for row in events}
    funnels = tuple(
        row for row in events
        if (row.get("type") == "atomspace_shadow_decision"
            and row.get("payload", {}).get("component_id") == _COMPONENT_ID))
    readouts = tuple(
        row for row in events
        if (row.get("type") == "atomspace_shadow_decision"
            and row.get("payload", {}).get("component_id")
            == _READOUT_COMPONENT_ID))
    parsed = []
    parse_errors = []
    for index, row in enumerate(funnels):
        try:
            parsed.append(FdasReplacementOpportunityFunnel.from_dict(
                row.get("payload", {}).get("details")))
        except (TypeError, ValueError) as exc:
            parse_errors.append("{}:{}".format(index, exc))
    stage_counts = {}
    for value in parsed:
        stage_counts[value.blocker_stage] = (
            stage_counts.get(value.blocker_stage, 0) + 1)
    final = tuple(row for row in events if row.get("type") == "run_completed")
    terminal = (
        final[0].get("payload", {}).get("summary", {})
        if len(final) == 1 else {})
    expected_counters = {
        "fdas_replacement_opportunity_funnel_evaluations": len(parsed),
        "fdas_replacement_opportunity_grounded": stage_counts.get(
            "grounded-pair-available", 0),
        "fdas_replacement_opportunity_no_safe_replacement": stage_counts.get(
            "no-safe-replacement-relation", 0),
    }
    declaration = manifest.get("dependent_atomspace", {}).get("manifest", {})
    readout_revisions = sorted(
        (row.get("payload", {}).get("snapshot_id"),
         row.get("payload", {}).get("revision_id"))
        for row in readouts)
    funnel_revisions = sorted(
        (row.get("payload", {}).get("snapshot_id"),
         row.get("payload", {}).get("revision_id"))
        for row in funnels)
    causal_chain_valid = all(
        len(row.get("caused_by", ())) == 1
        and by_id.get(row["caused_by"][0], {}).get("payload", {}).get(
            "component_id") == _READOUT_COMPONENT_ID
        and by_id[row["caused_by"][0]].get("payload", {}).get("snapshot_id")
        == row.get("payload", {}).get("snapshot_id")
        and by_id[row["caused_by"][0]].get("payload", {}).get("revision_id")
        == row.get("payload", {}).get("revision_id")
        for row in funnels)
    checks = {
        "parent_lifecycle_and_readout_audits_pass": (
            parent["acceptance"]["accepted"]),
        "manifest_freezes_non_authorizing_opportunity_funnel": (
            declaration.get("capabilities", {}).get(
                "coordinated_replacement_opportunity_funnel") == "shadow-live"
            and declaration.get(
                "coordinated_replacement_opportunity_funnel_diagnostic")
            == _DIAGNOSTIC),
        "all_funnel_events_are_typed_hash_valid_and_non_authorizing": (
            bool(funnels) and not parse_errors and len(parsed) == len(funnels)),
        "every_readout_revision_has_exactly_one_funnel": (
            readout_revisions == funnel_revisions),
        "funnel_events_are_causally_bound_to_their_readouts": (
            causal_chain_valid),
        "status_and_terminal_counters_match_funnel_events": all(
            status.get(name) == value and terminal.get(name) == value
            for name, value in expected_counters.items()),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "revision-level coordinated-replacement opportunity staging and "
            "why-not diagnosis only; no transition value, candidate recall, "
            "preference, action, outcome, score, or win-rate claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "parent_audit_hash": parent["structural_hash"],
        "parse_errors": parse_errors,
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "critical_source_garrison_observations": sum(
                value.critical_source_garrison_count for value in parsed),
            "deficit_target_city_observations": sum(
                value.deficit_target_city_count for value in parsed),
            "evaluations": len(parsed),
            "grounded_pairs": sum(value.grounded_pair_count for value in parsed),
            "reinforcement_route_observations": sum(
                value.reinforcement_route_count for value in parsed),
            "safe_replacement_relation_observations": sum(
                value.safe_replacement_relation_count for value in parsed),
            "stage_counts": dict(sorted(stage_counts.items())),
            "structural_join_observations": sum(
                value.structural_source_target_join_count for value in parsed),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
