"""The versioned controller is wired behind the grounded Impact boundary."""

from copy import deepcopy
import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
import freeciv_agent.planning.impact_flow_adapter as impact_flow_adapter_module  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ControlEventEmitter,
    GroundedImpactPlanner,
)
from freeciv_agent.planning.impact_unified_flow import (  # noqa: E402
    UnifiedImpactFlowEngine,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def _snapshot(source_seq=1):
    path = os.path.join(
        REPO, "benchmarks", "freeciv", "samples",
        "real_state_turn1.json")
    with open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    return ProxyStateDTO.parse(
        "impact-controller-integration",
        source_seq, payload).to_snapshot()


def _shadow_config():
    return {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_shadow",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
    }


def test_unified_shadow_preserves_legacy_plan_and_snapshot_byte_semantics():
    snapshot = _snapshot()
    before = snapshot.event_payload()
    advertised = frozenset(
        snapshot.legal_action_json)
    legacy = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v1",
        "pressure_controller_mode": "legacy_scalar",
    })
    shadow = GroundedImpactPlanner(
        _shadow_config())

    legacy_decision = legacy.plan(snapshot)
    shadow_decision = shadow.plan(snapshot)

    assert legacy_decision is not None
    assert shadow_decision is not None
    assert shadow_decision.candidate.action_key == (
        legacy_decision.candidate.action_key)
    assert shadow_decision.plan.to_dict() == (
        legacy_decision.plan.to_dict())
    assert shadow_decision.pressure_artifact == (
        legacy_decision.pressure_artifact)
    assert snapshot.event_payload() == before
    assert shadow.last_control_decision.controller_mode == (
        "unified_shadow")
    assert shadow.last_control_decision.artifact[
        "live_baseline_mode"] == "legacy_scalar"
    flow = next(
        row for row in shadow.last_control_decision.artifact[
            "shadow_decisions"]
        if row["controller_mode"] == "unified_flow")
    assert flow["health"] == "healthy"
    assert not flow["spendable"]
    assert flow["packet_conserved"]
    flow_decision = flow["decision"]
    assert not flow_decision["artifact"][
        "calibrated"]
    assert flow_decision["packet_schedule"][
        "conserved"]
    assert flow_decision["packet_schedule"][
        "committed_operation_ids"]
    assert set(flow_decision["artifact"][
        "admissible_candidate_keys"]) <= advertised
    assert all(
        value >= -1e-9
        for projection in flow_decision[
            "artifact"]["flow"][
                "projection_results"]
        for value in projection[
            "feasible_current"])
    assert flow_decision["artifact"]["flow"][
        "health"]["healthy"]


def test_scalar_v2_materializes_only_an_authoritative_candidate():
    snapshot = _snapshot()
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
    })
    advertised = frozenset(
        snapshot.legal_action_json)
    decision = planner.plan(snapshot)

    assert decision is not None
    assert decision.candidate.action_key in advertised
    assert planner.last_control_decision.selected_candidate_key == (
        decision.candidate.action_key)
    assert decision.pressure_artifact[
        "pressure"]["pressure_artifact_schema"] == "2.0"
    assert planner.last_control_decision.packet_schedule is not None
    assert planner.last_control_decision.packet_schedule.conserved
    assert (
        planner.last_control_decision.packet_schedule
        .committed_operation_ids)
    assert decision.plan.solver_identity == (
        GroundedImpactPlanner.SOLVER_IDENTITY)


def test_scalar_v2_stranded_pressure_uses_action_dependency_rail():
    snapshot = _snapshot()
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
    })
    diagnostics = {}
    excluded = tuple(
        row.action_key
        for row in planner.candidates(snapshot))

    decision = planner.plan(
        snapshot, excluded=excluded,
        diagnostics=diagnostics)

    assert decision is None
    assert planner.last_stranded_pressure_artifact[
        "pressure"]["pressure_artifact_schema"] == "2.0"
    assert diagnostics["stranded_pressure_calls"] == 1
    assert diagnostics["stranded_goal_count"] > 0


