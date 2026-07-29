"""Ordered, bounded, non-committing flow-view patch tests."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    BoundedFlowViewOwner,
    FlowPatch,
)
from Autotests.test_freeciv_flow_projection import _view  # noqa: E402


def _patch(sequence, operation, stable_id, payload=None, epoch=2):
    return FlowPatch(
        sequence_number=sequence,
        semantic_epoch=epoch,
        operation=operation,
        stable_ids=(stable_id,),
        payload=dict(payload or {}))


def _node_payload():
    return {
        "kind": "proposition",
        "context_digest": "patched-context",
        "clone_generation": 0,
        "source": "patch-test",
    }


def _edge_payload():
    return {
        "source_node_id": "source",
        "target_node_id": "extra",
        "kind": "probe_forward",
        "legality": {
            "probe_forward": True,
            "resource_accounting": True,
        },
        "context_digest": "patched-context",
        "clone_generation": 0,
        "source": "patch-test",
    }


def test_structural_overlay_preserves_immutable_base_and_invalidates_handle():
    base = _view()
    handle = base.local_handle("source")
    base_hash = base.to_dict()["view_hash"]
    owner = BoundedFlowViewOwner(base)
    result = owner.apply_safe_point((
        _patch(0, "AddNode", "extra", _node_payload()),
        _patch(1, "AddEdge", "source-extra", _edge_payload()),
    ))
    current = owner.materialize()

    assert result.structural_applied == 2
    assert base.to_dict()["view_hash"] == base_hash
    assert current.node("extra").stable_id == "extra"
    assert current.edge("source-extra").target_node_id == "extra"
    with pytest.raises(ValueError, match="stale local handle"):
        current.resolve(handle)


def test_identical_patch_replay_is_idempotent_but_conflict_fails():
    owner = BoundedFlowViewOwner(_view())
    patch = _patch(
        0, "UpdateCost", "target", {"cost": 2.0})
    first = owner.apply_safe_point((patch,))
    second = owner.apply_safe_point((patch,))

    assert first.applied_sequence_numbers == (0,)
    assert second.duplicate_sequence_numbers == (0,)
    with pytest.raises(ValueError, match="conflicts"):
        owner.submit((
            _patch(
                0, "UpdateCost", "target",
                {"cost": 3.0}),))


def test_patch_gap_or_reordering_fails_closed():
    owner = BoundedFlowViewOwner(_view())
    with pytest.raises(ValueError, match="expected 0"):
        owner.submit((
            _patch(
                1, "UpdateCost", "target",
                {"cost": 1.0}),))
    with pytest.raises(ValueError, match="expected 1"):
        owner.submit((
            _patch(
                0, "UpdateCost", "target",
                {"cost": 1.0}),
            _patch(
                2, "UpdateCost", "source",
                {"cost": 2.0}),
        ))
    assert owner.pending_count == 0
    owner.submit((
        _patch(
            0, "UpdateCost", "target",
            {"cost": 1.0}),))
    assert owner.pending_count == 1


def test_scalar_updates_coalesce_to_latest_semantics():
    owner = BoundedFlowViewOwner(_view())
    result = owner.apply_safe_point((
        _patch(
            0, "UpdateConductance", "edge-0",
            {"value": 0.2}),
        _patch(
            1, "UpdateConductance", "edge-0",
            {"value": 0.9}, epoch=3),
    ))

    assert result.coalesced_sequence_numbers == (0,)
    assert result.scalar_applied == 1
    assert owner.scalar_overlay[
        ("UpdateConductance", "edge-0")]["value"] == 0.9


def test_safe_point_bounds_structural_work_and_never_commits():
    owner = BoundedFlowViewOwner(_view())
    result = owner.apply_safe_point((
        _patch(0, "AddNode", "extra-a", _node_payload()),
        _patch(1, "AddNode", "extra-b", _node_payload()),
    ), maximum_structural_patches=1)

    assert result.structural_applied == 1
    assert result.deferred_structural_count == 1
    assert result.truth_mutations == 0
    assert result.semantic_commits == 0
    followup = owner.apply_safe_point(
        maximum_structural_patches=1)
    assert followup.structural_applied == 1
    assert followup.deferred_structural_count == 0


def test_retirement_and_rebuild_are_deterministic():
    patches = (
        _patch(0, "AddNode", "extra", _node_payload()),
        _patch(1, "AddEdge", "source-extra", _edge_payload()),
        _patch(2, "RetireNode", "target"),
    )
    first = BoundedFlowViewOwner(_view())
    second = BoundedFlowViewOwner(_view())
    first.apply_safe_point(patches)
    second.apply_safe_point(patches)

    rebuilt = first.rebuild()
    synchronous = second.materialize()
    assert rebuilt.to_dict()["view_hash"] == (
        synchronous.to_dict()["view_hash"])
    assert {row.stable_id for row in rebuilt.nodes} == {
        "extra", "source"}
    assert all(
        row.target_node_id != "target"
        for row in rebuilt.edges)


@pytest.mark.parametrize("payload", (
    {"commit": True},
    {"nested": {"truth_mutation": 1}},
    {"execution_authority": True},
))
def test_patch_schema_rejects_semantic_commit_fields(payload):
    with pytest.raises(ValueError, match="cannot perform semantic commit"):
        _patch(
            0, "UpdateTruthSummary",
            "target", payload)


def test_patch_added_operation_cannot_become_committable():
    owner = BoundedFlowViewOwner(_view())
    payload = _node_payload()
    payload.update({
        "kind": "operation",
        "committable": True,
    })
    with pytest.raises(ValueError, match="cannot be committable"):
        owner.apply_safe_point((
            _patch(0, "AddNode", "operation:x", payload),))
