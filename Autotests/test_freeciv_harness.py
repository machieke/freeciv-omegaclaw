"""M7 controller, reproducibility, statistics, fidelity, and capability gates."""

import json
import io
import os
import sys
import tempfile
from unittest import mock

import jsonschema
import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness import HarnessRunner, aggregate_runs, write_report  # noqa: E402
from freeciv.harness.config import CapabilityContext, load  # noqa: E402
from freeciv.harness.statistics import paired_delta, wilson  # noqa: E402
from freeciv.harness.aggregate import _calibration_report  # noqa: E402
from freeciv.harness.engine_live import (  # noqa: E402
    _available_research_names, _needs_cognitive_stack, _opponent_memory_path,
    _plain_prompt_state, _plain_state_summary, _release_configuration_active,
    _validate_compact_goal_proposal)
from freeciv.harness import engine_live  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes, structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402


def test_config_predeclares_identical_30_seed_matrix_and_20_game_induction():
    config = load()
    assert len(config["seeds"]) == 30 == len(set(config["seeds"]))
    assert config["induction"]["games"] >= 20
    assert config["conditions"] == [
        "a_stock_llm", "b_state_oracle", "c_dependency_scheduler",
        "d_uncertain_monitor", "e_full_loop"]
    assert config["model"]["name"] == "qwen3-coder-next:latest"
    assert config["model"]["think"] is False
    assert config["impact_policy"]["no_effect_retry_limit"] == 1
    assert config["rulebase"] == {
        "compiler_version": "freeciv-ruleset-compiler/1.0",
        "source_sha256": "8f6914743d8380fabd9bf1294556a53ba5e447532e4b9e9763d3d69c0c0120b4",
        "ir_sha256": "c7306b497f156462bd45b330186746a2304aadcc61bd05679c72fe36c1acadfd",
        "atomese_sha256": "73b7a33242ada1188accbeaa7eb546cb76f8d8d68034ae276c8412206774d277",
    }


def test_wilson_and_paired_bootstrap_are_bounded_and_deterministic():
    interval = wilson(20, 30)
    assert 0 <= interval["lower"] <= interval["estimate"] <= interval["upper"] <= 1
    first = paired_delta({1: 1, 2: 3}, {1: 2, 2: 7}, samples=1000, seed=9)
    second = paired_delta({2: 3, 1: 1}, {2: 7, 1: 2}, samples=1000, seed=9)
    assert first == second and first["paired_seeds"] == [1, 2]


def test_condition_capability_access_fails_closed():
    context = CapabilityContext("b_state_oracle", load()["capabilities"]["b_state_oracle"])
    assert context.use("authoritative_state")
    with pytest.raises(PermissionError, match="cannot import/use scheduler"):
        context.use("scheduler")


def test_live_candidates_exclude_server_rejected_research_actions():
    raw = {"legal_actions": [
        {"type": "tech_research", "tech_name": "Alphabet", "is_valid": True},
        {"type": "tech_research", "tech_name": "Engineering", "is_valid": False},
        {"type": "tech_research", "tech_name": "Alphabet", "is_valid": True},
        {"type": "unit_move", "tech_name": "Writing", "is_valid": True},
    ]}
    assert _available_research_names(raw) == ["Alphabet"]


def test_release_configuration_accepts_exact_reuse_and_rejects_drift():
    expected = {"ruleset": "civ2civ3", "mapseed": 104729}
    assert _release_configuration_active({
        "game_config_applied": True, "game_config": expected}, expected)
    assert _release_configuration_active({
        "game_config_applied": False, "game_config": expected}, expected)
    assert not _release_configuration_active({
        "game_config_applied": True, "game_config": None}, expected)
    assert not _release_configuration_active({
        "game_config_applied": False,
        "game_config": {"ruleset": "classic", "mapseed": 104729}}, expected)


