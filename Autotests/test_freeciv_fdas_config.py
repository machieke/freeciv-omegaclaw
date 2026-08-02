import copy
import json
import os
import sys

import pytest
import yaml


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.state.atomspace import DependentAtomSpaceConfig  # noqa: E402


def _values():
    with open(os.path.join(REPO, "profile", "dependent_atomspace.yaml"),
              encoding="utf-8") as stream:
        config = yaml.safe_load(stream)["dependent_atomspace"]
    with open(os.path.join(REPO, "profile", "fdas_manifest.json"),
              encoding="utf-8") as stream:
        manifest = json.load(stream)
    return config, manifest


def test_default_configuration_is_strict_shadow_only_and_manifest_valid():
    value, manifest = _values()
    config = DependentAtomSpaceConfig.from_dict(value, manifest)

    assert config.enabled is False
    assert config.shadow_enabled is True
    assert config.authority_enabled is False
    assert not any(config.section("domain_authority").values())
    assert not any(config.section("learning").values())
    assert config.section("projection")["operations"] is True
    assert config.to_dict() == value


def test_checked_city_stability_authority_profile_is_narrow_and_explicit():
    with open(os.path.join(
            REPO, "profile",
            "dependent_atomspace_city_stability_authority.yaml"),
            encoding="utf-8") as stream:
        value = yaml.safe_load(stream)["dependent_atomspace"]
    with open(os.path.join(
            REPO, "profile",
            "fdas_manifest_city_stability_authority.json"),
            encoding="utf-8") as stream:
        manifest = json.load(stream)

    config = DependentAtomSpaceConfig.from_dict(value, manifest)

    assert config.enabled is True
    assert config.authority_enabled is True
    assert config.shadow_refresh_policy == "every-snapshot"
    assert config.section("domain_authority") == {
        "city_defense": False,
        "city_production": False,
        "city_stability": True,
        "combat": False,
        "expansion": False,
        "local_movement": False,
        "research": False,
        "transport": False,
    }
    assert manifest["status"] == "bounded-authority"
    assert manifest["policy_authority"] is True


def test_checked_defense_shadow_profile_is_narrow_and_non_authoritative():
    with open(os.path.join(
            REPO, "profile", "dependent_atomspace_defense_shadow.yaml"),
            encoding="utf-8") as stream:
        value = yaml.safe_load(stream)["dependent_atomspace"]
    with open(os.path.join(
            REPO, "profile", "fdas_manifest_defense_shadow.json"),
            encoding="utf-8") as stream:
        manifest = json.load(stream)

    config = DependentAtomSpaceConfig.from_dict(value, manifest)

    assert config.enabled is True
    assert config.shadow_enabled is True
    assert config.authority_enabled is False
    assert config.shadow_refresh_policy == "turn-boundary-before-readout"
    assert config.cold_verify_sample_rate == 0.05
    assert config.section("projection") == {
        "beliefs": False,
        "city": True,
        "combat": False,
        "economy": True,
        "empire": True,
        "legacy_compatibility": True,
        "operations": True,
        "population_recovery": False,
        "region": True,
        "research": False,
        "route_corridors": False,
        "ruleset": True,
        "settlement_sites": False,
        "transport": False,
        "unit": True,
        "world": True,
    }
    assert not any(config.section("domain_authority").values())
    assert not any(config.section("learning").values())
    assert manifest["status"] == "shadow-live"
    assert manifest["policy_authority"] is False
    assert manifest["capabilities"]["unit_domain_projection"] == (
        "shadow-live")
    assert manifest["capabilities"]["defense_operation_reconciliation"] == (
        "shadow-live")


