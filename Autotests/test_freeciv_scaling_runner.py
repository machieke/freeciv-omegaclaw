"""Isolated-process measurement and replay tests for scaling trials."""

import json
import os
import subprocess
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
for candidate in (REPO, SRC):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from benchmarks.freeciv.scaling.runner import (  # noqa: E402
    freeze_campaign,
    initialize_campaign,
    payload_identity,
    run_isolated,
    run_cells,
    smoke_payloads,
    validate_frozen_campaign,
)
import benchmarks.freeciv.scaling.runner as scaling_runner  # noqa: E402
from benchmarks.freeciv.scaling.model import TrialResult  # noqa: E402


def test_all_surfaces_complete_in_isolated_processes():
    for payload in smoke_payloads(seed=71):
        result = run_isolated(payload, "test-source", wall_seconds=30)
        material = result.to_dict()
        assert material["status"] == "completed", material["errors"]
        assert material["metrics"]["peak_rss_bytes"] > 0
        assert material["metrics"]["wall_ms"] >= 0
        if material["trial"]["cell"]["surface"] == "bridge":
            assert material["metrics"]["controller_inclusive_ms"] >= 0


def test_isolated_semantic_replay_excludes_timing_identity():
    payload = smoke_payloads(seed=72)[1]
    left = run_isolated(payload, "test-source", wall_seconds=30).to_dict()
    right = run_isolated(payload, "test-source", wall_seconds=30).to_dict()
    assert left["correctness"]["outcome_hash"] == right["correctness"]["outcome_hash"]
    assert left["trial_id"] == right["trial_id"]


def test_isolated_worker_resolves_repo_imports_from_clean_shell(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    result = run_isolated(
        smoke_payloads(seed=73)[0], "test-source", wall_seconds=30)
    material = result.to_dict()
    assert material["status"] == "completed", material["errors"]
    assert material["actual_work"]["live_revision_atoms"] == 100


def test_frozen_campaign_binds_exact_payloads_and_source(tmp_path):
    root = str(tmp_path / "campaign")
    initialize_campaign(root)
    payload = smoke_payloads(seed=81)[0]
    frozen = freeze_campaign(root, (payload,))
    assert frozen["payload_count"] == 1
    assert frozen["payloads"][0]["payload_id"] == payload_identity(payload)
    assert validate_frozen_campaign(root, (payload,)) == frozen
    changed = dict(payload)
    changed["parameters"] = dict(payload["parameters"], atom_count=101)
    with pytest.raises(ValueError, match="not preregistered"):
        validate_frozen_campaign(root, (changed,))
    with pytest.raises(ValueError, match="source identity"):
        validate_frozen_campaign(root, (payload,), source_identity="changed")


def test_heldout_execution_refuses_missing_freeze(tmp_path):
    root = str(tmp_path / "campaign")
    initialize_campaign(root)
    with pytest.raises(ValueError, match="frozen preregistration"):
        run_cells(root, (smoke_payloads(seed=82)[0],), phase="heldout")


def test_plan_command_expands_primary_matrix_without_running_cells():
    output = subprocess.check_output((
        sys.executable,
        os.path.join(REPO, "scripts", "freeciv", "run_scalability_campaign.py"),
        "plan", "--surface", "atomspace", "--tiers", "A0,A2",
        "--design", "primary", "--seeds", "2",
    ), cwd=REPO, universal_newlines=True)
    material = json.loads(output)
    assert material["artifact_type"] == (
        "freeciv-scalability-selection-plan")
    assert material["payload_count"] == 29
    assert material["semantic_seed_count"] == 2
    assert material["surface_counts"] == {"atomspace": 29}
    assert material["timing_sample_count"] == 2
    assert len(material["payload_ids"]) == len(set(material["payload_ids"]))


def test_exact_trial_identity_resumes_without_rerunning(tmp_path, monkeypatch):
    root = str(tmp_path / "resume-campaign")
    initialize_campaign(root)
    payload = smoke_payloads(seed=84)[0]
    first = run_cells(root, (payload,), phase="discovery")

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("exact completed trial should have resumed")

    monkeypatch.setattr(scaling_runner, "run_isolated", unexpected_run)
    second = run_cells(root, (payload,), phase="discovery")
    assert second == first


def test_parallel_discovery_is_checkpointed_as_semantic_screening(tmp_path):
    root = str(tmp_path / "parallel-discovery")
    initialize_campaign(root)
    payloads = smoke_payloads(seed=85)[:3]

    results = run_cells(root, payloads, phase="discovery", workers=2)

    assert len(results) == 3
    assert all(row["status"] == "completed" for row in results)
    assert all(row["trial"]["telemetry_mode"] == "semantic-screening"
               for row in results)
    with open(os.path.join(root, "discovery", "trials.json"),
              encoding="utf-8") as handle:
        persisted = json.load(handle)
    assert persisted["worker_count"] == 2
    assert persisted["randomization"] == (
        "discovery-concurrent-screening-v1")
    assert {row["trial_id"] for row in persisted["results"]} == {
        row["trial_id"] for row in results}


def test_parallel_heldout_execution_is_rejected(tmp_path):
    root = str(tmp_path / "parallel-heldout")
    initialize_campaign(root)
    payload = smoke_payloads(seed=86)[0]
    freeze_campaign(root, (payload,))

    with pytest.raises(ValueError, match="exactly one worker"):
        run_cells(root, (payload,), phase="heldout", workers=2)


def test_repeated_resource_termination_stops_remaining_tier(
        tmp_path, monkeypatch):
    root = str(tmp_path / "tier-stop")
    initialize_campaign(root)
    payloads = tuple({
        "surface": "atomspace",
        "tier": "A4",
        "seed": seed,
        "parameters": {
            "atom_count": 100,
            "scope_count": 2,
            "support_multiplicity": 4,
            "topology": "local",
        },
    } for seed in (1, 2, 3)) + (smoke_payloads(seed=87)[0],)
    launched = []

    def bounded_worker(payload, source_identity, phase="discovery",
                       arm="kernel", telemetry_mode="aggregate", **_kwargs):
        launched.append((payload["tier"], payload["seed"]))
        trial = scaling_runner._trial_spec(
            payload, source_identity, phase=phase, arm=arm,
            telemetry_mode=telemetry_mode)
        if payload["tier"] == "A4":
            return TrialResult(
                trial, "stopped", (), (), (("stop_rule", "wall-time"),),
                ("wall limit exceeded",))
        return TrialResult(
            trial, "completed", (("live_revision_atoms", 100),),
            (("wall_ms", 1.0),),
            (("cold_incremental_equivalent", True),
             ("count_exact", True),
             ("synthetic_namespace_only", True)))

    monkeypatch.setattr(scaling_runner, "run_isolated", bounded_worker)
    results = run_cells(root, payloads, phase="discovery")

    assert launched == [("A4", 1), ("A4", 2), ("smoke", 87)]
    skipped = results[2]
    assert skipped["status"] == "stopped"
    assert skipped["correctness"]["stop_rule"] == (
        "repeated-resource-termination")
    assert skipped["correctness"]["workload_not_entered"] is True
    assert len(skipped["correctness"]["trigger_trial_ids"]) == 2
    assert results[3]["status"] == "completed"