def test_stock_condition_uses_only_legacy_action_summary_and_no_crisp_stack():
    raw = {"turn": 8, "gold": 99, "legal_actions": [
        {"type": "tech_research", "is_valid": True, "tech_name": "Alphabet"},
        {"type": "unit_move", "is_valid": False},
    ]}
    summary = _plain_state_summary(raw)
    assert summary == {"legal_action_kinds": ["tech_research"]}
    assert "turn" not in summary and "gold" not in summary
    assert _plain_prompt_state(summary) == "disabled"
    assert _plain_prompt_state({
        "cities": [{"id": 1}], "known_techs": ["Alphabet"],
        "legal_action_kinds": ["tech_research"],
        "research": {"beakers_per_turn": 4, "progress": 9, "target": "Writing"},
        "units": [{"id": 1, "type": "Settlers", "x": 5}],
        "visible_enemy_units": [{"id": 9, "type": "Warriors", "x": 8}],
    }) == {
        "city_count": 1, "known_techs": ["Alphabet"],
        "research": {"beakers_per_turn": 4, "target": "Writing"},
        "unit_types": ["Settlers"], "visible_enemy_types": ["Warriors"],
    }
    stock = CapabilityContext("a_stock_llm", load()["capabilities"]["a_stock_llm"])
    state = CapabilityContext("b_state_oracle", load()["capabilities"]["b_state_oracle"])
    crisp = CapabilityContext(
        "c_dependency_scheduler", load()["capabilities"]["c_dependency_scheduler"])
    assert not _needs_cognitive_stack(stock)
    assert not _needs_cognitive_stack(state)
    assert _needs_cognitive_stack(crisp)


def test_compact_live_goal_references_are_bounded_and_claim_free():
    valid = {"goal_indices": [0, 1], "selection": 1, "claims": []}
    assert _validate_compact_goal_proposal(valid, 2) is None
    for invalid in (
        {"goal_indices": [0, 0], "selection": 0, "claims": []},
        {"goal_indices": [2], "selection": 2, "claims": []},
        {"goal_indices": [0], "selection": 1, "claims": []},
        {"goal_indices": [0], "selection": 0, "claims": [{"text": "guess"}]},
    ):
        with pytest.raises(ValueError):
            _validate_compact_goal_proposal(invalid, 2)


def test_live_model_transport_reuses_identical_verified_decision_context(monkeypatch):
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout, json.loads(request.data)))
        return Response(json.dumps({
            "message": {"content": '{"selection":"end_turn"}'},
        }).encode("utf-8"))

    monkeypatch.setattr(engine_live.urllib.request, "urlopen", urlopen)
    engine_live._MODEL_JSON_CACHE.clear()
    manifest = {"model": "qwen3-coder-next:latest", "model_config": {
        "turn_timeout_seconds": 30, "max_tokens": 40,
        "temperature": 0, "think": False}}
    first = engine_live._ollama_json(manifest, "cache-test", ("selection",))
    second = engine_live._ollama_json(manifest, "cache-test", ("selection",))
    assert first[0] == second[0] == {"selection": "end_turn"}
    assert first[2] >= 0 and second[2] == 0
    assert len(calls) == 1 and calls[0][0].endswith("/api/chat")
    assert calls[0][2]["model"] == "qwen3-coder-next:latest"
    assert calls[0][2]["think"] is False
    engine_live._MODEL_JSON_CACHE.clear()


def test_live_model_lock_wait_is_inside_whole_turn_budget(monkeypatch):
    calls = []

    class ExhaustedLock:
        def acquire(self, timeout):
            calls.append(timeout)
            return False

        def release(self):
            raise AssertionError("an unacquired lock must not be released")

    monkeypatch.setattr(engine_live, "_MODEL_CACHE_LOCK", ExhaustedLock())
    manifest = {"model": "qwen3-coder-next:latest", "model_config": {
        "turn_timeout_seconds": 5, "temperature": 0}}
    with pytest.raises(RuntimeError, match="budget exhausted"):
        engine_live._ollama_json(manifest, "queued", ("selection",))
    assert calls == [3.0]


def test_engine_live_workers_are_bounded_to_dedicated_server_ports():
    runner = HarnessRunner("unused", backend="engine-live", workers=3)
    assert [runner._manifest(job, worker)["port"] for worker, job in enumerate([
        {"condition": "a_stock_llm", "seed": 1, "track": "main", "sequence": 0},
        {"condition": "a_stock_llm", "seed": 2, "track": "main", "sequence": 0},
        {"condition": "a_stock_llm", "seed": 3, "track": "main", "sequence": 0},
    ])] == [6001, 6002, 6003]
    with pytest.raises(ValueError, match="dedicated ports"):
        HarnessRunner("unused", backend="engine-live", workers=10)


