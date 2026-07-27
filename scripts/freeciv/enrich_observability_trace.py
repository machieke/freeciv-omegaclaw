#!/usr/bin/env python3
"""Create a typed observability copy of a historical FreeCiv trace.

The source trace is never modified.  Snapshot-difference conclusions are
explicitly marked ``inferred`` or ``unattributed``; this command does not
upgrade historical evidence to packet-exact facts.
"""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "src")
HARNESS = os.path.join(REPO, "benchmarks", "freeciv", "harness")
for path in (SRC, HARNESS):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain_observability import DomainObservabilityEmitter  # noqa: E402
from freeciv_agent.events.schema import (  # noqa: E402
    assert_event_schema, canonical_json_bytes,
)
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.rulesets.ir import (  # noqa: E402
    Requirement, Rule, RulesetIR,
)
from freeciv_agent.state.snapshot import (  # noqa: E402
    AuthoritativeSnapshot, CityState, EconomicState, ResearchState,
    SnapshotIdentity, UnitState,
)


def _load_ir(path):
    document = json.load(open(path, encoding="utf-8"))

    def requirement(row):
        return Requirement(
            kind=row["kind"], name=row["name"], range=row["range"],
            present=row["present"], semantic=row["semantic"],
            predicate=row["predicate"], arguments=tuple(row["arguments"]),
            source=dict(row["source"]), survives=bool(row.get("survives", False)))

    def rule(row):
        target = row["target"]
        return Rule(
            rule_id=row["rule_id"], target_kind=row["target_kind"],
            rule_name=row["rule_name"], display_name=row["display_name"],
            target_predicate=target["predicate"],
            target_arguments=tuple(target["arguments"]),
            antecedents=tuple(requirement(item) for item in row["antecedents"]),
            obsolescence=tuple(requirement(item) for item in row["obsolescence"]),
            quantitative=dict(row["quantitative"]), disabled=bool(row["disabled"]),
            source=dict(row["source"]), traits=dict(row.get("traits", {})),
            tv=dict(row.get("tv", {"strength": 1.0, "confidence": 0.99})))

    return RulesetIR(
        ruleset=document["ruleset"],
        compiler_version=document["compiler_version"],
        source_hashes=dict(document["source_hashes"]),
        rules=tuple(rule(row) for row in document["rules"]),
        grounded_signatures=tuple(document["grounded_signatures"]),
        predicate_catalog=tuple(document["predicate_catalog"]),
        parameters=dict(document.get("parameters", {})))


def _integer(value):
    return int(value) if value is not None else None


def _unit(row):
    return UnitState(
        unit_id=int(row["unit_id"]), owner=int(row["owner"]),
        unit_type=str(row["type"]), type_id=_integer(row.get("type_id")),
        tile=_integer(row.get("tile")), x=_integer(row.get("x")),
        y=_integer(row.get("y")), moves_left=_integer(row.get("moves_left")),
        hp=_integer(row.get("hp")), activity=row.get("activity"),
        upkeep=tuple(row.get("upkeep", ())))


def _city(row):
    return CityState(
        city_id=int(row["city_id"]), owner=int(row["owner"]),
        name=str(row.get("name", "")), tile=_integer(row.get("tile")),
        x=_integer(row.get("x")), y=_integer(row.get("y")),
        size=int(row.get("size", 0)),
        production_kind=_integer(row.get("production_kind")),
        production_value=_integer(row.get("production_value")),
        food_stock=_integer(row.get("food_stock")),
        shield_stock=_integer(row.get("shield_stock")),
        surplus=tuple(row.get("surplus", ())),
        production=tuple(row.get("production", ())),
        buildability_available=bool(row.get("buildability_available", False)),
        buildable=tuple(tuple(item) for item in row.get("buildable", ())),
        buildability_diagnostic=row.get("buildability_diagnostic"))