def test_checked_defense_authority_profile_requires_exact_bounded_stack():
    with open(os.path.join(
            REPO, "profile", "dependent_atomspace_defense_authority.yaml"),
            encoding="utf-8") as stream:
        value = yaml.safe_load(stream)["dependent_atomspace"]
    with open(os.path.join(
            REPO, "profile", "fdas_manifest_defense_authority.json"),
            encoding="utf-8") as stream:
        manifest = json.load(stream)

    config = DependentAtomSpaceConfig.from_dict(value, manifest)

    assert config.enabled is True
    assert config.authority_enabled is True
    assert config.shadow_refresh_policy == "every-snapshot"
    assert config.section("projection")["city"] is False
    assert config.section("projection")["economy"] is False
    assert config.section("projection")["region"] is False
    assert config.section("projection")["legacy_compatibility"] is False
    assert config.section("events")["support_level"] == "none"
    assert config.section("domain_authority") == {
        "city_defense": True,
        "city_production": False,
        "city_stability": False,
        "combat": False,
        "expansion": False,
        "local_movement": False,
        "research": False,
        "transport": False,
    }
    assert config.section("learning") == {
        "contextual_conductance_authority_enabled": False,
        "contextual_conductance_enabled": True,
        "episode_attribution_enabled": True,
        "induced_rule_readout_enabled": False,
        "induction_enabled": False,
    }
    assert manifest["status"] == "bounded-authority"
    assert manifest["policy_authority"] is True
    for capability in (
            "dependent_atom_pressure_adapter",
            "defense_operation_reconciliation",
            "defense_requirement_projection",
            "fdas_exact_commit_validation",
            "fdas_resource_packet_bridge",
            "operation_atom_projection",
            "unit_domain_projection"):
        assert manifest["capabilities"][capability] == "bounded-authority"

    for capability in (
            "contextual_conductance_learning",
            "episode_attribution",
            "episode_control_learning_bridge",
            "fdas_learning_diagnostics"):
        assert manifest["capabilities"][capability] == "shadow-live"

    for capability in (
            "defense_operation_reconciliation",
            "defense_requirement_projection",
            "operation_atom_projection"):
        rejected = copy.deepcopy(manifest)
        rejected["capabilities"][capability] = "shadow-live"
        with pytest.raises(ValueError, match=capability):
            DependentAtomSpaceConfig.from_dict(value, rejected)


def test_unknown_configuration_fields_and_invalid_budgets_fail_closed():
    value, manifest = _values()
    unknown = copy.deepcopy(value)
    unknown["projection"]["magic"] = True
    with pytest.raises(ValueError, match="unknown"):
        DependentAtomSpaceConfig.from_dict(unknown, manifest)

    invalid = copy.deepcopy(value)
    invalid["materialization"]["maximum_atoms_global"] = 0
    with pytest.raises(ValueError, match="must be positive"):
        DependentAtomSpaceConfig.from_dict(invalid, manifest)


def test_authority_requires_bounded_manifest_capabilities():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"]["city_stability"] = True

    accepted_manifest = copy.deepcopy(manifest)
    accepted_manifest["status"] = "bounded-authority"
    accepted_manifest["policy_authority"] = True
    with pytest.raises(ValueError, match="requires bounded-authority"):
        DependentAtomSpaceConfig.from_dict(value, accepted_manifest)

    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "city_domain_projection"):
        accepted_manifest["capabilities"][name] = "bounded-authority"
    config = DependentAtomSpaceConfig.from_dict(value, accepted_manifest)
    assert config.authority_enabled
    assert config.section("domain_authority")["city_stability"]


def test_domain_authority_cannot_bypass_global_gates():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["domain_authority"]["city_production"] = True
    with pytest.raises(ValueError, match="authority gate"):
        DependentAtomSpaceConfig.from_dict(value, manifest)


@pytest.mark.parametrize(("domain", "capabilities"), (
    ("expansion", (
        "region_domain_projection",
        "route_corridor_projection",
        "settlement_site_projection",
        "population_recovery_projection",
        "expansion_operation_projection",
    )),
    ("transport", (
        "transport_capability_projection",
        "transport_operation_projection",
    )),
    ("combat", (
        "combat_task_force_projection",
        "combat_operation_projection",
    )),
))
def test_phase7_authority_requires_every_exact_domain_capability(
        domain, capabilities):
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"][domain] = True
    accepted_manifest = copy.deepcopy(manifest)
    accepted_manifest["status"] = "bounded-authority"
    accepted_manifest["policy_authority"] = True
    value["projection"]["unit"] = True
    value["projection"]["region"] = True
    value["projection"].update({
        "combat": True,
        "population_recovery": True,
        "route_corridors": True,
        "settlement_sites": True,
        "transport": True,
    })
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation"):
        accepted_manifest["capabilities"][name] = "bounded-authority"

    with pytest.raises(ValueError, match="requires bounded-authority"):
        DependentAtomSpaceConfig.from_dict(value, accepted_manifest)

    for name in capabilities:
        accepted_manifest["capabilities"][name] = "bounded-authority"
    config = DependentAtomSpaceConfig.from_dict(value, accepted_manifest)

    assert config.section("domain_authority")[domain] is True


def test_belief_projection_requires_declared_component():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["projection"]["beliefs"] = True
    config = DependentAtomSpaceConfig.from_dict(value, manifest)
    assert config.section("projection")["beliefs"] is True

    missing = copy.deepcopy(manifest)
    missing["capabilities"]["belief_domain_projection"] = "not-built"
    with pytest.raises(ValueError, match="belief_domain_projection"):
        DependentAtomSpaceConfig.from_dict(value, missing)


