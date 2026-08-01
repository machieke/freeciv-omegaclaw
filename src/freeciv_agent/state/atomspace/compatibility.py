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
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    joined_identity_hash,
    term_value,
)


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


def _record(snapshot, atom, namespace, scope):
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
        snapshot.snapshot_id,
    ) + tuple(atom.args))
    dependency = DependencyRef(
        DependencyKey(
            "snapshot-projection",
            snapshot.snapshot_id,
            "legacy.{}.{}.{}".format(
                namespace.value,
                atom.predicate,
                key.atom_id[-20:])),
        witness_hash,
    )
    support = SupportRecord.from_hashes(
        "legacy-build-atomspaces",
        "1.0",
        key.key_hash,
        (dependency,),
        witness_hash,
        ("legacy-build-atomspaces/1.0",),
    )
    authority = (
        AuthorityClass.ENGINE_AUTHORITATIVE
        if namespace == AtomNamespace.AUTHORITATIVE
        else AuthorityClass.PACKET_OBSERVATION)
    validity = ValidityInterval(
        snapshot_id=snapshot.snapshot_id,
        valid_from_turn=snapshot.turn,
        valid_through_turn=snapshot.turn,
        source_seq=snapshot.identity.source_seq,
    )
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


def project_legacy_records(snapshot, scopes):
    """Convert the exact pre-FDAS projection into typed full-build records."""
    legacy = _build_legacy_atomspaces(snapshot)
    by_kind = _scope_by_kind(scopes)
    records = []
    for atom in sorted(legacy.authoritative):
        records.append(_record(
            snapshot, atom, AtomNamespace.AUTHORITATIVE, by_kind["empire"]))
    for atom in sorted(legacy.visible):
        records.append(_record(
            snapshot, atom, AtomNamespace.OBSERVATION, by_kind["world"]))
    if legacy.uncertain:
        raise ValueError(
            "Phase-1 compatibility has no uncertain legacy projection")
    return tuple(sorted(records, key=lambda value: value.atom_id))


def legacy_view_from_revision(revision):
    authoritative = set()
    visible = set()
    uncertain = set()
    for record in revision.records:
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
