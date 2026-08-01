import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AtomSpaceEventEmitter,
    AtomSpaceTransaction,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    DependentAtomSpaceRevision,
    EntityRef,
    FDAS_EVENT_TYPES,
    ScopeActivationSignal,
    ScopeActivator,
    ScopeSpec,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    legacy_predicate_registry,
)


def _revision():
    validity = ValidityInterval("event-snapshot", 4, 4, 1)
    scope = ScopeSpec(
        "scope:event:empire", "empire", 0,
        (EntityRef("player", "0"),), (), (), ("unit-activity",),
        frozenset((AtomNamespace.AUTHORITATIVE,)),
        20, 20, 20, 2, "snapshot", validity)
    key = AtomKey(
        AtomNamespace.AUTHORITATIVE, "unit-activity",
        (EntityRef("unit", "7"), SymbolRef("activity", "fortified")),
        scope.scope_id)
    dependency = DependencyRef(
        DependencyKey("snapshot-field", "unit:7", "activity"),
        structural_hash({"activity": "fortified"}))
    support = SupportRecord.create(
        "event-projector", "1.0", key.to_dict(), (dependency,),
        {"activity": "fortified"}, ("event-fixture",))
    record = AtomRecord.create(
        key, AuthorityClass.ENGINE_AUTHORITATIVE, {"crisp": True},
        validity, (support,), ("event-fixture",))
    transaction = AtomSpaceTransaction(
        "event-snapshot", legacy_predicate_registry(), (scope,))
    transaction.apply(record)
    revision_id = transaction.commit()
    return DependentAtomSpaceRevision(
        revision_id, "event-snapshot", transaction.records,
        transaction.scopes, revision_id.split("fdas-revision-", 1)[1],
        transaction.dependency_index)


def test_revision_event_stream_is_schema_valid_causal_and_bounded(tmp_path):
    revision = _revision()
    activation = ScopeActivator().activate(revision.scopes, (), 4)
    path = os.path.join(str(tmp_path), "events.jsonl")
    writer = EventWriter(
        path, "fdas-events", durable=False,
        clock=lambda: "2026-08-01T00:00:00Z")
    emitter = AtomSpaceEventEmitter(
        support_level="selected", maximum_detail_events=1)

    emitted = emitter.emit_revision(
        writer, 4, revision, activation=activation)
    learning = emitter.emit_component(
        writer, "conductance_sample_recorded", 4, revision,
        {"episode_id": "episode-1", "truth_mutated": False},
        caused_by=(emitted[-1]["event_id"],),
        component_id="fdas-episode-control-learning",
        component_version="1.0")

    report = validate_file(path)
    assert report.valid, report.errors
    with open(path, encoding="utf-8") as stream:
        rows = tuple(json.loads(line) for line in stream if line.strip())
    kinds = tuple(value["type"] for value in rows)
    assert kinds[:3] == (
        "atomspace_revision_started", "snapshot_delta_computed",
        "scope_activation_requested")
    assert "projection_batch_applied" in kinds
    assert "scope_materialized" in kinds
    assert "scope_budget_exhausted" in kinds
    assert "atomspace_revision_committed" in kinds
    assert rows[-1] == learning
    assert learning["caused_by"] == [emitted[-1]["event_id"]]
    for row in rows:
        payload = dict(row["payload"])
        payload_hash = payload.pop("structural_hash")
        assert payload_hash == structural_hash(payload)
        assert payload["revision_id"] == revision.revision_id
        assert payload["snapshot_id"] == revision.snapshot_id


def test_fdas_event_vocabulary_is_complete_and_unknown_type_fails():
    required = {
        "atomspace_revision_started", "snapshot_delta_computed",
        "projection_batch_applied", "atom_support_added",
        "atom_support_retracted", "atom_invalidated", "atom_rederived",
        "atomspace_revision_committed", "scope_activation_requested",
        "scope_materialized", "scope_budget_exhausted",
        "grounding_evaluated", "grounding_cache_hit", "derivation_fired",
        "derivation_unknown", "completeness_witness_used",
        "goal_instantiated", "goal_resolved", "operation_projected",
        "operation_candidate_instantiated", "operation_candidate_rejected",
        "pressure_graph_built", "atomspace_shadow_decision",
        "episode_opened", "episode_effect_observed",
        "episode_relief_attributed", "conductance_sample_recorded",
        "induced_rule_quarantined", "induced_rule_promoted",
        "induced_rule_demoted",
    }
    assert FDAS_EVENT_TYPES == required
    emitter = AtomSpaceEventEmitter()
    with pytest.raises(ValueError, match="unknown FDAS"):
        emitter.emit_component(
            object(), "invented", 4, _revision(), {})
