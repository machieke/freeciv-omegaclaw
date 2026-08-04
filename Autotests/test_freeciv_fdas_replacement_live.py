import json
from dataclasses import replace

from freeciv.harness.fdas_replacement_chain_outcome_live import (
    audit_fdas_replacement_chain_outcome_live,
)
from freeciv.harness.fdas_replacement_live import audit_fdas_replacement_live
from freeciv.harness.fdas_replacement_readout_live import (
    audit_fdas_replacement_readout_live,
)
from freeciv.harness.fdas_replacement_readout_cohort import (
    audit_fdas_replacement_readout_cohort,
)
from freeciv.harness.fdas_replacement_opportunity_cohort import (
    audit_fdas_replacement_opportunity_cohort,
)
from freeciv.harness.fdas_replacement_opportunity_live import (
    audit_fdas_replacement_opportunity_live,
)
from freeciv.harness.fdas_replacement_capacity_cohort import (
    audit_fdas_replacement_capacity_cohort,
)
from freeciv.harness.fdas_replacement_capacity_live import (
    audit_fdas_replacement_capacity_live,
)
from freeciv.harness.fdas_replacement_capacity_production_cohort import (
    audit_fdas_replacement_capacity_production_cohort,
)
from freeciv.harness.fdas_replacement_capacity_production_live import (
    audit_fdas_replacement_capacity_production_live,
)
from freeciv.harness.fdas_replacement_reproposal import (
    audit_fdas_replacement_reproposal,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.planning import (
    FdasReplacementChainOutcomeLabeler,
    FdasReplacementChainOutcomeStore,
    OperationRecord,
    REPLACEMENT_CHAIN_OUTCOME_TARGET,
)


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _atom_payload(snapshot_id, operation_id, store_digest):
    details = {
        "action_selection_changed": False,
        "binding": None,
        "disposition": "reservable",
        "identity": "fdas-coordinated-replacement-lifecycle/1.0",
        "operation_id": operation_id,
        "policy_authority": False,
        "previous_state": "proposed",
        "readout_authority": False,
        "reason": "current-coordinated-step-grounded",
        "snapshot_id": snapshot_id,
        "state": "reservable",
        "store_digest": store_digest,
        "truth_mutated": False,
    }
    material = {
        "component_id": "fdas-coordinated-replacement-lifecycle",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": snapshot_id,
    }
    material["structural_hash"] = structural_hash(material)
    return material


def _fixture(tmp_path, with_operation=True):
    manifest = {
        "attempt_id": "attempt-proof",
        "dependent_atomspace": {
            "config": {"projection": {"operations": True}},
            "manifest": {"capabilities": {
                "coordinated_replacement_lifecycle": "shadow-live"}},
        },
        "game_id": "replacement-live-proof",
        "manifest_identity": "manifest-proof",
        "source": {"commit": "a" * 40, "dirty": False},
    }
    persistence = structural_hash([
        manifest["manifest_identity"], manifest["attempt_id"],
        manifest["game_id"],
        "fdas-coordinated-replacement-operations/1.0",
    ])
    records = []
    operation_id = "replacement-proof"
    if with_operation:
        spec = {
            "created_turn": 4,
            "expiry_turn": 8,
            "goal_ids": ["pf-impact:survival"],
            "operation_id": operation_id,
            "operation_type": "fdas-defense:coordinated-replacement",
            "participants": [
                {"actor_class": "unit", "actor_id": "8", "required": True,
                 "role": "replacement"},
                {"actor_class": "unit", "actor_id": "7", "required": True,
                 "role": "reinforcement"},
            ],
            "provenance": ["fdas-coordinated-replacement-shadow/1.0"],
            "replacement_margin": 0.0,
            "ruleset_digest": "ruleset-proof",
            "schema_version": 1,
            "steps": [
                {"action_type": "unit_move", "actor_role": "replacement",
                 "completion_predicate_id": "replacement-at-source",
                 "maximum_attempts": 3,
                 "requirement_set_id": "replacement-requirements",
                 "step_id": "replacement-step", "target_ref": "city:3"},
                {"action_type": "unit_move", "actor_role": "reinforcement",
                 "completion_predicate_id": "reinforcement-at-target",
                 "maximum_attempts": 3,
                 "requirement_set_id": "reinforcement-requirements",
                 "step_id": "reinforcement-step", "target_ref": "city:4"},
            ],
            "target_ref": "city:4",
        }
        spec["spec_digest"] = structural_hash(spec)
        records.append({
            "progress": {
                "attempt_count": 0, "blocked_reason": None,
                "current_step_index": 0, "last_snapshot_id": "snapshot-4",
                "last_updated_turn": 4, "operation_id": operation_id,
                "state": "reservable", "terminal_reason": None,
            },
            "spec": spec,
        })
    store = {
        "persistence_identity": persistence,
        "quarantine_reason": None,
        "records": records,
        "schema_version": 1,
        "store_identity": "freeciv-operation-store/1.0",
    }
    store["store_digest"] = structural_hash(store)
    _write_json(tmp_path / "manifest.json", manifest)
    _write_json(
        tmp_path / "fdas-coordinated-replacement-operations.json", store)

    counters = {
        "fdas_replacement_blocked": 0,
        "fdas_replacement_candidates": 1 if with_operation else 0,
        "fdas_replacement_completions": 0,
        "fdas_replacement_expirations": 0,
        "fdas_replacement_operations": 1 if with_operation else 0,
        "fdas_replacement_reconciliations": 1 if with_operation else 0,
        "fdas_replacement_reservable": 1 if with_operation else 0,
        "fdas_replacement_step_advances": 0,
    }
    _write_json(tmp_path / "status.json", dict(
        counters, completed=True, horizon_reached=True))
    writer = EventWriter(
        str(tmp_path / "events.jsonl"), manifest["game_id"], durable=False,
        id_factory=iter(("event-1", "event-2")).__next__)
    parent = None
    if with_operation:
        row = writer.emit(
            "atomspace_shadow_decision", 4,
            _atom_payload("snapshot-4", operation_id, store["store_digest"]))
        parent = row["event_id"]
    writer.emit(
        "run_completed", 4,
        {"status": "completed", "summary": counters},
        caused_by=(() if parent is None else (parent,)))


def _add_candidate_readout(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "coordinated_replacement_candidate_readout"] = "shadow-live"
    activation["coordinated_replacement_candidate_readout_diagnostic"] = {
        "action_selection_changed": False,
        "combined_native_route_grounding_required": True,
        "direct_control_semantics": "protected-source-garrison-direct-move",
        "policy_authority": False,
        "readout_authority": False,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)

    pair = {
        "combined_estimated_turns": 2,
        "combined_movement_cost": 2,
        "direct_action_key": "direct-action",
        "direct_operation_id": "direct-proof",
        "direct_unsafe_reason": "protected-source-garrison",
        "lifecycle_operation_id": "replacement-proof",
        "replacement_action_key": "replacement-action",
        "replacement_actor_id": 8,
        "replacement_estimated_turns": 1,
        "replacement_movement_cost": 1,
        "replacement_operation_id": "replacement-proof",
        "reinforcement_actor_id": 7,
        "reinforcement_estimated_turns": 1,
        "reinforcement_movement_cost": 1,
        "requirement_context_hash": "requirement-proof",
        "safe_chain_grounded": True,
        "source_city_id": 3,
        "target_city_id": 4,
    }
    pair["result_hash"] = structural_hash(pair)
    details = {
        "action_selection_changed": False,
        "candidate_recall_changed": True,
        "direct_candidate_count": 1,
        "identity": "fdas-coordinated-replacement-candidate-readout/1.0",
        "pairs": [pair],
        "policy_authority": False,
        "readout_authority": False,
        "reason": "grounded-safe-chain-recalled",
        "rejected": [],
        "replacement_candidate_count": 1,
        "revision_id": "revision-1",
        "snapshot_id": "snapshot-4",
        "status": "eligible-shadow",
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    details["result_hash"] = structural_hash(details)
    payload = {
        "component_id": "fdas-coordinated-replacement-candidate-readout",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": "snapshot-4",
    }
    payload["structural_hash"] = structural_hash(payload)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    readout_event = {
        **events[-1],
        "caused_by": [events[0]["event_id"]],
        "event_id": "event-readout",
        "payload": payload,
        "seq": 1,
        "type": "atomspace_shadow_decision",
    }
    events[-1]["caused_by"] = ["event-readout"]
    events[-1]["seq"] = 2
    counters = {
        "fdas_replacement_readout_abstentions": 0,
        "fdas_replacement_readout_candidates": 1,
        "fdas_replacement_readout_direct_controls": 1,
        "fdas_replacement_readout_evaluations": 1,
        "fdas_replacement_readout_grounded_pairs": 1,
        "fdas_replacement_readout_rejections": 0,
    }
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n"
                for row in (events[0], readout_event, events[-1])),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _add_opportunity_funnel(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "coordinated_replacement_opportunity_funnel"] = "shadow-live"
    activation["coordinated_replacement_opportunity_funnel_diagnostic"] = {
        "action_selection_changed": False,
        "blocker_taxonomy": (
            "coordinated-replacement-opportunity-blockers/1.0"),
        "policy_authority": False,
        "readout_authority": False,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)
    details = {
        "action_selection_changed": False,
        "blocker_stage": "grounded-pair-available",
        "blocker_taxonomy": (
            "coordinated-replacement-opportunity-blockers/1.0"),
        "critical_source_garrison_count": 1,
        "current_replacement_candidate_count": 1,
        "deficit_target_city_count": 1,
        "grounded_pair_count": 1,
        "identity": "fdas-coordinated-replacement-opportunity-funnel/1.0",
        "policy_authority": False,
        "protected_direct_control_count": 1,
        "readout_authority": False,
        "readout_rejection_count": 0,
        "reinforcement_route_count": 1,
        "revision_id": "revision-1",
        "safe_replacement_relation_count": 1,
        "snapshot_id": "snapshot-4",
        "structural_source_target_join_count": 1,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    details["result_hash"] = structural_hash(details)
    payload = {
        "component_id": "fdas-coordinated-replacement-opportunity-funnel",
        "component_version": "1.0",
        "details": details,
        "revision_id": "revision-1",
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": "snapshot-4",
    }
    payload["structural_hash"] = structural_hash(payload)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    funnel_event = {
        **events[-1],
        "caused_by": [events[-2]["event_id"]],
        "event_id": "event-opportunity-funnel",
        "payload": payload,
        "seq": events[-1]["seq"],
        "type": "atomspace_shadow_decision",
    }
    events[-1]["caused_by"] = [funnel_event["event_id"]]
    events[-1]["seq"] += 1
    counters = {
        "fdas_replacement_opportunity_funnel_evaluations": 1,
        "fdas_replacement_opportunity_grounded": 1,
        "fdas_replacement_opportunity_no_safe_replacement": 0,
    }
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n"
                for row in (*events[:-1], funnel_event, events[-1])),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _add_replacement_capacity_evidence(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"]["replacement_capacity_demand"] = (
        "shadow-live")
    activation["replacement_capacity_demand_diagnostic"] = {
        "action_selection_changed": False,
        "candidate_authority": False,
        "policy_authority": False,
        "precondition": (
            "cross-city-critical-reinforcement-without-spare"),
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)

    def payload(details):
        value = {
            "component_id": "fdas-goal-pressure-shadow",
            "component_version": "1.0",
            "details": details,
            "revision_id": "revision-1",
            "ruleset_digest": "ruleset-proof",
            "snapshot_id": "snapshot-4",
        }
        value["structural_hash"] = structural_hash(value)
        return value

    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    terminal = events[-1]
    parent_id = events[-2]["event_id"]

    def event(event_type, seq, event_id, details, caused_by):
        return {
            **terminal,
            "caused_by": list(caused_by),
            "event_id": event_id,
            "payload": payload(details),
            "seq": seq,
            "type": event_type,
        }

    seq = terminal["seq"]
    goal = event("goal_instantiated", seq, "event-capacity-goal", {
        "deficit_atom_id": "atom-capacity-deficit",
        "deficit_predicate": "city-replacement-capacity-deficit",
        "explanation_hash": "capacity-explanation",
        "goal_id": "goal-capacity",
        "scope_id": "city-facts:3",
    }, (parent_id,))
    candidate = event(
        "operation_candidate_rejected", seq + 1,
        "event-capacity-candidate", {
            "action_key": "city-production:3:Riflemen",
            "authority_eligible": False,
            "blockers": ["shadow-only"],
            "candidate_hash": "capacity-candidate-hash",
            "legal_bound": True,
            "operation_id": "capacity-production-operation",
            "operation_type": (
                "fdas-shadow:city-replacement-capacity-deficit:"
                "city_production"),
        }, (parent_id,))
    pressure = event(
        "pressure_graph_built", seq + 2, "event-capacity-pressure",
        {"policy_authority": False}, (parent_id,))
    shadow = event(
        "atomspace_shadow_decision", seq + 3, "event-capacity-shadow",
        {"authority_eligible": False}, (pressure["event_id"],))
    terminal["caused_by"] = [shadow["event_id"]]
    terminal["seq"] = seq + 4
    counters = {
        "fdas_replacement_capacity_evaluations": 1,
        "fdas_replacement_capacity_deficit_goals": 1,
        "fdas_replacement_capacity_production_candidates": 1,
    }
    terminal["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in (
            *events[:-1], goal, candidate, pressure, shadow, terminal)),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _add_replacement_capacity_production_evidence(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "replacement_capacity_production_operation"] = "shadow-live"
    activation["replacement_capacity_production_operation_diagnostic"] = {
        "action_selection_changed": False,
        "candidate_authority": False,
        "completion_semantics": (
            "queue-selection-then-authoritative-product-observation"),
        "maximum_observation_horizon_turns": 64,
        "policy_authority": False,
        "queue_selection_is_goal_relief": False,
        "resource_semantics": (
            "exact-current-and-conditional-future-claims"),
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)

    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    candidate = next(
        row for row in events
        if (row["type"] == "operation_candidate_rejected"
            and row["payload"].get("component_id")
            == "fdas-goal-pressure-shadow"
            and row["payload"]["details"].get("operation_type") == (
                "fdas-shadow:city-replacement-capacity-deficit:"
                "city_production")))
    candidate["payload"]["details"]["blockers"] = [
        "delayed-production-completion-unobserved"]
    candidate["payload"]["details"]["grounded_production_operation"] = {
        "completion_eta": {
            "earliest_completion_turn": candidate["turn"] + 1,
            "latest_completion_turn": candidate["turn"] + 2,
        },
        "initial_step_index": 0,
        "model_artifact_hash": "grounded-model-hash",
        "policy_authority": False,
        "queue_selection_is_goal_relief": False,
        "requirement_set_id": "replacement-production-requirements",
        "resource_claim_count": 3,
        "shadow_only": True,
        "step_count": 2,
    }
    semantic = dict(candidate["payload"])
    semantic.pop("structural_hash", None)
    candidate["payload"]["structural_hash"] = structural_hash(semantic)
    counters = {
        "fdas_replacement_capacity_grounded_production_operations": 1,
        "fdas_replacement_capacity_production_model_abstentions": 0,
    }
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _add_reproposal_hardening_evidence(tmp_path):
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    values = {
        "fdas_replacement_reproposal_cooldown_turns": 32,
        "fdas_replacement_reproposal_suppressions": 7,
    }
    status.update(values)
    status["event_count"] = len(events)
    events[-1]["payload"]["summary"].update(values)
    events_path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in events),
        encoding="utf-8")
    _write_json(status_path, status)


