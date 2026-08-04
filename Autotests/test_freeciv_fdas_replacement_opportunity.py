from types import SimpleNamespace

import pytest

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    COORDINATED_REPLACEMENT_READOUT_IDENTITY,
    FdasCoordinatedReplacementReadout,
    FdasReplacementOpportunityFunnelEvaluator,
)
from freeciv_agent.state.atomspace import (
    AtomNamespace,
    EntityRef,
    SymbolRef,
)


def _record(predicate, arguments):
    return SimpleNamespace(key=SimpleNamespace(
        namespace=AtomNamespace.DERIVED,
        predicate=predicate,
        arguments=tuple(arguments)))


def _readout(replacement_count=0, direct_count=4, rejected=()):
    semantic = {
        "action_selection_changed": False,
        "candidate_recall_changed": False,
        "direct_candidate_count": direct_count,
        "identity": COORDINATED_REPLACEMENT_READOUT_IDENTITY,
        "pairs": [],
        "policy_authority": False,
        "readout_authority": False,
        "reason": "no-grounded-safe-chain",
        "rejected": sorted(set(rejected)),
        "replacement_candidate_count": replacement_count,
        "revision_id": "revision-1",
        "snapshot_id": "snapshot-1",
        "status": "abstained",
        "transition_value_estimated": False,
        "truth_mutated": False,
    }
    return FdasCoordinatedReplacementReadout(
        "abstained", "no-grounded-safe-chain", "snapshot-1", "revision-1",
        replacement_count, direct_count, (), tuple(semantic["rejected"]),
        structural_hash(semantic))


def _revision(include_safe=False):
    rows = [
        _record("city-garrison-deficit", (
            EntityRef("city", "20"), SymbolRef("defense-policy", "p"))),
        _record("unit-critical-garrison", (
            EntityRef("unit", "7"), EntityRef("city", "10"))),
        _record("unit-reinforcement-route", (
            EntityRef("unit", "7"), EntityRef("city", "20"))),
    ]
    if include_safe:
        rows.append(_record("unit-coordinated-replacement-for", (
            EntityRef("unit", "8"), EntityRef("unit", "7"),
            EntityRef("city", "10"))))
    return SimpleNamespace(
        snapshot_id="snapshot-1", revision_id="revision-1",
        records=tuple(rows))


def test_replacement_opportunity_funnel_identifies_missing_safe_replacement():
    result = FdasReplacementOpportunityFunnelEvaluator().evaluate(
        _revision(), _readout())

    assert result.blocker_stage == "no-safe-replacement-relation"
    assert result.deficit_target_city_count == 1
    assert result.critical_source_garrison_count == 1
    assert result.safe_replacement_relation_count == 0
    assert result.reinforcement_route_count == 1
    assert result.structural_source_target_join_count == 0
    assert result.protected_direct_control_count == 4
    assert result.to_dict()["truth_mutated"] is False
    assert result.to_dict()["readout_authority"] is False
    assert result == type(result).from_dict(result.to_dict())

    invalid = result.to_dict()
    invalid["policy_authority"] = True
    with pytest.raises(ValueError, match="semantics differ"):
        type(result).from_dict(invalid)


def test_replacement_opportunity_funnel_distinguishes_join_from_materialization():
    evaluator = FdasReplacementOpportunityFunnelEvaluator()

    missing = evaluator.evaluate(_revision(include_safe=True), _readout())
    materialized = evaluator.evaluate(
        _revision(include_safe=True),
        _readout(replacement_count=1, rejected=("operation:route-invalid",)))

    assert missing.structural_source_target_join_count == 1
    assert missing.blocker_stage == "structural-join-not-current-candidate"
    assert materialized.blocker_stage == "current-candidate-not-grounded"
    assert materialized.readout_rejection_count == 1
    assert missing == evaluator.evaluate(
        _revision(include_safe=True), _readout())


def test_replacement_opportunity_funnel_rejects_stale_revision():
    revision = _revision()
    revision.snapshot_id = "stale-snapshot"

    with pytest.raises(ValueError, match="current revision"):
        FdasReplacementOpportunityFunnelEvaluator().evaluate(
            revision, _readout())
