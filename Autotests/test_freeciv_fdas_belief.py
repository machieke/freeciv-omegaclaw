import copy
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.beliefs import (  # noqa: E402
    BeliefKey,
    BeliefStore,
    Evidence,
    ModelProvenance,
)
from freeciv_agent.config import belief_config  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import ObservationPolicy  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    BeliefProjector,
    DependentAtomSpaceStore,
    belief_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")
GAME_ID = "fdas-belief"


def _snapshot(turn, seq):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["turn"] = turn
    return ProxyStateDTO.parse(GAME_ID, seq, payload).to_snapshot()


def _evidence(provenance, turn=1, strength=1.0, location=(3, 4),
              selection_policy=None, model_provenance=None):
    return Evidence(
        provenance, GAME_ID, turn, location,
        "simulator" if model_provenance is not None else "visible-map",
        BeliefKey("opponent-has-technology", ("fixed-ai", "Navigation")),
        strength, 0.6 if model_provenance is not None else 0.8,
        "fixed-ai", "civ2civ3", "opponent-model/1.0",
        selection_policy=selection_policy,
        model_provenance=model_provenance,
    )


def _belief_records(revision):
    scopes = {
        value.scope_id for value in revision.scopes
        if value.scope_kind == "opponent-belief"}
    return tuple(
        value for value in revision.records
        if value.key.scope_id in scopes)


def test_belief_revision_projects_only_uncertain_and_diagnostic_records():
    store = BeliefStore(belief_config())
    store.observe(_evidence("visible-navigation"))
    snapshot = _snapshot(1, 900)
    revision = DependentAtomSpaceStore(
        domain_projector=BeliefProjector(store)).build(snapshot)
    records = _belief_records(revision)

    assert {value.key.predicate for value in records} == {
        "belief-about-opponent",
        "belief-context",
        "belief-current-revision",
        "belief-proposition",
        "belief-supported-by-evidence",
    }
    assert all(value.key.namespace == AtomNamespace.BELIEF
               for value in records)
    assert all(value.authority == AuthorityClass.UNCERTAIN_BELIEF
               for value in records)
    assert all(value.truth["crisp"] is False for value in records)
    assert all(value.validity.valid_through_turn == 1 for value in records)
    assert any(
        dependency.key.kind == "belief-revision"
        for value in records for support in value.supports
        for dependency in support.dependencies)


def test_simulator_identity_cap_and_selection_adjustment_are_projected():
    store = BeliefStore(belief_config())
    model = ModelProvenance(
        "simulator", "freeciv-forward-model", "1.0",
        structural_hash({"model": "freeciv-forward-model/1.0"}),
        False, 0.6)
    policy = ObservationPolicy(
        "resolve-navigation", "observe", 2.0, propensity=0.5)
    store.observe(_evidence(
        "simulated-navigation", selection_policy=policy,
        model_provenance=model))
    revision = DependentAtomSpaceStore(
        domain_projector=BeliefProjector(store)).build(_snapshot(1, 901))
    records = _belief_records(revision)

    assert "belief-model-source" in {
        value.key.predicate for value in records}
    assert "belief-selection-adjusted" in {
        value.key.predicate for value in records}
    model_record = next(
        value for value in records
        if value.key.predicate == "belief-model-source")
    assert model_record.supports[0].confidence_cap == 0.6
    # Selection propensity widens uncertainty in BeliefStore before projection.
    assert model_record.truth["confidence"] == 0.3


def test_stale_belief_projection_fails_until_store_decay_is_current():
    store = BeliefStore(belief_config())
    store.observe(_evidence("visible-navigation"))
    projector = BeliefProjector(store)

    with pytest.raises(ValueError, match="decayed"):
        DependentAtomSpaceStore(
            domain_projector=projector).build(_snapshot(2, 902))

    before = store.get(_evidence("unused").key).confidence
    store.decay_to(2)
    revision = DependentAtomSpaceStore(
        domain_projector=projector).build(_snapshot(2, 903))
    after = next(
        value.truth["confidence"] for value in _belief_records(revision)
        if value.key.predicate == "belief-proposition")

    assert after < before


def test_conflict_and_quarantine_are_explicit_but_never_authoritative():
    store = BeliefStore(belief_config())
    left = _evidence("left", strength=1.0, location=(3, 4))
    right = _evidence("right", strength=0.0, location=(8, 9))
    store.observe(left)
    store.observe(right)
    conflict = store.conflicts()[0]
    quarantine = next(
        value for value in store.context_quarantine_operations(
            conflict.conflict_id, 1)
        if value.context_id == left.context_id)
    store.apply_context_quarantine(quarantine)
    revision = DependentAtomSpaceStore(
        domain_projector=BeliefProjector(store)).build(_snapshot(1, 904))
    records = _belief_records(revision)
    by_predicate = {value.key.predicate: value for value in records}

    assert by_predicate["belief-conflict-target"].key.namespace == (
        AtomNamespace.BELIEF)
    assert by_predicate["belief-conflict-target"].authority == (
        AuthorityClass.UNCERTAIN_BELIEF)
    for predicate in (
            "belief-conflict-lineage",
            "belief-context-quarantine",
            "belief-quarantine-target",
            "belief-quarantine-context",
            "belief-quarantines-evidence",
            "belief-retains-evidence"):
        assert by_predicate[predicate].key.namespace == AtomNamespace.DIAGNOSTIC
        assert by_predicate[predicate].authority == AuthorityClass.CONTROL_MODEL
    assert not any(
        value.key.namespace in (
            AtomNamespace.AUTHORITATIVE, AtomNamespace.OPERATION)
        for value in records)


def test_belief_store_rematerializes_against_same_snapshot():
    belief_store = BeliefStore(belief_config())
    snapshot = _snapshot(1, 905)
    store = DependentAtomSpaceStore(
        domain_projector=BeliefProjector(belief_store))
    first = store.build(snapshot)
    assert _belief_records(first) == ()

    belief_store.observe(_evidence("late-same-snapshot"))
    rematerialized = store.rematerialize(snapshot)
    cold = store.prepare(snapshot, cold=True)

    assert _belief_records(rematerialized)
    assert rematerialized.records == cold.records
    assert rematerialized.scopes == cold.scopes


def test_expired_observation_retracts_belief_without_inventing_absence():
    store = BeliefStore(belief_config())
    store.observe(_evidence("visible-navigation"))
    expiry_turn = 1 + belief_config()["decay"]["default"]["window_turns"]
    store.decay_to(expiry_turn)

    revision = DependentAtomSpaceStore(
        domain_projector=BeliefProjector(store)).build(
            _snapshot(expiry_turn, 906))
    records = _belief_records(revision)

    assert records == ()
    assert not any(
        "absent" in value.key.predicate or "lacks" in value.key.predicate
        for value in revision.records)


def test_belief_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith("belief-")}
    expected = {
        value for value in belief_predicate_registry().predicates
        if value.startswith("belief-")}

    assert names == expected