def _outcome_event(event_type, seq, event_id, snapshot_id, revision_id,
                   label, transition, store_digest, caused_by):
    details = label.to_dict()
    details.update({
        "identity": "fdas-coordinated-replacement-chain-outcome/1.0",
        "induction_readout": False,
        "store_digest": store_digest,
        "transition": transition,
    })
    payload = {
        "component_id": "fdas-coordinated-replacement-chain-outcome",
        "component_version": "1.0",
        "details": details,
        "revision_id": revision_id,
        "ruleset_digest": "ruleset-proof",
        "snapshot_id": snapshot_id,
    }
    payload["structural_hash"] = structural_hash(payload)
    return {
        "caused_by": list(caused_by),
        "event_id": event_id,
        "game_id": "replacement-live-proof",
        "payload": payload,
        "schema_version": "1.0",
        "seq": seq,
        "ts": "2026-01-01T00:00:00Z",
        "turn": label.completion_turn if transition == "opened" else 36,
        "type": event_type,
    }


def _add_replacement_chain_outcome_evidence(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declaration = manifest["dependent_atomspace"]["manifest"]
    declaration["capabilities"][
        "coordinated_replacement_chain_outcome"] = "shadow-live"
    declaration["coordinated_replacement_chain_outcome_diagnostic"] = {
        "action_selection_changed": False,
        "completion_index_required": True,
        "induction_readout": False,
        "observation_window_turns": 32,
        "policy_authority": False,
        "readout_authority": False,
        "target_id": REPLACEMENT_CHAIN_OUTCOME_TARGET,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)

    operation_path = tmp_path / "fdas-coordinated-replacement-operations.json"
    operation_store = json.loads(operation_path.read_text(encoding="utf-8"))
    record_value = operation_store["records"][0]
    record_value["progress"].update({
        "current_step_index": 1,
        "state": "completed",
        "terminal_reason": "all-step-predicates-satisfied",
    })
    operation_semantic = dict(operation_store)
    operation_semantic.pop("store_digest")
    operation_store["store_digest"] = structural_hash(operation_semantic)
    _write_json(operation_path, operation_store)
    record = OperationRecord.from_dict(record_value)

    replacement_identity = structural_hash([
        manifest["manifest_identity"], manifest["attempt_id"],
        manifest["game_id"],
        "fdas-coordinated-replacement-operations/1.0",
    ])
    outcome_identity = structural_hash([
        replacement_identity,
        FdasReplacementChainOutcomeLabeler.LABELER_IDENTITY,
        REPLACEMENT_CHAIN_OUTCOME_TARGET,
    ])
    outcome_store = FdasReplacementChainOutcomeStore(outcome_identity)
    labeler = FdasReplacementChainOutcomeLabeler(outcome_store)
    pending = labeler.open(record, manifest["game_id"], 1)
    pending_digest = outcome_store.store_digest
    observed = replace(
        pending,
        status="observed",
        observed_turn=36,
        observed_revision_id="revision-36",
        outcome=True,
        observed_value=(("replacement_at_source", True),),
        reason="completed-replacement-chain-durable-at-due-turn",
        provenance_ids=tuple(sorted(set(
            pending.provenance_ids + (
                "assessment-revision:revision-36",)))))
    outcome_store.record(observed)
    outcome_store.save(str(
        tmp_path / "fdas-coordinated-replacement-outcome-labels.json"))

    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    opened = _outcome_event(
        "operation_outcome_label_opened", 2, "event-outcome-opened",
        "snapshot-4", "revision-1", pending, "opened", pending_digest,
        (events[1]["event_id"],))
    observed_event = _outcome_event(
        "operation_outcome_label_observed", 0, "event-outcome-observed",
        "snapshot-36", "revision-36", observed, "observed",
        outcome_store.store_digest, (opened["event_id"],))
    events[-1]["seq"] = 1
    events[-1]["turn"] = 36
    events[-1]["caused_by"] = [observed_event["event_id"]]
    counters = {
        "fdas_replacement_chain_outcomes_negative": 0,
        "fdas_replacement_chain_outcomes_observed": 1,
        "fdas_replacement_chain_outcomes_opened": 1,
        "fdas_replacement_chain_outcomes_pending": 0,
        "fdas_replacement_chain_outcomes_positive": 1,
    }
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in (
            events[0], events[1], opened, observed_event, events[-1])),
        encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)


