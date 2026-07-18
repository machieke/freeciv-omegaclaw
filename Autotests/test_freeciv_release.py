"""Whole-system release invariant audit tests."""

import json
import os
import subprocess
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.config import belief_config  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos", "freeciv-llm", "freeciv", "freeciv", "data")))
    return next(path for path in candidates if path and os.path.isfile(
        os.path.join(path, "civ2civ3", "techs.ruleset")))


def _release_trace(path):
    writer = EventWriter(path, "release-audit-test", durable=False)
    root = writer.emit("run_started", 0, {
        "manifest_identity": "release", "condition_id": "e_full_loop"})
    parent = root["event_id"]
    beliefs = belief_config()
    for key, value in sorted(beliefs.items()):
        if key in ("decay", "schema_version", "sweep"):
            continue
        event = writer.emit("metric_sample", 0, {
            "name": "belief_{}".format(key), "value": value, "unit": "ratio",
            "labels": {"declaration": "release_configuration"}},
            caused_by=[parent])
        parent = event["event_id"]
    for predicate, schedule in sorted(beliefs["decay"].items()):
        event = writer.emit("metric_sample", 0, {
            "name": "belief_decay_window_turns", "value": schedule["window_turns"],
            "unit": "turns", "labels": {
                "declaration": "release_configuration", "predicate": predicate,
                "formula": schedule["formula"]}}, caused_by=[parent])
        parent = event["event_id"]
    proposal = writer.emit("llm_proposal", 1, {
        "proposal_id": "proposal", "model": "qwen3-coder-next:latest",
        "prompt_version": "release-test/1.0", "goals": [], "claims": []},
        caused_by=[parent])
    sent = writer.emit("action_sent", 1, {
        "action_id": "action", "action": {"action_type": "end_turn"},
        "snapshot_id": "snapshot", "legal_actions_digest": "digest",
        "plan_id": None, "step_id": None}, caused_by=[proposal["event_id"]])
    writer.emit("action_result", 1, {
        "action_id": "action", "status": "accepted",
        "engine_response": {"accepted": True}, "engine_turn": 1},
        caused_by=[sent["event_id"]])


def test_release_audit_passes_all_cross_cutting_invariants():
    script = os.path.join(REPO, "scripts", "freeciv", "audit_release.py")
    with tempfile.TemporaryDirectory() as directory:
        events = os.path.join(directory, "events.jsonl")
        report = os.path.join(directory, "release-audit.json")
        _release_trace(events)
        process = subprocess.run([
            sys.executable, script, "--ruleset-root", _ruleset_root(),
            "--events", events, "--output", report,
        ], cwd=REPO, text=True, capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout + process.stderr
        value = json.load(open(report, encoding="utf-8"))
        assert value["passed"]
        assert value["checks"] and all(row["passed"] for row in value["checks"])
