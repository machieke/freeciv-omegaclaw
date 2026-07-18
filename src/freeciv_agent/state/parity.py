"""Independent packet-contract comparator for authoritative state/action parity."""

import copy
import hashlib
import json
import random

from ..events.schema import canonical_json_bytes
from ..execution import ExecutionGate, ProposedAction
from .dto import ProxyStateDTO
from .store import SnapshotStore


def _rows(value):
    return list(value.values()) if isinstance(value, dict) else list(value)


def _legal_json(value):
    rows = []
    if isinstance(value, list):
        rows = value
    else:
        for key in sorted(value, key=str):
            item = value[key]
            rows.extend(item if isinstance(item, list) else [item])
    result = []
    for row in rows:
        if row.get("is_valid") is False:
            continue
        if row.get("action_type"):
            normalized = copy.deepcopy(row)
            normalized.pop("is_valid", None)
            normalized.pop("reason", None)
        elif row.get("type") == "unit_action":
            action = str(row.get("action", ""))
            normalized = {
                "action_type": action if action.startswith("unit_") else "unit_" + action,
                "actor_id": row.get("unit_id", row.get("actor_id")),
            }
            if isinstance(row.get("params"), dict) and row["params"]:
                normalized["target"] = copy.deepcopy(row["params"])
        else:
            normalized = {"action_type": row.get("type")}
            if row.get("unit_id") is not None:
                normalized["actor_id"] = row["unit_id"]
            elif row.get("actor_id") is not None:
                normalized["actor_id"] = row["actor_id"]
            elif row.get("city_id") is not None:
                normalized["city_id"] = row["city_id"]
            for field in ("target", "production_kind", "production_value", "tech_id"):
                if field in row:
                    normalized[field] = copy.deepcopy(row[field])
        result.append(canonical_json_bytes(normalized).decode("utf-8"))
    return tuple(sorted(set(result)))


def packet_reference(payload):
    """Extract expected values independently from documented packet-backed fields."""
    player_id = int(payload["player_id"])
    authoritative = payload["authoritative"]
    cities = sorted((row for row in _rows(payload["cities"])
                     if int(row["owner"]) == player_id), key=lambda row: int(row["id"]))
    units = sorted((row for row in _rows(payload["units"])
                    if int(row["owner"]) == player_id), key=lambda row: int(row["id"]))
    visible = payload.get("visible_tiles")
    if visible is None:
        visible = [int(key) for key, value in payload["map"].get("visibility", {}).items()
                   if value]
    legal = _legal_json(payload["legal_actions"])
    own_atoms = set()
    for tech in payload["techs"].get("player{}".format(player_id), []):
        own_atoms.add(("has-tech", (str(player_id), tech)))
    for city in cities:
        cid = str(city["id"])
        own_atoms.add(("owns-city", (str(player_id), cid)))
        if city.get("tile") is not None:
            own_atoms.add(("city-at", (cid, str(city["tile"]))))
        if city.get("production_kind") is not None and city.get("production_value") is not None:
            own_atoms.add(("city-producing", (
                cid, str(city["production_kind"]), str(city["production_value"]))))
        build = city.get("buildability", {})
        if build.get("available") is True:
            for option in build.get("options", []):
                own_atoms.add(("buildable", (cid, str(option["type"]), str(option["id"]))))
    for unit in units:
        uid = str(unit["id"])
        own_atoms.add(("owns-unit", (str(player_id), uid)))
        own_atoms.add(("unit-type", (uid, str(unit["type"]))))
        if unit.get("tile") is not None:
            own_atoms.add(("unit-at", (uid, str(unit["tile"]))))
        if unit.get("activity"):
            own_atoms.add(("unit-activity", (uid, str(unit["activity"]))))
    return {
        "beakers_per_turn": authoritative["research"]["beakers_per_turn"],
        "cities": cities, "economy": authoritative["player"],
        "known_techs": tuple(sorted(payload["techs"].get(
            "player{}".format(player_id), []))),
        "legal": legal,
        "legal_digest": hashlib.sha256("\n".join(legal).encode("utf-8")).hexdigest(),
        "own_atoms": own_atoms, "player_id": player_id,
        "research": authoritative["research"], "ruleset": authoritative["ruleset"],
        "turn": int(payload["turn"]), "units": units,
        "visible": tuple(sorted(int(item) for item in visible)),
    }