def _activate_zero_opportunity_readout(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    activation = manifest["dependent_atomspace"]["manifest"]
    activation["capabilities"][
        "coordinated_replacement_candidate_readout"] = "shadow-live"
    activation["coordinated_replacement_candidate_readout_diagnostic"] = {
        "action_selection_changed": False,
        "combined_native_route_grounding_required": True,
        "direct_control_semantics": "protected-source-garrison-direct-move",
        "policy_authority": False,
        "readout_authority": False,
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    _write_json(manifest_path, manifest)
    counters = {
        "fdas_replacement_readout_abstentions": 0,
        "fdas_replacement_readout_candidates": 0,
        "fdas_replacement_readout_direct_controls": 0,
        "fdas_replacement_readout_evaluations": 0,
        "fdas_replacement_readout_grounded_pairs": 0,
        "fdas_replacement_readout_rejections": 0,
    }
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(counters)
    _write_json(status_path, status)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    events[-1]["payload"]["summary"].update(counters)
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")


def test_replacement_live_accepts_observed_shadow_lifecycle(tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["operations"] == 1
    assert report["summary"]["opportunity_observed"] is True


def test_replacement_live_separates_execution_events_from_reconciliations(
        tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    execution = dict(rows[0])
    execution["caused_by"] = [rows[0]["event_id"]]
    execution["event_id"] = "event-execution"
    execution["seq"] = 1
    execution["payload"] = dict(rows[0]["payload"])
    execution["payload"]["details"] = dict(
        rows[0]["payload"]["details"])
    execution["payload"]["details"].update({
        "disposition": "execution-activated",
        "previous_state": "reserved",
        "reason": "bounded-pilot-current-step-activated",
        "state": "active",
    })
    execution["payload"]["structural_hash"] = structural_hash(dict(
        (key, value) for key, value in execution["payload"].items()
        if key != "structural_hash"))
    rows[-1]["caused_by"] = [execution["event_id"]]
    rows[-1]["seq"] = 2
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n"
                for row in (rows[0], execution, rows[-1])),
        encoding="utf-8")

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["lifecycle_events"] == 2
    assert report["summary"]["execution_lifecycle_events"] == 1


def test_replacement_live_accepts_auditable_zero_opportunity(tmp_path):
    _fixture(tmp_path, with_operation=False)

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["operations"] == 0
    assert report["summary"]["opportunity_observed"] is False


def test_replacement_live_accepts_genuine_absorbing_terminal(tmp_path):
    _fixture(tmp_path)
    status_path = tmp_path / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update({
        "horizon_reached": False,
        "terminal_game_over": False,
        "terminal_player_elimination": True,
    })
    _write_json(status_path, status)
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(
        encoding="utf-8").splitlines()]
    events[-1]["payload"]["summary"].update({
        "horizon_reached": False,
        "terminal_game_over": False,
        "terminal_player_elimination": True,
    })
    events_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events),
        encoding="utf-8")

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["completion_endpoint"] == (
        "terminal-player-elimination")


