#!/usr/bin/env python3
"""Replay captured city mood stages through the combat candidate readout."""

import argparse
import copy
from dataclasses import replace
import json
import os
import statistics
import sys
import time


REPO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    GroundedImpactPlanner,
)
from freeciv_agent.state.snapshot import (  # noqa: E402
    BuildingState,
    CityState,
    EconomicState,
    GovernmentState,
    PlayerScoreState,
    ResearchState,
)
import run_gdo_combat_captured_replay as captured  # noqa: E402


DEFAULT_MANIFEST = captured.DEFAULT_MANIFEST
DEFAULT_OUTPUT = os.path.join(
    REPO, "benchmarks", "gdo",
    "gdo5_combat_candidate_readout_diagnostic.json")


def _city(row):
    mood = row.get(
        "citizen_mood", {})
    governor = row.get(
        "governor", {})
    return CityState(
        city_id=int(
            row["city_id"]),
        owner=int(
            row["owner"]),
        name=str(
            row["name"]),
        tile=row.get("tile"),
        x=row.get("x"),
        y=row.get("y"),
        size=int(
            row["size"]),
        production_kind=row.get(
            "production_kind"),
        production_value=row.get(
            "production_value"),
        food_stock=row.get(
            "food_stock"),
        shield_stock=row.get(
            "shield_stock"),
        surplus=tuple(
            int(value)
            for value in row.get(
                "surplus", ())),
        production=tuple(
            int(value)
            for value in row.get(
                "production", ())),
        buildability_available=bool(
            row.get(
                "buildability_available",
                False)),
        buildable=tuple(
            (
                str(value[0]),
                int(value[1]),
                str(value[2]),
            )
            for value in row.get(
                "buildable", ())),
        buildability_diagnostic=row.get(
            "buildability_diagnostic"),
        feeling_happy=tuple(
            int(value)
            for value in mood.get(
                "happy", ())),
        feeling_content=tuple(
            int(value)
            for value in mood.get(
                "content", ())),
        feeling_unhappy=tuple(
            int(value)
            for value in mood.get(
                "unhappy", ())),
        feeling_angry=tuple(
            int(value)
            for value in mood.get(
                "angry", ())),
        disorder=row.get(
            "disorder"),
        was_happy=row.get(
            "was_happy"),
        had_famine=row.get(
            "had_famine"),
        unhappy_penalty=tuple(
            int(value)
            for value in row.get(
                "unhappy_penalty", ())),
        usage=tuple(
            int(value)
            for value in row.get(
                "usage", ())),
        governor_available=bool(
            governor.get(
                "available", False)),
        governor_enabled=governor.get(
            "enabled"),
        governor_minimal_surplus=tuple(
            int(value)
            for value in governor.get(
                "minimal_surplus", ())),
        governor_factor=tuple(
            int(value)
            for value in governor.get(
                "factor", ())),
        governor_require_happy=governor.get(
            "require_happy"),
        governor_allow_disorder=governor.get(
            "allow_disorder"),
        governor_max_growth=governor.get(
            "max_growth"),
        governor_allow_specialists=governor.get(
            "allow_specialists"),
        governor_happy_factor=governor.get(
            "happy_factor"),
        buildings=tuple(
            BuildingState(
                improvement_id=int(
                    value[
                        "improvement_id"]),
                name=str(
                    value["name"]),
                upkeep=value.get(
                    "upkeep"))
            for value in row.get(
                "buildings", ())))