def compare_packet_state(payload, snapshot, atomspaces):
    reference = packet_reference(payload)
    actual_atoms = {(atom.predicate, atom.args) for atom in atomspaces.authoritative}
    mismatches = []

    def same(field, actual, expected):
        if actual != expected:
            mismatches.append({"field": field, "actual": actual, "expected": expected})

    same("turn", snapshot.turn, reference["turn"])
    same("player_id", snapshot.player_id, reference["player_id"])
    same("known_techs", snapshot.research.known_techs, reference["known_techs"])
    same("research.progress", snapshot.research.progress,
         reference["research"]["bulbs_researched"])
    same("research.cost", snapshot.research.cost,
         reference["research"].get("researching_cost"))
    same("research.beakers_per_turn", snapshot.research.beakers_per_turn,
         reference["beakers_per_turn"])
    same("economy.gold", snapshot.economy.gold, reference["economy"]["gold"])
    same("economy.gold_per_turn", snapshot.economy.gold_per_turn,
         reference["economy"]["gold_per_turn"])
    same("visible", snapshot.visible_tile_ids, reference["visible"])
    same("legal", snapshot.legal_action_json, reference["legal"])
    same("legal_digest", snapshot.legal_actions_digest, reference["legal_digest"])
    same("atoms", actual_atoms, reference["own_atoms"])
    same("unit_ids", tuple(unit.unit_id for unit in snapshot.units),
         tuple(int(row["id"]) for row in reference["units"]))
    same("city_ids", tuple(city.city_id for city in snapshot.cities),
         tuple(int(row["id"]) for row in reference["cities"]))
    for city in snapshot.cities:
        expected = next(row for row in reference["cities"] if int(row["id"]) == city.city_id)
        for name, actual, wanted in (
                ("size", city.size, int(expected["size"])),
                ("food_stock", city.food_stock, expected.get("food_stock")),
                ("shield_stock", city.shield_stock, expected.get("shield_stock")),
                ("surplus", city.surplus, tuple(expected.get("surplus", []))),
                ("production", city.production, tuple(expected.get("prod", []))),
                ("production_kind", city.production_kind, expected.get("production_kind")),
                ("production_value", city.production_value, expected.get("production_value"))):
            same("city.{}.{}".format(city.city_id, name), actual, wanted)
    return mismatches


def generated_packet_frames(base_payload, turns=100, seed=4202):
    randomizer = random.Random(seed)
    frames = []
    for offset in range(turns):
        payload = copy.deepcopy(base_payload)
        turn = int(base_payload["turn"]) + offset
        payload["turn"] = turn
        payload["game"]["turn"] = turn
        payload["authoritative"]["source_seq"] = 1000 + offset
        payload["authoritative"]["player"]["gold"] = 37 + offset * 4
        payload["authoritative"]["research"]["bulbs_researched"] = 24 + offset * 9
        city = payload["cities"]["3"]
        city["food_stock"] = 11 + offset * 2
        city["shield_stock"] = 6 + offset * 5
        city["prod"][1] = 3 + (offset % 7)
        city["surplus"][1] = city["prod"][1] - 1
        unit = payload["units"].get("7")
        if unit is not None:
            unit["moves_left"] = randomizer.randrange(0, 4)
            unit["activity"] = "sentry" if offset % 9 == 0 else "idle"
        # Exercise removal/reappearance and production replacement semantics.
        if offset % 10 == 5:
            payload["units"] = {}
            payload["legal_actions"] = [row for row in payload["legal_actions"]
                                        if row.get("actor_id") != 7]
        if offset % 13 == 7:
            city["production_kind"] = None
            city["production_value"] = None
        frames.append(payload)
    return frames


def run_state_action_parity(base_payload, turns=100, seed=4202):
    store = SnapshotStore()
    engine_submissions = []
    gate = ExecutionGate(store, lambda action: engine_submissions.append(action) or {
        "accepted": True})
    mismatches = []
    stale_rejections = 0
    engine_rejections = 0
    accepted_actions = 0
    prior_proposal = None
    for index, payload in enumerate(generated_packet_frames(base_payload, turns, seed)):
        snapshot = ProxyStateDTO.parse(
            "packet-parity", payload["authoritative"]["source_seq"], payload).to_snapshot()
        store.replace(snapshot)
        atoms = store.current_atomspaces("packet-parity", payload["player_id"])
        for mismatch in compare_packet_state(payload, snapshot, atoms):
            mismatch["turn"] = snapshot.turn
            mismatches.append(mismatch)
        if prior_proposal is not None:
            outcome = gate.execute("packet-parity", payload["player_id"], prior_proposal)
            if not outcome.submitted and outcome.reason == "stale_snapshot":
                stale_rejections += 1
            else:
                mismatches.append({"field": "stale_action_gate", "turn": snapshot.turn,
                                   "actual": outcome.reason, "expected": "stale_snapshot"})
        if snapshot.legal_action_json:
            action = json.loads(snapshot.legal_action_json[0])
            current = ProposedAction.create(action, snapshot)
            outcome = gate.execute("packet-parity", payload["player_id"], current)
            accepted_actions += int(outcome.status == "accepted")
            engine_rejections += int(outcome.status == "rejected" and outcome.submitted)
            prior_proposal = current
        else:
            prior_proposal = None
    return {
        "accepted_actions": accepted_actions, "engine_rejections": engine_rejections,
        "engine_submissions": len(engine_submissions), "mismatches": mismatches,
        "passed": not mismatches and engine_rejections == 0,
        "seed": seed, "stale_local_rejections": stale_rejections, "turns": turns,
    }
