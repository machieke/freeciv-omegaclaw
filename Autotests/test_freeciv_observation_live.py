"""Engine-live observation, simulation, and evidence-firewall gates."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.beliefs import ModelProvenance  # noqa: E402
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.pressure import (  # noqa: E402
    AtomState,
    BoundedDecision,
    CostVector,
    EvidenceLedger,
    EvidenceToken,
    Hypothesis,
    ObservationEvidenceGate,
    ObservationOutcome,
    ObservationSelectionRecord,
    ObservationTest,
    PacketBudget,
    ResourceKind,
    TruthState,
    ValueOfInformationPlanner,
    bounded_decision_information_value,
    expected_information_value,
)


def _provenance(scope=("civ2civ3", "horizon<=8")):
    return ModelProvenance(
        "simulator", "bounded-freeciv-projection", "1.0",
        structural_hash({"model": "bounded-freeciv-projection/1.0"}),
        False, 0.6, scope)


def _test(
        test_id, likelihood=1.0, relevance=1.0,
        overlap=0.0, execution_kind="observation",
        atom_id="uncertain-branch"):
    return ObservationTest(
        test_id=test_id,
        atom_id=atom_id,
        outcomes=(
            ObservationOutcome(
                "left", (("left", likelihood),
                         ("right", 1.0 - likelihood))),
            ObservationOutcome(
                "right", (("left", 1.0 - likelihood),
                          ("right", likelihood))),
        ),
        cost=CostVector(compute=1.0),
        model_provenance=_provenance(),
        decision_sensitivity=relevance,
        evidence_overlap=overlap,
        execution_kind=execution_kind)


def _hypotheses():
    return (
        Hypothesis("left", 0.5),
        Hypothesis("right", 0.5),
    )


def test_decision_irrelevant_uncertainty_does_not_dominate_observation_budget():
    irrelevant_perfect = _test(
        "irrelevant-perfect", likelihood=1.0,
        relevance=0.0)
    relevant_weak = _test(
        "relevant-weak", likelihood=0.7,
        relevance=1.0)

    ranked = ValueOfInformationPlanner.rank(
        _hypotheses(), (irrelevant_perfect, relevant_weak))

    assert ranked[0].test.test_id == "relevant-weak"
    assert ranked[-1].expected_information_gain == 0.0


def test_observation_result_updates_evidence_only_after_authoritative_return():
    evidence = EvidenceLedger()
    gate = ObservationEvidenceGate(evidence)
    record = ObservationSelectionRecord(
        "observe:route", "goal", True, 1.0, None,
        "deterministic-highest-priority")
    gate.record_selection(record)
    token = EvidenceToken(
        "authoritative-route-result", 1.0, 1.0, 4,
        source="authoritative-server",
        observation_policy=None)

    assert evidence.tokens == ()
    try:
        gate.authoritative_return(
            record.operation_id, token,
            authoritative=False)
    except ValueError as error:
        assert "non-authoritative" in str(error)
    else:
        raise AssertionError(
            "non-authoritative result registered evidence")
    assert evidence.tokens == ()

    gate.authoritative_return(record.operation_id, token)
    assert evidence.tokens == (token,)


def test_simulator_identity_and_confidence_cap_are_serialized():
    planner = ValueOfInformationPlanner(engine_live=True)
    value = expected_information_value(
        _hypotheses(),
        _test("simulate", execution_kind="simulation"))
    operation = planner.operation(
        value, "goal",
        deterministic_reason="bounded-simulation")

    model = operation.payload["model_provenance"]
    assert model["model_id"] == "bounded-freeciv-projection"
    assert model["confidence_cap"] == 0.6
    assert model["validity_scope"] == [
        "civ2civ3", "horizon<=8"]
    assert {
        row.resource for row in operation.packet_costs
    } == {ResourceKind.CPU, ResourceKind.SIMULATION}


def test_repeated_overlapping_observation_is_discounted():
    fresh = expected_information_value(
        _hypotheses(), _test("fresh", overlap=0.0))
    repeated = expected_information_value(
        _hypotheses(), _test("repeated", overlap=0.75))

    assert repeated.expected_information_gain == (
        fresh.expected_information_gain * 0.25)
    assert repeated.to_dict()["overlap_discount"] == 0.25


def test_observation_selection_propensity_is_logged():
    planner = ValueOfInformationPlanner(engine_live=True)
    value = expected_information_value(
        _hypotheses(), _test("route-refresh"))
    operation = planner.operation(
        value, "goal", propensity=None,
        deterministic_reason="deterministic-highest-priority")

    declaration = operation.payload["selection_declaration"]
    assert declaration == {
        "propensity": None,
        "reason": "deterministic-highest-priority",
    }
    assert {
        row.resource for row in operation.packet_costs
    } == {ResourceKind.CPU, ResourceKind.OBSERVATION}


def _conflict():
    from freeciv_agent.beliefs import BeliefKey, ConflictAtom
    key = BeliefKey("enemy-intent", ("fixed-ai",))
    return ConflictAtom(
        "conflict-intent", key, ("scout",), ("diplomacy",),
        {"strength": 1.0, "confidence": 0.8},
        {"strength": 0.0, "confidence": 0.8},
        0.0, 0.64, ("context-a", "context-b"), 4)


def test_decision_irrelevant_test_is_omitted_not_merely_ranked_last():
    planner = ValueOfInformationPlanner()
    decision = planner.decision_for_conflict(
        _conflict(), _hypotheses(), (
            _test("irrelevant", likelihood=1.0, relevance=0.0,
                  atom_id="conflict-intent"),))

    assert decision["operations"] == ()
    assert decision["schedule"]["selected_operation_id"] is None
    assert decision["selection_records"] == ()
    assert decision["omitted_tests"] == ({
        "reason": "decision-insensitive-uncertainty",
        "test_id": "irrelevant",
    },)


def test_observation_and_simulation_use_atomic_cpu_packet_budgets():
    planner = ValueOfInformationPlanner(engine_live=True)
    decision = planner.packet_decision_for_conflict(
        _conflict(), _hypotheses(), (
            _test("simulation", likelihood=0.95,
                  execution_kind="simulation", atom_id="conflict-intent"),
            _test("scout", likelihood=0.8,
                  execution_kind="observation", atom_id="conflict-intent"),
        ), (
            PacketBudget(ResourceKind.CPU, 1),
            PacketBudget(ResourceKind.OBSERVATION, 1),
            PacketBudget(ResourceKind.SIMULATION, 0),
        ))

    schedule = decision["packet_schedule"]
    assert decision["selected_operation_ids"] == ("observe:scout",)
    assert schedule.conserved
    by_id = {
        value.operation_id: value for value in schedule.reservations}
    assert by_id["observe:simulation"].state == "pending"
    assert by_id["observe:simulation"].reason == (
        "insufficient-whole-packets")
    assert by_id["observe:scout"].state == "committed"
    selected = {
        value.operation_id: value.selected
        for value in decision["selection_records"]}
    assert selected == {
        "observe:scout": True,
        "observe:simulation": False,
    }


def test_missing_cpu_budget_selects_no_observation():
    planner = ValueOfInformationPlanner(engine_live=True)
    decision = planner.packet_decision_for_conflict(
        _conflict(), _hypotheses(), (
            _test("scout", atom_id="conflict-intent"),), (
            PacketBudget(ResourceKind.CPU, 0),
            PacketBudget(ResourceKind.OBSERVATION, 1),
        ))

    assert decision["selected_operation_ids"] == ()
    assert not any(value.selected for value in decision["selection_records"])
    assert decision["packet_schedule"].conserved


def _presence_decision():
    return BoundedDecision(
        "opponent-presence-retention",
        "present",
        0.8,
        "refresh-opponent-presence",
        "retain-opponent-monitor")


def _presence_hypotheses():
    return (
        Hypothesis("present", 0.925),
        Hypothesis("epistemically-unknown", 0.075),
    )


def _presence_test(test_id, likelihood):
    return ObservationTest(
        test_id=test_id,
        atom_id="belief-opponent-present",
        outcomes=(
            ObservationOutcome(
                "supports-presence",
                (("present", likelihood),
                 ("epistemically-unknown", 1.0 - likelihood))),
            ObservationOutcome(
                "does-not-support-presence",
                (("present", 1.0 - likelihood),
                 ("epistemically-unknown", likelihood))),
        ),
        cost=CostVector(compute=0.01),
        model_provenance=_provenance(),
        # This declaration is intentionally ignored and recomputed from the
        # bounded decision's counterfactual outcome readouts.
        decision_sensitivity=1.0)


def test_decision_sensitivity_is_derived_from_counterfactual_readout():
    value = bounded_decision_information_value(
        _presence_hypotheses(), _presence_test("refresh", 0.9),
        _presence_decision())

    analysis = value.bounded_decision_analysis
    assert analysis.prior_action_id == "retain-opponent-monitor"
    assert analysis.decision_sensitive
    assert 0.0 < analysis.decision_change_probability < 1.0
    assert value.test.decision_sensitivity == (
        analysis.decision_change_probability)
    assert any(row["changes_decision"] for row in analysis.outcome_rows)


def test_test_that_cannot_cross_decision_boundary_is_omitted():
    planner = ValueOfInformationPlanner(engine_live=True)
    atom = AtomState(
        "belief-opponent-present",
        TruthState(1.0, 0.85, ("visible-player",), crisp=False))
    result = planner.packet_decision_for_uncertainty(
        atom, _presence_decision(), _presence_hypotheses(),
        (_presence_test("too-weak", 0.55),), (
            PacketBudget(ResourceKind.CPU, 1),
            PacketBudget(ResourceKind.OBSERVATION, 1),
        ))

    assert result["operations"] == ()
    assert result["selected_operation_ids"] == ()
    assert result["omitted_tests"] == ({
        "reason": "decision-insensitive-uncertainty",
        "test_id": "too-weak",
    },)
    assert result["packet_schedule"].conserved


def test_uncertain_belief_uses_epistemic_rail_and_atomic_packets():
    planner = ValueOfInformationPlanner(engine_live=True)
    atom = AtomState(
        "belief-opponent-present",
        TruthState(1.0, 0.85, ("visible-player",), crisp=False))
    result = planner.packet_decision_for_uncertainty(
        atom, _presence_decision(), _presence_hypotheses(),
        (_presence_test("refresh", 0.9),), (
            PacketBudget(ResourceKind.CPU, 1),
            PacketBudget(ResourceKind.OBSERVATION, 1),
        ))

    assert result["selected_operation_ids"] == ("observe:refresh",)
    assert result["packet_schedule"].conserved
    demand = result["pressure"].demand(result["goal"].goal_id)
    assert demand.achievement == 0.0
    assert demand.epistemic > 0.0
    selected = result["selection_records"][0]
    assert selected.selected
    assert selected.propensity is None


def test_crisp_fact_cannot_generate_observation_pressure():
    planner = ValueOfInformationPlanner(engine_live=True)
    atom = AtomState(
        "authoritative-opponent-present",
        TruthState(1.0, 1.0, (), crisp=True))
    try:
        planner.decision_for_uncertainty(
            atom, _presence_decision(), _presence_hypotheses(),
            (_presence_test("refresh", 0.9),))
    except ValueError as error:
        assert "crisp facts" in str(error)
    else:
        raise AssertionError("crisp fact created observation pressure")
