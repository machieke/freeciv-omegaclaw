"""Diagnose decomposed consequences of one completed replacement chain."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import FdasReplacementChainOutcomeLabel

from .fdas_replacement_execution_live import (
    audit_fdas_replacement_execution_live,
)


PR82_REPORT_STRUCTURAL_HASH = (
    "d5e51d12f87d5ab6ee656977dc80e7ea2df96bccb16781b075beb15b3264d3ea")


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


def _required_lifecycle_value(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("replacement consequence {} is required".format(name))
    return value


def replacement_chain_consequence(assignment, label, lifecycle_events):
    """Return an unweighted city/actor consequence vector."""
    if not isinstance(assignment, dict):
        raise TypeError("replacement consequence assignment is invalid")
    if not isinstance(label, dict):
        raise TypeError("replacement consequence label is invalid")
    parsed_label = FdasReplacementChainOutcomeLabel.from_dict(label)
    if (parsed_label.status != "observed"
            or parsed_label.observed_turn is None
            or parsed_label.outcome is None):
        raise ValueError("replacement consequence requires observed label")
    if (assignment.get("operation_id") != parsed_label.operation_id
            or assignment.get("operation_spec_digest")
            != parsed_label.operation_spec_digest
            or assignment.get("replacement_actor_id")
            != parsed_label.replacement_actor_id
            or assignment.get("reinforcement_actor_id")
            != parsed_label.reinforcement_actor_id
            or assignment.get("source_city_id")
            != parsed_label.source_city_id
            or assignment.get("target_city_id")
            != parsed_label.target_city_id):
        raise ValueError("replacement consequence identity differs")
    observed = dict(parsed_label.observed_value)
    completion_turn = int(parsed_label.completion_turn)
    observed_turn = int(parsed_label.observed_turn)
    rows = tuple(
        row for row in lifecycle_events
        if (isinstance(row, dict)
            and row.get("type") == "unit_lifecycle"
            and completion_turn < int(row.get("turn", -1)) <= observed_turn))
    actors = []
    for role, actor_id, present_key, placement_key, transport_key in (
            ("replacement", parsed_label.replacement_actor_id,
             "replacement_present", "replacement_at_source",
             "replacement_nontransported"),
            ("reinforcement", parsed_label.reinforcement_actor_id,
             "reinforcement_present", "reinforcement_at_target",
             "reinforcement_nontransported")):
        present = observed.get(present_key)
        placed = observed.get(placement_key)
        nontransported = observed.get(transport_key)
        if not all(isinstance(value, bool) for value in (
                present, placed, nontransported)):
            raise ValueError("replacement consequence label vector is invalid")
        actor_rows = tuple(
            row for row in rows
            if row.get("payload", {}).get("unit_id") == actor_id)
        disappeared = tuple(
            row for row in actor_rows
            if row.get("payload", {}).get("transition") == "disappeared")
        if present:
            if disappeared and not any(
                    row.get("payload", {}).get("transition") == "appeared"
                    and row.get("turn", -1) > disappeared[-1].get("turn", -1)
                    for row in actor_rows):
                raise ValueError(
                    "present replacement actor has unresolved disappearance")
            removal = None
        else:
            if len(disappeared) != 1:
                raise ValueError(
                    "absent replacement actor lacks one disappearance")
            row = disappeared[0]
            payload = row.get("payload", {})
            if any(
                    value.get("payload", {}).get("transition") == "appeared"
                    and value.get("turn", -1) > row.get("turn", -1)
                    for value in actor_rows):
                raise ValueError(
                    "absent replacement actor reappeared before observation")
            evidence_event_ids = tuple(payload.get("evidence_event_ids", ()))
            if (not row.get("caused_by") or not evidence_event_ids
                    or any(not isinstance(value, str) or not value
                           for value in evidence_event_ids)):
                raise ValueError(
                    "replacement disappearance lacks causal evidence")
            removal = {
                "cause": _required_lifecycle_value(
                    payload.get("cause"), "removal cause"),
                "detail": _required_lifecycle_value(
                    payload.get("detail"), "removal detail"),
                "evidence_event_ids": list(evidence_event_ids),
                "evidence_quality": _required_lifecycle_value(
                    payload.get("evidence_quality"), "evidence quality"),
                "event_id": _required_lifecycle_value(
                    row.get("event_id"), "removal event ID"),
                "last_position": payload.get("last_position"),
                "lifecycle_id": _required_lifecycle_value(
                    payload.get("lifecycle_id"), "lifecycle ID"),
                "turn": int(row["turn"]),
                "unit_type": _required_lifecycle_value(
                    payload.get("unit_type"), "unit type"),
            }
        actors.append({
            "actor_id": actor_id,
            "nontransported": nontransported,
            "placement_satisfied": placed,
            "present": present,
            "removal": removal,
            "role": role,
        })
    cities = {
        "source_city_retained": observed.get(
            "source_city_owned_and_present"),
        "target_city_retained": observed.get(
            "target_city_owned_and_present"),
    }
    if not all(isinstance(value, bool) for value in cities.values()):
        raise ValueError("replacement consequence city vector is invalid")
    value = {
        "actors": actors,
        "cities": cities,
        "completion_turn": completion_turn,
        "durability_outcome": parsed_label.outcome,
        "durability_reason": parsed_label.reason,
        "label_id": parsed_label.label_id,
        "observed_turn": observed_turn,
        "operation_id": parsed_label.operation_id,
        "summary": {
            "assigned_actor_survival_count": sum(
                row["present"] for row in actors),
            "city_retention_count": sum(cities.values()),
            "exact_combat_attributed_loss_count": sum(
                row["removal"] is not None
                and row["removal"]["evidence_quality"] == "exact"
                and row["removal"]["cause"].startswith("combat_")
                for row in actors),
        },
    }
    value["result_hash"] = structural_hash(value)
    return value


def audit_fdas_replacement_consequence(
        game_dir, parent_report_path, repo=None,
        expected_source_commit=None):
    """Audit the retrospective consequence vector against frozen PR82."""
    game_dir = os.path.abspath(game_dir)
    parent_report_path = os.path.abspath(parent_report_path)
    parent_report = _load(parent_report_path)
    reproduced_parent = audit_fdas_replacement_execution_live(
        game_dir, repo=repo, expected_source_commit=expected_source_commit)
    names = (
        "events.jsonl", "fdas-coordinated-replacement-execution.json",
        "fdas-coordinated-replacement-outcome-labels.json", "manifest.json",
        "status.json")
    paths = dict((name, os.path.join(game_dir, name)) for name in names)
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing replacement consequence evidence: {}".format(
            ", ".join(missing)))
    events = _events(paths["events.jsonl"])
    execution_store = _load(
        paths["fdas-coordinated-replacement-execution.json"])
    outcome_store = _load(
        paths["fdas-coordinated-replacement-outcome-labels.json"])
    assignment = execution_store.get("assignment")
    labels = tuple(
        row for row in outcome_store.get("labels", ())
        if assignment is not None
        and row.get("operation_id") == assignment.get("operation_id"))
    if len(labels) != 1:
        raise ValueError("replacement consequence requires one matching label")
    consequence = replacement_chain_consequence(
        assignment, labels[0], events)
    actor_rows = consequence["actors"]
    city_rows = consequence["cities"]
    checks = {
        "frozen_parent_report_is_reproduced": bool(
            parent_report.get("acceptance", {}).get("accepted") is True
            and reproduced_parent.get("acceptance", {}).get("accepted") is True
            and parent_report.get("structural_hash")
            == PR82_REPORT_STRUCTURAL_HASH
            and reproduced_parent.get("structural_hash")
            == PR82_REPORT_STRUCTURAL_HASH),
        "assignment_and_observed_label_match_exactly": bool(
            consequence["operation_id"] == assignment.get("operation_id")
            and consequence["durability_outcome"]
            == labels[0].get("outcome")
            and consequence["durability_reason"] == labels[0].get("reason")),
        "absent_actors_have_exact_first_removal_evidence": all(
            row["present"] or (
                row["removal"] is not None
                and row["removal"]["evidence_quality"] == "exact")
            for row in actor_rows),
        "component_counts_reconcile": bool(
            consequence["summary"]["assigned_actor_survival_count"]
            == sum(row["present"] for row in actor_rows)
            and consequence["summary"]["city_retention_count"]
            == sum(city_rows.values())),
        "diagnostic_does_not_relabel_or_score": bool(
            consequence["durability_outcome"] is False
            and "utility" not in consequence
            and "score" not in consequence
            and "preferred_action" not in consequence),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "retrospective decomposition of one known-seed negative label; "
            "no relabel, scalar utility, causal effect, policy, score, or "
            "win-rate claim"),
        "consequence": consequence,
        "evidence": {
            **dict(
                (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
                for name, path in sorted(paths.items())),
            "parent_report": {
                "path": _logical(parent_report_path, repo),
                "sha256": _sha256(parent_report_path),
            },
        },
        "parent_report_hash": PR82_REPORT_STRUCTURAL_HASH,
        "schema_version": "1.0",
        "source": _load(paths["manifest.json"]).get("source"),
    }
    report["structural_hash"] = structural_hash(report)
    return report
