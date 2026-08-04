"""Audit bounded terminal reproposal for coordinated replacement chains."""

import json
import os

from freeciv_agent.events.schema import structural_hash

from .fdas_replacement_live import _lifecycle_key
from .fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
)


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _event_summary(path):
    count = 0
    completed = ()
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            count += 1
            row = json.loads(line)
            if row.get("type") == "run_completed":
                completed += (row.get("payload", {}).get("summary", {}),)
    return count, completed


def audit_fdas_replacement_reproposal(
        game_dir, repo=None, expected_source_commit=None,
        maximum_operations=80, maximum_events=300000,
        expected_cooldown_turns=32):
    """Verify the PR80 cooldown and its known pathological integration case."""
    game_dir = os.path.abspath(game_dir)
    parent = audit_fdas_replacement_readout_live(game_dir, repo=repo)
    status = _load(os.path.join(game_dir, "status.json"))
    manifest = _load(os.path.join(game_dir, "manifest.json"))
    store = _load(os.path.join(
        game_dir, "fdas-coordinated-replacement-operations.json"))
    event_count, completed = _event_summary(os.path.join(
        game_dir, "events.jsonl"))
    records = tuple(store.get("records", ()))
    keys = tuple(_lifecycle_key(value) for value in records)
    source = manifest.get("source", {})
    suppressions = status.get(
        "fdas_replacement_reproposal_suppressions")
    cooldown_turns = status.get(
        "fdas_replacement_reproposal_cooldown_turns")
    terminal = completed[0] if len(completed) == 1 else {}

    checks = {
        "parent_lifecycle_and_readout_audit_passes": (
            parent["acceptance"]["accepted"]),
        "source_is_clean_and_expected_commit": (
            source.get("dirty") is False
            and (expected_source_commit is None
                 or source.get("commit") == expected_source_commit)),
        "cooldown_is_frozen_in_status_and_terminal_evidence": (
            cooldown_turns == expected_cooldown_turns
            and terminal.get(
                "fdas_replacement_reproposal_cooldown_turns")
            == expected_cooldown_turns),
        "terminal_reproposals_are_observably_suppressed": (
            isinstance(suppressions, int) and suppressions > 0
            and terminal.get(
                "fdas_replacement_reproposal_suppressions")
            == suppressions),
        "durable_operation_count_is_bounded": (
            len(records) <= maximum_operations),
        "event_ledger_count_is_bounded_and_exact": (
            event_count <= maximum_events
            and status.get("event_count") == event_count),
        "grounded_recall_remains_observable": (
            parent["summary"]["grounded_pairs"] > 0),
        "all_persisted_operations_have_logical_keys": (
            all(value is not None for value in keys)),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "bounded terminal-chain reproposal and evidence amplification on "
            "one known pathological seed only; no gameplay performance, "
            "transition value, preference, score, or win-rate claim"),
        "limits": {
            "expected_cooldown_turns": expected_cooldown_turns,
            "maximum_events": maximum_events,
            "maximum_operations": maximum_operations,
        },
        "parent_audit_hash": parent["structural_hash"],
        "schema_version": "1.0",
        "source": source,
        "summary": {
            "event_count": event_count,
            "grounded_pairs": parent["summary"]["grounded_pairs"],
            "logical_key_count": len(set(keys)),
            "operations": len(records),
            "reproposal_cooldown_turns": cooldown_turns,
            "reproposal_suppressions": suppressions,
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
