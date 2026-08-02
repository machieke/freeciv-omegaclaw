#!/usr/bin/env python3
"""Verify the default-off FDAS city-stability authority on frozen captures."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for path in (SRC, SCRIPT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import run_fdas_captured_replay as captured_replay  # noqa: E402

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    build_runtime,
    load_runtime_declaration,
)


DEFAULT_CONFIG = os.path.join(
    REPO, "profile", "dependent_atomspace_city_stability_authority.yaml")
DEFAULT_MANIFEST = os.path.join(
    REPO, "profile", "fdas_manifest_city_stability_authority.json")
DEFAULT_ROLLBACK_CONFIG = os.path.join(
    REPO, "profile", "dependent_atomspace.yaml")
CORE_IMPLEMENTATION_PATHS = (
    "src/freeciv_agent/planning/fdas.py",
    "src/freeciv_agent/planning/fdas_authority.py",
    "src/freeciv_agent/planning/fdas_commit.py",
    "src/freeciv_agent/planning/fdas_episodes.py",
    "src/freeciv_agent/pressure/fdas_adapter.py",
    "src/freeciv_agent/pressure/fdas_resources.py",
    "src/freeciv_agent/state/atomspace/runtime.py",
    "src/freeciv_agent/state/atomspace/unit.py",
    "benchmarks/freeciv/harness/engine_live.py",
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def implementation_identity(config_path=DEFAULT_CONFIG,
                            manifest_path=DEFAULT_MANIFEST):
    selected = tuple(
        os.path.relpath(os.path.abspath(path), REPO)
        for path in (config_path, manifest_path))
    implementation_paths = tuple(dict.fromkeys(
        CORE_IMPLEMENTATION_PATHS + selected))
    files = dict(
        (path, _sha256(os.path.join(REPO, path)))
        for path in implementation_paths)
    return {
        "files": files,
        "implementation_digest": structural_hash(files),
    }


def _percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def _latency(values):
    values = tuple(float(value) for value in values)
    return {
        "count": len(values),
        "maximum_ms": max(values) if values else None,
        "mean_ms": statistics.mean(values) if values else None,
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
    }


def _selected_legacy(relative, candidates):
    path = relative if os.path.isabs(relative) else os.path.join(REPO, relative)
    with open(path, encoding="utf-8") as stream:
        captured = json.load(stream)
    selected_id = captured.get("source_control", {}).get(
        "selected_operation_id")
    selected = next((
        row for row in captured.get("candidates", ())
        if row.get("operation_id") == selected_id
    ), None)
    if selected is None:
        return None, selected_id
    matches = tuple(
        row for row in candidates
        if (row.action == selected.get("action")
            and row.category == selected.get("category")))
    return (matches[0] if len(matches) == 1 else None), selected_id


def _run_once(snapshots, declaration, ruleset_ir):
    runtime = build_runtime(
        declaration,
        ruleset_ir=ruleset_ir,
        operation_records_source=lambda: ())
    rows = []
    failures = []
    for relative, snapshot, legacy_candidates in snapshots:
        try:
            selected, selected_id = _selected_legacy(
                relative, legacy_candidates)
            runtime.replace(snapshot)
            shadow = runtime.evaluate_shadow(snapshot, legacy_candidates)
            started = time.perf_counter()
            readout = runtime.evaluate_authority(
                snapshot, shadow, selected)
            elapsed = (time.perf_counter() - started) * 1000.0
            if readout is None:
                raise RuntimeError(
                    "authority profile returned no authority readout")
            rows.append({
                "action_key": readout.action_key,
                "authority_latency_ms": elapsed,
                "legacy_action_key": (
                    None if selected is None else selected.action_key),
                "legacy_category": (
                    None if selected is None else selected.category),
                "legacy_operation_id": selected_id,
                "path": relative,
                "readout": readout.to_dict(),
                "snapshot_id": snapshot.snapshot_id,
                "turn": snapshot.turn,
            })
        except Exception as error:
            failures.append({
                "diagnostic": str(error),
                "error_type": type(error).__name__,
                "path": relative,
                "snapshot_id": snapshot.snapshot_id,
            })
    return rows, failures


def _semantic_rows(rows):
    return tuple({
        key: value for key, value in row.items()
        if key != "authority_latency_ms"
    } for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--rollback-config", default=DEFAULT_ROLLBACK_CONFIG)
    parser.add_argument(
        "--authority-domain", default="city-stability",
        choices=("city-stability", "city-defense"))
    parser.add_argument("--capture-manifest", action="append",
                        dest="capture_manifests")
    parser.add_argument("--output")
    parser.add_argument(
        "--ruleset-root", default=os.environ.get("FREECIV_RULESET_ROOT"))
    parser.add_argument("--ruleset", default="civ2civ3")
    args = parser.parse_args(argv)
    if not args.ruleset_root:
        parser.error("--ruleset-root or FREECIV_RULESET_ROOT is required")

    patterns = args.capture_manifests or (
        captured_replay.DEFAULT_CAPTURE_GLOB,)
    manifests, fixtures, snapshots, gaps, corpus_failures = (
        captured_replay._load_corpus(patterns))
    declaration = load_runtime_declaration(args.config, args.manifest)
    rollback = load_runtime_declaration(args.rollback_config)
    ruleset_ir = compile_ruleset(args.ruleset_root, args.ruleset)
    first, first_failures = _run_once(
        snapshots, declaration, ruleset_ir)
    second, second_failures = _run_once(
        snapshots, declaration, ruleset_ir)
    failures = tuple(
        corpus_failures + first_failures + second_failures)
    authorized = tuple(
        row for row in first
        if row["readout"]["status"] == "authorized")
    fallbacks = tuple(
        row for row in first
        if row["readout"]["status"] == "fallback")
    disabled = tuple(
        row for row in first
        if row["readout"]["status"] == "disabled")
    fallback_reasons = Counter(
        row["readout"]["reason"] for row in fallbacks)

    exact_pass_through = all(
        row["action_key"] == row["legacy_action_key"]
        for row in authorized)
    exact_commit = all(
        row["readout"]["commit_validation"]
        ["plan_materialization_authorized"] is True
        and row["readout"]["commit_validation"]
        ["execution_authority"] is False
        for row in authorized)
    exact_resources = all(
        row["readout"]["operation_id"] in row["readout"]
        ["scheduling"]["joint_selected_operation_ids"]
        for row in authorized)
    pressure_selected = all(
        row["readout"]["authority_pressure"]["selected_operation_id"]
        == row["readout"]["operation_id"]
        for row in authorized)
    expected_domain = {
        "city-stability": "city_stability",
        "city-defense": "city_defense",
    }[args.authority_domain]
    expected_domains = {
        "city_defense": False,
        "city_production": False,
        "city_stability": False,
        "combat": False,
        "expansion": False,
        "local_movement": False,
        "research": False,
        "transport": False,
    }
    expected_domains[expected_domain] = True
    declared_shape = all(
        (row["legacy_category"] == "city_food_governor"
         and json.loads(row["action_key"])["action_type"]
         == "city_governor")
        if args.authority_domain == "city-stability" else
        (row["legacy_category"] == "city_defense"
         and json.loads(row["action_key"]) == {
             "action_type": "unit_fortify",
             "actor_id": json.loads(row["action_key"])["actor_id"],
         })
        for row in authorized)
    gates = {
        "authority_profile_is_narrow_{}".format(
            args.authority_domain.replace("-", "_")): (
            declaration["config"]["authority_enabled"] is True
            and declaration["config"]["domain_authority"]
            == expected_domains),
        "authorized_actions_match_declared_shape": declared_shape,
        "default_profile_rolls_back_all_fdas_authority": (
            rollback["config"]["authority_enabled"] is False
            and not any(rollback["config"]["domain_authority"].values())
            and rollback["manifest"]["policy_authority"] is False),
        "deterministic_readouts": (
            _semantic_rows(first) == _semantic_rows(second)),
        "exact_legacy_winner_pass_through": exact_pass_through,
        "final_execution_gate_remains_authoritative": exact_commit,
        "no_replay_failures": not failures,
        "positive_captured_authority_coverage": len(authorized) > 0,
        "pressure_route_selected_every_authorized_action": pressure_selected,
        "resource_and_packet_schedule_complete": exact_resources,
        "every_replay_has_explicit_authority_or_fallback": (
            len(first) == len(snapshots)
            and len(authorized) + len(fallbacks) + len(disabled)
            == len(snapshots)),
        "zero_policy_winner_changes": exact_pass_through,
    }
    report = {
        "claim_scope": (
            "bounded-{}-pass-through-authority; "
            "no-gameplay-improvement-claim".format(args.authority_domain)),
        "config": {
            "declaration_hash": declaration["declaration_hash"],
            "manifest_path": os.path.relpath(args.manifest, REPO),
            "profile_path": os.path.relpath(args.config, REPO),
            "rollback_declaration_hash": rollback["declaration_hash"],
            "rollback_profile_path": os.path.relpath(
                args.rollback_config, REPO),
        },
        "corpus": {
            "capture_completeness": (
                len(snapshots) / float(len(fixtures)) if fixtures else 0.0),
            "data_gaps": gaps,
            "manifests": manifests,
            "replayable_fixture_count": len(snapshots),
            "unique_fixture_count": len(fixtures),
        },
        "failures": list(failures),
        "fallback_reason_counts": dict(sorted(fallback_reasons.items())),
        "gates": gates,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latency": _latency(
            row["authority_latency_ms"] for row in first),
        "readouts": first,
        "result": {
            "authorized_count": len(authorized),
            "fallback_count": len(fallbacks),
            "passed": all(gates.values()),
            "policy_winner_change_count": sum(
                row["action_key"] != row["legacy_action_key"]
                for row in authorized),
        },
        "ruleset": args.ruleset,
        "schema_version": "1.1",
        "source": implementation_identity(args.config, args.manifest),
    }
    semantic = dict(report)
    semantic.pop("generated_at")
    report["report_hash"] = structural_hash(semantic)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0 if report["result"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
