"""M2 authoritative state, grounded-accessor, and execution-gate tests."""

import copy
import json
import os
import sys
import tempfile

import jsonschema
import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.execution import ExecutionGate, ProposedAction  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import (ContractError, GroundedRegistry, ProxyStateDTO,  # noqa: E402
                                 SnapshotConflict, SnapshotStore,
                                 StateSummaryService)
from freeciv_agent.state.atoms import QUANTITATIVE_PREDICATES  # noqa: E402
from freeciv_agent.state.parity import packet_reference, run_state_action_parity  # noqa: E402


FIXTURE_PATH = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2", "authoritative-state.fixture.json")
SCHEMA_PATH = os.path.join(REPO, "schemas", "freeciv-state", "v1", "snapshot.schema.json")


def _payload():
    with open(FIXTURE_PATH, encoding="utf-8") as stream:
        return json.load(stream)


def _snapshot(seq=431, payload=None):
    return ProxyStateDTO.parse("state-test", seq, payload or _payload()).to_snapshot()


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos", "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for state/ruleset integration tests")


def test_authoritative_contract_fixture_schema_and_stable_identity():
    payload = _payload()
    with open(SCHEMA_PATH, encoding="utf-8") as stream:
        jsonschema.Draft202012Validator(json.load(stream)).validate(payload)
    first = _snapshot()
    second = _snapshot()
    later_sequence = _snapshot(seq=432)
    assert first == second
    assert first.identity.state_hash == later_sequence.identity.state_hash
    assert first.snapshot_id != later_sequence.snapshot_id
    assert first.research.beakers_per_turn == 9
    assert first.economy.gold == 37
    assert first.player_alive is True
    assert first.city(3).production[1] == 5
    assert first.city(3).buildability_available
    assert first.visible_tile_ids == (82,)
    assert first.known_hut_tile_ids == ()
    assert first.legal_action_kinds == ("city_production", "unit_move")
    map_payload = first.map_dict()
    assert map_payload["tiles"] == [
        {"index": 82, "terrain": 1, "known": 2, "x": 2, "y": 2}]
    assert map_payload["visible"] == [[2, 2]]
    assert map_payload["coverage"] == {
        "status": "partial", "tile_records": 1, "visible_tiles": 1}


def test_government_mood_support_and_recovery_action_are_typed():
    payload = _payload()
    payload["authoritative"]["government"] = {
        "available": True, "current_id": 0, "current_name": "Anarchy",
        "target_id": 0, "target_name": "Anarchy",
        "revolution_finishes": payload["turn"],
        "in_revolution": True, "selection_required": True,
        "diagnostic": None,
    }
    unit = next(iter(payload["units"].values()))
    unit["homecity"] = 3
    unit["upkeep"] = [1, 1, 0, 2, 0, 0]
    city = payload["cities"]["3"]
    city.update({
        "ppl_happy": [0], "ppl_content": [1],
        "ppl_unhappy": [2], "ppl_angry": [0],
        "disorder": True, "was_happy": False, "had_famine": True,
        "unhappy_penalty": [0, 0, 0, 0, 0, 0],
        "usage": [1, 1, 0, 2, 0, 0],
    })
    payload["legal_actions"].append({
        "type": "government_change", "player_id": 0,
        "government_id": 1, "government_name": "Despotism",
        "target": {
            "government_id": 1, "government_name": "Despotism",
        },
        "is_valid": True,
    })

    snapshot = _snapshot(payload=payload)

    assert snapshot.government.current_name == "Anarchy"
    assert snapshot.government.selection_required
    assert snapshot.unit(unit["id"]).homecity == 3
    assert snapshot.city(3).disorder is True
    assert snapshot.city(3).had_famine is True
    assert "government_change" in snapshot.legal_action_kinds
    government_action = next(
        json.loads(row) for row in snapshot.legal_action_json
        if json.loads(row)["action_type"] == "government_change")
    assert government_action["target"] == {
        "government_id": 1, "government_name": "Despotism"}