def test_local_movement_authority_requires_both_focused_capabilities():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"]["local_movement"] = True
    value["projection"].update({
        "region": True, "route_corridors": True, "unit": True})
    promoted = copy.deepcopy(manifest)
    promoted["status"] = "bounded-authority"
    promoted["policy_authority"] = True
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "unit_domain_projection"):
        promoted["capabilities"][name] = "bounded-authority"

    with pytest.raises(ValueError, match="region_domain_projection"):
        DependentAtomSpaceConfig.from_dict(value, promoted)
    promoted["capabilities"][
        "region_domain_projection"] = "bounded-authority"
    with pytest.raises(ValueError, match="route_corridor_projection"):
        DependentAtomSpaceConfig.from_dict(value, promoted)
    promoted["capabilities"][
        "route_corridor_projection"] = "bounded-authority"

    config = DependentAtomSpaceConfig.from_dict(value, promoted)
    assert config.section("domain_authority")["local_movement"] is True


@pytest.mark.parametrize(("projection", "capability"), (
    ("combat", "combat_task_force_projection"),
    ("population_recovery", "population_recovery_projection"),
    ("region", "region_domain_projection"),
    ("route_corridors", "route_corridor_projection"),
    ("settlement_sites", "settlement_site_projection"),
    ("transport", "transport_capability_projection"),
))
def test_focused_shadow_projection_flags_are_independently_manifest_bound(
        projection, capability):
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["enabled"] = True
    value["projection"][projection] = True
    missing = copy.deepcopy(manifest)
    missing["capabilities"][capability] = "not-built"

    with pytest.raises(ValueError, match=capability):
        DependentAtomSpaceConfig.from_dict(value, missing)

    config = DependentAtomSpaceConfig.from_dict(value, manifest)
    assert config.section("projection")[projection] is True


def test_uncertain_assessment_requires_shadow_live_belief_and_observation():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["projection"]["beliefs"] = True
    value["inference"]["uncertain_assessment_enabled"] = True

    with pytest.raises(ValueError, match="requires shadow-live"):
        DependentAtomSpaceConfig.from_dict(value, manifest)

    accepted = copy.deepcopy(manifest)
    accepted["status"] = "bounded-authority"
    accepted["policy_authority"] = True
    accepted["capabilities"]["belief_domain_projection"] = "shadow-live"
    accepted["capabilities"]["observation_pressure_planning"] = "shadow-live"
    config = DependentAtomSpaceConfig.from_dict(value, accepted)
    assert config.section("inference")["uncertain_assessment_enabled"] is True


def test_authority_with_uncertain_assessment_requires_bounded_belief_firewall():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["projection"]["beliefs"] = True
    value["inference"]["uncertain_assessment_enabled"] = True
    value["domain_authority"]["city_stability"] = True
    accepted = copy.deepcopy(manifest)
    accepted["status"] = "bounded-authority"
    accepted["policy_authority"] = True
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "city_domain_projection"):
        accepted["capabilities"][name] = "bounded-authority"
    for name in (
            "belief_domain_projection",
            "observation_pressure_planning"):
        accepted["capabilities"][name] = "shadow-live"

    with pytest.raises(ValueError, match="requires bounded-authority"):
        DependentAtomSpaceConfig.from_dict(value, accepted)

    for name in (
            "belief_domain_projection",
            "observation_pressure_planning"):
        accepted["capabilities"][name] = "bounded-authority"
    config = DependentAtomSpaceConfig.from_dict(value, accepted)
    assert config.authority_enabled is True


def test_episode_learning_requires_explicit_shadow_live_capabilities():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["enabled"] = True
    value["learning"]["episode_attribution_enabled"] = True

    with pytest.raises(ValueError, match="requires shadow-live"):
        DependentAtomSpaceConfig.from_dict(value, manifest)

    accepted = copy.deepcopy(manifest)
    for name in ("episode_attribution", "fdas_learning_diagnostics"):
        accepted["capabilities"][name] = "shadow-live"
    value["learning"]["contextual_conductance_enabled"] = True
    with pytest.raises(ValueError, match="requires shadow-live"):
        DependentAtomSpaceConfig.from_dict(value, accepted)

    for name in (
            "episode_control_learning_bridge",
            "contextual_conductance_learning"):
        accepted["capabilities"][name] = "shadow-live"
    config = DependentAtomSpaceConfig.from_dict(value, accepted)
    assert config.section("learning")["contextual_conductance_enabled"]


