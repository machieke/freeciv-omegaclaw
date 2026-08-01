import copy
import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    CombatTaskForceProjector,
    DependentAtomSpaceStore,
    combat_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "benchmarks", "freeciv", "samples", "real_state_turn1.json")


def _rule(name, attack, defense, cost):
    return SimpleNamespace(
        target_kind="unit", display_name=name, rule_name=name,
        rule_id="unit:{}".format(name), quantitative={
            "attack": {"value": attack},
            "defense": {"value": defense},
            "hitpoints": {"value": 10},
            "firepower": {"value": 1},
            "build_cost": {"value": cost},
        })


def _ruleset():
    return SimpleNamespace(rules=(
        _rule("Warriors", 1, 1, 10),
        _rule("Phalanx", 1, 2, 20),
    ))


def _revision(unit):
    return {
        "activity": unit.get("activity"),
        "hp": unit.get("hp"),
        "id": unit.get("id"),
        "moves_left": unit.get("moves_left"),
        "owner": unit.get("owner"),
        "tile": unit.get("tile"),
        "transported": unit.get("transported"),
        "transported_by": unit.get("transported_by"),
        "type_id": unit.get("type_id"),
        "veteran": unit.get("veteran"),
    }


def _probability_rows(minimum, maximum):
    rows = []
    for action_id, action_name in (
            (24, "capture_units"), (45, "attack"),
            (46, "suicide_attack"), (49, "conquer_city"),
            (53, "bombard")):
        if action_name == "attack":
            row = (minimum, maximum, "bounded")
        else:
            row = (253, 0, "not_applicable")
        rows.append({
            "action_id": action_id, "action_name": action_name,
            "minimum": row[0], "maximum": row[1], "status": row[2],
        })
    return rows


def _snapshot():
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    template = payload["units"]["102"]
    actors = []
    for index, interval in enumerate(((140, 140), (80, 100))):
        actor_id = 102 + index
        actor = copy.deepcopy(template)
        actor.update({
            "activity": "idle", "hp": 10, "id": actor_id,
            "moves_left": 3, "owner": 0, "tile": 2030,
            "transported": False, "transported_by": 0,
            "type": "Warriors", "type_id": 0, "veteran": 0,
            "x": 14, "y": 42,
        })
        payload["units"][str(actor_id)] = actor
        payload["legal_actions"][str(actor_id)] = [{
            "action": "attack", "action_id": 45, "is_valid": True,
            "params": {"target": {"x": 14, "y": 41}},
            "type": "unit_action", "unit_id": actor_id,
        }]
        actors.append((actor, interval))
    defender = {
        "activity": "idle", "done_moving": False, "hp": 10,
        "id": 999, "moves_left": 3, "owner": 1, "tile": 1982,
        "transported": False, "transported_by": 0,
        "type": "Phalanx", "type_id": 2, "veteran": 0,
        "x": 14, "y": 41,
    }
    payload["units"]["999"] = defender
    payload["authoritative"] = {"combat_probabilities": []}
    for index, (actor, interval) in enumerate(actors):
        payload["authoritative"]["combat_probabilities"].append({
            "action_probabilities": _probability_rows(*interval),
            "actor_revision": _revision(actor),
            "actor_unit_id": actor["id"],
            "authority": "freeciv-server-action-probability",
            "player_id": 0, "request_kind": "background_refresh",
            "request_source_seq": index,
            "response_source_seq": index + 1,
            "schema_version": "1.0", "target_city_id": 0,
            "target_extra_id": -1,
            "target_stack_revision": [_revision(defender)],
            "target_tile_id": defender["tile"],
            "target_unit_id": defender["id"], "turn": 1,
        })
    return ProxyStateDTO.parse("fdas-combat", 2, payload).to_snapshot()


def _project(snapshot):
    return DependentAtomSpaceStore(domain_projector=CombatTaskForceProjector(
        _ruleset(), "ruleset-proof")).build(snapshot)


def test_native_intervals_keep_partition_and_unknown_mass_in_witnesses():
    revision = _project(_snapshot())
    engagement_scopes = [
        value for value in revision.scopes
        if value.scope_kind == "combat-engagement"]
    task_scopes = [
        value for value in revision.scopes if value.scope_kind == "task-force"]
    predicates = [value.key.predicate for value in revision.records]

    assert len(engagement_scopes) == 2
    assert len(task_scopes) == 1
    assert predicates.count("combat-outcome-partition") == 2
    assert predicates.count("combat-interval-unknown-mass-retained") == 1
    assert predicates.count("combat-current-legal-action") == 2
    assert "task-force-outcome-partition" in predicates
    assert {
        "task-force-conditional-attacker",
        "task-force-current-operation",
        "task-force-primary-attacker",
        "task-force-target-unit",
    }.issubset(set(predicates))


def test_target_visibility_is_required_for_action_and_task_force_readout():
    snapshot = _snapshot()
    hidden = replace(
        snapshot,
        identity=replace(
            snapshot.identity, source_seq=3,
            state_hash=structural_hash({"target": "hidden"})),
        visible_enemy_units=())
    revision = _project(hidden)
    predicates = {value.key.predicate for value in revision.records}

    assert sum(
        value.scope_kind == "combat-engagement"
        for value in revision.scopes) == 2
    assert not any(
        value.scope_kind == "task-force" for value in revision.scopes)
    assert "combat-engagement-visible-target" not in predicates
    assert "combat-current-legal-action" not in predicates
    assert "combat-outcome-partition" in predicates


def test_probability_interval_change_is_incremental_cold_equivalent():
    first = _snapshot()
    first_probability = first.combat_probabilities[1]
    changed_rows = tuple(
        replace(value, maximum=120)
        if value.action_name == "attack" else value
        for value in first_probability.action_probabilities)
    second = replace(
        first,
        identity=replace(
            first.identity, source_seq=3,
            state_hash=structural_hash({"attack_maximum": 120})),
        combat_probabilities=(
            first.combat_probabilities[0],
            replace(first_probability, action_probabilities=changed_rows),
        ))
    store = DependentAtomSpaceStore(
        domain_projector=CombatTaskForceProjector(
            _ruleset(), "ruleset-proof"))
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    current = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert current.revision_id != prior.revision_id


def test_combat_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith(("combat-", "task-force-"))}
    expected = {
        value for value in combat_predicate_registry().predicates
        if value.startswith(("combat-", "task-force-"))}

    assert names == expected
