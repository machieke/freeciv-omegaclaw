import copy
import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.pressure import (  # noqa: E402
    GameResourceKind,
    ResourceCapacityExtractor,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    DependentAtomSpaceStore,
    TransportCapabilityProjector,
    transport_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "benchmarks", "freeciv", "samples", "real_state_turn1.json")


def _rule(name, unit_class, capacity=0, cargo=(), flags=()):
    return SimpleNamespace(
        target_kind="unit",
        display_name=name,
        rule_name=name,
        quantitative={"transport_cap": {"value": capacity}},
        traits={
            "cargo": {"values": list(cargo)},
            "class": {"values": [unit_class]},
            "flags": {"values": list(flags)},
        })


def _ruleset(capacity=2):
    return SimpleNamespace(rules=(
        _rule("Settlers", "Small Land", flags=("Cities",)),
        _rule(
            "Trireme", "Trireme", capacity=capacity,
            cargo=("Land", "Merchant", "Small Land")),
    ))


def _unit(unit_id, unit_type, tile, transported=False,
          transported_by=0):
    return {
        "activity": "idle",
        # PACKET_UNIT_INFO.carrying is a trade-goods type, not cargo load.
        "carrying": -1,
        "done_moving": False,
        "homecity": 0,
        "hp": 20,
        "id": unit_id,
        "moves_left": 3,
        "owner": 0,
        "tile": tile,
        "transported": transported,
        "transported_by": transported_by,
        "type": unit_type,
        "type_id": 34 if unit_type == "Trireme" else 0,
        "upkeep": [],
        "veteran": 0,
        "x": tile % 48,
        "y": tile // 48,
    }