def test_unified_flow_semantic_artifact_is_deterministic():
    decisions = []
    for _ in range(2):
        planner = GroundedImpactPlanner(
            _shadow_config())
        planner.plan(_snapshot())
        row = next(
            value for value in
            planner.last_control_decision.artifact[
                "shadow_decisions"]
            if value["controller_mode"]
            == "unified_flow")
        decision = deepcopy(row["decision"])
        decision["artifact"].pop(
            "controller_telemetry")
        decisions.append(decision)

    assert decisions[0] == decisions[1]


def test_unified_flow_action_replay_ignores_transport_sequence():
    rows = []
    for source_seq in (7, 73):
        planner = GroundedImpactPlanner(
            _shadow_config())
        planner.plan(_snapshot(source_seq))
        row = next(
            value for value in
            planner.last_control_decision.artifact[
                "shadow_decisions"]
            if value["controller_mode"]
            == "unified_flow")
        rows.append(row["decision"])

    first, second = rows
    first_flow = first["artifact"]["flow"]
    second_flow = second["artifact"]["flow"]

    def semantic_paths(flow):
        return tuple(
            tuple(
                (
                    tuple(path["node_ids"]),
                    tuple(path["edge_ids"]),
                    path["rng_substream"],
                    path["sampling_stream"],
                )
                for path in batch["paths"])
            for batch in flow["probe_batches"])

    assert first["selected_candidate_key"] == (
        second["selected_candidate_key"])
    assert first["ordered_candidate_keys"] == (
        second["ordered_candidate_keys"])
    assert first_flow["factorization"]["view"][
        "probe_semantic_hash"
    ] == second_flow["factorization"]["view"][
        "probe_semantic_hash"]
    assert semantic_paths(first_flow) == (
        semantic_paths(second_flow))
    assert first_flow["transport_readout"] == (
        second_flow["transport_readout"])
    assert first_flow["factorization"]["view"][
        "snapshot_id"
    ] != second_flow["factorization"]["view"][
        "snapshot_id"]


def test_grouped_configuration_drives_live_engine_and_query_identity():
    default = GroundedImpactPlanner(
        _shadow_config())
    configured_values = _shadow_config()
    configured_values.update({
        "bridge": {
            "deposit_decay": 0.20,
            "minimum_ess": 0.40,
            "probe_count": 4,
            "reference_probe_fraction": 0.50,
            "temperature": 0.75,
        },
        "flow": {
            "candidate_region_relative_overlap": 0.60,
            "cfl_limit": 0.70,
            "diffusion": 0.02,
            "mass_tolerance": 1.0e-7,
            "maximum_candidate_regions_per_goal": 3,
            "maximum_microsteps": 4,
            "projection_tolerance": 1.0e-7,
            "time_step": 0.50,
            "turnover_fraction": 0.20,
        },
        "packets": {
            "budgets": {
                "cpu": 2,
            },
        },
    })
    configured = GroundedImpactPlanner(
        configured_values)
    engine = configured._control_adapter.controllers[
        "unified_flow"].engine

    assert engine.config.probe_path_count == 4
    assert engine.config.probe_reference_fraction == 0.50
    assert engine.config.probe_minimum_ess_fraction == 0.10
    assert engine.config.probe_deposit_decay == 0.20
    assert engine.config.turnover_fraction == 0.20
    assert (
        engine.config.candidate_region_relative_overlap
        == 0.60)
    assert (
        engine.config.maximum_candidate_regions_per_goal
        == 3)
    assert engine.config.transport_time_step == 0.50
    assert engine.config.transport_microsteps == 4
    assert dict(engine.config.packet_budgets)["cpu"] == 2
    assert engine.probes.config.temperature == 0.75
    assert engine.current_builder.deposit_decay == 0.20
    assert engine.transport.cfl_limit == 0.70

    default.plan(_snapshot())
    configured.plan(_snapshot())
    assert default.last_control_query.config_digest != (
        configured.last_control_query.config_digest)
    assert configured.last_control_query\
        .normalization_contract_hash == (
            engine.normalization_contract
            .contract_hash)


