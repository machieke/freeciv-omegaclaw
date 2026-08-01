"""Research operation assembly, one-slot scheduling, and lifecycle tests."""

import os
import sys
import tempfile
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.planning import (  # noqa: E402
    ControlEventEmitter,
    ImpactCandidate,
    OperationState,
    ResearchEnablingIntent,
    ResearchEnablingOperationAssembler,
    ResearchOperationLifecycle,
)
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateValidity,
    GroundedResearchTransitionModel,
)
from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
)
from freeciv_agent.rulesets.ir import Requirement, Rule  # noqa: E402
from freeciv_agent.state import ResearchOptionState, ResearchState  # noqa: E402


def _requirement(name):
    return Requirement(
        "Tech", name, "Player", True,
        "symbolic", "has-tech",
        ("$player", name),
        {
            "file": "synthetic/techs.ruleset",
            "field": "reqs", "line": 1,
            "section": "advance_{}".format(
                name.lower()),
        })


def _rule(name, requirements=()):
    return Rule(
        "synthetic:tech:{}".format(name),
        "tech", name, name,
        "researchable", ("$player", name),
        tuple(_requirement(row) for row in requirements),
        (), {"cost": {"value": 20}}, False,
        {
            "file": "synthetic/techs.ruleset",
            "field": "name", "line": 1,
            "section": "advance_{}".format(
                name.lower()),
        })


def _ruleset():
    return SimpleNamespace(rules=(
        _rule("Applied", ("Foundation",)),
        _rule("Foundation"),
        _rule("Unrelated"),
    ))


def _intent(
        immediate="Foundation",
        strategic="Applied",
        deadline=30,
        emergency=False):
    return ResearchEnablingIntent(
        operation_type="RESEARCH_ENABLER",
        immediate_tech=immediate,
        strategic_target_tech=strategic,
        downstream_operation_id=(
            "strategy-operation:applied"),
        completion_deadline_turn=deadline,
        scheduling_bid=4.0,
        emergency=emergency)


def _snapshot(
        intent, turn=10,
        current="Unrelated",
        progress=5, cost=30,
        rate=5, known=(),
        advertise=True, suffix="a"):
    action = intent.action(0)
    option = ResearchOptionState(
        tech_name=intent.immediate_tech,
        tech_id=7,
        tech_cost=20,
        action_json=canonical_json_bytes(
            action).decode("utf-8"))
    actions = (
        (option.action_json,)
        if advertise else ())
    research = ResearchState(
        known_techs=tuple(sorted(known)),
        target_id=7 if current else None,
        target_name=current,
        progress=progress,
        cost=cost,
        beakers_per_turn=rate,
        available=True)
    return SimpleNamespace(
        player_id=0,
        turn=turn,
        snapshot_id="snapshot:{}:{}".format(
            turn, suffix),
        legal_actions_digest="legal:{}:{}".format(
            turn, suffix),
        legal_action_json=actions,
        research=research,
        research_option=lambda name: (
            option if name
            == option.tech_name else None),
        cities=(),
        units=(),
        economy=SimpleNamespace(gold=50))


def _estimate(snapshot, intent):
    action = intent.action(snapshot.player_id)
    request = DomainEstimateRequest(
        request_id="q" * 64,
        snapshot=snapshot,
        ruleset_ir=_ruleset(),
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category="research_strategy",
            utility=9999.0,
            rationale=(
                "candidate utility is not model input"),
            projection={
                "strategic_target_tech":
                    intent.strategic_target_tech,
            }),
        goal_losses=((
            "pf-impact:science", 3.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            "ruleset", snapshot.turn,
            snapshot.turn),
        horizon_turn=(
            intent.completion_deadline_turn))
    return GroundedResearchTransitionModel().estimate(
        request)


def _assembly(snapshot, intent):
    return ResearchEnablingOperationAssembler.assemble(
        snapshot, intent,
        _estimate(snapshot, intent),
        ("pf-impact:science",),
        "ruleset")


