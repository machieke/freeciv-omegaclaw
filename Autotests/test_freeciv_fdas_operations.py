import copy
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    CandidateOperationFactory,
    GoalFactory,
    OperationState,
    OperationStore,
)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    CityEconomyProjector,
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    OperationProjector,
    operation_predicate_registry,
    ruleset_digest,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append("/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS operation integration")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _case(ir):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["cities"]["3"].update({
        "disorder": True,
        "surplus": [0, 0, 4, 1, 0, 9],
    })
    payload["legal_actions"].append({
        "type": "city_governor",
        "city_id": 3,
        "target": {
            "food_surplus_reserve": 1,
            "require_happy": True,
        },
        "is_valid": True,
    })
    snapshot = ProxyStateDTO.parse(
        "fdas-operations", 450, payload).to_snapshot()
    digest = ruleset_digest(ir)
    city = CityEconomyProjector(ir, digest)
    city_store = DependentAtomSpaceStore(domain_projector=city)
    city_revision = city_store.build(snapshot)
    goals = GoalFactory().instantiate(
        city_revision,
        city_store.query_current(
            snapshot.identity.game_id, snapshot.player_id),
    )
    candidates = CandidateOperationFactory(ir, digest).instantiate(
        snapshot, goals)
    operation_store = OperationStore("fdas-operation-projection-test")
    for candidate in candidates:
        operation_store.propose(
            candidate.operation, snapshot.snapshot_id, snapshot.turn)
    projector = CompositeDomainProjector((
        city,
        OperationProjector(operation_store),
    ))
    store = DependentAtomSpaceStore(domain_projector=projector)
    revision = store.build(snapshot)
    return snapshot, operation_store, store, revision, candidates


def _operation_records(revision):
    return tuple(
        value for value in revision.records
        if value.key.namespace == AtomNamespace.OPERATION)


def test_operation_projection_is_lossless_structural_and_dependency_backed(ir):
    snapshot, operation_store, _store, revision, candidates = _case(ir)
    records = _operation_records(revision)
    predicates = {value.key.predicate for value in records}

    assert len(revision.dependency_index.operation_atom_ids) == len(candidates)
    assert {
        "operation-current-step",
        "operation-participant",
        "operation-participant-role",
        "operation-ruleset",
        "operation-serves-goal",
        "operation-specification",
        "operation-state",
        "operation-step",
        "operation-step-action",
        "operation-step-completes",
        "operation-step-requires",
        "operation-target",
        "operation-type",
    }.issubset(predicates)
    assert all(
        value.authority == AuthorityClass.CONTROL_MODEL
        for value in records)
    assert all(value.truth == {"structural": True} for value in records)
    assert all(
        dependency.key.kind == "operation-revision"
        for value in records
        for support in value.supports
        for dependency in support.dependencies)
    assert all(
        value.validity.snapshot_id == snapshot.snapshot_id
        for value in records)
    assert all(
        operation_store.get(candidate.operation.operation_id).spec.spec_digest
        in {
            argument.symbol
            for value in records
            if value.key.predicate == "operation-specification"
            for argument in value.key.arguments
            if getattr(argument, "catalog", None) == "operation-spec-digest"
        }
        for candidate in candidates)


def test_operation_progress_rematerialization_changes_only_progress_dependents(ir):
    snapshot, operation_store, store, before, candidates = _case(ir)
    operation_id = candidates[0].operation.operation_id
    immutable_before = {
        value.atom_id: value
        for value in _operation_records(before)
        if value.key.predicate not in (
            "operation-current-step", "operation-state")
    }

    operation_store.transition(
        operation_id,
        OperationState.BLOCKED,
        snapshot.snapshot_id,
        snapshot.turn,
        reason="exact-requirement-unavailable",
    )
    after = store.rematerialize(snapshot)
    immutable_after = {
        value.atom_id: value
        for value in _operation_records(after)
        if value.key.predicate not in (
            "operation-blocked-reason",
            "operation-current-step",
            "operation-state",
        )
    }
    state = next(
        value for value in _operation_records(after)
        if (value.key.predicate == "operation-state"
            and value.key.arguments[0].entity_id == operation_id))
    reason = next(
        value for value in _operation_records(after)
        if (value.key.predicate == "operation-blocked-reason"
            and value.key.arguments[0].entity_id == operation_id))

    assert after.revision_id != before.revision_id
    assert immutable_after == immutable_before
    assert state.key.arguments[1].symbol == "blocked"
    assert state.lifecycle == "blocked"
    assert reason.key.arguments[1].symbol == "exact-requirement-unavailable"
    assert operation_id in after.dependency_index.operation_atom_ids
    assert after.metrics.invalidated_supports >= 2


def test_operation_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    component = {
        value["name"] for value in catalog["predicates"]
        if (value["namespace"] == "operation"
            and value["status"] == "component-only")}

    assert component == set(
        operation_predicate_registry().predicates
    ).difference({
        value["name"] for value in catalog["predicates"]
        if value["status"] == "legacy"
    })


def test_operation_projection_rejects_quarantined_store(ir):
    snapshot, _operation_store, _store, _revision, _candidates = _case(ir)
    quarantined = OperationStore(
        "fdas-operation-projection-test",
        quarantine_reason="integrity-check-failed")
    projector = OperationProjector(quarantined)

    with pytest.raises(ValueError, match="quarantined"):
        projector.scopes(snapshot)
