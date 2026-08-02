"""Deterministic audit for paired FDAS observation-pressure shadow evidence."""

import hashlib
import json
import os

from freeciv_agent.events.schema import structural_hash


COHORT = "fdas_observation_pressure_shadow_diagnostic_v1"
MECHANISM = "fdas-observation-pressure-shadow/1.0"


def _load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _load_events(path):
    with open(path, encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _logical_path(path, repo=None):
    absolute = os.path.abspath(path)
    if repo is not None:
        relative = os.path.relpath(absolute, os.path.abspath(repo))
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    return absolute


def _arm_directory(root, arm):
    arm_root = os.path.join(
        root, "games", "impact_pair", COHORT, arm, "e_full_loop")
    candidates = []
    if os.path.isdir(arm_root):
        for name in sorted(os.listdir(arm_root)):
            path = os.path.join(arm_root, name)
            if os.path.isfile(os.path.join(path, "manifest.json")):
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(
            "expected exactly one {} game, found {}".format(
                arm, len(candidates)))
    return candidates[0]


def _latency(events, name):
    values = tuple(
        float(row["payload"]["value"])
        for row in events
        if (row["type"] == "metric_sample"
            and row["payload"].get("name") == name))
    return {
        "count": len(values),
        "maximum_ms": max(values) if values else None,
    }


def _audit_arm(root, arm, repo=None):
    game_dir = _arm_directory(root, arm)
    paths = dict(
        (name, os.path.join(game_dir, name))
        for name in ("events.jsonl", "manifest.json", "status.json"))
    missing = tuple(name for name, path in paths.items()
                    if not os.path.isfile(path))
    if missing:
        raise ValueError("missing {} evidence: {}".format(
            arm, ", ".join(missing)))
    events = _load_events(paths["events.jsonl"])
    by_id = dict((row["event_id"], row) for row in events)
    manifest = _load_json(paths["manifest.json"])
    status = _load_json(paths["status.json"])
    declaration = manifest.get("dependent_atomspace", {})
    config = declaration.get("config", {})
    capability_manifest = declaration.get("manifest", {})
    packets = tuple(
        row for row in events
        if (row["type"] == "packet_reserved"
            and row["payload"].get("summary", {}).get("mechanism")
            == MECHANISM))
    pressure = tuple(
        row for row in events
        if (row["type"] == "pressure_propagated"
            and row["payload"].get("config", {}).get("mechanism")
            == MECHANISM))
    scored = tuple(row for row in events if row["type"] == "operation_scored")
    sent = tuple(row for row in events if row["type"] == "action_sent")
    results = tuple(row for row in events if row["type"] == "action_result")
    authority = tuple(
        row for row in events
        if row["type"] == "atomspace_authority_decision")
    selected_evidence = tuple(
        row for row in events
        if (row["type"] == "observation"
            and row["payload"].get("selection_policy") is not None))
    summary = packets[0]["payload"]["summary"] if len(packets) == 1 else {}
    packet_schedule = summary.get("packet_schedule", {})
    accounting = packet_schedule.get("accounting", {})
    information = summary.get("information_values", [])
    information_value = information[0] if len(information) == 1 else {}
    analysis = (
        information_value.get("bounded_decision_analysis", {})
        if len(information) == 1 else {})
    test = information_value.get("test", {})
    model = test.get("model_provenance", {})
    selections = summary.get("selection_records", [])
    selected_ids = summary.get("selected_operation_ids", [])
    packet_parent = (
        by_id.get(packets[0]["caused_by"][0])
        if len(packets) == 1 and len(packets[0].get("caused_by", ())) == 1
        else None)
    pressure_parent = (
        by_id.get(packet_parent["caused_by"][0])
        if packet_parent is not None
        and len(packet_parent.get("caused_by", ())) == 1 else None)
    beliefs = manifest.get("beliefs", {})
    planning_latency = _latency(
        events, "fdas_observation_pressure_latency_ms")
    checks = {
        "action_results_are_complete_and_accepted": (
            bool(sent) and len(sent) == len(results)
            == status.get("engine_actions")
            and all(row["payload"].get("status") == "accepted"
                    for row in results)
            and status.get("rejected_actions") == 0),
        "bounded_decision_can_change": (
            analysis.get("decision_sensitive") is True
            and 0.0 < analysis.get("decision_change_probability", 0.0) <= 1.0
            and any(row.get("changes_decision")
                    for row in analysis.get("outcomes", ()))
            and test.get("decision_sensitivity")
            == analysis.get("decision_change_probability")
            and information_value.get("expected_information_gain", 0.0) > 0.0),
        "causal_pressure_score_packet_chain_is_complete": (
            len(pressure) == len(packets) == 1
            and packet_parent is not None
            and packet_parent.get("type") == "operation_scored"
            and pressure_parent == pressure[0]),
        "evidence_firewall_remained_closed": (
            summary.get("evidence_write_authorized") is False
            and summary.get("truth_mutated") is False
            and summary.get("evidence_registration_status")
            == "awaiting-authoritative-return"
            and summary.get("evidence_count_before_planning")
            == summary.get("evidence_count_after_planning")
            and summary.get("evidence_store_hash_before_planning")
            == summary.get("evidence_store_hash_after_planning")
            and not selected_evidence),
        "manifest_binds_shadow_only_activation": (
            declaration.get("config_source")
            == "profile/dependent_atomspace_observation_pressure_shadow.yaml"
            and declaration.get("manifest_source")
            == "profile/fdas_manifest_observation_pressure_shadow.json"
            and config.get("enabled") is True
            and config.get("shadow_enabled") is True
            and config.get("authority_enabled") is False
            and config.get("projection", {}).get("beliefs") is True
            and config.get("inference", {}).get(
                "uncertain_assessment_enabled") is True
            and capability_manifest.get("policy_authority") is False
            and capability_manifest.get("capabilities", {}).get(
                "belief_domain_projection") == "shadow-live"
            and capability_manifest.get("capabilities", {}).get(
                "observation_pressure_planning") == "shadow-live"),
        "packet_commit_is_atomic_and_conserved": (
            packet_schedule.get("conserved") is True
            and len(selected_ids) == 1
            and packet_schedule.get("committed_operation_ids") == selected_ids
            and accounting.get("cpu", {}).get("consumed") == 1
            and accounting.get("observation", {}).get("consumed") == 1
            and len(selections) == 1
            and selections[0].get("selected") is True),
        "selection_widening_and_model_cap_are_recorded": (
            summary.get("selection_effect_widening", {}).get("propensity")
            is None
            and summary.get("selection_effect_widening", {}).get("status")
            == "required-on-authoritative-return"
            and summary.get("selection_effect_widening", {}).get(
                "configured_unknown_propensity_discount")
            == beliefs.get("selection_unknown_discount")
            and model.get("source_kind") == "simulator"
            and model.get("exact") is False
            and model.get("confidence_cap")
            == beliefs.get("simulation_confidence_cap")),
        "no_policy_or_action_authority": (
            summary.get("policy_authority") is False
            and summary.get("shadow_only") is True
            and not authority
            and status.get("fdas_authority_actions") == 0
            and status.get("operation_authority_actions") == 0),
        "observation_planning_latency_within_budget": (
            planning_latency["count"] == 1
            and planning_latency["maximum_ms"] is not None
            and planning_latency["maximum_ms"] <= 250.0),
        "status_counters_match_shadow_artifacts": (
            status.get("fdas_observation_pressure_decisions") == len(packets)
            and status.get("fdas_observation_pressure_selected")
            == len(selected_ids)
            and status.get("fdas_observation_pressure_packet_commits")
            == len(selected_ids)),
        "source_is_clean": manifest.get("source", {}).get("dirty") is False,
    }
    return {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "arm": arm,
        "evidence": dict(
            (name, {"path": _logical_path(path, repo), "sha256": _sha256(path)})
            for name, path in sorted(paths.items())),
        "source": manifest.get("source"),
        "latency": {"observation_pressure": planning_latency},
        "summary": {
            "actions": len(sent),
            "decision_change_probability": analysis.get(
                "decision_change_probability"),
            "observation_pressure_decisions": len(packets),
            "packet_commits": len(selected_ids),
            "selected_evidence_write_throughs": len(selected_evidence),
        },
    }


def audit_fdas_observation_live(root, repo=None):
    """Verify live decision-sensitive packet planning without evidence writes."""
    root = os.path.abspath(root)
    aggregate_path = os.path.join(root, "impact-aggregate.json")
    run_summary_path = os.path.join(root, "impact-run-summary.json")
    if not os.path.isfile(aggregate_path) or not os.path.isfile(run_summary_path):
        raise ValueError("paired aggregate and run summary are required")
    aggregate = _load_json(aggregate_path)
    run_summary = _load_json(run_summary_path)
    arms = tuple(_audit_arm(root, arm, repo)
                 for arm in ("baseline", "treatment"))
    commits = {arm["source"].get("commit") for arm in arms}
    implementation_hashes = {
        arm["source"].get("implementation_sha256") for arm in arms}
    checks = {
        "both_arms_pass_observation_acceptance": all(
            arm["acceptance"]["accepted"] for arm in arms),
        "cohort_completed_without_failures": (
            aggregate.get("complete_pairs") == 1
            and not aggregate.get("failures")
            and run_summary.get("completed") == 2
            and run_summary.get("infrastructure_failures") == 0),
        "cohort_is_predeclared_and_claim_ineligible": (
            aggregate.get("design", {}).get("cohort") == COHORT
            and aggregate.get("design", {}).get("claim_eligible") is False
            and aggregate.get("claim_evaluation", {}).get("status")
            == "ineligible"),
        "paired_source_is_clean_and_stable": (
            len(commits) == 1 and None not in commits
            and len(implementation_hashes) == 1
            and None not in implementation_hashes
            and run_summary.get("source_stable") is True
            and aggregate.get("source_freeze", {}).get("passed") is True),
    }
    report = {
        "acceptance": {"accepted": all(checks.values()), "checks": checks},
        "arms": arms,
        "claim_scope": (
            "manifest-bound decision-sensitive observation-pressure planning, "
            "scalar-v2 epistemic routing, atomic shadow packet accounting, "
            "model provenance, selection widening, and evidence non-mutation; "
            "no executed observation, evidence return, policy authority, score, "
            "or gameplay improvement claim"),
        "cohort": COHORT,
        "evidence": {
            "impact_aggregate": {
                "path": _logical_path(aggregate_path, repo),
                "sha256": _sha256(aggregate_path),
            },
            "impact_run_summary": {
                "path": _logical_path(run_summary_path, repo),
                "sha256": _sha256(run_summary_path),
            },
        },
        "schema_version": "1.0",
        "source": {
            "commit": next(iter(commits)),
            "implementation_sha256": next(iter(implementation_hashes)),
        },
        "summary": {
            name: sum(arm["summary"][name] for arm in arms)
            for name in (
                "actions", "observation_pressure_decisions",
                "packet_commits", "selected_evidence_write_throughs")
        },
    }
    report["structural_hash"] = structural_hash(report)
    return report
