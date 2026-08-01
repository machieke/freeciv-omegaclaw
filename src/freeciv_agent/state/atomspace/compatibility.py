"""Lossless bridge between legacy flat atoms and typed FDAS records."""

from ...events.schema import structural_hash
from ..atoms import (
    Atom,
    SnapshotAtomspaces,
    _build_legacy_atomspaces,
)
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    EntityRef,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    joined_identity_hash,
    term_value,
)
from .delta import snapshot_dependency_fingerprints, snapshot_dependency_ref


_ARGUMENT_KINDS = {
    "buildable": ("city", "production-kind", "production-target"),
    "city-at": ("city", "tile"),
    "city-producing": ("city", "production-kind", "production-target"),
    "has-tech": ("player", "technology"),
    "owns-city": ("player", "city"),
    "owns-unit": ("player", "unit"),
    "tile-visible": ("tile",),
    "unit-activity": ("unit", "activity"),
    "unit-at": ("unit", "tile"),
    "unit-type": ("unit", "unit-type"),
}
_SYMBOL_KINDS = frozenset((
    "activity",
    "production-kind",
    "unit-type",
))
_CRISP_TRUTH = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_TRUTH_HASH = structural_hash(_CRISP_TRUTH)


def _term(kind, value):
    if isinstance(value, bool) or not isinstance(value, str) or not value:
        raise ValueError("legacy atom arguments must be non-empty strings")
    if kind in _SYMBOL_KINDS:
        return SymbolRef(kind, value)
    return EntityRef(kind, value)


def _scope_by_kind(scopes):
    result = {}
    for scope in scopes:
        if scope.scope_kind in result:
            raise ValueError("duplicate scope kind in compatibility projection")
        result[scope.scope_kind] = scope
    return result


def _dependency_paths(atom):
    first = atom.args[0]
    if atom.predicate == "buildable":
        return (
            "cities.{}.buildability_available".format(first),
            "cities.{}.buildable".format(first),
        )
    if atom.predicate == "city-at":
        return ("cities.{}.tile".format(first),)
    if atom.predicate == "city-producing":
        return (
            "cities.{}.production_kind".format(first),
            "cities.{}.production_value".format(first),
        )
    if atom.predicate == "has-tech":
        return ("known_techs.{}".format(atom.args[1]),)
    if atom.predicate == "owns-city":
        return ("cities.{}.__exists__".format(atom.args[1]),)
    if atom.predicate == "owns-unit":
        return ("units.{}.__exists__".format(atom.args[1]),)
    if atom.predicate == "tile-visible":
        return ("visible_tile_ids.{}".format(first),)
    if atom.predicate == "unit-activity":
        return ("units.{}.activity".format(first),)
    if atom.predicate == "unit-at":
        return ("units.{}.tile".format(first),)
    if atom.predicate == "unit-type":
        return (
            "units.{}.type".format(first),
            "units.{}.unit_type".format(first),
        )
    raise KeyError("no dependency projection for {}".format(atom.predicate))


def _dependencies(snapshot, atom, fingerprints):
    paths = _dependency_paths(atom)
    available = []
    for path in paths:
        try:
            available.append(snapshot_dependency_ref(
                snapshot, path, fingerprints))
        except KeyError:
            # `UnitState.grounded_dict()` exposes `type`; the lightweight
            # baseline fixture view exposes `unit_type`. Exactly one alias is
            # expected and both resolve to the same typed unit relation.
            if atom.predicate != "unit-type":
                raise
    if not available:
        raise KeyError(
            "no dependency source resolved for {}".format(atom.predicate))
    return tuple(available)


def _record(snapshot, atom, namespace, scope, fingerprints, validity):
    kinds = _ARGUMENT_KINDS[atom.predicate]
    key = AtomKey(
        namespace,
        atom.predicate,
        tuple(_term(kind, value) for kind, value in zip(kinds, atom.args)),
        scope.scope_id,
    )
    witness_hash = joined_identity_hash((
        "legacy-atom",
        namespace.value,
        atom.predicate,
    ) + tuple(atom.args))
    dependencies = _dependencies(snapshot, atom, fingerprints)
    support = SupportRecord.from_hashes(
        "legacy-build-atomspaces",
        "1.0",
        key.key_hash,
        dependencies,
        witness_hash,
        ("legacy-build-atomspaces/1.0",),
    )
    authority = (
        AuthorityClass.ENGINE_AUTHORITATIVE
        if namespace == AtomNamespace.AUTHORITATIVE
        else AuthorityClass.PACKET_OBSERVATION)
    return AtomRecord.create(
        key,
        authority,
        truth=_CRISP_TRUTH,
        validity=validity,
        supports=(support,),
        provenance_ids=("legacy-build-atomspaces/1.0",),
        tags=(("migration", "phase-1-compatibility"),),
        truth_hash=_CRISP_TRUTH_HASH,
    )