def test_player_rates_action_and_net_gold_components_are_typed():
    payload = _payload()
    payload["authoritative"]["player"].update({
        "gold_per_turn": -2,
        "city_gold_surplus_per_turn": 3,
        "unit_gold_upkeep": 5,
        "gold_upkeep_reserve": 5,
        "gold_upkeep_style": "Mixed",
    })
    payload["legal_actions"].append({
        "type": "player_rates", "player_id": 0,
        "target": {
            "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
        },
        "is_valid": True,
    })

    snapshot = _snapshot(payload=payload)

    assert snapshot.economy.gold_per_turn == -2
    assert snapshot.economy.city_gold_surplus_per_turn == 3
    assert snapshot.economy.unit_gold_upkeep == 5
    assert snapshot.economy.gold_upkeep_reserve == 5
    assert snapshot.economy.gold_upkeep_style == "Mixed"
    assert "player_rates" in snapshot.legal_action_kinds
    rate_action = next(
        json.loads(row) for row in snapshot.legal_action_json
        if json.loads(row)["action_type"] == "player_rates")
    assert rate_action == {
        "action_type": "player_rates", "actor_id": 0,
        "target": {
            "luxury_rate": 0, "science_rate": 50, "tax_rate": 50,
        },
    }


def test_packet_parity_normalizes_sustainability_control_actions_independently():
    payload = _payload()
    payload["legal_actions"] = [
        {
            "type": "player_rates", "player_id": 0,
            "target": {
                "tax_rate": 50, "science_rate": 50, "luxury_rate": 0,
            },
            "is_valid": True,
        },
        {
            "type": "unit_action", "action": "home_city", "unit_id": 7,
            "params": {"city": "Roma", "city_id": 3},
            "is_valid": True,
        },
    ]

    snapshot = _snapshot(payload=payload)
    reference = packet_reference(payload)

    assert snapshot.legal_action_json == reference["legal"]
    assert snapshot.legal_actions_digest == reference["legal_digest"]


def test_packet_known_hut_tiles_are_typed_and_part_of_snapshot_identity():
    payload = _payload()
    payload["authoritative"]["known_hut_tiles"] = [82, 41, 82]
    with_huts = _snapshot(payload=payload)
    without_huts = _snapshot()

    assert with_huts.known_hut_tile_ids == (41, 82)
    assert with_huts.map_dict()["known_hut_tile_ids"] == [41, 82]
    assert with_huts.identity.state_hash != without_huts.identity.state_hash


@pytest.mark.parametrize("tile_id", (-1, 1000))
def test_packet_known_hut_tiles_must_be_within_map(tile_id):
    payload = _payload()
    payload["authoritative"]["known_hut_tiles"] = [tile_id]

    with pytest.raises(ContractError, match="must be within the map"):
        _snapshot(payload=payload)


