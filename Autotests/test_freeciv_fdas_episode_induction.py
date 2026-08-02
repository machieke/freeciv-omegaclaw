import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    DecisionEpisode,
    DecisionEpisodeStore,
    EPISODE_SCHEMA_VERSION,
    EpisodeInductionSpec,
    FdasEpisodeInductionAdapter,
    FdasEpisodeInductionHeldoutGate,
    FdasEpisodeInductionShadow,
)
from freeciv_agent.pressure import (  # noqa: E402
    InductionLedger,
    InductionPromotionApproval,
    PatternMiner,
    ReplayValidator,
)


def _episode(index, status, cohort="train", event_id=None, tile="10"):
    terminal = status in (
        "goal-relief-observed", "effect-without-goal-relief",
        "no-effect-observed", "confounded-unattributable")
    relieved = status == "goal-relief-observed"
    return DecisionEpisode(
        EPISODE_SCHEMA_VERSION,
        "episode-{}-{}".format(cohort, index),
        "episode-induction",
        0,
        "operation-{}-{}".format(cohort, index),
        '{"action_type":"unit_move","actor_id":7}',
        "before-{}-{}".format(cohort, index),
        "after-{}-{}".format(cohort, index) if terminal else None,
        ("pf-impact:survival",),
        (("era", "ancient"),
         ("actor_tile_before", str(tile)),
         ("operation_type", "move_defender_to_city"),
         ("target_tile", "10"),
         ("terrain", "land")),
        ("atom-defense-route",),
        ("support-{}-{}".format(cohort, index),),
        ("grounding-route",),
        ("prediction-route",),
        ("claim-unit-{}".format(index),),
        "validation-current",
        event_id or "execution-{}-{}".format(cohort, index),
        {} if terminal else None,
        ({"effect": "defender-arrived"},) if relieved else (),
        (("pf-impact:survival", 1.0),) if relieved else (),
        status,
        ("fdas-defense-episode-recorder/1.0",),
    )


def _spec(episode):
    return EpisodeInductionSpec(
        episode.episode_id,
        ("era", "terrain"),
        ("operation_type",),
        (("route-grounded", "grounding-route"),),
    )


def _correlated_population(cohort, inverted=False):
    rows = []
    for index in range(16):
        tile = "10" if index % 2 == 0 else "20"
        relieved = (tile == "10") != inverted
        rows.append(_episode(
            index,
            "goal-relief-observed" if relieved else "no-effect-observed",
            cohort=cohort,
            tile=tile))
    return tuple(rows)


def test_only_attributable_terminal_episode_is_encoded_without_authority():
    relieved = _episode(0, "goal-relief-observed")
    no_effect = _episode(1, "no-effect-observed")
    effect_only = _episode(2, "effect-without-goal-relief")
    pending = _episode(3, "delayed-effect-pending")
    confounded = _episode(4, "confounded-unattributable")
    store = DecisionEpisodeStore(
        "fdas-induction", (relieved, no_effect, effect_only, pending,
                           confounded))
    adapter = FdasEpisodeInductionAdapter(store)

    positive = adapter.encode(_spec(relieved))
    negative = adapter.encode(_spec(no_effect))
    transition_without_relief = adapter.encode(_spec(effect_only))
    abstentions = tuple(adapter.encode(_spec(value)) for value in (
        pending, confounded))

    assert positive.accepted and positive.induction_episode.outcome is True
    assert negative.accepted and negative.induction_episode.outcome is False
    assert transition_without_relief.accepted
    assert transition_without_relief.induction_episode.outcome is False
    assert positive.induction_episode.context == (
        ("era", "ancient"), ("terrain", "land"))
    assert positive.induction_episode.features == (
        "context:operation_type=move_defender_to_city", "route-grounded")
    assert positive.truth_mutated is False
    assert positive.policy_authority is False
    assert not any(value.accepted for value in abstentions)
    assert all(value.induction_episode is None for value in abstentions)