def test_research_assembly_has_explicit_dependency_and_one_slot_claim():
    intent = _intent()
    snapshot = _snapshot(intent)
    assembly = _assembly(snapshot, intent)

    assert assembly is not None
    assert assembly.initial_step_index == 0
    assert [row.action_type for row in assembly.spec.steps] == [
        "tech_research",
        "observe_research_completion",
    ]
    assert any(
        premise == "dependency:Foundation:declared"
        for premise in assembly.requirement_set.premise_ids)
    dependency = assembly.model_artifact[
        "dependency_profile"]
    assert dependency["propagation_mode"] == (
        "decomposed_ruleset_dependency_graph")
    assert dependency["legacy_tech_want_applied"] is False
    hard = tuple(
        row for row in assembly.resource_request.claims
        if row.hardness == ClaimHardness.HARD_CURRENT)
    future = tuple(
        row for row in assembly.resource_request.claims
        if row.hardness
        == ClaimHardness.CONDITIONAL_FUTURE)
    assert {row.resource.kind for row in hard} == {
        GameResourceKind.RESEARCH_SLOT,
        GameResourceKind.ACTION_BUDGET,
    }
    assert {row.resource.kind for row in future} == {
        GameResourceKind.RESEARCH_SLOT,
    }
    assert all(
        row.resource.owner_id == "player:0"
        for row in hard
        if row.resource.kind
        == GameResourceKind.RESEARCH_SLOT)


def test_emergency_research_requires_latest_eta_to_fit_deadline():
    intent = _intent(
        deadline=12, emergency=True)
    snapshot = _snapshot(
        intent, rate=1)

    assert _assembly(snapshot, intent) is None


def test_selected_research_starts_at_observation_step():
    intent = _intent()
    snapshot = _snapshot(
        intent, current="Foundation",
        progress=5, cost=20)
    assembly = _assembly(snapshot, intent)
    lifecycle = ResearchOperationLifecycle(
        "already-selected")

    update = lifecycle.register(
        assembly, snapshot)[0]
    record = lifecycle.store.get(
        assembly.spec.operation_id)

    assert assembly.initial_step_index == 1
    assert update.disposition == "waiting"
    assert update.next_action is None
    assert record.progress.state == OperationState.ACTIVE
    assert record.progress.current_step_index == 1


def test_prerequisite_completion_requests_replan_without_downstream_release():
    intent = _intent()
    before = _snapshot(intent)
    assembly = _assembly(before, intent)
    lifecycle = ResearchOperationLifecycle(
        "prerequisite")

    registered = lifecycle.register(
        assembly, before)[0]
    committed = lifecycle.commit_matching_action(
        before, intent.action(0),
        accepted=True)[0]
    selected = _snapshot(
        intent, turn=11,
        current="Foundation",
        progress=0, cost=20,
        advertise=False,
        suffix="selected")
    waiting = lifecycle.observe(selected)[0]
    learned = _snapshot(
        intent, turn=15,
        current=None,
        progress=0, cost=20,
        known=("Foundation",),
        advertise=False,
        suffix="learned")
    completed = lifecycle.observe(learned)[0]

    assert registered.disposition == "reserved"
    assert committed.disposition == "step_committed"
    assert waiting.disposition == "waiting"
    assert waiting.step_index == 1
    assert completed.disposition == "completed"
    assert completed.technology_ref == (
        "technology:Foundation")
    assert completed.dependency_ready
    assert not completed.downstream_ready
    assert completed.replan_required
    assert completed.downstream_operation_id is None


def test_final_technology_completion_releases_downstream_operation():
    intent = _intent(
        immediate="Applied",
        strategic="Applied")
    initial = _snapshot(
        intent, current="Applied",
        progress=10, cost=20,
        known=("Foundation",))
    assembly = _assembly(initial, intent)
    lifecycle = ResearchOperationLifecycle(
        "strategic-completion")
    lifecycle.register(assembly, initial)
    learned = _snapshot(
        intent, turn=12,
        current=None, progress=0,
        cost=20,
        known=("Applied", "Foundation"),
        advertise=False,
        suffix="learned")

    update = lifecycle.observe(learned)[0]

    assert update.disposition == "completed"
    assert update.dependency_ready
    assert update.downstream_ready
    assert not update.replan_required
    assert update.downstream_operation_id == (
        intent.downstream_operation_id)


