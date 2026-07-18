"""M5 atomic invalidation, no-zombie, locality, and repair latency gates."""

import os
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.execution import ExecutionGate, ProposedAction  # noqa: E402
from freeciv_agent.monitoring import AtomRevision, LocalRepairer, PlanMonitor  # noqa: E402
from freeciv_agent.planning import (Plan, PlanAssumption, PlanStep,  # noqa: E402
                                    ResourceLedger)


HASHES = tuple("{:064x}".format(index) for index in range(1, 11))


def _plan(plan_id="plan-monitor", assumptions=None, step_count=3):
    steps = tuple(PlanStep(
        "step-{}".format(index), "move", {"tile": [index, index]}, 10 + index,
        1, 1.0, spatial={"x": index, "y": index}) for index in range(step_count))
    assumptions = assumptions or (
        PlanAssumption(
            "chokepoint-clear", 0.6, {"strength": 0.8, "confidence": 0.7},
            ("step-0",), "node-choke", HASHES[0], ("prov-scout",)),)
    return Plan(
        plan_id, "goal-expand", HASHES[-1], "snapshot-1", steps,
        ResourceLedger(), (), "branch", "turns-to-goal", 3.0, 0.8, 3,
        "test-solver", assumptions=tuple(assumptions))


def _revision(atom="chokepoint-clear", event_id="revision-1", turn=2,
              prior=0.7, posterior=0.4):
    return AtomRevision(
        atom, {"strength": 0.8, "confidence": prior},
        {"strength": 0.2, "confidence": posterior}, event_id, turn)


def test_chokepoint_invalidates_same_turn_names_atom_and_blocks_execution():
    monitor = PlanMonitor()
    monitor.register(_plan())
    invalidation, = monitor.evaluate(_revision())
    assert invalidation.turn == 2
    assert invalidation.broken_assumption.atom_id == "chokepoint-clear"
    assert invalidation.affected_step_ids == ("step-0",)
    assert monitor.status("plan-monitor") == "INVALID"
    assert monitor.guard_execution("plan-monitor") == (False, "plan_invalid")


def test_simultaneous_failures_form_one_deterministic_transaction():
    assumptions = (
        PlanAssumption("b", 0.6, {"strength": 1.0, "confidence": 0.8},
                       ("step-1",), "node-b", HASHES[1], ("p-b",)),
        PlanAssumption("a", 0.6, {"strength": 1.0, "confidence": 0.8},
                       ("step-0",), "node-a", HASHES[0], ("p-a",)),
    )
    first = PlanMonitor(); first.register(_plan(assumptions=assumptions))
    second = PlanMonitor(); second.register(_plan(assumptions=assumptions))
    revisions = (_revision("b", "rev-b"), _revision("a", "rev-a"))
    left, = first.evaluate_batch(revisions)
    right, = second.evaluate_batch(tuple(reversed(revisions)))
    assert left == right
    assert [item.atom_id for item in left.broken_assumptions] == ["a", "b"]
    assert left.affected_step_ids == ("step-0", "step-1")


def test_local_repair_only_calls_broken_subtree_and_reuses_other_hashes():
    monitor = PlanMonitor(); monitor.register(_plan())
    invalidation, = monitor.evaluate(_revision())
    calls = []
    replacement = _plan("plan-replacement")

    def rederive(subtree, _invalidation):
        calls.append(subtree)
        return HASHES[9], replacement

    result = LocalRepairer(rederive).repair(invalidation, HASHES[:5])
    assert result.executable
    assert calls == [HASHES[0]]
    assert result.reused_subtree_hashes == HASHES[1:5]
    assert result.rederived_subtree_hashes == (HASHES[9],)
    assert result.replacement_plan.reused_subtree_hashes == HASHES[1:5]


def test_repair_failure_and_timeout_are_explicit_nonplans():
    monitor = PlanMonitor(); monitor.register(_plan())
    invalidation, = monitor.evaluate(_revision())
    failed = LocalRepairer(lambda _hash, _inv: None).repair(invalidation, HASHES)
    timed = LocalRepairer(lambda _hash, _inv: (HASHES[1], _plan()), timeout_ms=-1).repair(
        invalidation, HASHES)
    assert not failed.executable and failed.reason == "NO_REPLACEMENT_FOR_SUBTREE"
    assert not timed.executable and timed.reason == "REPAIR_TIMEOUT"


def test_repair_under_two_seconds_for_50_step_plan():
    assumption = PlanAssumption(
        "route-safe", 0.5, {"strength": 1.0, "confidence": 0.7},
        tuple("step-{}".format(index) for index in range(50)),
        "node-route", HASHES[0], ("p",))
    monitor = PlanMonitor(); monitor.register(_plan(assumptions=(assumption,), step_count=50))
    invalidation, = monitor.evaluate(_revision("route-safe"))
    result = LocalRepairer(lambda _hash, _inv: (HASHES[1], _plan("new", step_count=50))).repair(
        invalidation, HASHES)
    assert result.executable and result.latency_ms < 2000


def test_50_adversarial_runs_send_zero_actions_from_invalid_plans():
    transport_calls = []

    class Snapshot:
        turn = 2
        snapshot_id = "snapshot-1"
        legal_actions_digest = "legal"

    class Store:
        @staticmethod
        def current(_game, _player):
            return Snapshot()

    for index in range(50):
        monitor = PlanMonitor()
        plan = _plan("plan-{}".format(index))
        monitor.register(plan)
        monitor.evaluate(_revision(event_id="revision-{}".format(index)))
        gate = ExecutionGate(Store(), lambda value: transport_calls.append(value),
                             plan_monitor=monitor)
        proposed = ProposedAction(
            "action-{}".format(index), {"type": "unit_move"}, "snapshot-1",
            "legal", plan.plan_id, "step-0")
        outcome = gate.execute("game", 1, proposed)
        assert not outcome.submitted and outcome.reason == "plan_invalid"
    assert transport_calls == []


def test_real_invalidation_events_validate_with_complete_causality():
    monitor = PlanMonitor(); monitor.register(_plan())
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "monitor-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "d_uncertain_monitor", "manifest_identity": "m"})
        revision_event = writer.emit("revision", 2, {
            "evidence_tv": {"strength": 0.0, "confidence": 0.9},
            "formula": {"name": "revision", "inputs": {"conflict": True}},
            "operation": "apply",
            "posterior_tv": {"strength": 0.2, "confidence": 0.4},
            "prior_tv": {"strength": 0.8, "confidence": 0.7},
            "provenance_id": "enemy-seen",
            "target_atom": {
                "args": [4, 4], "atom_id": "chokepoint-clear", "crisp": False,
                "predicate": "tile-clear", "provenance_ids": ["enemy-seen"],
                "tv": {"strength": 0.2, "confidence": 0.4}},
        }, caused_by=[root["event_id"]])
        rows = monitor.emit_batch(
            (_revision(event_id=revision_event["event_id"]),), writer,
            [revision_event["event_id"]])
        report = validate_file(path)
        assert len(rows) == 1
        assert rows[0][1]["caused_by"]
        assert report.valid, report.to_dict()