def test_context_and_evidence_features_must_be_linked_to_episode():
    episode = _episode(0, "goal-relief-observed")
    adapter = FdasEpisodeInductionAdapter(
        DecisionEpisodeStore("fdas-induction", (episode,)))

    missing_context = adapter.encode(EpisodeInductionSpec(
        episode.episode_id, ("unknown",), ("operation_type",)))
    unlinked_evidence = adapter.encode(EpisodeInductionSpec(
        episode.episode_id, ("era",), ("operation_type",),
        (("invented-feature", "not-linked"),)))

    assert not missing_context.accepted
    assert missing_context.reason.startswith("episode-context-keys-missing")
    assert not unlinked_evidence.accepted
    assert unlinked_evidence.reason.startswith(
        "episode-feature-evidence-unlinked")


def test_shared_execution_lineage_rejects_independent_training_claim():
    episodes = tuple(
        _episode(index, "goal-relief-observed", event_id="shared-event")
        for index in range(2))
    adapter = FdasEpisodeInductionAdapter(
        DecisionEpisodeStore("fdas-induction", episodes))
    rows = tuple(adapter.encode(_spec(value)).induction_episode
                 for value in episodes)

    with pytest.raises(ValueError, match="not independent"):
        PatternMiner(minimum_support=2).mine(rows, "route-relieves-goal")


def test_encoded_training_and_disjoint_holdout_obey_quarantine_lifecycle():
    training = tuple(
        _episode(
            index,
            "goal-relief-observed" if index % 2 == 0
            else "no-effect-observed")
        for index in range(8))
    heldout = tuple(
        _episode(
            index,
            "goal-relief-observed" if index % 2 == 0
            else "no-effect-observed",
            cohort="holdout")
        for index in range(8))
    store = DecisionEpisodeStore("fdas-induction", training + heldout)
    adapter = FdasEpisodeInductionAdapter(store)
    training_rows = tuple(
        adapter.encode(_spec(value)).induction_episode for value in training)
    heldout_rows = tuple(
        adapter.encode(_spec(value)).induction_episode for value in heldout)

    proposals = PatternMiner(
        minimum_support=4, maximum_antecedents=1,
        minimum_residual=0.0).mine(training_rows, "route-relieves-goal")
    assert proposals
    proposal = proposals[0]
    ledger = InductionLedger(identity="fdas-episode-induction")
    assert ledger.propose(proposal)
    assert ledger.status(proposal.proposal_id) == "quarantined"
    assert ledger.promoted_rules() == ()

    validation = ReplayValidator(
        minimum_samples=8, minimum_activations=4,
        minimum_brier_improvement=0.0,
        minimum_calibration_improvement=0.0).validate(
            proposal, heldout_rows)
    approval = (
        InductionPromotionApproval.issue(
            proposal, validation, "a" * 64, "b" * 64)
        if validation.verdict == "promoted" else None)
    ledger.record_validation(validation, approval=approval)
    assert ledger.status(proposal.proposal_id) in ("promoted", "demoted")
    if validation.verdict == "promoted":
        assert ledger.promoted_rules() == (proposal,)
    else:
        assert ledger.promoted_rules() == ()


def test_live_shadow_mines_only_quarantined_rules_and_replay_is_idempotent():
    episodes = tuple(
        _episode(
            index,
            "goal-relief-observed" if index < 2 else "no-effect-observed",
            tile="10" if index < 2 else "20")
        for index in range(4))
    store = DecisionEpisodeStore("fdas-induction-shadow", episodes)
    ledger = InductionLedger(identity="fdas-induction-shadow")
    shadow = FdasEpisodeInductionShadow(
        store,
        ledger,
        PatternMiner(
            minimum_support=2,
            maximum_antecedents=1,
            minimum_residual=0.05))

    first = shadow.evaluate()
    first_hash = ledger.state_hash
    second = shadow.evaluate()

    assert first.proposals
    assert first.newly_quarantined_proposal_ids
    assert not first.duplicate_proposal_ids
    assert all(
        ledger.status(proposal_id) == "quarantined"
        for proposal_id in first.newly_quarantined_proposal_ids)
    assert ledger.promoted_rules() == ()
    assert first.truth_mutated is False
    assert first.policy_authority is False
    assert second.newly_quarantined_proposal_ids == ()
    assert second.duplicate_proposal_ids == tuple(
        sorted(value.proposal_id for value in first.proposals))
    assert ledger.state_hash == first_hash