def test_old_optimized_proxy_response_is_readable_but_fail_closed():
    with open(os.path.join(REPO, "benchmarks", "freeciv", "samples",
                           "real_state_turn1.json"), encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse("legacy", 1, json.load(stream)).to_snapshot()
    assert len(snapshot.units) == 7
    assert not snapshot.ruleset_ready
    assert not snapshot.research.available
    assert not snapshot.economy.available
    assert snapshot.player_alive is None
    assert snapshot.ruleset_diagnostic


def test_player_alive_must_be_an_exact_boolean():
    payload = _payload()
    payload["authoritative"]["player"]["is_alive"] = 0

    with pytest.raises(ContractError, match="player.is_alive must be a boolean"):
        _snapshot(payload=payload)


def test_player_alive_is_part_of_snapshot_identity():
    alive = _snapshot()
    payload = _payload()
    payload["authoritative"]["player"]["is_alive"] = False
    eliminated = _snapshot(payload=payload)

    assert eliminated.player_alive is False
    assert eliminated.own_state_dict()["player_alive"] is False
    assert alive.identity.state_hash != eliminated.identity.state_hash


def test_visible_foreign_units_are_observations_not_authoritative_own_state():
    payload = _payload()
    foreign = copy.deepcopy(payload["units"]["7"])
    foreign["id"] = 700
    foreign["owner"] = 1
    payload["units"]["700"] = foreign
    snapshot = _snapshot(payload=payload)
    assert snapshot.unit(700) is None
    assert snapshot.visible_enemy_unit(700).owner == 1
    assert all(row["unit_id"] != 700 for row in snapshot.own_state_dict()["units"])
    assert snapshot.map_dict()["visible_enemy_units"][0]["unit_id"] == 700
    store = SnapshotStore()
    store.replace(snapshot)
    atoms = store.current_atomspaces("state-test", 0).authoritative
    assert not any(atom.predicate == "owns-unit" and 700 in atom.args for atom in atoms)


def test_map_tiles_are_normalized_and_invalid_spatial_evidence_fails_closed():
    payload = _payload()
    payload["map"]["tiles"] = [{"index": 82, "terrain": "grassland"}]
    tile = _snapshot(payload=payload).map_dict()["tiles"][0]
    assert tile == {
        "index": 82, "terrain": "grassland", "x": 2, "y": 2}

    wrong_coordinate = _payload()
    wrong_coordinate["map"]["tiles"] = [{"index": 82, "x": 3, "y": 2}]
    with pytest.raises(ContractError, match="coordinates must match"):
        _snapshot(payload=wrong_coordinate)

    duplicate = _payload()
    duplicate["map"]["tiles"] = [{"index": 82}, {"index": 82}]
    with pytest.raises(ContractError, match="duplicate index"):
        _snapshot(payload=duplicate)

    invalid_visibility = _payload()
    invalid_visibility["visible_tiles"] = [1000]
    with pytest.raises(ContractError, match="visible_tiles entries must be within"):
        _snapshot(payload=invalid_visibility)

    missing_visibility_index = _payload()
    missing_visibility_index["visible_tiles"] = [{}]
    with pytest.raises(ContractError, match="requires an exact tile index"):
        _snapshot(payload=missing_visibility_index)

    invalid_visibility_type = _payload()
    invalid_visibility_type.pop("visible_tiles")
    invalid_visibility_type["map"]["visibility"] = {"82": 1}
    with pytest.raises(ContractError, match="values must be booleans"):
        _snapshot(payload=invalid_visibility_type)


def test_transactional_replace_removes_disappearing_entities_and_quantities_are_not_atoms():
    store = SnapshotStore()
    first = _snapshot()
    store.replace(first)
    before = store.current_atomspaces("state-test", 0)
    assert any(atom.predicate == "owns-unit" for atom in before.authoritative)
    assert not ({atom.predicate for atom in before.authoritative} & QUANTITATIVE_PREDICATES)

    payload = _payload()
    payload["turn"] += 1
    payload["game"]["turn"] += 1
    payload["units"] = {}
    payload["cities"]["3"]["production_kind"] = None
    payload["cities"]["3"]["production_value"] = None
    second = _snapshot(seq=500, payload=payload)
    store.replace(second)
    after = store.current_atomspaces("state-test", 0)
    assert not any(atom.predicate in ("owns-unit", "city-producing")
                   for atom in after.authoritative)
    with pytest.raises(SnapshotConflict):
        store.replace(first)


def test_grounded_registry_is_generated_from_ir_and_returns_typed_values():
    store = SnapshotStore()
    snapshot = _snapshot()
    store.replace(snapshot)
    registry = GroundedRegistry(compile_ruleset(_ruleset_root(), "civ2civ3"), store)
    assert set(registry.signatures) == GroundedRegistry.IMPLEMENTED
    assert registry.check("beakers-per-turn", snapshot.snapshot_id, 0).value == 9
    assert registry.check("city-size-at-least", snapshot.snapshot_id, 3, 3).executable
    assert registry.check("shield-stockpile", snapshot.snapshot_id, 3).value == 6
    assert registry.check("shields-per-turn", snapshot.snapshot_id, 3).value == 5
    assert registry.check("research-cost", snapshot.snapshot_id,
                          "civ2civ3", "Writing").value == 80
    build = registry.check("build-cost", snapshot.snapshot_id,
                           "civ2civ3", "unit", "Warriors")
    assert build.available and build.value > 0


def test_missing_buildability_and_ruleset_block_actions_without_transport():
    payload = _payload()
    payload["cities"]["3"].pop("buildability")
    payload["authoritative"]["ruleset"]["ready"] = False
    snapshot = _snapshot(payload=payload)
    store = SnapshotStore()
    store.replace(snapshot)
    submissions = []
    proposal = ProposedAction.create({
        "action_type": "city_production", "city_id": 3,
        "production_kind": 0, "production_value": 4,
    }, snapshot)
    outcome = ExecutionGate(store, submissions.append).execute("state-test", 0, proposal)
    assert not outcome.submitted and outcome.reason == "ruleset_unavailable"
    assert submissions == []


def test_stale_action_is_rejected_locally_and_current_exact_action_is_sent_once():
    store = SnapshotStore()
    first = _snapshot()
    store.replace(first)
    action = {"action_type": "unit_move", "actor_id": 7,
              "target": {"direction": "e", "x": 3, "y": 2}}
    stale = ProposedAction.create(action, first, "plan-1", "step-1")
    payload = _payload()
    payload["turn"] += 1
    payload["game"]["turn"] += 1
    current = _snapshot(seq=500, payload=payload)
    store.replace(current)
    submissions = []
    gate = ExecutionGate(store, lambda value: submissions.append(value) or {"accepted": True})
    rejected = gate.execute("state-test", 0, stale)
    assert rejected.reason == "stale_snapshot" and not rejected.submitted
    accepted = gate.execute("state-test", 0, ProposedAction.create(action, current))
    assert accepted.status == "accepted" and accepted.submitted
    assert submissions == [action]


def test_local_gate_rejection_is_a_valid_non_sent_action_lifecycle():
    store = SnapshotStore()
    snapshot = _snapshot()
    store.replace(snapshot)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "state-test", durable=False)
        root = writer.emit("run_started", snapshot.turn, {
            "condition_id": "state-test", "manifest_identity": "m"})
        stale = ProposedAction.create(
            {"action_type": "end_turn"}, snapshot, "plan-invalid", "step-invalid")
        payload = _payload()
        payload["turn"] += 1
        payload["game"]["turn"] += 1
        store.replace(_snapshot(seq=500, payload=payload))
        outcome = ExecutionGate(store, lambda _action: pytest.fail(
            "local rejection must not invoke transport"), writer).execute(
                "state-test", 0, stale, [root["event_id"]])
        report = validate_file(path)
    assert not outcome.submitted and outcome.reason == "stale_snapshot"
    assert report.valid, report.to_dict()


