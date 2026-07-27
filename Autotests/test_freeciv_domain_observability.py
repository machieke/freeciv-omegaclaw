"""Typed technology, production, and unit-lifecycle trace projections."""

import json
import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (
        os.path.join(_REPO, "src"),
        os.path.join(_REPO, "benchmarks", "freeciv", "harness")):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain_observability import DomainObservabilityEmitter  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.rulesets.ir import Requirement, Rule, RulesetIR  # noqa: E402
from freeciv_agent.state.snapshot import (  # noqa: E402
    AuthoritativeSnapshot, CityState, EconomicState, ResearchState,
    SnapshotIdentity, UnitState,
)


def _ir():
    requirement = Requirement(
        kind="Tech", name="Alphabet", range="Player", present=True,
        semantic="symbolic", predicate="has-tech",
        arguments=("$player", "Alphabet"),
        source={"file": "techs.ruleset", "line": 1})
    rule = Rule(
        rule_id="test:tech:Writing", target_kind="tech",
        rule_name="Writing", display_name="Writing",
        target_predicate="researchable",
        target_arguments=("$player", "Writing"),
        antecedents=(requirement,), obsolescence=(), quantitative={},
        disabled=False, source={"file": "techs.ruleset", "line": 2})
    return RulesetIR(
        ruleset="test", compiler_version="test/1",
        source_hashes={"techs.ruleset": "0" * 64}, rules=(rule,),
        grounded_signatures=(), predicate_catalog=())


def _city(city_id=1, name="Roma", target="Riflemen"):
    return CityState(
        city_id=city_id, owner=0, name=name, tile=10, x=2, y=3, size=2,
        production_kind=6, production_value=10, food_stock=4,
        shield_stock=8, surplus=(3, 4, 2, 1, 0, 1),
        production=(5, 4, 2, 1, 0, 1), buildability_available=True,
        buildable=(("unit", 10, target),))


def _unit(unit_id, unit_type, x=2, y=3):
    return UnitState(
        unit_id=unit_id, owner=0, unit_type=unit_type, type_id=0,
        tile=10, x=x, y=y, moves_left=3, hp=10, activity="idle")


def _snapshot(turn, units, cities=None, progress=0, rate=0):
    identity = SnapshotIdentity("game", turn, turn, str(turn) * 64)
    return AuthoritativeSnapshot(
        identity=identity, player_id=0, player_alive=True, phase="playing",
        ruleset_ready=True, ruleset_diagnostic=None,
        research=ResearchState(
            known_techs=("Alphabet",), target_id=2, target_name="Writing",
            progress=progress, cost=10, beakers_per_turn=rate, available=True),
        economy=EconomicState(
            gold=50, gold_per_turn=1, tax_rate=40, science_rate=60,
            luxury_rate=0, available=True),
        cities=tuple(cities or (_city(),)), units=tuple(units),
        visible_enemy_units=(), visible_tile_ids=(), known_hut_tile_ids=(),
        map_width=4, map_height=4, map_tiles=(), legal_action_json=(),
        legal_actions_digest="0" * 64, legal_action_kinds=())


def _read(path):
    return [
        json.loads(line) for line in open(path, encoding="utf-8")
        if line.strip()]


def test_domain_events_make_stalls_yields_and_lifecycle_explicit(tmp_path):
    path = str(tmp_path / "events.jsonl")
    writer = EventWriter(path, "game", durable=False)
    root = writer.emit(
        "run_started", 0,
        {"manifest_identity": "manifest", "condition_id": "condition"})
    emitter = DomainObservabilityEmitter(writer, _ir())

    first = _snapshot(1, (_unit(7, "Settlers"),))
    first_event = writer.emit(
        "state_snapshot", 1, first.event_payload(),
        caused_by=[root["event_id"]])
    emitter.emit_snapshot(first, first_event["event_id"])

    second = _snapshot(
        3, (_unit(8, "Riflemen"),),
        cities=(_city(), _city(2, "Neapolis")))
    second_event = writer.emit(
        "state_snapshot", 3, second.event_payload(),
        caused_by=[first_event["event_id"]])
    emitter.emit_snapshot(second, second_event["event_id"])

    rows = _read(path)
    assert sum(row["type"] == "technology_catalog" for row in rows) == 1
    progress = [row["payload"] for row in rows
                if row["type"] == "technology_progress"]
    assert progress[-1]["status"] == "stalled"
    assert progress[-1]["stalled_turns"] == 2
    assert progress[-1]["researchable_techs"] == ["Writing"]
    production = next(
        row["payload"] for row in rows if row["type"] == "production_state")
    assert production["cities"][0]["outputs"] == {
        "food": 5, "shield": 4, "trade": 2,
        "gold": 1, "luxury": 0, "science": 1,
    }
    lifecycle = [row["payload"] for row in rows
                 if row["type"] == "unit_lifecycle"]
    by_unit = {row["unit_id"]: row for row in lifecycle if row["transition"] == "disappeared"}
    assert by_unit[7]["cause"] == "city_founded"
    assert by_unit[7]["evidence_quality"] == "inferred"
    appeared = next(
        row for row in lifecycle
        if row["unit_id"] == 8 and row["transition"] == "appeared")
    assert appeared["cause"] == "production_completed"
    assert appeared["evidence_quality"] == "inferred"


def test_proxy_combat_journal_upgrades_disappearance_to_exact(tmp_path):
    path = str(tmp_path / "events.jsonl")
    writer = EventWriter(path, "game", durable=False)
    root = writer.emit(
        "run_started", 0,
        {"manifest_identity": "manifest", "condition_id": "condition"})
    emitter = DomainObservabilityEmitter(writer, _ir())
    first = _snapshot(1, (_unit(9, "Riflemen"),))
    state = writer.emit(
        "state_snapshot", 1, first.event_payload(),
        caused_by=[root["event_id"]])
    emitter.emit_snapshot(first, state["event_id"])
    second = _snapshot(2, ())
    state = writer.emit(
        "state_snapshot", 2, second.event_payload(),
        caused_by=[state["event_id"]])
    emitter.emit_snapshot(second, state["event_id"], raw={
        "authoritative": {"unit_lifecycle": [{
            "transition": "disappeared", "unit_id": 9, "source_seq": 2,
            "cause": "combat_attacker_lost",
            "detail": "Combat packet reported attacker HP 0.",
        }]}})
    removal = next(
        row["payload"] for row in _read(path)
        if row["type"] == "unit_lifecycle"
        and row["payload"]["transition"] == "disappeared")
    assert removal["cause"] == "combat_attacker_lost"
    assert removal["evidence_quality"] == "exact"
