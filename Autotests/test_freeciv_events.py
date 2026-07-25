"""V0 event schema, writer, causal validator, and synthetic-log tests."""

import json
import os
import sys
import tempfile
import threading
import subprocess
import asyncio

from websockets import connect, serve


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from freeciv_agent.events import model, schema, synthetic  # noqa: E402
from freeciv_agent.events.validator import validate_file, validate_stream  # noqa: E402
from freeciv_agent.events.writer import EventWriteError, EventWriter  # noqa: E402
from freeciv_agent.events.tail import EventCursor, PersistedEventTail, TailProtocolError  # noqa: E402


def _codes(report):
    return [item.code for item in report.errors]


def test_every_known_event_type_has_published_payload_definition():
    _, payloads = schema.published_schemas()
    assert set(schema.KNOWN_EVENT_TYPES).issubset(payloads["$defs"])


def test_generated_types_are_current():
    script = os.path.join(_REPO, "scripts", "freeciv", "generate_event_types.py")
    proc = subprocess.run([sys.executable, script, "--check"], cwd=_REPO,
                          text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_simulator_observation_requires_explicit_model_provenance():
    rows = [
        {
            "schema_version": "1.0", "event_id": "root", "game_id": "g",
            "turn": 0, "seq": 0, "ts": "2026-01-01T00:00:00Z",
            "type": "run_started", "caused_by": [],
            "payload": {"manifest_identity": "m", "condition_id": "d"},
        },
        {
            "schema_version": "1.0", "event_id": "simulation", "game_id": "g",
            "turn": 1, "seq": 0, "ts": "2026-01-01T00:00:00Z",
            "type": "observation", "caused_by": ["root"],
            "payload": {
                "observation_id": "observation", "provenance_id": "p",
                "source": "simulator", "age_turns": 0,
                "atom": {
                    "atom_id": "a", "predicate": "enemy-route",
                    "args": ["enemy"], "crisp": False,
                    "provenance_ids": ["p"],
                    "tv": {"strength": 1.0, "confidence": 0.6},
                },
            },
        },
    ]
    report = validate_stream(
        [json.dumps(row) + "\n" for row in rows],
        require_action_roots=False)
    assert "E_SIMULATOR_PROVENANCE" in _codes(report)


def test_writer_assigns_contiguous_turn_scoped_sequences():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "g", clock=synthetic.fixed_clock,
                             id_factory=synthetic.DeterministicIds(), durable=False)
        first = writer.emit("run_started", 0, {"manifest_identity": "x", "condition_id": "a"})
        second = writer.emit("metric_sample", 1, {
            "name": "m", "value": 0, "unit": "n", "labels": {},
        }, caused_by=[first["event_id"]])
        third = writer.emit("metric_sample", 1, {
            "name": "m", "value": 1, "unit": "n", "labels": {},
        }, caused_by=[second["event_id"]])
        assert [first["seq"], second["seq"], third["seq"]] == [0, 0, 1]
        assert validate_file(path).valid


def test_writer_rejects_forward_parent_duplicate_id_turn_regression_and_schema_error():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "g", clock=synthetic.fixed_clock,
                             id_factory=synthetic.DeterministicIds(), durable=False)
        root = writer.emit("run_started", 1, {"manifest_identity": "x", "condition_id": "a"},
                           event_id="root")
        for call, expected in (
            (lambda: writer.emit("metric_sample", 1, {"name": "m", "value": 1,
                                                       "unit": "n", "labels": {}},
                                 caused_by=["future"]), "causal parents"),
            (lambda: writer.emit("metric_sample", 1, {"name": "m", "value": 1,
                                                       "unit": "n", "labels": {}},
                                 caused_by=[root["event_id"]], event_id="root"), "duplicate"),
            (lambda: writer.emit("metric_sample", 0, {"name": "m", "value": 1,
                                                       "unit": "n", "labels": {}}), "turn regression"),
            (lambda: writer.emit("metric_sample", 1, {"name": "m"}), "invalid event schema"),
        ):
            try:
                call()
                assert False, "expected EventWriteError/ValueError"
            except (EventWriteError, ValueError) as exc:
                assert expected in str(exc)
        assert sum(1 for line in open(path, encoding="utf-8") if line.strip()) == 1