@pytest.mark.asyncio
async def test_async_execution_gate_uses_identical_preflight_and_event_path():
    store = SnapshotStore()
    snapshot = _snapshot()
    store.replace(snapshot)
    submissions = []

    async def transport(action):
        submissions.append(action)
        return {"accepted": True, "source": "async-live"}

    action = {"action_type": "unit_move", "actor_id": 7,
              "target": {"direction": "e", "x": 3, "y": 2}}
    diagnostics = {}
    outcome = await ExecutionGate(store, transport).execute_async(
        "state-test", 0, ProposedAction.create(action, snapshot),
        diagnostics=diagnostics)
    assert outcome.status == "accepted" and outcome.submitted
    assert submissions == [action]
    assert diagnostics["calls"] == 1
    assert diagnostics["preflight_latency_ms"] >= 0.0
    assert diagnostics["sent_event_latency_ms"] >= 0.0
    assert diagnostics["transport_latency_ms"] >= 0.0
    assert diagnostics["completion_event_latency_ms"] >= 0.0


def test_proxy_research_action_is_canonical_and_executable():
    payload = _payload()
    payload["legal_actions"] = [{
        "type": "tech_research", "tech_id": 25,
        "tech_name": "Engineering", "tech_cost": 370.0,
        "reason": "researchable", "is_valid": True,
    }]
    snapshot = _snapshot(payload=payload)
    action = {
        "action_type": "tech_research", "actor_id": 0,
        "target": {"tech_name": "Engineering"},
    }
    assert snapshot.legal_action_json == (
        json.dumps(action, sort_keys=True, separators=(",", ":")),)
    store = SnapshotStore()
    store.replace(snapshot)
    submitted = []
    outcome = ExecutionGate(
        store, lambda value: submitted.append(value) or {"accepted": True}).execute(
            "state-test", 0, ProposedAction.create(action, snapshot))
    assert outcome.status == "accepted"
    assert submitted == [action]


def test_proxy_internal_move_found_city_and_attack_actions_are_canonical():
    payload = _payload()
    payload["legal_actions"] = [
        {"type": "unit_move", "action": "move", "unit_id": 7,
         "params": {"direction": "e", "target": {"x": 3, "y": 2}},
         "is_valid": True, "priority": 5},
        {"type": "unit_action", "action": "build_city", "unit_id": 8,
         "params": {}, "is_valid": True, "action_id": 27},
        {"type": "unit_action", "action": "attack", "unit_id": 7,
         "params": {"direction": "e", "target": {"x": 4, "y": 2}},
         "is_valid": True, "action_id": 29},
    ]
    snapshot = _snapshot(payload=payload)
    actions = [json.loads(row) for row in snapshot.legal_action_json]
    assert {row["action_type"] for row in actions} == {
        "unit_move", "unit_build_city", "unit_attack"}
    assert next(row for row in actions if row["action_type"] == "unit_move") == {
        "action_type": "unit_move", "actor_id": 7,
        "target": {"x": 3, "y": 2}}
    assert next(row for row in actions if row["action_type"] == "unit_attack") == {
        "action_type": "unit_attack", "actor_id": 7,
        "target": {"x": 4, "y": 2}}


