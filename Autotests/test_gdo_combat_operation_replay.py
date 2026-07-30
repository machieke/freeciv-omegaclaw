"""Deterministic GDO-5 atomic-versus-independent replay acceptance."""

import copy
import importlib.util
import json
import os


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SCRIPT = os.path.join(
    REPO, "scripts",
    "run_gdo_combat_operation_replay.py")
CORPUS = os.path.join(
    REPO, "benchmarks", "gdo",
    "combat_operation_scenarios_v1.json")
CAPTURED_SCRIPT = os.path.join(
    REPO, "scripts",
    "run_gdo_combat_captured_replay.py")
LIFECYCLE_SCRIPT = os.path.join(
    REPO, "scripts",
    "run_gdo_combat_lifecycle_replay.py")
CAPTURED_MANIFEST = os.path.join(
    REPO, "benchmarks", "gdo",
    "captured_snapshots",
    "combat_operations_native_160_manifest.json")
STORED_SYNTHETIC_REPORT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_synthetic_diagnostic.json")
STORED_CAPTURED_REPORT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_captured_diagnostic.json")
STORED_LIFECYCLE_REPORT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_operation_lifecycle_diagnostic.json")


def _module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "gdo5_combat_replay",
            SCRIPT))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def _captured_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "gdo5_captured_combat_replay",
            CAPTURED_SCRIPT))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def _lifecycle_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "gdo5_combat_lifecycle_replay",
            LIFECYCLE_SCRIPT))
    module = (
        importlib.util
        .module_from_spec(spec))
    spec.loader.exec_module(
        module)
    return module


def test_atomic_combat_replay_passes_declared_mechanism_gates():
    module = _module()
    with open(
            CORPUS,
            encoding="utf-8") as stream:
        corpus = json.load(
            stream)

    report = module.run(
        corpus, iterations=3)

    assert report["passed"]
    assert report[
        "authority"] == (
            "synthetic-mechanism-only")
    assert not report[
        "policy_authority"]
    assert all(
        report["gates"].values())
    independent_duplicates = sum(
        row["independent"][
            "duplicated_target_count"]
        for row in report[
            "scenarios"])
    atomic_duplicates = sum(
        row["atomic"][
            "duplicated_target_count"]
        for row in report[
            "scenarios"])
    independent_partial = sum(
        row["independent"][
            "partial_activation_count"]
        for row in report[
            "scenarios"])
    atomic_partial = sum(
        row["atomic"][
            "partial_activation_count"]
        for row in report[
            "scenarios"])
    assert independent_duplicates > (
        atomic_duplicates) == 0
    assert independent_partial > (
        atomic_partial) == 0
    hashable = copy.deepcopy(
        report)
    expected = hashable.pop(
        "report_hash")
    assert (
        module.structural_hash(
            hashable)
    ) == expected


def test_combat_replay_corpus_is_frozen_and_synthetic():
    module = _module()
    with open(
            CORPUS,
            encoding="utf-8") as stream:
        corpus = json.load(
            stream)

    first = module.run(
        corpus, iterations=2)
    second = module.run(
        corpus, iterations=2)

    assert (
        first["corpus_hash"]
        == second["corpus_hash"])
    assert [
        (
            row["scenario_id"],
            row["atomic"][
                "decision_digest"],
        )
        for row in first[
            "scenarios"]
    ] == [
        (
            row["scenario_id"],
            row["atomic"][
                "decision_digest"],
        )
        for row in second[
            "scenarios"]
    ]
    assert corpus[
        "authority"] == (
            "synthetic-mechanism-only")


def test_captured_native_replay_matches_logged_atomic_readout():
    module = _captured_module()

    report = module.run(
        CAPTURED_MANIFEST,
        iterations=3,
        action_budget=8)

    assert report["passed"]
    assert report[
        "fixture_count"] == 5
    assert report[
        "atomic_duplicate_target_count"] == 0
    assert report[
        "independent_duplicate_target_count"] == 5
    assert all(
        row[
            "candidate_ids_match_source"]
        and row[
            "selected_ids_match_source"]
        and row[
            "reason_map_matches_source"]
        for row in report[
            "replays"])
    hashable = copy.deepcopy(
        report)
    expected = hashable.pop(
        "report_hash")
    assert (
        module.structural_hash(
            hashable)
    ) == expected


def test_checked_in_combat_diagnostics_pass_and_are_self_hashed():
    module = _module()
    for path, authority in (
        (
            STORED_SYNTHETIC_REPORT,
            "synthetic-mechanism-only",
        ),
        (
            STORED_CAPTURED_REPORT,
            "captured-player-visible-engine-events",
        ),
        (
            STORED_LIFECYCLE_REPORT,
            "synthetic-lifecycle-mechanism-only",
        ),
    ):
        with open(
                path,
                encoding="utf-8") as stream:
            report = json.load(
                stream)
        hashable = copy.deepcopy(
            report)
        expected = hashable.pop(
            "report_hash")

        assert report["passed"]
        assert report[
            "authority"] == authority
        assert not report[
            "policy_authority"]
        assert all(
            report["gates"].values())
        assert (
            module.structural_hash(
                hashable)
        ) == expected


def test_combat_lifecycle_replay_closes_terminal_and_release_gates():
    module = _lifecycle_module()
    with open(
            CORPUS,
            encoding="utf-8") as stream:
        corpus = json.load(
            stream)

    report = module.run(
        corpus, iterations=3)

    assert report["passed"]
    assert report[
        "flow_count"] == 9
    assert all(
        report["gates"].values())
    assert {
        row["flow_id"]:
            row["final_state"]
        for row in report[
            "flows"]
    } == module.EXPECTED_FINAL_STATES
    assert all(
        row[
            "active_claim_count"]
        == 0
        for row in report[
            "flows"])
    hashable = copy.deepcopy(
        report)
    expected = hashable.pop(
        "report_hash")
    assert (
        module.structural_hash(
            hashable)
    ) == expected
