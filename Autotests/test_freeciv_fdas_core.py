import json
import os
import sys
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AtomSpaceTransaction,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    DependentAtomSpaceStore,
    EntityRef,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    legacy_predicate_registry,
    legacy_view_from_revision,
    snapshot_scopes,
)
from freeciv_agent.state.atoms import (  # noqa: E402
    _build_legacy_atomspaces,
    build_atomspaces,
)


def _unit(row):
    return SimpleNamespace(
        unit_id=int(row["unit_id"]),
        unit_type=str(row.get("type", "")),
        tile=row.get("tile"),
        activity=row.get("activity"),
        x=row.get("x"),
        y=row.get("y"),
    )


def _city(row):
    return SimpleNamespace(
        city_id=int(row["city_id"]),
        tile=row.get("tile"),
        production_kind=row.get("production_kind"),
        production_value=row.get("production_value"),
        buildability_available=bool(
            row.get("buildability_available", False)),
        buildable=tuple(
            tuple(value) for value in row.get("buildable", ())),
        x=row.get("x"),
        y=row.get("y"),
    )


def _snapshot(event):
    payload = event["payload"]
    own = payload["own_state"]
    map_row = payload.get("map") or {}
    units = tuple(_unit(row) for row in own.get("units", ()))
    return SimpleNamespace(
        identity=SimpleNamespace(
            game_id=str(event["game_id"]),
            source_seq=int(payload["source_seq"])),
        player_id=int(payload["player_id"]),
        turn=int(event["turn"]),
        snapshot_id=str(payload["snapshot_id"]),
        research=SimpleNamespace(
            known_techs=tuple(
                own.get("research", {}).get("known_techs", ()))),
        cities=tuple(_city(row) for row in own.get("cities", ())),
        units=units,
        visible_tile_ids=tuple(map_row.get("visible_tile_ids", ())),
    )


def _fixtures():
    manifest_path = os.path.join(
        REPO,
        "benchmarks/gdo/captured_snapshots/"
        "city_defense_grounded_160_manifest.json")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    for fixture in manifest["fixtures"]:
        with open(os.path.join(REPO, fixture["path"]), encoding="utf-8") as stream:
            captured = json.load(stream)
        assert structural_hash(captured) == fixture["fixture_sha256"]
        yield _snapshot(captured["snapshot_event"])


def _support(key, snapshot_id="snapshot-1"):
    dependency = DependencyRef(
        DependencyKey("snapshot-field", snapshot_id, "test.value"),
        structural_hash({"value": 1}),
    )
    return SupportRecord.create(
        "test-derivation",
        "1.0",
        key.to_dict(),
        (dependency,),
        {"value": 1},
        ("test",),
    )


def test_typed_terms_and_atom_ids_are_deterministic_and_numeric_terms_fail():
    key = AtomKey(
        AtomNamespace.AUTHORITATIVE,
        "owns-city",
        (EntityRef("player", "1"), EntityRef("city", "17")),
        "scope:test:empire",
    )
    duplicate = AtomKey(
        "authoritative",
        "owns-city",
        (EntityRef("player", "1"), EntityRef("city", "17")),
        "scope:test:empire",
    )

    assert key == duplicate
    assert key.atom_id == duplicate.atom_id
    assert key.atom_id.startswith("atom-")
    with pytest.raises(TypeError, match="EntityRef or SymbolRef"):
        AtomKey(
            AtomNamespace.AUTHORITATIVE,
            "owns-city",
            (1, EntityRef("city", "17")),
            "scope:test:empire",
        )
    with pytest.raises(ValueError, match="entity ID"):
        EntityRef("city", "")
    with pytest.raises(ValueError, match="symbol"):
        SymbolRef("activity", "")