def test_writer_resume_validates_and_continues_sequence():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        ids = synthetic.DeterministicIds()
        writer = EventWriter(path, "g", clock=synthetic.fixed_clock, id_factory=ids, durable=False)
        writer.emit("run_started", 0, {"manifest_identity": "x", "condition_id": "a"})
        resumed = EventWriter(path, "g", clock=synthetic.fixed_clock,
                              id_factory=lambda: "resumed", durable=False, resume=True)
        event = resumed.emit("metric_sample", 0, {
            "name": "m", "value": 1, "unit": "n", "labels": {},
        })
        assert event["seq"] == 1
        assert validate_file(path).valid


def test_turn_sync_mode_fsyncs_boundaries_and_completion(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        syncs = []
        monkeypatch.setattr(os, "fsync", lambda fd: syncs.append(fd))
        writer = EventWriter(
            path, "turn-sync", clock=synthetic.fixed_clock,
            id_factory=synthetic.DeterministicIds(), durable=True,
            sync_mode="turn")
        root = writer.emit("run_started", 0, {
            "manifest_identity": "x", "condition_id": "a"})
        writer.emit("metric_sample", 0, {
            "name": "same-turn", "value": 0, "unit": "ratio", "labels": {},
        }, caused_by=[root["event_id"]])
        assert syncs == []

        writer.emit("metric_sample", 1, {
            "name": "next-turn", "value": 1, "unit": "ratio", "labels": {},
        })
        assert len(syncs) == 1
        writer.emit("metric_sample", 1, {
            "name": "same-next-turn", "value": 2, "unit": "ratio", "labels": {},
        })
        assert len(syncs) == 1
        writer.emit("run_completed", 1, {
            "status": "completed", "summary": {}})
        assert len(syncs) == 2
        assert validate_file(path).valid


def test_writer_rejects_unknown_sync_mode():
    with tempfile.TemporaryDirectory() as directory:
        try:
            EventWriter(
                os.path.join(directory, "events.jsonl"), "bad-sync",
                sync_mode="batch")
            assert False, "expected sync_mode validation"
        except ValueError as exc:
            assert "sync_mode" in str(exc)


def test_persisted_tail_resumes_after_ui_and_emitter_restart_without_duplicates():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "live-g", clock=synthetic.fixed_clock,
                             id_factory=synthetic.DeterministicIds(), durable=True)
        first = writer.emit("run_started", 0, {
            "manifest_identity": "live", "condition_id": "e_full_loop"})
        tail = PersistedEventTail(path, "live-g", poll_interval=0.005, max_batch=1)

        async def scenario():
            async with serve(tail.handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                endpoint = "ws://127.0.0.1:{}".format(port)
                async with connect(endpoint) as socket:
                    await socket.send(json.dumps({
                        "type": "subscribe", "game_id": "live-g", "schema_version": "1.0",
                        "after": {"turn": -1, "seq": -1}}))
                    ack = json.loads(await asyncio.wait_for(socket.recv(), 1))
                    observed_first = json.loads(await asyncio.wait_for(socket.recv(), 1))
                    assert ack["persisted_first"] is True
                    assert observed_first["event_id"] == first["event_id"]

                # The writer process is reconstructed from disk before event two.
                resumed = EventWriter(path, "live-g", clock=synthetic.fixed_clock,
                                      id_factory=lambda: "after-restart", resume=True, durable=True)
                second = resumed.emit("metric_sample", 1, {
                    "name": "loop_latency_ms", "value": 10, "unit": "ms", "labels": {}})
                async with connect(endpoint) as socket:
                    await socket.send(json.dumps({
                        "type": "subscribe", "game_id": "live-g", "schema_version": "1.0",
                        "after": {"turn": observed_first["turn"], "seq": observed_first["seq"]}}))
                    await asyncio.wait_for(socket.recv(), 1)
                    observed_second = json.loads(await asyncio.wait_for(socket.recv(), 1))
                    assert observed_second["event_id"] == second["event_id"]
                    assert observed_second["event_id"] != observed_first["event_id"]

        asyncio.run(scenario())
        assert validate_file(path).valid


def test_persisted_tail_rejects_partial_records_and_incompatible_subscriptions():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        with open(path, "wb") as stream:
            stream.write(b'{"schema_version":"1.0"')
        tail = PersistedEventTail(path, "g")
        try:
            tail._read_after(EventCursor(-1, -1))
            assert False, "expected partial JSONL rejection"
        except TailProtocolError as exc:
            assert exc.code == "E_TAIL_TRUNCATED"
        try:
            tail._parse_subscription(json.dumps({
                "type": "subscribe", "game_id": "g", "schema_version": "2.0"}))
            assert False, "expected incompatible schema rejection"
        except TailProtocolError as exc:
            assert exc.code == "E_SUBSCRIBE_SCHEMA"


def test_concurrent_writer_keeps_unique_contiguous_sequences():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "g", clock=synthetic.fixed_clock,
                             id_factory=synthetic.DeterministicIds(), durable=False)
        writer.emit("run_started", 0, {"manifest_identity": "x", "condition_id": "a"})
        threads = []
        for index in range(40):
            thread = threading.Thread(target=lambda i=index: writer.emit("metric_sample", 1, {
                "name": "thread", "value": i, "unit": "n", "labels": {},
            }))
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        seqs = [row["seq"] for row in rows if row["turn"] == 1]
        assert seqs == list(range(40))
        assert len({row["event_id"] for row in rows}) == 41
        assert validate_file(path).valid