def _snapshot(event):
    payload = event["payload"]
    own = payload["own_state"]
    research = own.get("research", {})
    economy = own.get("economy", {})
    map_row = payload.get("map", {})
    identity = SnapshotIdentity(
        event["game_id"], event["turn"], int(payload.get("source_seq", 0)),
        str(payload["state_hash"]))
    return AuthoritativeSnapshot(
        identity=identity, player_id=int(payload["player_id"]),
        player_alive=own.get("player_alive"), phase="historical",
        ruleset_ready=bool(own.get("ruleset_ready", False)),
        ruleset_diagnostic=own.get("ruleset_diagnostic"),
        research=ResearchState(
            known_techs=tuple(research.get("known_techs", ())),
            target_id=_integer(research.get("target_id")),
            target_name=research.get("target_name"),
            progress=_integer(research.get("progress")),
            cost=_integer(research.get("cost")),
            beakers_per_turn=_integer(research.get("beakers_per_turn")),
            available=bool(research.get("available", False)),
            diagnostic=research.get("diagnostic")),
        economy=EconomicState(
            gold=_integer(economy.get("gold")),
            gold_per_turn=_integer(economy.get("gold_per_turn")),
            tax_rate=_integer(economy.get("tax_rate")),
            science_rate=_integer(economy.get("science_rate")),
            luxury_rate=_integer(economy.get("luxury_rate")),
            available=bool(economy.get("available", False)),
            diagnostic=economy.get("diagnostic")),
        cities=tuple(_city(row) for row in own.get("cities", ())),
        units=tuple(_unit(row) for row in own.get("units", ())),
        visible_enemy_units=tuple(
            _unit(row) for row in map_row.get("visible_enemy_units", ())),
        visible_tile_ids=tuple(map_row.get("visible_tile_ids", ())),
        known_hut_tile_ids=tuple(map_row.get("known_hut_tile_ids", ())),
        map_width=int(map_row.get("width", 0)),
        map_height=int(map_row.get("height", 0)),
        map_tiles=tuple(map_row.get("tiles", ())),
        legal_action_json=(),
        legal_actions_digest=str(
            payload.get("legal_actions_digest", "0" * 64)),
        legal_action_kinds=())


class _Collector(object):
    def __init__(self, game_id):
        self.game_id = game_id
        self.events = []
        self.source = None
        self.ordinal = 0

    def begin(self, source):
        self.source = source
        self.events = []
        self.ordinal = 0

    def emit(self, event_type, turn, payload, caused_by=None, **_):
        identity = hashlib.sha256(canonical_json_bytes([
            self.source["event_id"], event_type, self.ordinal, payload
        ])).hexdigest()
        self.ordinal += 1
        event = {
            "schema_version": "1.0",
            "event_id": "enriched-" + identity[:24],
            "game_id": self.game_id,
            "turn": int(turn),
            "seq": -1,
            "ts": self.source["ts"],
            "type": event_type,
            "caused_by": list(caused_by or ()),
            "payload": payload,
        }
        self.events.append(event)
        return event


def enrich(source, destination, ir, force=False):
    if os.path.exists(destination) and not force:
        raise RuntimeError("destination already exists: {}".format(destination))
    rows = [
        json.loads(line) for line in open(source, encoding="utf-8")
        if line.strip()]
    if not rows:
        raise RuntimeError("source trace is empty")
    collector = _Collector(rows[0]["game_id"])
    emitter = DomainObservabilityEmitter(collector, ir)
    merged = []
    actions = {}
    prior_units = set()
    for event in rows:
        merged.append(dict(event))
        if event["type"] == "action_sent":
            action = event["payload"].get("action", {})
            actor_id = action.get("actor_id")
            if actor_id is not None:
                actions[int(actor_id)] = (
                    str(action.get("action_type", "")), event["event_id"])
        if event["type"] != "state_snapshot":
            continue
        snapshot = _snapshot(event)
        current_units = {unit.unit_id for unit in snapshot.units}
        lifecycle = []
        for unit_id in sorted(prior_units - current_units):
            action = actions.get(unit_id)
            if action is None:
                continue
            action_type, action_event_id = action
            cause = (
                "city_founded" if action_type == "unit_build_city"
                else "combat_attacker_lost" if action_type == "unit_attack"
                else None)
            if cause:
                lifecycle.append({
                    "transition": "disappeared",
                    "unit_id": unit_id,
                    "source_seq": snapshot.identity.source_seq,
                    "cause": cause,
                    "evidence_quality": "inferred",
                    "evidence_event_ids": [action_event_id],
                    "detail": (
                        "Historical inference: the unit disappeared after its "
                        "{} action; no combat/removal cause packet was recorded."
                    ).format(action_type),
                })
        raw = {"authoritative": {"unit_lifecycle": lifecycle}}
        collector.begin(event)
        emitter.emit_snapshot(snapshot, event["event_id"], raw=raw)
        merged.extend(collector.events)
        prior_units = current_units
        actions = {}

    sequence = {}
    for event in merged:
        turn = int(event["turn"])
        event["seq"] = sequence.get(turn, 0)
        sequence[turn] = event["seq"] + 1
        assert_event_schema(event)
    parent = os.path.dirname(os.path.abspath(destination))
    os.makedirs(parent, exist_ok=True)
    with open(destination, "wb") as stream:
        for event in merged:
            stream.write(canonical_json_bytes(event) + b"\n")
    report = validate_file(destination)
    if not report.valid:
        raise RuntimeError(
            "enriched trace failed validation: {}".format(
                report.errors[0].code))
    return {
        "source_events": len(rows),
        "enriched_events": len(merged),
        "added_events": len(merged) - len(rows),
        "destination": os.path.abspath(destination),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument(
        "--ruleset-ir",
        default=os.path.join(
            REPO, "build", "freeciv", "rulesets-v2", "civ2civ3",
            "ruleset.ir.json"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    result = enrich(
        args.source, args.destination, _load_ir(args.ruleset_ir),
        force=args.force)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
