import os
import sys
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.beliefs import (  # noqa: E402
    DeterministicRuleEngine,
    InferenceRequest,
    compare_technology_proof,
)
from freeciv_agent.oracle import (  # noqa: E402
    CrispStateView,
    DependencyOracle,
)
from freeciv_agent.rulesets.audit import audit  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    EntityRef,
    RulesetAtomSpaceStore,
    SymbolRef,
    ruleset_digest,
)
from freeciv_agent.state.grounded import GroundedRegistry  # noqa: E402


def _root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append("/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos",
        "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS ruleset integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def test_ir_2_semantics_are_canonical_typed_and_audited(ir):
    duplicate = compile_ruleset(_root(), "civ2civ3")
    report = audit(ir, _root())

    assert structural_hash(ir.to_dict()) == structural_hash(duplicate.to_dict())
    assert ir.to_dict()["schema_version"] == "2.0"
    assert report["passed"], report
    assert report["semantic_issues"] == []
    assert report["semantic_coverage"] == ir.semantics_coverage
    assert set(value.entity_kind for value in ir.capabilities) >= {
        "building-type", "government", "tech-type", "terrain", "unit-type",
    }
    assert any(
        dict(value.traits).get("trait-kind") == "roles"
        for value in ir.capabilities)
    assert all(value.provenance for value in ir.capabilities)
    assert all(
        value.completeness_spec is not None
        for value in ir.requirement_expressions
        if value.kind == "not")


def test_action_effect_gaps_are_explicit_and_never_promoted_to_exact(ir):
    effects = dict((value.effect_id, value) for value in ir.effects)

    assert ir.action_schemas
    assert all(value.legal_binding_required for value in ir.action_schemas)
    assert all(
        effects[effect_id].unknown_reason
        for schema in ir.action_schemas
        for effect_id in schema.effects)
    assert all(
        effects[effect_id].exact_grounding is None
        for schema in ir.action_schemas
        for effect_id in schema.effects)
    assert ir.semantics_coverage["unknown_effects"] == len(
        ir.action_schemas)
    assert ir.semantics_coverage["exact_ruleset_effects"] > 0


def test_grounding_specs_wrap_exact_legacy_signatures(ir):
    specs = dict((value.name, value) for value in ir.grounding_specs)

    assert set(specs) == GroundedRegistry.IMPLEMENTED
    assert all(value.dependency_paths for value in specs.values())
    assert all(value.witness_schema == "grounding-witness/1.0"
               for value in specs.values())
    assert {value.authority for value in specs.values()} == {
        "ruleset_exact", "snapshot_exact"}


def test_ruleset_projection_is_stable_provenanced_and_numeric_free(ir):
    store = RulesetAtomSpaceStore()
    first = store.build(ir)
    second = store.build(ir)
    digest = ruleset_digest(ir)

    assert first == second
    assert first.revision_id == second.revision_id
    assert len(first.records) < 25000
    assert all(value.key.namespace == AtomNamespace.RULESET
               for value in first.records)
    assert all(value.authority == AuthorityClass.RULESET_EXACT
               for value in first.records)
    assert all(value.validity.ruleset_digest == digest
               for value in first.records)
    assert all(value.supports and value.provenance_ids
               for value in first.records)
    assert all(
        isinstance(argument, (EntityRef, SymbolRef))
        for value in first.records
        for argument in value.key.arguments)
    assert any(
        value.key.predicate == "effect-status"
        and value.key.arguments[1] == SymbolRef("effect-status", "unknown")
        for value in first.records)


def test_ruleset_digest_change_never_reuses_static_atoms(ir):
    changed_hashes = dict(ir.source_hashes)
    first_key = sorted(changed_hashes)[0]
    changed_hashes[first_key] = "f" * 64
    changed = replace(ir, source_hashes=changed_hashes)
    store = RulesetAtomSpaceStore()
    first = store.build(ir)
    second = store.build(changed)

    assert ruleset_digest(ir) != ruleset_digest(changed)
    assert first.revision_id != second.revision_id
    assert not set(first.dependency_index.atom_by_id).intersection(
        second.dependency_index.atom_by_id)


def test_generic_technology_proof_matches_legacy_oracle_for_all_targets(ir):
    oracle = DependencyOracle(ir)
    technologies = tuple(
        value.rule_name for value in ir.rules
        if value.target_kind == "tech")
    empty = CrispStateView(
        "generic-parity-empty", known_techs=(), player="0")
    empty_reports = [
        compare_technology_proof(ir, empty, "0", technology, oracle)
        for technology in technologies]

    assert all(value["status_parity"] for value in empty_reports)
    assert all(value["prerequisite_parity"] for value in empty_reports)
    known = tuple(sorted(set(
        prerequisite
        for value in empty_reports
        for prerequisite in value["legacy_prerequisites"])))
    complete = CrispStateView(
        "generic-parity-complete", known_techs=known, player="0")
    complete_reports = [
        compare_technology_proof(ir, complete, "0", technology, oracle)
        for technology in technologies]

    assert all(value["status_parity"] for value in complete_reports)
    assert all(value["prerequisite_parity"] for value in complete_reports)


def test_generic_proof_budget_exhaustion_is_unknown_not_false(ir):
    target = next(
        value.rule_name for value in ir.rules
        if value.target_kind == "tech" and len(value.antecedents) > 1)
    request = InferenceRequest(
        "prove",
        {"predicate": "researchable", "arguments": ["0", target]},
        "scope:test:proof",
        frozenset((AtomNamespace.AUTHORITATIVE, AtomNamespace.RULESET)),
        maximum_depth=1,
        maximum_bindings=1,
        maximum_rule_fires=1,
    )
    outcome = DeterministicRuleEngine(ir).prove(
        "researchable",
        ("0", target),
        CrispStateView("budget", known_techs=(), player="0"),
        request,
    )

    assert outcome.status == "UNKNOWN"
    assert outcome.truncated
    assert ("budget-exhausted", "rule-fires") in outcome.blockers