def test_engine_live_clears_stale_proxy_game_before_server_recycle(monkeypatch):
    calls = []

    def terminate(game_id, token):
        calls.append(("terminate", game_id, token))

    def recycle(port):
        calls.append(("recycle", port))

    async def play(run_dir, manifest, context):
        calls.append(("play", run_dir, manifest["game_id"], context))
        return {"completed": True}

    monkeypatch.setattr(engine_live, "_terminate_proxy", terminate)
    monkeypatch.setattr(engine_live, "_recycle_server", recycle)
    monkeypatch.setattr(engine_live, "_play", play)
    context = object()
    result = engine_live.run_game(
        "/tmp/run", {"game_id": "release-retry", "port": 6001}, context)

    assert result == {"completed": True}
    assert calls == [
        ("terminate", "release-retry", "test-token-fc3d-001"),
        ("recycle", 6001),
        ("play", "/tmp/run", "release-retry", context),
        ("terminate", "release-retry", "test-token-fc3d-001"),
        ("recycle", 6001),
    ]


def test_worker_assignment_does_not_change_behavioral_manifest_identity():
    runner = HarnessRunner("unused", backend="engine-live", workers=3)
    job = {"condition": "a_stock_llm", "seed": 104729,
           "track": "main", "sequence": 0}
    left = runner._manifest(job, 0)
    right = runner._manifest(job, 2)
    assert left["port"] != right["port"]
    assert left["manifest_identity"] == right["manifest_identity"]
    assert left["source"]["commit"]
    assert len(left["source"]["implementation_sha256"]) == 64
    assert left["source"]["source_files"] > 20


def test_total_controller_concurrency_changes_behavioral_manifest_identity():
    job = {"condition": "a_stock_llm", "seed": 104729,
           "track": "main", "sequence": 0}
    three = HarnessRunner("unused", backend="engine-live", workers=3)._manifest(job, 0)
    nine = HarnessRunner("unused", backend="engine-live", workers=9)._manifest(job, 0)
    assert three["controller_workers"] == 3
    assert nine["controller_workers"] == 9
    assert three["manifest_identity"] != nine["manifest_identity"]


def test_smoke_filters_use_a_seed_prefix_and_selected_condition_only():
    runner = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",))
    jobs = runner._jobs(include_induction=False, include_grading=False)
    assert jobs == [{
        "condition": "e_full_loop", "seed": runner.config["seeds"][0],
        "track": "main", "sequence": 0}]


def test_induction_memory_is_condition_isolated():
    run_dir = os.path.join(
        "out", "games", "induction", "d_uncertain_monitor", "104729-01")
    left = _opponent_memory_path(run_dir, "d_uncertain_monitor")
    right = _opponent_memory_path(run_dir, "e_full_loop")
    assert left != right
    assert left.endswith(os.path.join("opponent-memory", "d_uncertain_monitor.json"))
    assert right.endswith(os.path.join("opponent-memory", "e_full_loop.json"))


def test_partial_smoke_aggregate_report_marks_unrun_conditions_na():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        summary = runner.run(
            resume=False, include_induction=False, include_grading=False)
        assert summary["jobs"] == summary["completed"] == 1
        aggregate = aggregate_runs(directory)
        write_report(directory, aggregate)
        report = open(os.path.join(directory, "report.md"), encoding="utf-8").read()
        assert "| a_stock_llm | 0 | 0 | n/a (n=0) | n/a (n=0) |" in report
        assert "| e_full_loop | 1 |" in report


def test_calibration_is_pooled_bucketed_and_reports_insufficient_samples():
    rows = [{
        "manifest": {"condition_id": "d_uncertain_monitor"},
        "calibration": ([{"atom_id": "a{}".format(index), "opponent": "fixed",
                          "strength": 0.95, "truth": 1} for index in range(10)]
                        + [{"atom_id": "b{}".format(index), "opponent": "fixed",
                            "strength": 0.15, "truth": 0} for index in range(3)]),
    }]
    report = _calibration_report(rows)
    assert report["pooled"]["samples"] == 13
    low, high = report["pooled"]["buckets"]
    assert low["bucket"] == "0.1" and low["within_tolerance"] is None
    assert high["bucket"] == "0.9" and high["samples"] == 10
    assert high["absolute_error"] == pytest.approx(0.05)
    assert high["within_tolerance"] is True
    assert report["per_opponent"]["fixed"] == report["pooled"]