def test_predicate_registry_rejects_unknown_wrong_namespace_arity_and_kind():
    registry = legacy_predicate_registry()
    valid = AtomKey(
        AtomNamespace.AUTHORITATIVE,
        "owns-unit",
        (EntityRef("player", "1"), EntityRef("unit", "42")),
        "scope:test:empire",
    )
    assert registry.validate(valid, "empire") == valid

    with pytest.raises(KeyError, match="unregistered"):
        registry.require("invented-predicate")
    with pytest.raises(ValueError, match="namespace"):
        registry.validate(AtomKey(
            AtomNamespace.OBSERVATION,
            "owns-unit",
            valid.arguments,
            "scope:test:empire",
        ), "empire")
    with pytest.raises(ValueError, match="expects 2"):
        registry.validate(AtomKey(
            AtomNamespace.AUTHORITATIVE,
            "owns-unit",
            (EntityRef("player", "1"),),
            "scope:test:empire",
        ), "empire")
    with pytest.raises(ValueError, match="requires"):
        registry.validate(AtomKey(
            AtomNamespace.AUTHORITATIVE,
            "owns-unit",
            (EntityRef("player", "1"), EntityRef("city", "42")),
            "scope:test:empire",
        ), "empire")


def test_support_and_record_identity_include_dependencies_and_validity():
    key = AtomKey(
        AtomNamespace.AUTHORITATIVE,
        "unit-activity",
        (EntityRef("unit", "42"), SymbolRef("activity", "fortified")),
        "scope:test:empire",
    )
    first_support = _support(key)
    second_support = _support(key)
    validity = ValidityInterval("snapshot-1", 3, 3, 7)
    first = AtomRecord.create(
        key,
        AuthorityClass.ENGINE_AUTHORITATIVE,
        {"crisp": True, "strength": 1.0, "confidence": 1.0},
        validity,
        (first_support,),
        ("test",),
    )
    second = AtomRecord.create(
        key,
        AuthorityClass.ENGINE_AUTHORITATIVE,
        {"crisp": True, "strength": 1.0, "confidence": 1.0},
        validity,
        (second_support,),
        ("test",),
    )

    assert first_support == second_support
    assert first == second
    assert first.materialization_key == second.materialization_key
    changed = SupportRecord.create(
        "test-derivation",
        "1.0",
        key.to_dict(),
        (DependencyRef(
            DependencyKey("snapshot-field", "snapshot-1", "test.value"),
            structural_hash({"value": 2})),),
        {"value": 2},
        ("test",),
    )
    assert changed.support_id != first_support.support_id


def test_transaction_fails_closed_and_rollback_publishes_nothing():
    snapshot = next(_fixtures())
    scopes = snapshot_scopes(snapshot)
    transaction = AtomSpaceTransaction(
        snapshot.snapshot_id, legacy_predicate_registry(), scopes)
    bad_key = AtomKey(
        AtomNamespace.OBSERVATION,
        "owns-city",
        (EntityRef("player", "1"), EntityRef("city", "17")),
        next(scope.scope_id for scope in scopes if scope.scope_kind == "world"),
    )
    bad = AtomRecord.create(
        bad_key,
        AuthorityClass.PACKET_OBSERVATION,
        {"crisp": True},
        ValidityInterval(snapshot.snapshot_id, snapshot.turn, snapshot.turn, 1),
        (_support(bad_key, snapshot.snapshot_id),),
        ("test",),
    )
    with pytest.raises(ValueError, match="owns-city"):
        transaction.apply(bad)
    transaction.rollback()
    with pytest.raises(RuntimeError, match="closed"):
        transaction.apply(bad)
    with pytest.raises(RuntimeError, match="has not committed"):
        transaction.records


def test_full_build_is_deterministic_and_legacy_compatible_on_all_fixtures():
    store = DependentAtomSpaceStore()
    for snapshot in _fixtures():
        frozen = _build_legacy_atomspaces(snapshot)
        first = store.build(snapshot)
        second = store.build(snapshot)
        compatible = legacy_view_from_revision(first)

        assert first == second
        assert first.revision_id == second.revision_id
        assert first.build_hash == second.build_hash
        assert len(first.records) == len({row.atom_id for row in first.records})
        assert len(first.records) == (
            len(frozen.authoritative)
            + len(frozen.visible)
            + len(frozen.uncertain))
        assert compatible == frozen
        assert build_atomspaces(snapshot) == frozen
        assert all(record.supports for record in first.records)
        assert all(
            record.validity.snapshot_id == snapshot.snapshot_id
            for record in first.records)
