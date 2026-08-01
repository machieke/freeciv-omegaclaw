import copy
import importlib.util
import json
import os
import random
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state import ProxyStateDTO, SnapshotStore  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AtomSpaceTransaction,
    AuthorityClass,
    DependencyIndex,
    DependencyKey,
    DependencyRef,
    DependentAtomSpaceStore,
    DerivationRegistry,
    DerivationSpec,
    EntityRef,
    SnapshotDelta,
    StaleAtomSpaceRevision,
    SupportRecord,
    ValidityInterval,
    legacy_predicate_registry,
    snapshot_dependency_fingerprints,
    snapshot_scopes,
)


FIXTURE = os.path.join(
    REPO, "contracts/freeciv-proxy/v2/authoritative-state.fixture.json")


def _payload():
    with open(FIXTURE, encoding="utf-8") as stream:
        return json.load(stream)


def _snapshot(payload=None, source_seq=431):
    return ProxyStateDTO.parse(
        "fdas-dependency-test", source_seq, payload or _payload()).to_snapshot()


def _captured_snapshots():
    script_path = os.path.join(REPO, "scripts/run_fdas_phase0_baseline.py")
    spec = importlib.util.spec_from_file_location("fdas_phase0", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(os.path.join(
            REPO,
            "benchmarks/gdo/captured_snapshots/"
            "city_defense_grounded_160_manifest.json"), encoding="utf-8") as stream:
        manifest = json.load(stream)
    result = []
    for fixture in manifest["fixtures"]:
        with open(os.path.join(REPO, fixture["path"]), encoding="utf-8") as stream:
            captured = json.load(stream)
        result.append(module._snapshot_view(captured["snapshot_event"]))
    return tuple(result)


def _support(dependency, suffix):
    return SupportRecord.create(
        "multiple-support-test",
        "1.0",
        {"suffix": suffix},
        (dependency,),
        {"source": suffix},
        ("test",),
    )


def _record(snapshot, key, support):
    return AtomRecord.create(
        key,
        AuthorityClass.ENGINE_AUTHORITATIVE,
        {"confidence": 1.0, "crisp": True, "strength": 1.0},
        ValidityInterval(
            snapshot.snapshot_id,
            snapshot.turn,
            snapshot.turn,
            snapshot.identity.source_seq,
        ),
        (support,),
        ("test",),
    )


def test_snapshot_delta_is_field_specific_and_stable():
    first = _snapshot()
    payload = _payload()
    payload["cities"]["3"]["production_value"] = 5
    second = _snapshot(payload, 432)

    delta = SnapshotDelta.between(first, second)
    paths = {key.path for key in delta.changed_dependency_keys}

    assert delta.prior_snapshot_id == first.snapshot_id
    assert delta.current_snapshot_id == second.snapshot_id
    assert delta.source_seq_advanced
    assert not delta.turn_advanced
    assert not delta.legal_actions_changed
    assert not delta.visibility_changed
    assert "cities.3.production_value" in paths
    assert all(not path.startswith("units.") for path in paths)
    assert len(delta.collection_updates) == 1
    assert delta.collection_updates[0].collection == "cities"
    assert delta == SnapshotDelta.between(first, second)


def test_closed_collection_membership_is_fingerprinted_and_invalidated():
    first = _snapshot()
    payload = copy.deepcopy(_payload())
    payload["units"]["90"] = {
        "activity": "idle",
        "hp": 10,
        "id": 90,
        "moves_left": 3,
        "owner": 1,
        "tile": 82,
        "type": "Warriors",
        "type_id": 4,
        "upkeep": [0, 0, 0, 0, 0, 0],
        "x": 2,
        "y": 2,
    }
    second = _snapshot(payload, 432)

    fingerprints = snapshot_dependency_fingerprints(first)
    paths = {key.path for key in fingerprints}
    changed = {
        key.path for key in SnapshotDelta.between(
            first, second).changed_dependency_keys}

    assert "visible_enemy_units.__members__" in paths
    assert "visible_enemy_units.__members__" in changed
    assert "visible_enemy_units.90.__exists__" in changed


def test_incremental_projection_matches_cold_and_recomputes_changed_relation():
    first = _snapshot()
    payload = _payload()
    payload["cities"]["3"]["production_value"] = 5
    second = _snapshot(payload, 432)
    store = DependentAtomSpaceStore()
    prior = store.build(first)

    verification = store.verify_incremental(second, first, prior)
    revision = store.update(second)

    assert verification.equivalent, verification.to_dict()
    assert verification.mismatch_categories == ()
    assert revision.metrics.recomputed_records == 1
    assert revision.metrics.refreshed_records == len(revision.records) - 1
    assert revision.metrics.invalidated_supports == 1
    assert revision.metrics.unsupported_atoms == 1
    assert revision.dependency_index.stale_dependencies(
        snapshot_dependency_fingerprints(second)) == ()


def test_randomized_mutation_sequence_is_cold_equivalent():
    randomizer = random.Random(1729)
    payload = _payload()
    prior_snapshot = _snapshot(payload, 431)
    store = DependentAtomSpaceStore()
    prior_revision = store.build(prior_snapshot)
    fields = ("production_value", "food_stock", "shield_stock")
    for source_seq in range(432, 452):
        payload = copy.deepcopy(payload)
        field = randomizer.choice(fields)
        payload["cities"]["3"][field] = randomizer.randint(0, 30)
        payload["units"]["7"]["activity"] = randomizer.choice((
            "idle", "fortified", "sentry"))
        current = _snapshot(payload, source_seq)
        verification = store.verify_incremental(
            current, prior_snapshot, prior_revision)
        assert verification.equivalent, verification.to_dict()
        prior_revision = store.update(current)
        prior_snapshot = current


def test_captured_revision_sequence_is_incremental_cold_equivalent():
    snapshots = _captured_snapshots()
    store = DependentAtomSpaceStore(revision_retention=4)
    prior_snapshot = snapshots[0]
    prior_revision = store.build(prior_snapshot)
    recomputed = []
    for current in snapshots[1:]:
        verification = store.verify_incremental(
            current, prior_snapshot, prior_revision)
        assert verification.equivalent, verification.to_dict()
        prior_revision = store.update(current)
        recomputed.append(prior_revision.metrics.recomputed_records)
        prior_snapshot = current

    assert len(recomputed) == 12
    assert all(value < len(prior_revision.records) for value in recomputed)


def test_support_retraction_preserves_an_atom_with_independent_support():
    snapshot = _snapshot()
    scopes = snapshot_scopes(snapshot)
    scope_id = next(
        value.scope_id for value in scopes if value.scope_kind == "empire")
    key = AtomKey(
        AtomNamespace.AUTHORITATIVE,
        "owns-city",
        (EntityRef("player", "0"), EntityRef("city", "3")),
        scope_id,
    )
    first_key = DependencyKey("snapshot-field", "test", "first")
    second_key = DependencyKey("snapshot-field", "test", "second")
    first_support = _support(
        DependencyRef(first_key, structural_hash(1)), "first")
    second_support = _support(
        DependencyRef(second_key, structural_hash(2)), "second")
    transaction = AtomSpaceTransaction(
        snapshot.snapshot_id, legacy_predicate_registry(), scopes)
    transaction.apply(_record(snapshot, key, first_support))
    transaction.apply(_record(snapshot, key, second_support))

    invalidation = transaction.invalidate((first_key,))
    transaction.commit()
    remaining = transaction.records

    assert invalidation.surviving_atom_ids == (key.atom_id,)
    assert invalidation.unsupported_atom_ids == ()
    assert len(remaining) == 1
    assert remaining[0].supports == (second_support,)


def _spec(derivation_id, stratum, evaluator, depends_on=(),
          output_templates=(), completeness=None):
    return DerivationSpec(
        derivation_id=derivation_id,
        version="1.0",
        stratum=stratum,
        scope_kinds=frozenset(("empire",)),
        input_patterns=(),
        grounding_calls=(),
        output_templates=output_templates,
        evaluator=evaluator,
        completeness=completeness,
        eager_policy="always",
        cache_policy="revision",
        maximum_bindings=10,
        maximum_outputs_per_binding=10,
        export_policy="local",
        depends_on=depends_on,
    )


def test_derivations_reject_undeclared_access_and_invalid_strata():
    declared = DependencyKey("snapshot-field", "test", "declared")
    hidden = DependencyKey("snapshot-field", "test", "hidden")
    registry = DerivationRegistry((
        _spec("reads-declared", 0, lambda context: (
            {"value": context.read(declared)},)),
    ))
    run = registry.evaluate(
        "reads-declared",
        "empire",
        {declared: 7},
        (declared,),
    )

    assert run.outputs == ({"value": 7},)
    assert run.dependencies[0].key == declared
    with pytest.raises(RuntimeError, match="undeclared"):
        DerivationRegistry((
            _spec("reads-hidden", 0, lambda context: (
                context.read(hidden),)),
        )).evaluate(
            "reads-hidden", "empire", {hidden: 9}, (declared,))

    invalid = DerivationRegistry()
    invalid.register(_spec("base", 1, lambda _context: ()))
    invalid.register(_spec(
        "dependent", 1, lambda _context: (), depends_on=("base",)))
    with pytest.raises(ValueError, match="strata"):
        invalid.validate()

    cycle = DerivationRegistry()
    cycle.register(_spec(
        "cycle-a", 1, lambda _context: (), depends_on=("cycle-b",)))
    cycle.register(_spec(
        "cycle-b", 2, lambda _context: (), depends_on=("cycle-a",)))
    with pytest.raises(ValueError, match="cycle"):
        cycle.validate()

    with pytest.raises(ValueError, match="completeness"):
        _spec(
            "unsafe-negative",
            0,
            lambda _context: (),
            output_templates=({"negated": True},),
        )


def test_reverse_index_invalidates_transitive_atom_dependencies():
    snapshot = _snapshot()
    scope_id = next(
        value.scope_id for value in snapshot_scopes(snapshot)
        if value.scope_kind == "empire")
    source_key = DependencyKey("snapshot-field", "test", "source")
    backup_key = DependencyKey("snapshot-field", "test", "backup")
    base_key = AtomKey(
        AtomNamespace.AUTHORITATIVE,
        "owns-city",
        (EntityRef("player", "0"), EntityRef("city", "3")),
        scope_id,
    )
    base_single = _record(
        snapshot,
        base_key,
        _support(DependencyRef(source_key, structural_hash(1)), "base"),
    )
    backup_support = _support(
        DependencyRef(backup_key, structural_hash(2)), "backup")
    base = AtomRecord.create(
        base_single.key,
        base_single.authority,
        base_single.truth,
        base_single.validity,
        base_single.supports + (backup_support,),
        base_single.provenance_ids,
    )
    derived_key = AtomKey(
        AtomNamespace.DERIVED,
        "derived-test",
        (EntityRef("city", "3"),),
        scope_id,
    )
    derived_support = _support(DependencyRef(
        DependencyKey("atom-record", base.atom_id, "truth"),
        base.materialization_key,
    ), "derived")
    derived = AtomRecord.create(
        derived_key,
        AuthorityClass.DETERMINISTIC_DERIVED,
        {"confidence": 1.0, "crisp": True, "strength": 1.0},
        base.validity,
        (derived_support,),
        ("test",),
    )

    index = DependencyIndex.build((base, derived))
    surviving = index.invalidate((source_key,))
    result = index.invalidate((source_key, backup_key))

    assert surviving.surviving_atom_ids == (base.atom_id,)
    assert derived.atom_id not in surviving.affected_atom_ids
    assert result.invalid_support_ids == tuple(sorted((
        base_single.supports[0].support_id,
        backup_support.support_id,
        derived_support.support_id,
    )))
    assert result.unsupported_atom_ids == tuple(sorted((
        base.atom_id,
        derived.atom_id,
    )))


def test_revision_lease_prevents_collection_until_release():
    store = DependentAtomSpaceStore(revision_retention=2)
    first_snapshot = _snapshot(source_seq=431)
    first = store.build(first_snapshot)
    lease = store.lease(first.revision_id)
    for source_seq in (432, 433, 434):
        store.update(_snapshot(source_seq=source_seq))

    assert lease.revision == first
    lease.release()
    assert store.revision(first.revision_id) is None


def test_snapshot_store_publishes_a_consistent_revision_pair():
    store = SnapshotStore()
    first = _snapshot(source_seq=431)
    store.replace(first)
    snapshot, revision = store.current_pair("fdas-dependency-test", 0)

    assert snapshot == first
    assert revision.snapshot_id == snapshot.snapshot_id
    assert store.current_atomspaces(
        "fdas-dependency-test", 0).snapshot_id == snapshot.snapshot_id
    with store.lease_dependent_revision(
            "fdas-dependency-test", 0) as leased:
        assert leased == revision


def test_decision_query_rejects_a_stale_revision():
    first_snapshot = _snapshot(source_seq=431)
    second_snapshot = _snapshot(source_seq=432)
    store = DependentAtomSpaceStore()
    first = store.build(first_snapshot)
    second = store.update(second_snapshot)

    current_query = store.query_current("fdas-dependency-test", 0)
    assert current_query.revision == second
    with pytest.raises(StaleAtomSpaceRevision, match="stale"):
        store.query_revision(
            first.revision_id,
            expected_snapshot_id=second.snapshot_id,
            decision_safe=True,
        )
