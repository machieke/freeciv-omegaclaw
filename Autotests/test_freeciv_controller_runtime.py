"""Complete S5 runtime modes, grouped configuration, and fail-closed gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (
        os.path.join(REPO, "src"),
        os.path.join(REPO, "benchmarks")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from freeciv_agent.pf_runtime import (  # noqa: E402
    CONTROLLER_MODES,
    PFRuntimeConfigurationError,
    build_controller_activation,
    controller_declaration,
)


def _v2(mode):
    value = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": mode,
        "pressure_packet_scheduler_enabled": True,
    }
    if mode in (
            "bridge_scalar", "unified_shadow",
            "bridge_scalar_advisory",
            "unified_flow_advisory",
            "unified_flow_live"):
        value["pressure_bridge_enabled"] = True
    if mode in (
            "unified_shadow",
            "unified_flow_advisory",
            "unified_flow_live"):
        value["pressure_flow_enabled"] = True
    if mode == "unified_flow_live":
        value.update({
            "pressure_flow_live_enabled": True,
            "pressure_commit_revalidation_enabled": True,
        })
    return value


def test_runtime_declares_every_recommended_mode_and_artifact_identity():
    declaration = controller_declaration()

    assert tuple(declaration["modes"]) == CONTROLLER_MODES
    assert declaration["adapter"] == (
        "impact-control-adapter/1.0")
    assert declaration["artifact_schemas"]["pressure"] == [
        "1.0", "2.0"]
    assert declaration["artifact_schemas"]["flow_patch"] == "1.0"
    assert declaration["fallback_modes"] == [
        "scalar_v2", "legacy_scalar", "canonical"]


@pytest.mark.parametrize("mode", CONTROLLER_MODES)
def test_every_declared_mode_has_a_valid_explicit_configuration(mode):
    if mode == "canonical":
        policy = {
            "pressure_enabled": False,
            "pressure_controller_mode": "canonical",
        }
    elif mode == "legacy_scalar":
        policy = {
            "pressure_enabled": True,
            "pressure_semantics_version": "v1",
            "pressure_controller_mode": mode,
        }
    else:
        policy = _v2(mode)
    activation = build_controller_activation(policy)

    assert activation["controller_policy"][
        "pressure_controller_mode"] == mode
    assert activation["artifact_schema_versions"][
        "pressure"] == (
            "1.0" if mode in (
                "canonical", "legacy_scalar") else "2.0")
    assert activation["fallback_available"]["canonical"]


def test_grouped_configuration_maps_to_flat_policy_and_is_reported():
    policy = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_flow_advisory",
        "pressure_v2": {
            "achievement_uncertainty_split": True,
            "signed_channels": True,
            "distributional_risk": True,
            "requirement_sets": True,
            "packet_scheduler": True,
        },
        "bridge": {
            "enabled": True,
            "estimator_policy": "importance_corrected",
            "importance_corrected": True,
            "reference_likelihood_support": True,
            "minimum_ess": 64.0,
        },
        "flow": {
            "enabled": True,
            "time_step": 0.05,
        },
        "safety": {
            "commit_revalidation": True,
        },
    }
    activation = build_controller_activation(policy)

    assert activation["controller_policy"][
        "pressure_packet_scheduler_enabled"]
    assert activation["controller_policy"][
        "pressure_bridge_enabled"]
    assert activation["controller_policy"][
        "pressure_flow_enabled"]
    assert activation["configuration_groups"][
        "bridge"]["minimum_ess"] == 64.0
    assert activation["estimator_policy"] == (
        "importance_corrected")
    assert activation["normalization_contract"] == (
        "robust-feature-scales/1.0")


@pytest.mark.parametrize("policy,reason", (
    ({
        "pressure_bridge_importance_corrected_enabled": True,
    }, "reference likelihood"),
    ({
        "pressure_shaping_capacity_structural_updates_enabled": True,
    }, "cannot authorize structural"),
    ({
        "pressure_llm_expansion_enabled": True,
    }, "validation packet budget"),
    ({
        "pressure_semantics_version": "v2",
        "pressure_packet_scheduler_enabled": True,
        "pressure_flow_enabled": True,
    }, "flow requires bridge"),
    ({
        "bridge": {
            "enabled": True,
            "unknown": 1,
        },
    }, "unknown fields"),
))
def test_invalid_controller_combinations_fail_closed(policy, reason):
    with pytest.raises(
            PFRuntimeConfigurationError,
            match=reason):
        build_controller_activation(policy)


def test_controller_activation_reports_live_layers_separately():
    policy = _v2("unified_shadow")
    report = build_controller_activation(policy)

    assert report["controller_policy"][
        "pressure_controller_mode"] == "unified_shadow"
    assert report["layers"][
        "bounded_staleness_view"]["enabled"]
    assert report["layers"][
        "decision_explanations"]["enabled"]