def project_legacy_records(snapshot, scopes, fingerprints=None):
    """Convert the exact pre-FDAS projection into typed full-build records."""
    legacy = _build_legacy_atomspaces(snapshot)
    by_kind = _scope_by_kind(scopes)
    fingerprints = fingerprints or snapshot_dependency_fingerprints(snapshot)
    validity = ValidityInterval(
        snapshot_id=snapshot.snapshot_id,
        valid_from_turn=snapshot.turn,
        valid_through_turn=snapshot.turn,
        source_seq=snapshot.identity.source_seq,
    )
    records = []
    for atom in sorted(legacy.authoritative):
        records.append(_record(
            snapshot, atom, AtomNamespace.AUTHORITATIVE, by_kind["empire"],
            fingerprints, validity))
    for atom in sorted(legacy.visible):
        records.append(_record(
            snapshot, atom, AtomNamespace.OBSERVATION, by_kind["world"],
            fingerprints, validity))
    if legacy.uncertain:
        raise ValueError(
            "Phase-1 compatibility has no uncertain legacy projection")
    return tuple(sorted(records, key=lambda value: value.atom_id))


def _legacy_identity(record):
    return (
        record.key.namespace,
        record.key.predicate,
        tuple(term_value(value) for value in record.key.arguments),
    )


def _refreshed_record(record, validity):
    return AtomRecord.create(
        record.key,
        record.authority,
        truth=_CRISP_TRUTH,
        validity=validity,
        supports=record.supports,
        provenance_ids=record.provenance_ids,
        lifecycle=record.lifecycle,
        tags=record.tags,
        truth_hash=_CRISP_TRUTH_HASH,
    )


def project_legacy_records_incremental(
        snapshot, scopes, prior_revision, fingerprints=None):
    """Refresh unchanged supports and recompute only changed base relations."""
    if prior_revision is None:
        records = project_legacy_records(snapshot, scopes, fingerprints)
        return records, {
            "recomputed_records": len(records),
            "refreshed_records": 0,
            "removed_records": 0,
        }
    legacy = _build_legacy_atomspaces(snapshot)
    by_kind = _scope_by_kind(scopes)
    fingerprints = fingerprints or snapshot_dependency_fingerprints(snapshot)
    validity = ValidityInterval(
        snapshot_id=snapshot.snapshot_id,
        valid_from_turn=snapshot.turn,
        valid_through_turn=snapshot.turn,
        source_seq=snapshot.identity.source_seq,
    )
    legacy_predicates = frozenset(_ARGUMENT_KINDS)
    prior = dict(
        (_legacy_identity(value), value)
        for value in prior_revision.records
        if (value.key.predicate in legacy_predicates
            and value.key.namespace in (
                AtomNamespace.AUTHORITATIVE, AtomNamespace.OBSERVATION)))
    records = []
    recomputed = 0
    refreshed = 0
    identities = []
    for namespace, atoms, scope in (
            (AtomNamespace.AUTHORITATIVE,
             legacy.authoritative, by_kind["empire"]),
            (AtomNamespace.OBSERVATION,
             legacy.visible, by_kind["world"])):
        for atom in sorted(atoms):
            identity = (namespace, atom.predicate, tuple(atom.args))
            identities.append(identity)
            old = prior.get(identity)
            reusable = old is not None and all(
                fingerprints.get(dependency.key) == dependency.fingerprint
                for support in old.supports
                for dependency in support.dependencies)
            if reusable:
                records.append(_refreshed_record(old, validity))
                refreshed += 1
            else:
                records.append(_record(
                    snapshot, atom, namespace, scope, fingerprints, validity))
                recomputed += 1
    return tuple(sorted(records, key=lambda value: value.atom_id)), {
        "recomputed_records": recomputed,
        "refreshed_records": refreshed,
        "removed_records": len(set(prior).difference(identities)),
    }


def legacy_view_from_revision(revision):
    authoritative = set()
    visible = set()
    uncertain = set()
    for record in revision.records:
        if record.key.predicate not in _ARGUMENT_KINDS:
            continue
        atom = Atom(
            record.key.predicate,
            tuple(term_value(value) for value in record.key.arguments),
        )
        if record.key.namespace == AtomNamespace.AUTHORITATIVE:
            authoritative.add(atom)
        elif record.key.namespace == AtomNamespace.OBSERVATION:
            visible.add(atom)
        elif record.key.namespace == AtomNamespace.BELIEF:
            uncertain.add(atom)
    return SnapshotAtomspaces(
        revision.snapshot_id,
        frozenset(authoritative),
        frozenset(visible),
        frozenset(uncertain),
    )


def build_compatible_atomspaces(snapshot):
    from .store import DependentAtomSpaceStore
    revision = DependentAtomSpaceStore().build(snapshot)
    return legacy_view_from_revision(revision)
