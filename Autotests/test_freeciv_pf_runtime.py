"""PF-PLN live activation declarations, manifests, and event evidence."""

import copy
import json
import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv.harness.runner import HarnessRunner  # noqa: E402
from freeciv_agent.config import (  # noqa: E402
    FreecivConfigError,
    condition,
    load_config,
    pf_pln_runtime_config,
    validate_config,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.pf_runtime import (  # noqa: E402
    PFRuntimeConfigurationError,
    build_controller_activation,
    build_runtime_activation,
    emit_runtime_activation,
    enabled_phases,
    validate_controller_policy,
    validate_runtime_activation,
)


def _policy(pressure=True, learning=True):
    return {
        "pressure_enabled": bool(pressure),
        "pressure_learning_enabled": bool(learning),
    }


def test_checked_profile_declares_exact_runtime_support_boundary():
    declaration = pf_pln_runtime_config()
    components = declaration["components"]
    assert sorted(row["phase"] for row in components.values()) == list(
        range(10))
    assert {
        row["phase"] for row in components.values()
        if row["support"] == "engine-live"
    } == {0, 1, 4, 9}
    assert {
        row["phase"] for row in components.values()
        if row["support"] == "component-only"
    } == {2, 3, 5, 6, 7, 8}


def test_profile_rejects_claiming_an_unwired_component_is_live():
    data = load_config()
    data["pf_pln_runtime"]["components"]["llm_gateway"][
        "support"] = "engine-live"
    with pytest.raises(FreecivConfigError, match="llm_gateway support"):
        validate_config(data)


def test_runtime_activation_is_derived_from_backend_capability_and_policy():
    declaration = pf_pln_runtime_config()
    full = condition("e_full_loop")["capabilities"]
    live = build_runtime_activation(
        declaration, "engine-live", full, _policy())
    assert enabled_phases(live) == (0, 1, 4, 9)
    assert all(
        not row["enabled"]
        for row in live["components"].values()
        if row["support"] == "component-only")

    pressure_off = build_runtime_activation(
        declaration, "engine-live", full, _policy(False, False))
    representative = build_runtime_activation(
        declaration, "representative", full, _policy())
    no_scheduler = build_runtime_activation(
        declaration,
        "engine-live",
        condition("b_state_oracle")["capabilities"],
        _policy(),
    )
    assert enabled_phases(pressure_off) == ()
    assert enabled_phases(representative) == ()
    assert enabled_phases(no_scheduler) == ()
    assert pressure_off["components"]["executable_semantics"][
        "reason"] == "policy-disabled:pressure_enabled"
    assert no_scheduler["components"]["multi_goal_field"][
        "reason"] == "capability-disabled:scheduler"


def test_runtime_report_tampering_fails_closed():
    capabilities = condition("e_full_loop")["capabilities"]
    report = build_runtime_activation(
        pf_pln_runtime_config(),
        "engine-live",
        capabilities,
        _policy(),
    )
    changed = copy.deepcopy(report)
    changed["components"]["llm_gateway"]["enabled"] = True
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="activation report mismatch"):
        validate_runtime_activation(
            changed, "engine-live", capabilities, _policy())


def test_activation_events_are_complete_schema_valid_and_causal():
    report = build_runtime_activation(
        pf_pln_runtime_config(),
        "engine-live",
        condition("e_full_loop")["capabilities"],
        _policy(),
    )
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "pf-runtime-events", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "e_full_loop",
            "manifest_identity": "runtime-test",
        })
        parent, events = emit_runtime_activation(
            writer, 0, root["event_id"], report, "e_full_loop", "main")
        validation = validate_file(path)
        rows = [
            json.loads(line) for line in open(path, encoding="utf-8")
            if line.strip()]

    assert validation.valid, [
        error.to_dict() for error in validation.errors]
    assert len(events) == 10
    assert parent == events[-1]["event_id"]
    assert [int(row["payload"]["labels"]["phase"])
            for row in rows[1:]] == list(range(10))
    assert {
        int(row["payload"]["labels"]["phase"])
        for row in rows[1:]
        if row["payload"]["value"] == 1.0
    } == {0, 1, 4, 9}
    assert rows[1]["caused_by"] == [root["event_id"]]
    for previous, current in zip(rows[1:], rows[2:]):
        assert current["caused_by"] == [previous["event_id"]]


def test_harness_manifest_records_backend_specific_activation():
    job = {
        "condition": "e_full_loop",
        "seed": 104729,
        "sequence": 0,
        "track": "main",
    }
    live = HarnessRunner(
        "unused", backend="engine-live", workers=1)._manifest(job, 0)
    representative = HarnessRunner(
        "unused", backend="representative", workers=1)._manifest(job, 0)
    assert enabled_phases(live["pf_pln_runtime"]) == (0, 1, 4, 9)
    assert enabled_phases(representative["pf_pln_runtime"]) == ()
    assert live["manifest_identity"] != representative[
        "manifest_identity"]


def test_source_sink_research_gate_requires_all_cheaper_stages():
    base = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_shadow",
        "pressure_packet_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
        "pressure_flow_research_entry_gate_required": True,
    }
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="protected candidate union"):
        validate_controller_policy(base)

    enabled = dict(base, **{
        "pressure_bridge_readout_policy":
            "corrected-probe-union",
        "pressure_flow_protected_candidate_union_enabled":
            True,
        "pressure_transition_value_enabled": True,
        "pressure_transition_value_authority_enabled": True,
        "pressure_path_persistence_enabled": True,
    })
    policy = validate_controller_policy(enabled)
    activation = build_controller_activation(enabled)

    assert policy[
        "pressure_flow_research_entry_gate_required"]
    assert activation["layers"][
        "path_persistence"]["enabled"]
    assert activation["layers"][
        "source_sink_flow"]["enabled"]