def test_flow_overlap_selects_region_then_pf_scores_operation_once():
    scores = {
        "scalar-first": SimpleNamespace(
            admissible=True, priority=10.0),
        "flow-first": SimpleNamespace(
            admissible=True, priority=5.0),
        "inadmissible": SimpleNamespace(
            admissible=False, priority=100.0),
    }
    selected, regions = (
        UnifiedImpactFlowEngine
        ._select_candidate_region(
            (
                ("scalar-first", "node-a", 0.20),
                ("flow-first", "node-b", 1.00),
                ("inadmissible", "node-c", 2.00),
            ),
            scores,
            {
                "scalar-first": "goal",
                "flow-first": "goal",
                "inadmissible": "goal",
            },
            relative_overlap=0.50,
            maximum_regions_per_goal=8))

    assert tuple(row[0] for row in selected) == (
        "flow-first",)
    assert regions[0]["maximum_overlap"] == 1.0
    assert regions[0]["threshold_overlap"] == 0.5


def test_flow_region_cap_preserves_typed_pf_order_after_overlap_gate():
    scores = {
        "a": SimpleNamespace(
            admissible=True, priority=3.0),
        "b": SimpleNamespace(
            admissible=True, priority=2.0),
        "c": SimpleNamespace(
            admissible=True, priority=1.0),
    }
    selected, _ = (
        UnifiedImpactFlowEngine
        ._select_candidate_region(
            (
                ("a", "node-a", 0.80),
                ("b", "node-b", 1.00),
                ("c", "node-c", 0.90),
            ),
            scores,
            dict((key, "goal") for key in scores),
            relative_overlap=0.50,
            maximum_regions_per_goal=2))

    assert tuple(row[0] for row in selected) == (
        "a", "b")


def test_protected_flow_union_cannot_displace_scalar_candidate():
    config = _shadow_config()
    config[
        "pressure_flow_protected_candidate_union_enabled"
    ] = True
    planner = GroundedImpactPlanner(config)
    planner.plan(_snapshot())
    shadows = {
        row["controller_mode"]: row["decision"]
        for row in planner.last_control_decision
        .artifact["shadow_decisions"]
    }
    scalar = shadows["scalar_v2"]
    flow = shadows["unified_flow"]
    union = flow["artifact"]["flow"][
        "transport_readout"]["candidate_union"]

    assert flow["selected_candidate_key"] == (
        scalar["selected_candidate_key"])
    assert union["readout_policy"] == (
        "corrected-probe-union")
    assert union["scalar_ranked_operation_ids"][0] == (
        flow["artifact"]["flow"][
            "transport_readout"][
                "selected_operation_id"])
    assert not any(
        row["used_in_final_score"]
        for row in union["signal_ledger"]["uses"]
        if row["signal_name"] in (
            "bridge_height",
            "corrected_probe_weight",
            "raw_probe_count"))


def test_disabled_flow_configuration_has_no_query_semantic_effect():
    base = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
    }
    changed = dict(base)
    changed["flow"] = {
        "diffusion": 0.25,
        "maximum_microsteps": 3,
        "time_step": 0.25,
        "turnover_fraction": 0.50,
    }
    left = GroundedImpactPlanner(base)
    right = GroundedImpactPlanner(changed)

    left.plan(_snapshot())
    right.plan(_snapshot())

    assert left.last_control_query.config_digest == (
        right.last_control_query.config_digest)
    assert left.last_control_query\
        .normalization_contract_hash == (
            right.last_control_query
            .normalization_contract_hash)
    assert left.last_control_decision.decision_hash == (
        right.last_control_decision.decision_hash)