def _snapshot(fixture):
    snapshot = captured._snapshot(
        fixture)
    own_state = fixture[
        "snapshot_event"][
        "payload"][
        "own_state"]
    rows = own_state.get(
            "cities", ())
    economy = own_state.get(
        "economy", {})
    research = own_state.get(
        "research", {})
    government = own_state.get(
        "government", {})
    score = own_state.get(
        "score", {})
    return replace(
        snapshot,
        cities=tuple(
            sorted(
                (_city(row)
                 for row in rows),
                key=lambda value:
                    value.city_id)),
        economy=EconomicState(
            gold=economy.get(
                "gold"),
            gold_per_turn=economy.get(
                "gold_per_turn"),
            tax_rate=economy.get(
                "tax_rate"),
            science_rate=economy.get(
                "science_rate"),
            luxury_rate=economy.get(
                "luxury_rate"),
            available=bool(
                economy.get(
                    "available", False)),
            diagnostic=economy.get(
                "diagnostic"),
            city_gold_surplus_per_turn=(
                economy.get(
                    "city_gold_surplus_per_turn")),
            unit_gold_upkeep=economy.get(
                "unit_gold_upkeep"),
            gold_upkeep_reserve=economy.get(
                "gold_upkeep_reserve"),
            gold_upkeep_style=economy.get(
                "gold_upkeep_style"),
            operating_gold_per_turn=economy.get(
                "operating_gold_per_turn"),
            capitalization_gold_per_turn=(
                economy.get(
                    "capitalization_gold_per_turn"))),
        research=ResearchState(
            known_techs=tuple(
                str(value)
                for value in research.get(
                    "known_techs", ())),
            target_id=research.get(
                "target_id"),
            target_name=research.get(
                "target_name"),
            progress=research.get(
                "progress"),
            cost=research.get(
                "cost"),
            beakers_per_turn=research.get(
                "beakers_per_turn"),
            available=bool(
                research.get(
                    "available", False)),
            diagnostic=research.get(
                "diagnostic"),
            gross_beakers_per_turn=(
                research.get(
                    "gross_beakers_per_turn")),
            tech_upkeep=research.get(
                "tech_upkeep")),
        government=GovernmentState(
            current_id=government.get(
                "current_id"),
            current_name=government.get(
                "current_name"),
            target_id=government.get(
                "target_id"),
            target_name=government.get(
                "target_name"),
            revolution_finishes=(
                government.get(
                    "revolution_finishes")),
            in_revolution=bool(
                government.get(
                    "in_revolution", False)),
            selection_required=bool(
                government.get(
                    "selection_required",
                    False)),
            available=bool(
                government.get(
                    "available", False)),
            diagnostic=government.get(
                "diagnostic")),
        own_score=score.get(
            "own"),
        opponent_scores=tuple(
            PlayerScoreState(
                player_id=int(
                    value[
                        "player_id"]),
                name=str(
                    value["name"]),
                score=value.get(
                    "score"),
                is_alive=value.get(
                    "is_alive"))
            for value in score.get(
                "opponents", ())))


def _legacy_required_garrison(
        planner, city):
    margin = planner._city_mood_margin(
        city)
    if (
            city.disorder is True
            or (
                margin is not None
                and margin <= 1)):
        return min(
            planner
            .military_units_per_city_limit,
            max(1, int(
                city.size or 1)))
    return 1


def _target_position(
        snapshot, fixture):
    target_id = fixture[
        "joint_groups"][0][
            "target_unit_id"]
    target = snapshot.visible_enemy_unit(
        target_id)
    if (
            target is None
            or target.x is None
            or target.y is None):
        raise ValueError(
            "captured joint target position is unavailable")
    return (
        int(target.x),
        int(target.y))


def _evaluate(fixture):
    snapshot = _snapshot(
        fixture)
    planner = (
        GroundedImpactPlanner())
    group = fixture[
        "joint_groups"][0]
    actor_ids = tuple(
        int(value)
        for value in group[
            "actor_unit_ids"])
    actors = tuple(
        snapshot.unit(actor_id)
        for actor_id in actor_ids)
    if (
            not actors
            or any(
                actor is None
                for actor in actors)
            or len({
                (actor.x, actor.y)
                for actor in actors
            }) != 1):
        raise ValueError(
            "captured joint actors are not co-located")
    position = (
        actors[0].x,
        actors[0].y)
    city = next((
        value for value in
        snapshot.cities
        if (
            value.x,
            value.y) == position
    ), None)
    if city is None:
        raise ValueError(
            "captured joint actors have no city mood context")
    local_defender_count = sum(
        1 for unit in snapshot.units
        if (
            unit.x,
            unit.y) == position
        and unit.unit_id in actor_ids)
    legacy_required = (
        _legacy_required_garrison(
            planner, city))
    current_required = (
        planner
        ._required_garrison_count(
            city))
    started = time.perf_counter()
    candidates = planner.candidates(
        snapshot)
    latency_ms = (
        time.perf_counter()
        - started) * 1000.0
    target_position = (
        _target_position(
            snapshot, fixture))
    recalled_actor_ids = tuple(sorted({
        int(row.action[
            "actor_id"])
        for row in candidates
        if (
            row.category
                == "tactical_attack"
            and row.action.get(
                "action_type")
                == "unit_attack"
            and (
                row.action.get(
                    "target", {}).get(
                        "x"),
                row.action.get(
                    "target", {}).get(
                        "y"),
            ) == target_position
            and row.action.get(
                "actor_id")
                in actor_ids)
    }))
    readout = {
        "city_id": city.city_id,
        "current_required_garrison":
            current_required,
        "joint_actor_ids": list(
            actor_ids),
        "legacy_all_joint_actors_suppressed":
            local_defender_count
            <= legacy_required,
        "legacy_required_garrison":
            legacy_required,
        "local_joint_defender_count":
            local_defender_count,
        "martial_law_relief":
            planner
            ._city_martial_law_relief(
                city),
        "recalled_attack_actor_ids":
            list(recalled_actor_ids),
        "single_step_preserves_required_garrison":
            local_defender_count - 1
            >= current_required,
        "snapshot_id":
            snapshot.snapshot_id,
        "target_position": list(
            target_position),
    }
    readout["readout_digest"] = (
        structural_hash(readout))
    return readout, latency_ms


