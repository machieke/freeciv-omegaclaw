"""Audit engine-live FDAS episode induction shadow and quarantine safety."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


ELIGIBLE_OUTCOMES = frozenset((
    "goal-relief-observed",
    "effect-without-goal-relief",
    "no-effect-observed",
))


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


def audit_fdas_induction_live(game_dir, repo=None):
    """Verify live episode encoding can create only quarantined artifacts."""
    game_dir = os.path.abspath(game_dir)
    paths = dict(
        (name, os.path.join(game_dir, name))
        for name in (
            "events.jsonl", "fdas-decision-episodes.json",
            "fdas-induction-ledger.json", "manifest.json", "status.json"))
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing induction evidence: {}".format(
            ", ".join(missing)))
    events = _events(paths["events.jsonl"])
    manifest = _load(paths["manifest.json"])
    status = _load(paths["status.json"])
    episodes = _load(paths["fdas-decision-episodes.json"])
    ledger = _load(paths["fdas-induction-ledger.json"])
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    capabilities = declaration.get("manifest", {}).get("capabilities", {})
    episode_rows = tuple(episodes.get("episodes", ()))
    eligible = tuple(
        row for row in episode_rows
        if row.get("outcome_status") in ELIGIBLE_OUTCOMES)
    latency = tuple(
        row for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name")
            == "fdas_episode_induction_latency_ms"))
    quarantined_events = tuple(
        row for row in events if row["type"] == "induced_rule_quarantined")
    promoted_events = tuple(
        row for row in events if row["type"] == "induced_rule_promoted")
    demoted_events = tuple(
        row for row in events if row["type"] == "induced_rule_demoted")
    rule_validations = tuple(
        row for row in events if row["type"] == "rule_validated")
    actions = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    proposals = ledger.get("proposals", {})
    validations = ledger.get("validations", {})
    ledger_material = dict(ledger)
    claimed_ledger_hash = ledger_material.pop("state_hash", None)
    accepted_labels = sum(
        int(row["payload"].get("labels", {}).get(
            "accepted_encodings", "0")) for row in latency)
    abstained_labels = sum(
        int(row["payload"].get("labels", {}).get(
            "abstained_encodings", "0")) for row in latency)
    quarantine_details = tuple(
        row["payload"].get("details", {}) for row in quarantined_events)
    checks = {
        "actions_are_complete_and_accepted": (
            bool(actions)
            and len(actions) == len(results) == status.get("engine_actions")
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "activation_is_manifest_bound_shadow_induction": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_defense_induction_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_defense_induction_shadow.json"
            and config.get("learning", {}).get(
                "episode_attribution_enabled") is True
            and config.get("learning", {}).get(
                "contextual_conductance_enabled") is True
            and config.get("learning", {}).get("induction_enabled") is True
            and config.get("learning", {}).get(
                "induced_rule_readout_enabled") is False
            and capabilities.get("episode_induction_bridge") == "shadow-live"
            and capabilities.get("quarantined_contextual_induction")
            == "shadow-live"
            and capabilities.get("induced_rule_heldout_gate")
            == "component-only"),
        "durable_episode_population_is_attributable": (
            episodes.get("quarantine_reason") is None
            and len(eligible) >= 2
            and status.get("fdas_induction_episodes_encoded")
            == len(eligible)
            and accepted_labels == len(eligible)),
        "induction_evaluations_are_causal_and_bounded": (
            bool(latency)
            and all(row.get("caused_by") for row in latency)
            and max(row["payload"]["value"] for row in latency) <= 250.0
            and all(
                row["payload"].get("labels", {}).get("policy_authority")
                == "False"
                and row["payload"].get("labels", {}).get("truth_mutated")
                == "False"
                for row in latency)),
        "ledger_is_hash_valid_and_quarantine_only": (
            claimed_ledger_hash == structural_hash(ledger_material)
            and all(row.get("status") == "quarantined"
                    for row in proposals.values())
            and not validations
            and status.get("fdas_induction_promoted_rules") == 0),
        "proposal_events_match_durable_quarantine": (
            len(quarantined_events) == len(proposals)
            == status.get("fdas_induction_proposals_quarantined")
            and all(
                row.get("status") == "quarantined"
                and row.get("policy_authority") is False
                and row.get("truth_mutated") is False
                and row.get("proposal_id") in proposals
                for row in quarantine_details)),
        "no_holdout_or_promotion_is_fabricated": (
            not promoted_events and not demoted_events and not rule_validations
            and status.get("fdas_induction_promoted_rules") == 0),
        "status_encoding_counters_match_events": (
            status.get("fdas_induction_episode_abstentions")
            == abstained_labels
            and status.get("fdas_induction_duplicate_proposals", 0) >= 0),
        "source_is_clean_and_horizon_completed": (
            manifest.get("source", {}).get("dirty") is False
            and status.get("completed") is True
            and status.get("horizon_reached") is True),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "claim_scope": (
            "live durable defense episodes encoded into bounded induction, "
            "independence/residual gates, durable quarantine, and zero rule "
            "readout; no held-out promotion, induced-rule authority, score, "
            "or gameplay-improvement claim"),
        "evidence": dict(
            (name, {"path": _logical(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "schema_version": "1.0",
        "source": manifest.get("source"),
        "summary": {
            "accepted_actions": sum(
                row["payload"].get("status") == "accepted" for row in results),
            "attributable_episodes": len(eligible),
            "induction_evaluations": len(latency),
            "maximum_induction_latency_ms": max(
                (row["payload"]["value"] for row in latency), default=None),
            "proposals_quarantined": len(proposals),
            "rules_promoted": status.get("fdas_induction_promoted_rules"),
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