def test_unified_flow_fault_falls_back_without_changing_live_shadow_plan():
    snapshot = _snapshot()
    legacy = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v1",
        "pressure_controller_mode": "legacy_scalar",
    })
    expected = legacy.plan(snapshot)
    planner = GroundedImpactPlanner(
        _shadow_config())
    engine = planner._control_adapter.controllers[
        "unified_flow"].engine

    class BrokenFactorBuilder:
        @staticmethod
        def build(*_args, **_kwargs):
            raise ValueError(
                "injected-factorization-failure")

    engine.factor_builder = BrokenFactorBuilder()
    actual = planner.plan(snapshot)
    row = next(
        value for value in
        planner.last_control_decision.artifact[
            "shadow_decisions"]
        if value["controller_mode"]
        == "unified_flow")

    assert actual.candidate.action_key == (
        expected.candidate.action_key)
    assert row["health"] == "unhealthy"
    assert not row["spendable"]
    assert row["decision"]["artifact"][
        "fallback_reason"] == (
            "flow-exception:ValueError")
    assert row["decision"]["artifact"]["flow"] == {
        "exception_message":
            "injected-factorization-failure",
        "exception_type": "ValueError",
    }
    assert row["decision"]["packet_schedule"][
        "conserved"]


def test_configured_uncalibrated_advisory_revalidates_and_can_rank():
    config = _shadow_config()
    config["pressure_controller_mode"] = (
        "unified_flow_advisory")
    config["teleology"] = {
        "calibration_required": False,
    }
    planner = GroundedImpactPlanner(config)
    snapshot = _snapshot()
    decision = planner.plan(snapshot)
    control = planner.last_control_decision

    assert decision is not None
    assert control.controller_mode == (
        "unified_flow_advisory")
    assert control.health == "healthy"
    assert control.artifact["advisory_accepted"]
    assert control.artifact["validation"][
        "disposition"] == "commit"
    assert control.selected_candidate_key in (
        snapshot.legal_action_json)


def test_advisory_decision_hash_excludes_nested_wall_clock_telemetry():
    hashes = []
    artifacts = []
    for _ in range(2):
        config = _shadow_config()
        config["pressure_controller_mode"] = (
            "unified_flow_advisory")
        planner = GroundedImpactPlanner(config)
        planner.plan(_snapshot())
        hashes.append(
            planner.last_control_decision
            .decision_hash)
        artifacts.append(
            planner.last_control_decision
            .artifact)

    assert hashes[0] == hashes[1]
    assert artifacts[0]["target_artifact"][
        "artifact"]["controller_telemetry"] != (
            artifacts[1]["target_artifact"][
                "artifact"][
                    "controller_telemetry"])


def test_authoritative_outcome_reaches_versioned_control_ledger():
    config = _shadow_config()
    config["pressure_controller_mode"] = (
        "unified_flow_advisory")
    planner = GroundedImpactPlanner(config)
    before = _snapshot()
    decision = planner.plan(before)

    planner.record_outcome(
        decision.candidate,
        before,
        True,
        after_snapshot=before,
        feedback_id="control-outcome-test")
    record = planner.last_control_outcome_record

    assert record is not None
    assert record.controller_mode == (
        "unified_flow_advisory")
    assert record.selected_candidate_key == (
        decision.candidate.action_key)
    assert record.executed_candidate_key == (
        decision.candidate.action_key)
    assert record.effect_observed is True
    assert record.counterfactual_status == (
        "observed-selected-execution")
    assert planner._control_adapter.outcome_records == (
        record,)


