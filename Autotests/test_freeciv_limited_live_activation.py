"""Stage-S5 evidence-locked limited live activation and rollback gates."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pf_runtime import (  # noqa: E402
    PFRuntimeConfigurationError,
    build_controller_activation,
)
from freeciv_agent.planning import (  # noqa: E402
    ControllerRollback,
    ImpactControlAdapter,
    LimitedLiveActivationGate,
    LiveScopePolicy,
    PairedCohortEvidence,
)
from Autotests.test_freeciv_advisory_control import (  # noqa: E402
    _ScalarRanker,
    _Snapshot,
    _candidates,
    _engine,
)


def _evidence(**changes):
    values = {
        "cohort_id": "fresh-engine-confirmation-v1",
        "preregistered_primary_metric":
            "packet completion before deadline",
        "ruleset_digest": "ruleset-v1",
        "opponent_profile": "classic-ai",
        "horizon_turns": 480,
        "controller_profile_hash": "profile-v1",
        "treatment_seeds": (1, 3, 5),
        "control_seeds": (2, 4, 6),
        "tuning_protocol_hash": "tuning-v1",
        "engine_backed": True,
        "fresh_confirmation": True,
        "primary_effect": 0.2,
        "confidence_interval": (0.05, 0.35),
        "primary_endpoint_met": True,
        "controller_inclusive_compute": True,
        "exact_replay_valid": True,
        "schema_valid": True,
        "unsupported_legality_violations": 0,
        "safety_violations": 0,
        "pilot_data_excluded": True,
        "gdo9_entry_gate_passed": True,
        "gdo9_entry_report_hash":
            "gdo9-entry-approved-v1",
    }
    values.update(changes)
    return PairedCohortEvidence(**values)


def _adapter(evidence=None, categories=("exploration_move",)):
    snapshot = _Snapshot()
    temporary = ImpactControlAdapter()
    query = temporary.build_query(
        snapshot, _candidates(), 5, 40, 6,
        {"exploration": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")
    gate = LimitedLiveActivationGate(
        LiveScopePolicy(
            enabled_categories=categories,
            enabled_context_digests=(
                query.context_digest,),
            maximum_commit_rejection_rate=0.05,
            maximum_controller_latency_ms=500.0))
    adapter = ImpactControlAdapter(
        scalar_v2_ranker=_ScalarRanker(),
        unified_flow_engine=_engine(),
        live_activation_gate=gate,
        live_evidence=evidence)
    owned_query = adapter.build_query(
        snapshot, _candidates(), 5, 40, 6,
        {"exploration": {}},
        normalization_contract_hash="normalization-v1",
        ruleset_digest="ruleset-v1")
    return adapter, owned_query


def test_fresh_engine_paired_evidence_unlocks_only_scoped_category():
    adapter, query = _adapter(_evidence())
    decision = adapter.rank_or_schedule(
        query, "unified_flow_live")

    assert decision.health == "healthy"
    assert decision.controller_mode == "unified_flow_live"
    assert decision.artifact["activation"]["allowed"]
    assert decision.artifact["engine_evidence_hash"] == (
        _evidence().evidence_hash)


def test_missing_or_synthetic_evidence_cannot_enable_live_flow():
    for evidence in (
            None,
            _evidence(engine_backed=False),
            _evidence(
                gdo9_entry_gate_passed=False,
                gdo9_entry_report_hash=None)):
        adapter, query = _adapter(evidence)
        decision = adapter.rank_or_schedule(
            query, "unified_flow_live")

        assert decision.health == "fallback"
        assert decision.controller_mode == "scalar_v2"
        assert decision.fallback_chain[0] == (
            "unified_flow_live")


def test_unscoped_category_cannot_be_enabled_by_good_cohort():
    adapter, query = _adapter(
        _evidence(), categories=("city_defense",))
    decision = adapter.rank_or_schedule(
        query, "unified_flow_live")

    assert decision.health == "fallback"
    assert "category-not-enabled" in (
        decision.artifact["gate_reasons"])


def test_rollback_releases_all_packets_without_truth_mutation():
    adapter, query = _adapter(_evidence())
    decision = adapter.rank_or_schedule(
        query, "unified_flow_live")
    rollback = ControllerRollback().rollback(
        decision, "scalar_v2")

    assert rollback.released_packets
    assert rollback.expired_operation_ids
    assert rollback.truth_mutations == 0
    assert rollback.target_mode == "scalar_v2"


def test_live_runtime_requires_explicit_enable_and_revalidation():
    base = {
        "pressure_enabled": True,
        "pressure_semantics_version": "v2",
        "pressure_controller_mode": "unified_flow_live",
        "pressure_packet_scheduler_enabled": True,
        "pressure_bridge_enabled": True,
        "pressure_flow_enabled": True,
    }
    with pytest.raises(
            PFRuntimeConfigurationError,
            match="explicit live enablement"):
        build_controller_activation(base)
    base.update({
        "pressure_flow_live_enabled": True,
        "pressure_commit_revalidation_enabled": True,
    })
    activation = build_controller_activation(base)

    assert activation["controller_policy"][
        "pressure_controller_mode"] == "unified_flow_live"