def test_full_250_run_matrix_aggregates_byte_identically_and_preserves_fidelity():
    with tempfile.TemporaryDirectory() as directory:
        summary = HarnessRunner(directory, workers=4).run(resume=False)
        assert summary["jobs"] == summary["completed"] == 250
        assert summary["infrastructure_failures"] == 0
        aggregate = aggregate_runs(directory)
        assert all(row["completed_games"] == 30 for row in aggregate["conditions"].values())
        assert aggregate["grading_ab"]["games_per_arm"] == 30
        assert aggregate["induction"]["d_uncertain_monitor"]["games"] == 20
        assert aggregate["induction"]["e_full_loop"]["games"] == 20
        assert aggregate["induction"]["oracle_vs_induction"]["prediction_assumed"] is False
        assert aggregate["calibration"]["pooled"]["samples"] == 60
        assert aggregate["calibration"]["per_opponent"][
            "builtin-ai-experimental"]["samples"] == 60
        assert any(result["estimate"] is not None and result["estimate"] < 0
                   for metrics in aggregate["marginal_deltas"].values()
                   for result in metrics.values())
        first = canonical_json_bytes(aggregate)
        second = canonical_json_bytes(aggregate_runs(directory))
        assert first == second
        path = write_report(directory, aggregate)
        assert open(path, "rb").read() == first + b"\n"
        event_report = validate_file(os.path.join(directory, "aggregate-events.jsonl"))
        assert event_report.valid, event_report.to_dict()
        schema = json.load(open(os.path.join(
            REPO, "schemas", "freeciv-harness", "v1", "aggregate.schema.json"), encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(aggregate)


def test_resume_skips_valid_completed_games_without_double_applying_events():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory, workers=4)
        first = runner.run(resume=True, include_induction=False, include_grading=False)
        second = runner.run(resume=True, include_induction=False, include_grading=False)
        assert first["completed"] == second["completed"] == 150
        assert second["resumed"] == 150


def test_resume_never_reuses_a_completed_game_from_another_configuration():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory)
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        first = runner._run_one((0, job), resume=True)
        first_identity = first["manifest"]["manifest_identity"]
        runner.config["turn_limit"] += 1
        runner.config["configuration_hash"] = structural_hash(runner.config)
        second = runner._run_one((0, job), resume=True)
        assert not first["resumed"] and not second["resumed"]
        assert second["manifest"]["manifest_identity"] != first_identity


def test_game_manifest_records_source_rulebase_schema_and_wall_clock():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        result = runner._run_one((0, job), resume=False)
        manifest = json.load(open(os.path.join(
            result["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        assert manifest["events_schema_version"] == "1.0"
        assert manifest["source"]["commit"]
        assert len(manifest["source"]["implementation_sha256"]) == 64
        assert manifest["rulebase"] == runner.config["rulebase"]
        assert manifest["runtime"]["started_at"].endswith("Z")
        assert manifest["runtime"]["ended_at"].endswith("Z")
        assert len(manifest["attempt_id"]) == 16


def test_retry_keeps_behavior_identity_but_rotates_proxy_attempt_identity():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory)
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        first = runner._run_one((0, job), resume=False)
        first_manifest = json.load(open(os.path.join(
            first["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        second = runner._run_one((0, job), resume=False)
        second_manifest = json.load(open(os.path.join(
            second["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        assert first_manifest["manifest_identity"] == second_manifest["manifest_identity"]
        assert first_manifest["attempt_id"] != second_manifest["attempt_id"]


def test_rerun_replaces_stale_completed_status_before_backend_execution():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        manifest = runner._manifest(job, 0)
        run_dir = manifest["_run_dir"]
        os.makedirs(run_dir, exist_ok=True)
        status_path = os.path.join(run_dir, "status.json")
        with open(status_path, "w", encoding="utf-8") as stream:
            json.dump({"status": "completed", "completed": True}, stream)

        observed = {}

        def backend(_run_dir, _manifest, _context):
            observed.update(json.load(open(status_path, encoding="utf-8")))
            EventWriter(
                os.path.join(_run_dir, "events.jsonl"),
                _manifest["game_id"], durable=False,
            ).emit("run_started", 0, {
                "condition_id": _manifest["condition_id"],
                "manifest_identity": _manifest["manifest_identity"],
            })
            return {"completed": True, "infrastructure_failure": False}

        with mock.patch("freeciv.harness.runner.representative_game", backend):
            result = runner._run_one((0, job), resume=False)
        assert result["status"]["status"] == "completed"
        assert observed == {
            "status": "running", "completed": False,
            "infrastructure_failure": False,
            "manifest_identity": manifest["manifest_identity"],
        }
