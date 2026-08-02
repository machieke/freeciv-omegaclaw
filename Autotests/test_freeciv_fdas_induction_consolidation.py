import os
import sys

import json
import subprocess

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    InducedRuleProposal,
    InductionEpisode,
    InductionPromotionApproval,
    PromotedRuleConsolidation,
    PromotedRuleConsolidator,
    PromotedRuleShadowReadout,
    ReplayMetrics,
    ReplayValidation,
)


def _proposal(proposal_id, antecedent, probability=0.8, support=8,
              positives=7, context=(("schema", "causal-v1"),)):
    return InducedRuleProposal(
        proposal_id=proposal_id,
        antecedent=antecedent,
        consequent="durable-defense-relief",
        context=context,
        probability=probability,
        baseline_probability=0.5,
        support=support,
        positives=positives,
        training_episode_ids=tuple(
            "training-{}".format(index) for index in range(8)),
        provenance_ids=tuple(
            "training-provenance-{}".format(index) for index in range(8)),
        prediction_residual=abs(probability - 0.5),
        compression_gain=0.75,
        expected_generalization=1.0,
        overfit_risk=0.125 * len(antecedent),
        trigger_pressure=1.0,
    )


def _validation(proposal):
    return ReplayValidation(
        "validation-{}".format(proposal.proposal_id),
        proposal.proposal_id,
        "promoted",
        "replay_gate_passed",
        tuple("holdout-{}".format(index) for index in range(8)),
        ReplayMetrics(8, 6, 0.25, 0.20, 0.7, 0.6,
                      0.2, 0.1, 0.0, 0.0),
        (("minimum_activations", 4),),
    )


def _approved(proposals):
    validations = tuple(_validation(value) for value in proposals)
    approvals = tuple(
        InductionPromotionApproval.issue(
            proposal, validation, "a" * 64, "b" * 64)
        for proposal, validation in zip(proposals, validations))
    return validations, approvals


def test_consolidation_removes_only_strict_same_prediction_subsumptions():
    simple = _proposal("rule-simple", ("feature:a",))
    redundant = _proposal(
        "rule-redundant", ("feature:a", "feature:b"))
    distinct_prediction = _proposal(
        "rule-distinct", ("feature:a", "feature:c"),
        probability=0.7, positives=6)
    incomparable = _proposal(
        "rule-incomparable", ("feature:b", "feature:c"))
    proposals = (redundant, incomparable, simple, distinct_prediction)
    validations, approvals = _approved(proposals)

    result = PromotedRuleConsolidator().consolidate(
        proposals, validations, approvals)

    assert set(result.retained_rule_ids) == {
        "rule-simple", "rule-distinct", "rule-incomparable"}
    assert len(result.suppressions) == 1
    assert result.suppressions[0].proposal_id == "rule-redundant"
    assert result.suppressions[0].retained_proposal_id == "rule-simple"
    assert result.suppressions[0].retained_antecedent == ("feature:a",)
    assert result.suppressions[0].removed_antecedents == ("feature:b",)
    assert result.to_dict()["truth_mutated"] is False
    assert result.to_dict()["policy_authority"] is False
    assert result.to_dict()["readout_authority"] is False


def test_consolidation_is_order_invariant_and_retained_basis_is_idempotent():
    simple = _proposal("rule-simple", ("feature:a",))
    middle = _proposal("rule-middle", ("feature:a", "feature:b"))
    widest = _proposal(
        "rule-widest", ("feature:a", "feature:b", "feature:c"))
    proposals = (widest, simple, middle)
    validations, approvals = _approved(proposals)
    consolidator = PromotedRuleConsolidator()

    first = consolidator.consolidate(proposals, validations, approvals)
    reversed_result = consolidator.consolidate(
        tuple(reversed(proposals)),
        tuple(reversed(validations)),
        tuple(reversed(approvals)))
    retained = tuple(
        value for value in proposals
        if value.proposal_id in first.retained_rule_ids)
    retained_validations = tuple(
        value for value in validations
        if value.proposal_id in first.retained_rule_ids)
    retained_approvals = tuple(
        value for value in approvals
        if value.proposal_id in first.retained_rule_ids)
    second = consolidator.consolidate(
        retained, retained_validations, retained_approvals)

    assert first.to_dict() == reversed_result.to_dict()
    assert first.retained_rule_ids == ("rule-simple",)
    assert second.retained_rule_ids == first.retained_rule_ids
    assert second.suppressions == ()


def test_consolidation_requires_exact_matching_approved_cohort():
    first = _proposal("rule-first", ("feature:a",))
    second = _proposal("rule-second", ("feature:a", "feature:b"))
    proposals = (first, second)
    validations, approvals = _approved(proposals)

    with pytest.raises(ValueError, match="one validation and approval"):
        PromotedRuleConsolidator().consolidate(
            proposals, validations, approvals[:1])

    foreign_approval = InductionPromotionApproval.issue(
        second, validations[1], "c" * 64, "d" * 64)
    with pytest.raises(ValueError, match="one approved cohort"):
        PromotedRuleConsolidator().consolidate(
            proposals, validations, (approvals[0], foreign_approval))


