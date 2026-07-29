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
    CostVector,
    EvidenceLedger,
    EvidenceToken,
    Hypothesis,
    ObservationEvidenceGate,
    ObservationOutcome,
    ObservationSelectionRecord,
    ObservationTest,
    ResourceKind,
    ValueOfInformationPlanner,
    expected_information_value,
)


def _provenance(scope=("civ2civ3", "horizon<=8")):
    return ModelProvenance(
        "simulator", "bounded-freeciv-projection", "1.0",
        structural_hash({"model": "bounded-freeciv-projection/1.0"}),
        False, 0.6, scope)


def _test(
        test_id, likelihood=1.0, relevance=1.0,
        overlap=0.0, execution_kind="observation"):
    return ObservationTest(
        test_id=test_id,
        atom_id="uncertain-branch",
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