def test_frozen_transition_model_declaration_is_explicit():
    base = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_transition_value_enabled": True,
        "pressure_transition_value_read_only": True,
    }
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="explicit model path"):
        validate_controller_policy(base)
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="declared together"):
        validate_controller_policy(dict(
            base,
            pressure_transition_value_model_path=(
                "docs/freeciv/evidence/model.json")))

    policy = validate_controller_policy(dict(
        base,
        pressure_transition_value_model_path=(
            "docs/freeciv/evidence/model.json"),
        pressure_transition_value_model_identity=(
            "frozen-training-v1")))
    assert policy[
        "pressure_transition_value_read_only"]
    assert policy[
        "pressure_transition_value_model_identity"] == (
            "frozen-training-v1")


def test_grounded_domain_estimates_are_default_off_shadow_only():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    shadow = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_domain_estimates_enabled": True,
    })

    assert not default["layers"][
        "grounded_domain_estimates"]["enabled"]
    assert shadow["layers"][
        "grounded_domain_estimates"]["enabled"]
    assert shadow["controller_policy"][
        "pressure_domain_estimates_enabled"]
    assert not shadow["controller_policy"][
        "pressure_domain_estimates_authority_enabled"]


def test_grounded_domain_authority_fails_closed_during_shadow_stage():
    base = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_domain_estimates_enabled": True,
        "pressure_domain_estimates_authority_enabled": True,
    }
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="commit revalidation"):
        validate_controller_policy(base)
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="shadow-only GDO-1"):
        validate_controller_policy(dict(
            base,
            pressure_commit_revalidation_enabled=True))


def test_identity_resource_scheduler_is_default_off_and_packet_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "identity_resource_scheduler"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="requires packet scheduling"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_resource_scheduler_enabled": True,
        })

    shadow = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
    })
    assert shadow["layers"][
        "identity_resource_scheduler"]["enabled"]
    assert shadow["controller_policy"][
        "pressure_resource_scheduler_enabled"]


def test_city_defense_operations_are_default_off_and_lifecycle_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "city_defense_operations"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="require operation lifecycle"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_packet_scheduler_enabled": True,
            "pressure_city_defense_operations_enabled": True,
        })

    shadow = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_city_defense_operations_enabled": True,
    })
    assert shadow["layers"][
        "operation_lifecycle"]["enabled"]
    assert shadow["layers"][
        "city_defense_operations"]["enabled"]
    assert shadow["controller_policy"][
        "pressure_city_defense_operations_enabled"]


def test_native_movement_routes_are_default_off_and_grounded_defense_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "native_movement_routes"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="require grounded domain estimates"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_native_movement_routes_enabled": True,
        })

    enabled = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_city_defense_operations_enabled": True,
        "pressure_native_movement_routes_enabled": True,
    })
    assert enabled["layers"][
        "native_movement_routes"]["enabled"]
    assert enabled["controller_policy"][
        "pressure_native_movement_routes_enabled"]


def test_native_combat_and_atomic_operations_are_default_off_and_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "native_combat_probabilities"]["enabled"]
    assert not default["layers"][
        "combat_operations"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="require grounded domain estimates"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_native_combat_probabilities_enabled": True,
        })
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="combat operations require"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_domain_estimates_enabled": True,
            "pressure_native_combat_probabilities_enabled": True,
            "pressure_combat_operations_enabled": True,
        })

    enabled = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_native_combat_probabilities_enabled": True,
        "pressure_combat_operations_enabled": True,
    })
    assert enabled["layers"][
        "native_combat_probabilities"]["enabled"]
    assert enabled["layers"][
        "combat_operations"]["enabled"]


def test_transport_operations_are_default_off_and_grounded_stack_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "transport_operations"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="transport operations require"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_transport_operations_enabled": True,
        })

    enabled = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_native_movement_routes_enabled": True,
        "pressure_transport_operations_enabled": True,
    })
    assert enabled["layers"][
        "native_movement_routes"]["enabled"]
    assert enabled["layers"][
        "transport_operations"]["enabled"]
    assert enabled["controller_policy"][
        "pressure_transport_operations_enabled"]


def test_production_operations_are_default_off_and_grounded_stack_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "production_operations"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="production operations require"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_production_operations_enabled": True,
        })

    enabled = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_production_operations_enabled": True,
    })
    assert enabled["layers"][
        "production_operations"]["enabled"]
    assert enabled["controller_policy"][
        "pressure_production_operations_enabled"]


def test_research_operations_are_default_off_and_grounded_stack_gated():
    default = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
    })
    assert not default["layers"][
        "research_operations"]["enabled"]

    with pytest.raises(
            PFRuntimeConfigurationError,
            match="research operations require"):
        validate_controller_policy({
            "pressure_enabled": True,
            "pressure_semantics_version": "v2",
            "pressure_controller_mode": "scalar_v2",
            "pressure_research_operations_enabled": True,
        })

    enabled = build_controller_activation({
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "scalar_v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_resource_scheduler_enabled": True,
        "pressure_requirement_sets_enabled": True,
        "pressure_domain_estimates_enabled": True,
        "pressure_commit_revalidation_enabled": True,
        "pressure_operation_lifecycle_enabled": True,
        "pressure_research_operations_enabled": True,
    })
    assert enabled["layers"][
        "research_operations"]["enabled"]
    assert enabled["controller_policy"][
        "pressure_research_operations_enabled"]
