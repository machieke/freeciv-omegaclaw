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
    assert config.section("projection")["operations"] is True
    assert config.to_dict() == value


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

    with pytest.raises(ValueError, match="requires bounded-authority"):
        DependentAtomSpaceConfig.from_dict(value, manifest)

    accepted_manifest = copy.deepcopy(manifest)
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