def test_good_scenarios_validate_and_bad_scenarios_fail_with_stable_codes():
    expected = {
        "bad-orphan-action": "E_CAUSAL_ACTION_ROOT",
        "bad-crisp-drift": "E_CRISP_TV_DRIFT",
        "bad-duplicate-provenance": "E_DUPLICATE_PROVENANCE",
        "bad-write-through": "E_CONFABULATION_WRITE_THROUGH",
        "bad-seq-gap": "E_SEQ_GAP",
    }
    with tempfile.TemporaryDirectory() as directory:
        for name in synthetic.GOOD_SCENARIOS:
            path = os.path.join(directory, name + ".jsonl")
            synthetic.generate(name, path)
            report = validate_file(path)
            assert report.valid, (name, report.to_dict())
        for name, code in expected.items():
            path = os.path.join(directory, name + ".jsonl")
            synthetic.generate(name, path)
            report = validate_file(path)
            assert not report.valid
            assert code in _codes(report), (name, report.to_dict())


def test_canonical_goal_selection_is_a_valid_action_root_and_strict_payload():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "canonical-selection.jsonl")
        synthetic.generate("normal-crisp", path)
        rows = [json.loads(line) for line in open(path, encoding="utf-8")]
        proposal = next(row for row in rows if row["type"] == "llm_proposal")
        proposal["type"] = "goal_selection"
        proposal["payload"] = {
            "candidate_count": 1,
            "goal": {
                "arguments": ["player-1", "Pottery"],
                "goal_id": "goal-live-1",
                "predicate": "researchable",
                "target_id": "civ2civ3:tech:Pottery",
            },
            "model_call_avoided": True,
            "policy": "canonical-singleton-bypass-v1",
            "proposal_id": "proposal-1",
            "selection_id": "goal-live-1",
            "source": "canonical_catalog",
        }
        report = validate_stream(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows)
        assert report.valid, report.to_dict()
        malformed = json.loads(json.dumps(proposal))
        malformed["payload"]["candidate_count"] = 2
        assert schema.validate_event_schema(malformed)


def test_validator_rejects_action_sent_from_already_invalid_plan():
    with tempfile.TemporaryDirectory() as directory:
        normal_path = os.path.join(directory, "normal.jsonl")
        invalidation_path = os.path.join(directory, "invalidation.jsonl")
        synthetic.generate("normal-crisp", normal_path)
        synthetic.generate("invalidation-repair", invalidation_path)
        events = [json.loads(line) for line in open(normal_path, encoding="utf-8")]
        invalidation_rows = [json.loads(line) for line in open(
            invalidation_path, encoding="utf-8")]
        created_index = next(
            index for index, event in enumerate(events)
            if event["type"] == "plan_created")
        invalidation = next(
            event for event in invalidation_rows
            if event["type"] == "plan_invalidated")
        invalidation.update({
            "event_id": "forced-plan-invalidation",
            "game_id": events[0]["game_id"],
            "turn": 1,
            "seq": events[created_index]["seq"] + 1,
            "caused_by": [events[created_index]["event_id"]],
        })
        invalidation["payload"]["plan_id"] = "plan-1"
        for event in events[created_index + 1:]:
            if event["turn"] == 1:
                event["seq"] += 1
        events.insert(created_index + 1, invalidation)
        report = validate_stream(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in events)
        diagnostics = [error for error in report.errors
                       if error.code == "E_INVALID_PLAN_ACTION"]
        assert len(diagnostics) == 1
        action = next(event for event in events if event["type"] == "action_sent")
        assert diagnostics[0].event_id == action["event_id"]


