import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    ActivatedDomainProjector,
    EntityRef,
    ScopeActivationPolicy,
    ScopeActivationSignal,
    ScopeActivator,
    ScopeSpec,
    ValidityInterval,
    legacy_predicate_registry,
)


def _scope(scope_id, kind):
    return ScopeSpec(
        scope_id, kind, 0, (EntityRef(kind, scope_id),), (), (), (),
        frozenset((AtomNamespace.DERIVED,)), 20, 20, 20, 2,
        "test", ValidityInterval("snapshot-4", 4, 4, 1))


def _scopes():
    return (
        _scope("world", "world"),
        _scope("empire", "empire"),
        _scope("city:1", "city-facts"),
        _scope("region:low", "region"),
        _scope("region:high", "region"),
        _scope("belief:1", "opponent-belief"),
    )


def test_activation_is_reasoned_budgeted_and_deterministic():
    activator = ScopeActivator(ScopeActivationPolicy(
        maximum_active_scopes=6,
        maximum_by_kind=(("region", 1), ("opponent-belief", 1)),
        focused_scope_ttl_turns=2))
    signals = (
        ScopeActivationSignal(
            "region:low", "bounded-exploration", "packet:explore", 0.2),
        ScopeActivationSignal(
            "region:high", "visible-threat", "goal:survival", 0.9,
            ("atom:threat",)),
        ScopeActivationSignal(
            "belief:1", "decision-sensitive-uncertainty",
            "packet:observation", 0.8),
    )

    first = activator.activate(_scopes(), signals, 4)
    second = activator.activate(_scopes(), tuple(reversed(signals)), 4)

    assert first == second
    assert first.active_scope_ids == (
        "belief:1", "city:1", "empire", "region:high", "world")
    assert first.rejected == ({
        "reason": "scope-kind-budget-exhausted",
        "scope_id": "region:low", "scope_kind": "region"},)
    request = next(value for value in first.requests
                   if value.scope_id == "region:high")
    assert request.reason == "visible-threat"
    assert request.funded_by == "goal:survival"
    assert request.causal_parent_ids == ("atom:threat",)
    semantic = {
        "activator_identity": ScopeActivator.ACTIVATOR_IDENTITY,
        "rejected": list(first.rejected),
        "requests": [value.to_dict() for value in first.requests],
        "turn": 4,
    }
    assert first.state_hash == structural_hash(semantic)


def test_scope_momentum_expires_and_never_implies_a_world_fact():
    activator = ScopeActivator(ScopeActivationPolicy(
        maximum_active_scopes=6,
        maximum_by_kind=(("region", 2), ("opponent-belief", 1)),
        focused_scope_ttl_turns=2))
    initial = activator.activate(_scopes(), (
        ScopeActivationSignal(
            "region:high", "visible-threat", "goal:survival", 0.9),
    ), 4)
    retained = activator.activate(_scopes(), (), 5, initial)
    expired = activator.activate(_scopes(), (), 7, retained)

    request = next(value for value in retained.requests
                   if value.scope_id == "region:high")
    assert request.retained is True
    assert request.reason == "retained-scope-momentum"
    assert "region:high" not in expired.active_scope_ids
    assert set(expired.active_scope_ids) == {"city:1", "empire", "world"}


def test_activation_rejects_unknown_scope_and_turn_regression():
    activator = ScopeActivator()
    with pytest.raises(ValueError, match="unknown scope"):
        activator.activate(_scopes(), (
            ScopeActivationSignal("missing", "query", "cpu", 0.5),), 4)
    prior = activator.activate(_scopes(), (), 4)
    with pytest.raises(ValueError, match="turn regressed"):
        activator.activate(_scopes(), (), 3, prior)


def test_activated_projector_publishes_only_funded_scope_records():
    class Projector(object):
        predicate_registry = legacy_predicate_registry()

        @staticmethod
        def scopes(_snapshot):
            return _scopes()

        @staticmethod
        def extend_fingerprints(fingerprints):
            return dict(fingerprints)

        @staticmethod
        def project(_snapshot, scopes, _fingerprints):
            return tuple(SimpleNamespace(
                atom_id="atom:" + value.scope_id,
                key=SimpleNamespace(scope_id=value.scope_id))
                         for value in scopes)

    snapshot = SimpleNamespace(snapshot_id="snapshot-4", turn=4)
    wrapper = ActivatedDomainProjector(
        Projector(), ScopeActivator(),
        lambda _snapshot, _scopes: (
            ScopeActivationSignal(
                "region:high", "visible-threat", "goal:survival", 0.9),))
    selected_scopes = wrapper.scopes(snapshot)
    records = wrapper.project(snapshot, selected_scopes, {})

    assert set(value.scope_id for value in selected_scopes) == {
        "city:1", "empire", "region:high", "world"}
    assert set(value.key.scope_id for value in records) == {
        "city:1", "empire", "region:high", "world"}
    assert wrapper.activation(snapshot.snapshot_id).active_scope_ids == (
        "city:1", "empire", "region:high", "world")