def test_live_shadow_abstains_when_training_lineage_is_not_independent():
    episodes = tuple(
        _episode(
            index,
            "goal-relief-observed" if index < 2 else "no-effect-observed",
            event_id="shared-execution",
            tile="10" if index < 2 else "20")
        for index in range(4))
    ledger = InductionLedger(identity="fdas-induction-shadow")
    result = FdasEpisodeInductionShadow(
        DecisionEpisodeStore("fdas-induction-shadow", episodes),
        ledger,
        PatternMiner(
            minimum_support=2,
            maximum_antecedents=1,
            minimum_residual=0.05)).evaluate()

    assert result.mining_reason == "training-provenance-not-independent"
    assert result.proposals == ()
    assert ledger.snapshot()["proposals"] == {}


def test_heldout_gate_promotes_only_with_disjoint_versioned_approval(tmp_path):
    training = DecisionEpisodeStore(
        "fdas-induction-training",
        _correlated_population("training"))
    holdout = DecisionEpisodeStore(
        "fdas-induction-holdout",
        _correlated_population("holdout"))
    ledger_path = tmp_path / "heldout-ledger.json"
    ledger = InductionLedger(
        str(ledger_path), identity="fdas-induction-heldout")
    gate = FdasEpisodeInductionHeldoutGate(
        training, holdout, ledger)

    first = gate.evaluate()
    state_hash = ledger.state_hash
    second = gate.evaluate()
    persisted = InductionLedger(
        str(ledger_path), identity="fdas-induction-heldout")

    assert first.proposals
    assert first.promoted_rule_ids
    assert not first.demoted_rule_ids
    assert len(first.approvals) == len(first.promoted_rule_ids)
    assert all(
        value.to_dict()["policy_authority"] is False
        and value.to_dict()["readout_authority"] is False
        for value in first.approvals)
    assert first.truth_mutated is False
    assert first.policy_authority is False
    assert first.readout_authority is False
    assert len(persisted.promoted_rules()) == len(first.promoted_rule_ids)
    assert persisted.state_hash == state_hash == ledger.state_hash
    assert second.newly_quarantined_proposal_ids == ()
    assert second.newly_validated_ids == ()
    assert set(second.duplicate_proposal_ids) == set(
        first.promoted_rule_ids)
    assert len(second.duplicate_validation_ids) == len(
        first.promoted_rule_ids)


def test_heldout_gate_demotes_out_of_sample_reversal_without_approval():
    training = DecisionEpisodeStore(
        "fdas-induction-training",
        _correlated_population("training"))
    holdout = DecisionEpisodeStore(
        "fdas-induction-reversed-holdout",
        _correlated_population("holdout", inverted=True))
    ledger = InductionLedger(identity="fdas-induction-demotion")

    result = FdasEpisodeInductionHeldoutGate(
        training, holdout, ledger).evaluate()

    assert result.proposals
    assert result.demoted_rule_ids
    assert not result.promoted_rule_ids
    assert result.approvals == ()
    assert ledger.promoted_rules() == ()


def test_heldout_gate_rejects_episode_partition_overlap():
    episodes = _correlated_population("shared")
    training = DecisionEpisodeStore("training-partition", episodes)
    holdout = DecisionEpisodeStore("holdout-partition", episodes)
    gate = FdasEpisodeInductionHeldoutGate(
        training, holdout,
        InductionLedger(identity="fdas-induction-overlap"))

    with pytest.raises(ValueError, match="episode overlap"):
        gate.evaluate()