def test_unknown_event_is_preserved_and_warned_not_dropped():
    event = {
        "schema_version": "1.0", "event_id": "e1", "game_id": "g", "turn": 0,
        "seq": 0, "ts": synthetic.fixed_clock(), "type": "future_event",
        "caused_by": [], "payload": {"new": [1, 2, 3]},
    }
    report = validate_stream([json.dumps(event) + "\n"])
    assert report.valid
    assert [warning.code for warning in report.warnings] == ["W_UNKNOWN_TYPE"]
    assert report.event_count == 1


def test_generation_is_byte_deterministic():
    with tempfile.TemporaryDirectory() as directory:
        first = os.path.join(directory, "first.jsonl")
        second = os.path.join(directory, "second.jsonl")
        synthetic.generate("normal-crisp", first)
        synthetic.generate("normal-crisp", second)
        assert open(first, "rb").read() == open(second, "rb").read()


def test_tracked_compact_fixtures_are_current():
    fixtures = os.path.join(_REPO, "Autotests", "fixtures", "freeciv-events", "v1")
    with tempfile.TemporaryDirectory() as directory:
        for name in synthetic.ALL_SCENARIOS:
            generated = os.path.join(directory, name + ".jsonl")
            synthetic.generate(name, generated)
            tracked = os.path.join(fixtures, name + ".jsonl")
            assert open(generated, "rb").read() == open(tracked, "rb").read(), name


def test_quarantine_fixture_contains_all_false_claims_and_zero_write_through():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "quarantine.jsonl")
        synthetic.generate("quarantine-40", path)
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        quarantines = [row for row in rows if row["type"] == "quarantine"]
        metrics = [row for row in rows if row["type"] == "metric_sample"]
        assert len(quarantines) == 40
        assert len({row["payload"]["claim_id"] for row in quarantines}) == 40
        assert metrics[-1]["payload"]["name"] == "confabulation_write_through"
        assert metrics[-1]["payload"]["value"] == 0


def test_proof_hash_tampering_is_detected():
    goal = model.atom("goal", "researchable", ["p", "t"])
    leaf = model.proof_node("leaf", "premise", goal, True)
    proof = model.proof_tree("leaf", [leaf])
    assert len(proof["structural_hash"]) == 64
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "normal.jsonl")
        synthetic.generate("normal-crisp", path)
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        result = next(row for row in rows if row["type"] == "pln_result")
        result["payload"]["proof"]["nodes"][0]["satisfied"] = False
        report = validate_stream([json.dumps(row) + "\n" for row in rows])
        assert "E_PROOF_HASH" in _codes(report)


def test_structural_hash_ignores_node_ids_and_deduplicates_shared_subtrees():
    value = model.atom("same-atom", "has-tech", ["p", "Alphabet"])
    first = model.proof_node("leaf-a", "premise", value, True)
    second = model.proof_node("leaf-b", "premise", value, True)
    root = model.proof_node("root", "and", model.atom("goal", "researchable", ["p", "Pottery"]),
                            True, premise_node_refs=["leaf-a", "leaf-b"])
    proof = model.proof_tree("root", [first, second, root])
    leaf_hashes = [node["subtree_hash"] for node in proof["nodes"] if node["node_id"].startswith("leaf")]
    assert leaf_hashes[0] == leaf_hashes[1]
    compact = model.deduplicate_proof_tree(proof)
    assert len(compact["nodes"]) == 2
    compact_root = next(node for node in compact["nodes"] if node["node_id"] == "root")
    assert compact_root["premise_node_refs"] == ["leaf-a", "leaf-a"]


def test_deduplication_reduces_serialized_volume_without_changing_root_hash():
    script = os.path.join(_REPO, "scripts", "freeciv", "proof_dedup_report.py")
    proc = subprocess.run([sys.executable, script, "--repetitions", "40"], cwd=_REPO,
                          text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["expanded_nodes"] == 41
    assert result["compact_nodes"] == 2
    assert result["saved_bytes"] > 0
    assert result["structural_hash_stable"] is True


def test_compact_performance_fixture_stays_under_turn_volume_budget():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "performance.jsonl")
        synthetic.generate_performance(path, turns=5, atoms_per_turn=250)
        report = validate_file(path)
        assert report.valid, report.to_dict()
        assert max(report.bytes_by_turn.values()) < 5 * 1024 * 1024
        assert report.event_count == 1 + 5 * 5
