import json
import os
import subprocess
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atoms import (  # noqa: E402
    LEGACY_AUTHORITATIVE_PREDICATES,
    LEGACY_PROJECTED_PREDICATES,
    LEGACY_VISIBLE_PREDICATES,
    QUANTITATIVE_PREDICATES,
)
from freeciv_agent.state.grounded import GroundedRegistry  # noqa: E402


def _json(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as stream:
        return json.load(stream)


def test_fdas_manifest_exposes_only_evidenced_component_capabilities():
    manifest = _json("profile/fdas_manifest.json")

    assert manifest["schema_version"] == "1.0"
    assert manifest["status"] == "component-only"
    assert manifest["component_enabled"] is True
    assert manifest["policy_authority"] is False
    assert manifest["capabilities"]
    component_only = {
        "dependent_atomspace_core",
        "dependent_atom_pressure_adapter",
        "dependency_truth_maintenance",
        "fdas_exact_commit_validation",
        "fdas_resource_packet_bridge",
        "city_domain_projection",
        "generic_rule_execution",
        "incremental_snapshot_projection",
        "operation_atom_projection",
        "ruleset_domain_projection",
    }
    assert {
        key for key, value in manifest["capabilities"].items()
        if value == "component-only"
    } == component_only
    assert {
        value for key, value in manifest["capabilities"].items()
        if key not in component_only
    } == {"not-built"}


def test_fdas_phase0_catalog_freezes_legacy_projection_and_groundings():
    catalog = _json("profile/fdas_catalog.json")
    legacy_predicates = {
        row["name"] for row in catalog["predicates"]
        if row["status"] == "legacy"
    }
    legacy_groundings = {
        row["name"] for row in catalog["groundings"]
        if row["status"] == "legacy"
    }

    assert legacy_predicates == LEGACY_PROJECTED_PREDICATES
    assert legacy_groundings == GroundedRegistry.IMPLEMENTED
    assert not legacy_predicates.intersection(QUANTITATIVE_PREDICATES)
    assert {
        row["name"] for row in catalog["predicates"]
        if row["namespace"] == "authoritative"
        and row["status"] == "legacy"
    } == LEGACY_AUTHORITATIVE_PREDICATES
    assert {
        row["name"] for row in catalog["predicates"]
        if row["namespace"] == "observation"
        and row["status"] == "legacy"
    } == LEGACY_VISIBLE_PREDICATES
    assert len(catalog["namespaces"]) == len(set(catalog["namespaces"]))
    assert all(
        row["arity"] == len(row["argument_kinds"])
        for row in catalog["predicates"])


def test_fdas_phase0_baseline_is_self_hashed_and_source_complete():
    baseline = _json("benchmarks/fdas/phase0-baseline.json")
    semantic = baseline["semantic"]
    fixtures = semantic["fixtures"]

    assert baseline["report_hash"] == structural_hash(semantic)
    assert semantic["authority"] == "diagnostic-replay-only"
    assert semantic["capability_status"] == "not-built"
    assert len(fixtures) == semantic["manifest"]["fixture_count"] == 13
    assert semantic["inventory"]["legacy_projection"] == {
        "all_predicates": sorted(LEGACY_PROJECTED_PREDICATES),
        "authoritative_predicates": sorted(LEGACY_AUTHORITATIVE_PREDICATES),
        "visible_predicates": sorted(LEGACY_VISIBLE_PREDICATES),
    }
    assert semantic["inventory"]["grounded_predicates"] == sorted(
        GroundedRegistry.IMPLEMENTED)
    for fixture in fixtures:
        assert fixture["candidate_count"] == len(fixture["candidates"])
        assert fixture["projection"]["uncertain"] == []
        selected_id = fixture["source_selection"]["selected_operation_id"]
        assert selected_id in {
            row["operation_id"] for row in fixture["candidates"]}
        assert fixture["technology_proof"]["proof_hash"]
        assert fixture["adapter"]["graph_hash"]


def test_fdas_phase0_generator_reproduces_semantic_hash():
    completed = subprocess.run(
        [
            sys.executable,
            os.path.join(REPO, "scripts", "run_fdas_phase0_baseline.py"),
            "--check",
            "--iterations",
            "1",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    baseline = _json("benchmarks/fdas/phase0-baseline.json")
    assert completed.stdout.strip() == baseline["report_hash"]