def _percentile(values, fraction):
    rows = sorted(
        float(value)
        for value in values)
    return rows[
        int(float(fraction)
            * (len(rows) - 1))]


def _latency_summary(values):
    return {
        "maximum_ms": max(
            values),
        "mean_ms": statistics.mean(
            values),
        "p50_ms": statistics.median(
            values),
        "p95_ms": _percentile(
            values, 0.95),
        "sample_count": len(
            values),
    }


def run(manifest_path, iterations):
    manifest, fixtures = (
        captured._load_manifest(
            manifest_path))
    first = []
    latencies = []
    digests = {}
    for entry, fixture in fixtures:
        readout, latency = (
            _evaluate(fixture))
        first.append({
            "fixture_path":
                entry["path"],
            "readout": readout,
            "turn": int(
                entry["turn"]),
        })
        latencies.append(
            latency)
        digests.setdefault(
            entry["path"], set()).add(
                readout[
                    "readout_digest"])
    for _ in range(
            iterations - 1):
        for entry, fixture in fixtures:
            readout, latency = (
                _evaluate(fixture))
            latencies.append(
                latency)
            digests[
                entry["path"]].add(
                    readout[
                        "readout_digest"])
    gates = {
        "captured_authority_only":
            manifest["authority"]
            == "player-visible-engine-event",
        "candidate_readout_deterministic":
            all(
                len(values) == 1
                for values in
                digests.values()),
        "current_readout_recalls_every_joint_state":
            all(
                row["readout"][
                    "recalled_attack_actor_ids"]
                for row in first),
        "legacy_rule_suppressed_every_joint_state":
            all(
                row["readout"][
                    "legacy_all_joint_actors_suppressed"]
                for row in first),
        "martial_law_relief_never_increases_requirement":
            all(
                row["readout"][
                    "current_required_garrison"]
                <= row["readout"][
                    "legacy_required_garrison"]
                for row in first),
        "p95_candidate_readout_below_20_ms":
            _percentile(
                latencies, 0.95)
            < 20.0,
        "single_step_preserves_required_garrison":
            all(
                row["readout"][
                    "single_step_preserves_required_garrison"]
                for row in first),
    }
    report = {
        "authority":
            "captured-player-visible-engine-events",
        "claim_status":
            "candidate-recall-mechanism-only-no-execution-or-score-claim",
        "fixture_count": len(
            first),
        "gates": gates,
        "iterations": int(
            iterations),
        "latency": _latency_summary(
            latencies),
        "manifest_hash":
            manifest[
                "manifest_hash"],
        "passed": all(
            gates.values()),
        "policy_authority": False,
        "replays": first,
        "schema_version": "1.0",
        "source_events_sha256":
            manifest[
                "source_events_sha256"],
    }
    report["report_hash"] = (
        structural_hash(report))
    return report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=100)
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error(
            "--iterations must be in 1..10000")
    report = run(
        args.manifest,
        args.iterations)
    with open(
            args.output, "wb") as stream:
        stream.write(
            canonical_json_bytes(
                report))
        stream.write(b"\n")
    print(json.dumps({
        "output": os.path.abspath(
            args.output),
        "passed": report[
            "passed"],
        "report_hash": report[
            "report_hash"],
    }, sort_keys=True))
    return 0 if report[
        "passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
