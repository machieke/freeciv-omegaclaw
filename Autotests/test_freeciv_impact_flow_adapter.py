"""Stage-S5 versioned Impact control adapter and semantic epoch gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    ControlDecision,
    ImpactCandidate,
    ImpactControlAdapter,
)


class _Snapshot:
    def __init__(self, snapshot_id="snapshot-1", turn=4):
        self.snapshot_id = snapshot_id
        self.legal_actions_digest = "legal-1"
        self.turn = turn
        self.ruleset_name = "classic"

    def event_payload(self):
        return {
            "legal_actions_digest": self.legal_actions_digest,
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
        }


class _Ranker:
    def rank(
            self, snapshot, candidates,
            expansion_city_target, horizon_turn,
            survival_threat_radius, **kwargs):
        del (
            snapshot, expansion_city_target,
            horizon_turn, survival_threat_radius,
            kwargs)
        rows = tuple(sorted(
            candidates,
            key=lambda row: row.action_key,
            reverse=True))
        return rows, {"ranker": "fake"}


def _candidates():
    return (
        ImpactCandidate(
            {"action_type": "unit_move", "actor_id": 1},
            "exploration_move", 2.0, "first"),
        ImpactCandidate(
            {"action_type": "city_production", "city_id": 2},
            "production_continuity", 1.0, "second"),
    )


def _query(adapter, **changes):
    values = {
        "snapshot": _Snapshot(),
        "candidates": _candidates(),
        "expansion_city_target": 5,
        "horizon_turn": 40,
        "survival_threat_radius": 6,
        "goal_facts": {
            "exploration": {"demand": 1.0},
            "survival": {"demand": 0.5},
        },
        "pressure_generation": 3,
        "lifecycle_clone_generation": 2,
        "normalization_contract_hash": "normalization-v1",
        "controller_config": {"mode": "shadow"},
        "ruleset_digest": "ruleset-v1",
    }
    values.update(changes)
    return adapter.build_query(**values)


def test_semantic_epoch_changes_for_every_control_identity_input():
    adapter = ImpactControlAdapter()
    baseline = _query(adapter)
    same = _query(adapter)
    changed_pressure = _query(
        adapter, pressure_generation=4)
    changed_normalization = _query(
        adapter,
        normalization_contract_hash="normalization-v2")
    changed_candidates = _query(
        adapter, candidates=_candidates()[:1])

    assert baseline.semantic_epoch == same.semantic_epoch
    assert baseline.query_hash == same.query_hash
    assert len({
        baseline.semantic_epoch,
        changed_pressure.semantic_epoch,
        changed_normalization.semantic_epoch,
        changed_candidates.semantic_epoch,
    }) == 4


def test_canonical_controller_uses_only_grounded_candidate_set():
    adapter = ImpactControlAdapter()
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "canonical")

    assert decision.health == "healthy"
    assert decision.controller_mode == "canonical"
    assert decision.selected_candidate_key == (
        _candidates()[0].action_key)
    assert set(decision.ordered_candidate_keys) == set(
        query.candidate_keys)


def test_historical_ranker_order_is_preserved_by_wrapper():
    ranker = _Ranker()
    adapter = ImpactControlAdapter(
        legacy_ranker=ranker)
    query = _query(adapter)
    direct, artifact = ranker.rank(
        _Snapshot(), query.grounded_candidates,
        5, 40, 6)
    decision = adapter.rank_or_schedule(
        query, "legacy_scalar")

    assert decision.ordered_candidate_keys == tuple(
        row.action_key for row in direct)
    assert decision.artifact["ranker_artifact"] == artifact


def test_unavailable_controller_falls_back_without_new_candidate():
    adapter = ImpactControlAdapter()
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "unified_flow")

    assert decision.health == "fallback"
    assert decision.controller_mode == "canonical"
    assert decision.fallback_chain == (
        "unified_flow", "canonical")
    assert set(decision.ordered_candidate_keys) <= set(
        query.candidate_keys)


def test_controller_cannot_inject_unadvertised_action():
    def bad_engine(query, snapshot):
        del query, snapshot
        return ControlDecision(
            ordered_candidate_keys=("not-advertised",),
            selected_candidate_key="not-advertised",
            packet_schedule=None,
            controller_mode="unified_flow",
            artifact={},
            health="healthy",
            fallback_chain=())

    adapter = ImpactControlAdapter(
        unified_flow_engine=bad_engine)
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "unified_flow")

    assert decision.health == "fallback"
    assert decision.controller_mode == "canonical"
    assert decision.artifact["fallback_reason"] == (
        "controller-error")


def test_counterfactual_outcome_is_unknown_when_not_executed():
    adapter = ImpactControlAdapter()
    query = _query(adapter)
    decision = adapter.rank_or_schedule(
        query, "canonical")
    record = adapter.record_outcome(
        decision, _Snapshot("before"),
        _Snapshot("after"),
        {
            "executed_candidate_key": "different",
            "effect_observed": True,
        })

    assert record.counterfactual_status == (
        "unknown-counterfactual")
    assert record.effect_observed is None
    assert adapter.outcome_records == (record,)


def test_query_owned_by_different_adapter_is_rejected():
    first = ImpactControlAdapter()
    second = ImpactControlAdapter()
    query = _query(first)

    with pytest.raises(ValueError, match="not owned"):
        second.rank_or_schedule(query, "canonical")