def test_unified_control_events_are_aggregate_schema_valid_and_linked(
        tmp_path):
    planner = GroundedImpactPlanner(
        _shadow_config())
    snapshot = _snapshot()
    decision = planner.plan(snapshot)
    path = str(tmp_path / "events.jsonl")
    writer = EventWriter(
        path, "control-events-test",
        durable=False,
        id_factory=(
            lambda counter=iter(range(1000)):
            "event-{}".format(next(counter))))
    root = writer.emit(
        "run_started", 0, {
            "condition_id": "test",
            "manifest_identity": "test",
        })
    emitter = ControlEventEmitter()
    events = emitter.emit_decision(
        writer, snapshot.turn,
        planner.last_control_query,
        planner.last_control_decision,
        caused_by=(root["event_id"],))

    assert [row["type"] for row in events] == [
        "teleology_estimated",
        "bridge_estimated",
        "probe_block_completed",
        "path_current_deposited",
        "flow_projected",
        "attention_advected",
        "packet_reserved",
        "flow_candidate_selected",
    ]
    assert events[0]["caused_by"] == [
        root["event_id"]]
    for previous, current in zip(
            events, events[1:]):
        assert current["caused_by"] == [
            previous["event_id"]]
        assert current["payload"][
            "parent_event_ids"] == (
                current["caused_by"])
        assert current["payload"][
            "query_id"] == (
                planner.last_control_query
                .query_id)
    assert "paths" not in events[2][
        "payload"]["summary"]["batches"][0]
    flow_selection = events[-1][
        "payload"]["summary"]
    assert flow_selection[
        "selection_disposition"] == "shadow-only"
    assert flow_selection[
        "effective_candidate_key"] == (
            planner.last_control_decision
            .selected_candidate_key)
    assert flow_selection[
        "selected_candidate_key"] in (
            planner.last_control_query
            .candidate_keys)

    planner.record_outcome(
        decision.candidate, snapshot, True,
        after_snapshot=snapshot,
        feedback_id="control-event-outcome")
    outcome = emitter.emit_outcome(
        writer, snapshot.turn,
        planner.last_control_outcome_query,
        planner.last_control_outcome_decision,
        planner.last_control_outcome_record,
        caused_by=(events[-1]["event_id"],))

    assert outcome["type"] == (
        "control_outcome_recorded")
    assert outcome["payload"]["summary"][
        "counterfactual_status"] == (
            "observed-selected-execution")
    assert validate_file(path).valid


def test_direct_bridge_union_is_emitted_without_numerical_flow(
        tmp_path):
    planner = GroundedImpactPlanner({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "bridge_scalar",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_bridge_readout_policy":
            "protected-message-union",
    })
    snapshot = _snapshot()
    planner.plan(snapshot)
    path = str(tmp_path / "events.jsonl")
    writer = EventWriter(
        path, "direct-bridge-events-test",
        durable=False)
    root = writer.emit(
        "run_started", 0, {
            "condition_id": "test",
            "manifest_identity": "test",
        })

    events = ControlEventEmitter().emit_decision(
        writer, snapshot.turn,
        planner.last_control_query,
        planner.last_control_decision,
        caused_by=(root["event_id"],))

    event_types = [
        row["type"] for row in events]
    assert "bridge_estimated" in event_types
    assert "flow_candidate_selected" in event_types
    assert "probe_block_completed" not in event_types
    selection = next(
        row for row in events
        if row["type"]
        == "flow_candidate_selected")
    summary = selection[
        "payload"]["summary"]
    assert summary["readout_source"] == (
        "protected-bridge-scalar")
    candidate_union = summary[
        "transport_readout"][
            "candidate_union"]
    assert candidate_union[
        "readout_policy"] == (
            "protected-message-union")
    assert candidate_union["members"]
    assert validate_file(path).valid


def test_control_event_chain_hashes_large_decision_once(
        tmp_path, monkeypatch):
    planner = GroundedImpactPlanner(
        _shadow_config())
    snapshot = _snapshot()
    decision = planner.plan(snapshot)
    path = str(tmp_path / "events.jsonl")
    writer = EventWriter(
        path, "control-event-hash-test",
        durable=False)
    root = writer.emit(
        "run_started", 0, {
            "condition_id": "test",
            "manifest_identity": "test",
        })
    calls = {"count": 0}
    original = (
        impact_flow_adapter_module
        .structural_hash)

    def tracked(value):
        calls["count"] += 1
        return original(value)

    monkeypatch.setattr(
        impact_flow_adapter_module,
        "structural_hash", tracked)
    emitter = ControlEventEmitter()
    events = emitter.emit_decision(
        writer, snapshot.turn,
        planner.last_control_query,
        planner.last_control_decision,
        caused_by=(root["event_id"],))

    assert len(events) == 8
    assert calls["count"] == 1

    planner.record_outcome(
        decision.candidate, snapshot, True,
        after_snapshot=snapshot,
        feedback_id="control-event-hash-outcome")
    calls["count"] = 0
    emitter.emit_outcome(
        writer, snapshot.turn,
        planner.last_control_outcome_query,
        planner.last_control_outcome_decision,
        planner.last_control_outcome_record,
        caused_by=(events[-1]["event_id"],))
    assert calls["count"] == 0