def test_accepted_selection_must_be_observed_and_stall_can_repair():
    intent = _intent()
    before = _snapshot(intent)
    assembly = _assembly(before, intent)
    lifecycle = ResearchOperationLifecycle(
        "no-effect")
    lifecycle.register(assembly, before)
    lifecycle.commit_matching_action(
        before, intent.action(0),
        accepted=True)
    no_effect = _snapshot(
        intent, turn=11,
        current="Unrelated",
        advertise=False,
        suffix="no-effect")

    update = lifecycle.observe(no_effect)[0]

    assert update.disposition == "blocked"
    assert update.reason == (
        "accepted-research-action-not-observed")

    selected_intent = _intent()
    selected = _snapshot(
        selected_intent,
        current="Foundation",
        progress=5, cost=20,
        rate=5, suffix="initial")
    selected_assembly = _assembly(
        selected, selected_intent)
    repair = ResearchOperationLifecycle(
        "stall-repair")
    repair.register(
        selected_assembly, selected)
    stalled = _snapshot(
        selected_intent, turn=11,
        current="Foundation",
        progress=5, cost=20,
        rate=0, suffix="stalled")
    blocked = repair.observe(stalled)[0]
    recovered = _snapshot(
        selected_intent, turn=12,
        current="Foundation",
        progress=6, cost=20,
        rate=5, suffix="recovered")
    repaired = repair.observe(recovered)[0]

    assert blocked.reason == (
        "research-beaker-output-stalled")
    assert repaired.disposition == "repaired"
    assert not repaired.dependency_ready


def test_live_shadow_observer_attributes_selection_and_technology():
    intent = _intent()
    before = _snapshot(intent)
    action = intent.action(0)
    outcome = SimpleNamespace(
        submitted=True,
        status="accepted",
        reason=None,
        action_id="engine-research-1")

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(
            directory, "events.jsonl")
        writer = EventWriter(
            path, "research-live-shadow",
            durable=False)
        emitter = ControlEventEmitter()
        prepared = (
            emitter
            .prepare_grounded_enabling_operation(
                writer, before,
                _ruleset(), "ruleset",
                action, 30))
        committed = (
            emitter
            .emit_grounded_enabling_action_outcome(
                writer, before,
                action, outcome,
                caused_by=(
                    prepared[-1]["event_id"],)))
        selected = _snapshot(
            intent, turn=11,
            current="Foundation",
            progress=0, cost=20,
            advertise=False,
            suffix="selected")
        waiting = (
            emitter
            .resolve_grounded_enabling_operations(
                writer, selected,
                research_enabled=True,
                caused_by=(
                    committed[-1]["event_id"],)))
        learned = _snapshot(
            intent, turn=15,
            current=None,
            progress=0, cost=20,
            known=("Foundation",),
            advertise=False,
            suffix="learned")
        completed = (
            emitter
            .resolve_grounded_enabling_operations(
                writer, learned,
                research_enabled=True,
                caused_by=(
                    waiting[-1]["event_id"],)))
        writer.sync()
        report = validate_file(path)

    event_types = tuple(
        row["type"]
        for row in (
            prepared + committed
            + waiting + completed))
    assert "domain_estimate_emitted" in event_types
    assert "operation_proposed" in event_types
    assert "operation_reserved" in event_types
    assert "operation_step_committed" in event_types
    assert "operation_completed" in event_types
    completion = next(
        row for row in completed
        if row["type"]
        == "operation_completed")
    assert completion["payload"][
        "technology_ref"] == (
            "technology:Foundation")
    assert completion["payload"][
        "downstream_ready"] is True
    assert completion["payload"][
        "replan_required"] is False
    assert report.valid, [
        row.to_dict()
        for row in report.errors]