def test_replacement_live_rejects_authority_leak(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    rows[0]["payload"]["details"]["policy_authority"] = True
    rows[0]["payload"]["structural_hash"] = structural_hash(dict(
        (key, value) for key, value in rows[0]["payload"].items()
        if key != "structural_hash"))
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8")

    report = audit_fdas_replacement_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "lifecycle_events_are_revision_bound_and_non_authorizing"] is False


def test_replacement_readout_live_accepts_grounded_safe_chain(tmp_path):
    _fixture(tmp_path)
    _add_candidate_readout(tmp_path)

    report = audit_fdas_replacement_readout_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["grounded_pairs"] == 1
    assert report["summary"]["replacement_candidates"] == 1


def test_replacement_opportunity_live_accepts_exact_stage_partition(tmp_path):
    _fixture(tmp_path)
    _add_candidate_readout(tmp_path)
    _add_opportunity_funnel(tmp_path)

    report = audit_fdas_replacement_opportunity_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["evaluations"] == 1
    assert report["summary"]["stage_counts"] == {
        "grounded-pair-available": 1}


def test_replacement_reproposal_audit_accepts_bounded_hardening(tmp_path):
    _fixture(tmp_path)
    _add_candidate_readout(tmp_path)
    _add_reproposal_hardening_evidence(tmp_path)

    report = audit_fdas_replacement_reproposal(
        str(tmp_path), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"] == {
        "event_count": 3,
        "grounded_pairs": 1,
        "logical_key_count": 1,
        "operations": 1,
        "reproposal_cooldown_turns": 32,
        "reproposal_suppressions": 7,
    }