def test_consolidation_does_not_merge_different_context_or_training_sample():
    simple = _proposal("rule-simple", ("feature:a",))
    other_context = _proposal(
        "rule-other-context", ("feature:a", "feature:b"),
        context=(("schema", "causal-v2"),))
    other_sample = _proposal(
        "rule-other-sample", ("feature:a", "feature:c"),
        support=7, positives=6)
    proposals = (simple, other_context, other_sample)
    validations, approvals = _approved(proposals)

    result = PromotedRuleConsolidator().consolidate(
        proposals, validations, approvals)

    assert set(result.retained_rule_ids) == set(
        value.proposal_id for value in proposals)
    assert result.suppressions == ()


def test_consolidation_runner_reduces_frozen_pr29_to_four_rule_basis(tmp_path):
    output = tmp_path / "consolidation.json"
    result = subprocess.run([
        sys.executable,
        os.path.join(REPO, "scripts", "freeciv",
                     "consolidate_fdas_promoted_rules.py"),
        "--input",
        os.path.join(REPO, "docs", "freeciv", "evidence",
                     "fdas-pr29-causal-induction-holdout-engine.json"),
        "--output", str(output),
    ], cwd=REPO, text=True, capture_output=True, timeout=30)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stderr
    assert report["acceptance"]["accepted"] is True
    assert len(report["consolidation"]["input_rule_ids"]) == 13
    assert len(report["consolidation"]["retained_rule_ids"]) == 4
    assert len(report["consolidation"]["suppressions"]) == 9
    assert report["consolidation"]["readout_authority"] is False


def _readout(proposals):
    validations, approvals = _approved(proposals)
    consolidation = PromotedRuleConsolidator().consolidate(
        proposals, validations, approvals)
    return PromotedRuleShadowReadout(
        proposals, validations, approvals, consolidation)


def _induction_episode(features, outcome=True):
    return InductionEpisode(
        "future-episode",
        (("schema", "causal-v1"),),
        features,
        outcome,
        ("future-provenance",),
    )


def test_shadow_readout_prefers_unique_more_specific_prediction():
    simple = _proposal("rule-simple", ("feature:a",))
    specific = _proposal(
        "rule-specific", ("feature:a", "feature:b"),
        probability=0.7, positives=6)
    result = _readout((simple, specific)).read(
        _induction_episode(("feature:a", "feature:b")))
    value = result.to_dict()

    assert result.accepted is True
    assert result.matching_rule_ids == ("rule-simple", "rule-specific")
    assert result.maximal_rule_ids == ("rule-specific",)
    assert result.selected_probability == 0.7
    assert value["prediction_direction"] == "above_baseline"
    assert value["predictions"][0]["interval"]["lower"] < 0.7
    assert value["predictions"][0]["interval"]["upper"] > 0.7
    assert value["truth_mutated"] is False
    assert value["policy_authority"] is False
    assert value["readout_authority"] is False
    assert value["action_selection_changed"] is False


def test_shadow_readout_abstains_on_incomparable_maximal_predictions():
    left = _proposal(
        "rule-left", ("feature:a", "feature:b"),
        probability=0.7, positives=6)
    right = _proposal(
        "rule-right", ("feature:a", "feature:c"),
        probability=0.8, positives=7)
    result = _readout((left, right)).read(
        _induction_episode(("feature:a", "feature:b", "feature:c")))

    assert result.accepted is False
    assert result.reason == "ambiguous_maximal_predictions"
    assert result.selected_probability is None
    assert result.maximal_rule_ids == ("rule-left", "rule-right")
    assert len(result.predictions) == 2


def test_shadow_readout_is_outcome_blind_and_explicitly_abstains_on_no_match():
    readout = _readout((_proposal("rule-simple", ("feature:a",)),))
    positive = readout.read(_induction_episode(("feature:a",), True))
    negative = readout.read(_induction_episode(("feature:a",), False))
    no_match = readout.read(_induction_episode(("feature:z",), True))

    assert positive.to_dict() == negative.to_dict()
    assert no_match.accepted is False
    assert no_match.reason == "no_approved_rule_matches"
    assert no_match.predictions == ()


def test_shadow_readout_rejects_consolidation_not_reproduced_from_approvals():
    simple = _proposal("rule-simple", ("feature:a",))
    redundant = _proposal("rule-redundant", ("feature:a", "feature:b"))
    proposals = (simple, redundant)
    validations, approvals = _approved(proposals)
    forged = PromotedRuleConsolidation(
        ("rule-simple", "rule-redundant"),
        ("rule-simple", "rule-redundant"),
        ())

    with pytest.raises(ValueError, match="does not match approvals"):
        PromotedRuleShadowReadout(
            proposals, validations, approvals, forged)