def test_learning_dependencies_fail_closed_before_manifest_validation():
    value, manifest = _values()
    invalid = copy.deepcopy(value)
    invalid["learning"]["contextual_conductance_enabled"] = True
    with pytest.raises(ValueError, match="requires episode attribution"):
        DependentAtomSpaceConfig.from_dict(invalid, manifest)

    invalid = copy.deepcopy(value)
    invalid["learning"]["induced_rule_readout_enabled"] = True
    with pytest.raises(ValueError, match="requires induction"):
        DependentAtomSpaceConfig.from_dict(invalid, manifest)


def test_learning_authority_requires_holdout_and_versioned_bounded_capability():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    for key in (
            "episode_attribution_enabled",
            "contextual_conductance_enabled",
            "contextual_conductance_authority_enabled",
            "induction_enabled",
            "induced_rule_readout_enabled"):
        value["learning"][key] = True
    accepted = copy.deepcopy(manifest)
    accepted["status"] = "bounded-authority"
    accepted["policy_authority"] = True
    for name in (
            "episode_attribution", "fdas_learning_diagnostics",
            "episode_control_learning_bridge",
            "contextual_conductance_learning",
            "episode_induction_bridge",
            "quarantined_contextual_induction"):
        accepted["capabilities"][name] = "bounded-authority"

    with pytest.raises(ValueError, match="holdout_gate"):
        DependentAtomSpaceConfig.from_dict(value, accepted)

    accepted["capabilities"][
        "contextual_conductance_holdout_gate"] = "bounded-authority"
    with pytest.raises(ValueError, match="induced_rule_heldout_gate"):
        DependentAtomSpaceConfig.from_dict(value, accepted)

    accepted["capabilities"][
        "induced_rule_heldout_gate"] = "bounded-authority"
    config = DependentAtomSpaceConfig.from_dict(value, accepted)
    assert config.section("learning")[
        "contextual_conductance_authority_enabled"]
    assert config.section("learning")["induced_rule_readout_enabled"]


def test_authority_rejects_missing_aggregate_manifest_promotion():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"]["city_stability"] = True
    promoted = copy.deepcopy(manifest)
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "city_domain_projection"):
        promoted["capabilities"][name] = "bounded-authority"

    with pytest.raises(ValueError, match="manifest policy authority"):
        DependentAtomSpaceConfig.from_dict(value, promoted)
    promoted["policy_authority"] = True
    with pytest.raises(ValueError, match="aggregate manifest status"):
        DependentAtomSpaceConfig.from_dict(value, promoted)


def test_preacceptance_profile_cannot_disable_cold_verification():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value["cold_verify_sample_rate"] = 0.0
    with pytest.raises(ValueError, match="cannot be disabled"):
        DependentAtomSpaceConfig.from_dict(value, manifest)


def test_turn_sampled_shadow_cannot_be_combined_with_authority():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({
        "authority_enabled": True,
        "enabled": True,
        "shadow_refresh_policy": "turn-boundary-before-readout",
    })

    with pytest.raises(ValueError, match="every-snapshot materialization"):
        DependentAtomSpaceConfig.from_dict(value, manifest)


def test_authority_requires_live_domain_projection_and_explanations():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"]["city_stability"] = True
    promoted = copy.deepcopy(manifest)
    promoted["status"] = "bounded-authority"
    promoted["policy_authority"] = True
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "city_domain_projection"):
        promoted["capabilities"][name] = "bounded-authority"

    value["projection"]["operations"] = False
    with pytest.raises(ValueError, match="operations projection"):
        DependentAtomSpaceConfig.from_dict(value, promoted)
    value["projection"]["operations"] = True
    value["events"]["explanation_capture"] = False
    with pytest.raises(ValueError, match="explanation capture"):
        DependentAtomSpaceConfig.from_dict(value, promoted)


def test_research_authority_requires_generic_engine_projection_and_parity():
    value, manifest = _values()
    value = copy.deepcopy(value)
    value.update({"enabled": True, "authority_enabled": True})
    value["domain_authority"]["research"] = True
    promoted = copy.deepcopy(manifest)
    promoted["status"] = "bounded-authority"
    promoted["policy_authority"] = True
    for name in (
            "dependent_atom_pressure_adapter",
            "fdas_resource_packet_bridge",
            "fdas_exact_commit_validation",
            "ruleset_domain_projection",
            "generic_rule_execution"):
        promoted["capabilities"][name] = "bounded-authority"

    with pytest.raises(ValueError, match="generic rule engine"):
        DependentAtomSpaceConfig.from_dict(value, promoted)
    value["inference"]["generic_rule_engine_enabled"] = True
    config = DependentAtomSpaceConfig.from_dict(value, promoted)
    assert config.section("domain_authority")["research"] is True