def test_replacement_chain_outcome_audit_accepts_exact_lifecycle(tmp_path):
    _fixture(tmp_path)
    _add_candidate_readout(tmp_path)
    _add_replacement_chain_outcome_evidence(tmp_path)

    report = audit_fdas_replacement_chain_outcome_live(
        str(tmp_path), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"] == {
        "completed_operations": 1,
        "labels": 1,
        "negative": 0,
        "observed": 1,
        "pending": 0,
        "positive": 1,
    }


def test_replacement_readout_allows_zero_opportunity_in_cohort_scope(tmp_path):
    _fixture(tmp_path, with_operation=False)
    _activate_zero_opportunity_readout(tmp_path)

    report = audit_fdas_replacement_readout_live(
        str(tmp_path), require_grounded_pair=False)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["grounded_pairs"] == 0


def test_replacement_readout_cohort_requires_two_opportunity_games(tmp_path):
    run_dir = tmp_path / "cohort"
    games = run_dir / "games" / "main" / "e_full_loop"
    for seed in (101, 103):
        game_dir = games / (str(seed) + "-00")
        game_dir.mkdir(parents=True)
        _fixture(game_dir)
        _add_candidate_readout(game_dir)
    _write_json(run_dir / "run-summary.json", {
        "completed": 2, "infrastructure_failures": 0,
        "jobs": 2, "resumed": 0,
    })

    report = audit_fdas_replacement_readout_cohort(
        str(run_dir), (101, 103), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["opportunity_game_count"] == 2
    assert report["summary"]["grounded_pair_count"] == 2


def test_replacement_opportunity_cohort_partitions_all_evaluations(tmp_path):
    run_dir = tmp_path / "cohort"
    games = run_dir / "games" / "main" / "e_full_loop"
    for seed in (101, 103):
        game_dir = games / (str(seed) + "-00")
        game_dir.mkdir(parents=True)
        _fixture(game_dir)
        _add_candidate_readout(game_dir)
        _add_opportunity_funnel(game_dir)
    _write_json(run_dir / "run-summary.json", {
        "completed": 2, "infrastructure_failures": 0,
        "jobs": 2, "resumed": 0,
    })

    report = audit_fdas_replacement_opportunity_cohort(
        str(run_dir), (101, 103), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["evaluation_count"] == 2
    assert report["summary"]["stage_counts"] == {
        "grounded-pair-available": 2}


def test_replacement_capacity_cohort_audits_shadow_recall(tmp_path):
    run_dir = tmp_path / "cohort"
    games = run_dir / "games" / "main" / "e_full_loop"
    for seed in (101, 103):
        game_dir = games / (str(seed) + "-00")
        game_dir.mkdir(parents=True)
        _fixture(game_dir)
        _add_candidate_readout(game_dir)
        _add_opportunity_funnel(game_dir)
        _add_replacement_capacity_evidence(game_dir)
        live = audit_fdas_replacement_capacity_live(str(game_dir))
        assert live["acceptance"]["accepted"] is True
    _write_json(run_dir / "run-summary.json", {
        "completed": 2, "infrastructure_failures": 0,
        "jobs": 2, "resumed": 0,
    })

    report = audit_fdas_replacement_capacity_cohort(
        str(run_dir), (101, 103), expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["evaluation_count"] == 2
    assert report["summary"]["capacity_deficit_goal_count"] == 2
    assert report["summary"]["capacity_production_candidate_count"] == 2


def test_replacement_capacity_production_cohort_audits_delayed_grounding(
        tmp_path):
    run_dir = tmp_path / "cohort"
    games = run_dir / "games" / "main" / "e_full_loop"
    for seed in (101, 103, 107, 109):
        game_dir = games / (str(seed) + "-00")
        game_dir.mkdir(parents=True)
        _fixture(game_dir)
        _add_candidate_readout(game_dir)
        _add_opportunity_funnel(game_dir)
        _add_replacement_capacity_evidence(game_dir)
        _add_replacement_capacity_production_evidence(game_dir)
        live = audit_fdas_replacement_capacity_production_live(str(game_dir))
        assert live["acceptance"]["accepted"] is True
    _write_json(run_dir / "run-summary.json", {
        "completed": 4, "infrastructure_failures": 0,
        "jobs": 4, "resumed": 0,
    })

    report = audit_fdas_replacement_capacity_production_cohort(
        str(run_dir), (101, 103, 107, 109),
        expected_source_commit="a" * 40)

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["capacity_production_candidate_count"] == 4
    assert report["summary"]["grounded_production_operation_count"] == 4
    assert report["summary"]["production_model_abstention_count"] == 0
