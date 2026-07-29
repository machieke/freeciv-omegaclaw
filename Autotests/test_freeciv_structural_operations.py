"""Shadow lifecycle and induction typed-operation gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    CloneLifecycleStore,
    CloneManager,
    CloneSplitRequest,
    CloneState,
    InducedRuleProposal,
    InductionLedger,
    ResourceKind,
    StructuralOperationFactory,
    StructuralShadowLedger,
    TruthState,
)


def _split_request(
        generation=1, predictive_gain=1.0,
        trigger_pressure=100.0):
    return CloneSplitRequest(
        atom_id="enemy-intent",
        parent_clone_id="clone-1",
        generation=generation,
        current_clone_count=1,
        predictive_gain=predictive_gain,
        added_parameters=1,
        split_score=0.9,
        successor_gate_passed=True,
        lineage_gate_passed=True,
        merge_gate_checked=True,
        trigger_pressure=trigger_pressure)


def _proposal(source="pattern", uncertainty=0.0):
    return InducedRuleProposal(
        proposal_id="proposal-{}".format(source),
        antecedent=("feature:a",),
        consequent="outcome:b",
        context=(("ruleset", "civ2civ3"),),
        probability=0.8,
        baseline_probability=0.5,
        support=2,
        positives=2,
        training_episode_ids=("episode-1", "episode-2"),
        provenance_ids=("evidence-1", "evidence-2"),
        prediction_residual=0.6,
        compression_gain=0.4,
        expected_generalization=0.7,
        overfit_risk=0.1,
        trigger_pressure=1.0,
        source=source,
        source_proposal_ids=(
            ("proposal-pattern",)
            if source == "analogy" else ()),
        transfer_uncertainty=uncertainty)


def _store(path):
    store = CloneLifecycleStore(
        path, manager=CloneManager(
            split_threshold=0.5,
            complexity_penalty=0.5))
    store.initialize("enemy-intent", (
        CloneState(
            "clone-1", "enemy-intent", 1.0,
            TruthState(0.5, 0.5)),
    ))
    return store


def test_clone_split_pressure_cannot_bypass_predictive_gain_gate():
    factory = StructuralOperationFactory(CloneManager(
        split_threshold=0.5,
        complexity_penalty=1.0))

    decision = factory.propose_clone_split(
        _split_request(
            predictive_gain=0.1,
            trigger_pressure=1000000.0))

    assert not decision.accepted
    assert decision.reason == (
        "predictive_complexity_or_cap_gate_failed")


def test_inductive_proposal_requires_heldout_validation_packets():
    proposal = _proposal()
    validation = StructuralOperationFactory.heldout_validation_operation(
        proposal, "frontier")
    rejected = StructuralOperationFactory.promote_induced_rule(
        proposal, validation=None,
        heldout_packets_committed=False,
        atom_id="frontier")

    assert {
        row.resource for row in validation.packet_costs
    } == {ResourceKind.CPU, ResourceKind.SIMULATION}
    assert not rejected.accepted
    assert rejected.reason == (
        "heldout_validation_packets_required")


def test_analogy_uncertainty_is_preserved_in_typed_advantage():
    proposal = _proposal("analogy", uncertainty=0.4)

    operation = StructuralOperationFactory.analogy_operation(
        proposal, "frontier", "goal")
    advantage = operation.typed_advantage_for("goal")

    assert advantage.relief_variance == 0.4
    assert operation.success_probability == 0.6
    assert operation.payload["proposal"][
        "transfer_uncertainty"] == 0.4


def test_structural_operation_uses_current_clone_generation_at_commit(
        tmp_path):
    store = _store(str(tmp_path / "clones.json"))
    factory = StructuralOperationFactory(store.manager)
    proposed = factory.propose_clone_split(
        _split_request(generation=store.generation("enemy-intent")))
    evaluated = factory.evaluate_clone_split(proposed)
    store.bayes_update(
        "enemy-intent", {"clone-1": 1.0},
        "new-generation")

    stale = factory.commit_clone_split(
        proposed, evaluated, exact_validation=True,
        current_generation=store.generation("enemy-intent"))

    assert not stale.accepted
    assert stale.reason == "stale_clone_generation"

    current = factory.propose_clone_split(
        _split_request(generation=store.generation("enemy-intent")))
    current_evaluation = factory.evaluate_clone_split(current)
    commit = factory.commit_clone_split(
        current, current_evaluation,
        exact_validation=True,
        current_generation=store.generation("enemy-intent"))
    assert commit.accepted
    assert commit.operation.payload[
        "expected_generation"] == 2


def test_shadow_structural_operation_writes_no_durable_semantics(
        tmp_path):
    store = _store(str(tmp_path / "clones.json"))
    induction = InductionLedger(
        str(tmp_path / "induction.json"))
    before = (store.state_hash, induction.state_hash)
    decision = StructuralOperationFactory(
        store.manager).propose_clone_split(
            _split_request(
                generation=store.generation("enemy-intent")))
    ledger = StructuralShadowLedger()

    ledger.record(
        decision.operation, True, 0.5,
        store.state_hash)
    ledger.realize(decision.operation.operation_id, 0.25)

    assert (store.state_hash, induction.state_hash) == before
    assert store.clones("enemy-intent")[0].clone_id == "clone-1"
    assert induction.promoted_rules() == ()