def test_proxy_move_preserves_only_typed_settlement_site_evidence():
    payload = _payload()
    payload["legal_actions"] = [{
        "type": "unit_move", "unit_id": 7,
        "params": {
            "target": {"x": 3, "y": 2},
            "settlement_site_eligible": True,
        },
        "is_valid": True,
    }]

    action = json.loads(_snapshot(payload=payload).legal_action_json[0])

    assert action == {
        "action_type": "unit_move", "actor_id": 7,
        "settlement_site_eligible": True,
        "target": {"x": 3, "y": 2},
    }
    payload["legal_actions"][0]["params"]["settlement_site_eligible"] = 1
    with pytest.raises(ContractError, match="settlement_site_eligible"):
        _snapshot(payload=payload)


def test_proxy_join_city_action_requires_and_preserves_exact_city_id():
    payload = _payload()
    payload["legal_actions"] = [{
        "action_type": "unit_join_city", "actor_id": 7,
        "target": {"city": "Rome", "city_id": 3}, "is_valid": True,
        "action_id": 28,
    }]
    action = json.loads(_snapshot(payload=payload).legal_action_json[0])
    assert action["target"] == {"city": "Rome", "city_id": 3}

    payload["legal_actions"][0]["target"].pop("city_id")
    with pytest.raises(ContractError, match="target.city_id"):
        _snapshot(payload=payload)


def test_summary_is_query_only_and_does_not_expose_raw_snapshot_or_legal_payloads():
    store = SnapshotStore()
    store.replace(_snapshot())
    summary = StateSummaryService(store).query("state-test", 0)
    value = summary.to_dict()
    assert value["snapshot_id"]
    assert value["research"]["beakers_per_turn"] == 9
    assert value["legal_action_kinds"] == list(
        store.current("state-test", 0).legal_action_kinds)
    assert "legal_actions" not in value and "authoritative" not in value
    assert "visible_enemy_units" in value
    llm_init = open(os.path.join(SRC, "freeciv_agent", "llm", "__init__.py"),
                    encoding="utf-8").read()
    assert "ProxyStateDTO" not in llm_init and "AuthoritativeSnapshot" not in llm_init


def test_snapshot_grounded_and_action_lifecycle_events_validate():
    store = SnapshotStore()
    snapshot = _snapshot()
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "state-test", durable=False)
        root = writer.emit("run_started", snapshot.turn,
                           {"condition_id": "state-test", "manifest_identity": "m"})
        state_event = store.emit_replace(snapshot, writer, [root["event_id"]])
        proposal_event = writer.emit("llm_proposal", snapshot.turn, {
            "claims": [], "goals": [{"predicate": "move"}], "model": "fixture",
            "prompt_version": "m2-test", "proposal_id": "proposal-state-test",
        }, caused_by=[state_event["event_id"]])
        registry = GroundedRegistry(compile_ruleset(_ruleset_root(), "civ2civ3"), store)
        check, check_event = registry.emit_check(
            "gold-at-least", snapshot.snapshot_id, writer, snapshot.turn,
            0, 20, caused_by=[proposal_event["event_id"]])
        action = {"action_type": "unit_move", "actor_id": 7,
                  "target": {"direction": "e", "x": 3, "y": 2}}
        proposal = ProposedAction.create(action, snapshot,
                                         grounded_preconditions=(check,))
        outcome = ExecutionGate(store, lambda value: {"accepted": True}, writer).execute(
            "state-test", 0, proposal, [check_event["event_id"]])
        report = validate_file(path)
    assert outcome.status == "accepted"
    assert report.valid, report.to_dict()


def test_100_turn_packet_state_and_randomized_legal_action_parity():
    report = run_state_action_parity(_payload(), turns=100, seed=4202)
    assert report["passed"], report["mismatches"][:3]
    assert report["stale_local_rejections"] == 99
    assert report["engine_rejections"] == 0