def _move(actor_id, target_tile, transport_required):
    return {
        "action_type": "unit_move",
        "actor_id": actor_id,
        "is_valid": True,
        "movement_cost": 3,
        "target": {"x": target_tile % 48, "y": target_tile // 48},
        "transport_required": transport_required,
    }


def _payload(cargo_count=0, transported=False, second_ferry=False,
             missing_load=False):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    founder_tile = 201 if transported else 200
    units = {
        "102": _unit(
            102, "Settlers", founder_tile,
            transported=transported,
            transported_by=200 if transported else 0),
        "200": _unit(200, "Trireme", 201),
    }
    loaded = 1 if transported else 0
    for offset in range(max(0, cargo_count - loaded)):
        cargo_id = 300 + offset
        units[str(cargo_id)] = _unit(
            cargo_id, "Settlers", 201,
            transported=True, transported_by=200)
    if missing_load:
        units["200"].pop("transported")
    if second_ferry:
        units["201"] = _unit(201, "Trireme", 201)
    payload["units"] = units
    payload["legal_actions"] = [
        _move(102, 202 if transported else 201, not transported)]
    return payload


def _snapshot(payload, source_seq):
    return ProxyStateDTO.parse(
        "fdas-transport", source_seq, payload).to_snapshot()


def _revision(payload, source_seq, capacity=2):
    ruleset = _ruleset(capacity)
    snapshot = _snapshot(payload, source_seq)
    projector = TransportCapabilityProjector(ruleset, "ruleset-proof")
    return snapshot, ruleset, DependentAtomSpaceStore(
        domain_projector=projector).build(snapshot)


def _carrier_records(revision, carrier_id=200):
    scope = next(
        value for value in revision.scopes
        if value.scope_kind == "transport"
        and value.root_entities[0].entity_id == "unit:{}".format(carrier_id))
    return tuple(
        value for value in revision.records
        if value.key.scope_id == scope.scope_id)


def test_transport_profile_capacity_and_unique_embark_are_exactly_projected():
    snapshot, ruleset, revision = _revision(_payload(), 600)
    records = _carrier_records(revision)
    predicates = {value.key.predicate for value in records}

    assert {
        "transport-accepts-unit-class",
        "transport-backed-by-unit",
        "transport-cargo-compatible",
        "transport-compatible-founder",
        "transport-current-embark-action",
        "transport-seat-available",
        "transport-seat-resource",
        "unit-ruleset-founder-capable",
    }.issubset(predicates)
    capacity = next(
        value for value in ResourceCapacityExtractor().extract(
            snapshot, ruleset_ir=ruleset).capacities
        if value.resource.kind == GameResourceKind.TRANSPORT_SEAT)
    resource_atom = next(
        value for value in records
        if value.key.predicate == "transport-seat-resource")
    assert resource_atom.key.arguments[1].entity_id == (
        capacity.resource.resource_id)
    assert capacity.quantity == 2


def test_full_or_unknown_load_never_projects_available_capacity_or_embark():
    _snapshot_value, _ruleset_value, full = _revision(
        _payload(cargo_count=2), 601)
    full_predicates = {
        value.key.predicate for value in _carrier_records(full)}
    assert "transport-at-capacity" in full_predicates
    assert "transport-seat-available" not in full_predicates
    assert "transport-current-embark-action" not in full_predicates

    _snapshot_value, _ruleset_value, unknown = _revision(
        _payload(missing_load=True), 602)
    unknown_predicates = {
        value.key.predicate for value in _carrier_records(unknown)}
    assert "transport-seat-resource" not in unknown_predicates
    assert "transport-seat-available" not in unknown_predicates
    assert "transport-at-capacity" not in unknown_predicates
    assert "transport-current-embark-action" not in unknown_predicates


def test_ambiguous_carrier_omits_embark_edge_and_exact_carriage_allows_exit():
    _snapshot_value, _ruleset_value, ambiguous = _revision(
        _payload(second_ferry=True), 603)
    assert not any(
        value.key.predicate == "transport-current-embark-action"
        for value in ambiguous.records)

    _snapshot_value, _ruleset_value, carried = _revision(
        _payload(cargo_count=1, transported=True), 604)
    predicates = {
        value.key.predicate for value in _carrier_records(carried)}
    assert "unit-carried-by" in predicates
    assert "transport-current-disembark-action" in predicates
    assert "transport-current-embark-action" not in predicates


def test_transport_capacity_retracts_incrementally_at_full_load():
    ruleset = _ruleset()
    projector = TransportCapabilityProjector(ruleset, "ruleset-proof")
    store = DependentAtomSpaceStore(domain_projector=projector)
    first = _snapshot(_payload(cargo_count=0), 605)
    second = _snapshot(_payload(cargo_count=2), 606)
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    current = store.update(second)
    predicates = {value.key.predicate for value in _carrier_records(current)}

    assert verification.equivalent, verification.to_dict()
    assert "transport-seat-available" not in predicates
    assert "transport-at-capacity" in predicates


def test_transport_load_is_derived_from_relations_not_trade_goods():
    empty_payload = _payload()
    empty_payload["units"]["200"]["carrying"] = 7
    empty = _snapshot(empty_payload, 607)
    loaded = _snapshot(_payload(cargo_count=1), 608)

    assert empty.unit(200).carrying == 7
    assert empty.unit(200).cargo_count == 0
    assert loaded.unit(200).carrying == -1
    assert loaded.unit(200).cargo_count == 1


def test_explicit_transport_load_must_match_authoritative_relations():
    payload = _payload(cargo_count=1)
    payload["units"]["200"]["cargo_count"] = 0

    try:
        _snapshot(payload, 609)
    except ValueError as error:
        assert "contradicts transported_by relations" in str(error)
    else:
        raise AssertionError("contradictory cargo_count was accepted")


def test_transport_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    names = {
        value["name"] for value in catalog["predicates"]
        if value["status"] == "component-only"
        and value["name"].startswith(("transport-", "unit-carried-",
                                      "unit-ruleset-founder-"))}
    expected = {
        value for value in transport_predicate_registry().predicates
        if value.startswith(("transport-", "unit-carried-",
                             "unit-ruleset-founder-"))}

    assert names == expected
