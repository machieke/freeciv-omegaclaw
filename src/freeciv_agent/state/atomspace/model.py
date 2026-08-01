"""Immutable typed records for the component-only FDAS full builder."""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property

from ...events.schema import structural_hash


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} must be a non-empty string".format(name))
    return value


def _optional_nonnegative_integer(value, name):
    if value is None:
        return value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{} must be a non-negative integer or absent".format(name))
    return value


def joined_identity_hash(values):
    """Hash already-canonical scalar identities without JSON re-encoding."""
    encoded_values = []
    for value in values:
        encoded = str(value).encode("utf-8")
        encoded_values.append(
            str(len(encoded)).encode("ascii") + b":" + encoded)
    return hashlib.sha256(b"".join(encoded_values)).hexdigest()


class AtomNamespace(str, Enum):
    RULESET = "ruleset"
    AUTHORITATIVE = "authoritative"
    OBSERVATION = "observation"
    DERIVED = "derived"
    BELIEF = "belief"
    GOAL = "goal"
    OPERATION = "operation"
    EPISODE = "episode"
    DIAGNOSTIC = "diagnostic"


class AuthorityClass(str, Enum):
    RULESET_EXACT = "ruleset_exact"
    ENGINE_AUTHORITATIVE = "engine_authoritative"
    PACKET_OBSERVATION = "packet_observation"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    UNCERTAIN_BELIEF = "uncertain_belief"
    CONTROL_MODEL = "control_model"
    POLICY = "policy"


@dataclass(frozen=True, order=True)
class EntityRef:
    kind: str
    entity_id: str

    def __post_init__(self):
        _required_text(self.kind, "entity kind")
        _required_text(self.entity_id, "entity ID")

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "kind": self.kind,
            "term_type": "entity",
        }


@dataclass(frozen=True, order=True)
class SymbolRef:
    catalog: str
    symbol: str

    def __post_init__(self):
        _required_text(self.catalog, "symbol catalog")
        _required_text(self.symbol, "symbol")

    def to_dict(self):
        return {
            "catalog": self.catalog,
            "symbol": self.symbol,
            "term_type": "symbol",
        }


def term_kind(term):
    if isinstance(term, EntityRef):
        return term.kind
    if isinstance(term, SymbolRef):
        return term.catalog
    raise TypeError("atom arguments must be EntityRef or SymbolRef")


def term_value(term):
    if isinstance(term, EntityRef):
        return term.entity_id
    if isinstance(term, SymbolRef):
        return term.symbol
    raise TypeError("atom arguments must be EntityRef or SymbolRef")


@dataclass(frozen=True, order=True)
class AtomKey:
    namespace: AtomNamespace
    predicate: str
    arguments: tuple
    scope_id: str

    def __post_init__(self):
        if not isinstance(self.namespace, AtomNamespace):
            object.__setattr__(self, "namespace", AtomNamespace(self.namespace))
        _required_text(self.predicate, "atom predicate")
        _required_text(self.scope_id, "atom scope ID")
        object.__setattr__(self, "arguments", tuple(self.arguments))
        for term in self.arguments:
            term_kind(term)

    @cached_property
    def key_hash(self):
        identity_parts = [
            self.namespace.value,
            self.predicate,
            self.scope_id,
        ]
        for term in self.arguments:
            identity_parts.extend((
                "entity" if isinstance(term, EntityRef) else "symbol",
                term_kind(term),
                term_value(term),
            ))
        return joined_identity_hash(identity_parts)

    @cached_property
    def atom_id(self):
        return "atom-" + self.key_hash[:32]

    def to_dict(self):
        return {
            "arguments": [term.to_dict() for term in self.arguments],
            "namespace": self.namespace.value,
            "predicate": self.predicate,
            "scope_id": self.scope_id,
        }


@dataclass(frozen=True, order=True)
class DependencyKey:
    kind: str
    owner_id: str
    path: str

    def __post_init__(self):
        _required_text(self.kind, "dependency kind")
        _required_text(self.owner_id, "dependency owner ID")
        _required_text(self.path, "dependency path")

    def to_dict(self):
        return {
            "kind": self.kind,
            "owner_id": self.owner_id,
            "path": self.path,
        }


@dataclass(frozen=True, order=True)
class DependencyRef:
    key: DependencyKey
    fingerprint: str

    def __post_init__(self):
        if not isinstance(self.key, DependencyKey):
            raise TypeError("dependency reference requires DependencyKey")
        _required_text(self.fingerprint, "dependency fingerprint")

    def to_dict(self):
        return {
            "fingerprint": self.fingerprint,
            "key": self.key.to_dict(),
        }

    @cached_property
    def identity_hash(self):
        return joined_identity_hash((
            self.key.kind,
            self.key.owner_id,
            self.key.path,
            self.fingerprint,
        ))


@dataclass(frozen=True)
class ValidityInterval:
    snapshot_id: object = None
    valid_from_turn: object = None
    valid_through_turn: object = None
    source_seq: object = None
    ruleset_digest: object = None

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "validity snapshot ID"),
                (self.ruleset_digest, "validity ruleset digest")):
            if value is not None:
                _required_text(value, name)
        _optional_nonnegative_integer(
            self.valid_from_turn, "valid-from turn")
        _optional_nonnegative_integer(
            self.valid_through_turn, "valid-through turn")
        _optional_nonnegative_integer(self.source_seq, "source sequence")
        if (self.valid_from_turn is not None
                and self.valid_through_turn is not None
                and self.valid_through_turn < self.valid_from_turn):
            raise ValueError("valid-through turn cannot precede valid-from turn")

    def to_dict(self):
        return {
            "ruleset_digest": self.ruleset_digest,
            "snapshot_id": self.snapshot_id,
            "source_seq": self.source_seq,
            "valid_from_turn": self.valid_from_turn,
            "valid_through_turn": self.valid_through_turn,
        }

    @cached_property
    def identity_hash(self):
        return joined_identity_hash((
            self.snapshot_id,
            self.valid_from_turn,
            self.valid_through_turn,
            self.source_seq,
            self.ruleset_digest,
        ))


@dataclass(frozen=True)
class SupportRecord:
    support_id: str
    derivation_id: str
    derivation_version: str
    binding_hash: str
    dependencies: tuple
    witness_hash: str
    provenance_ids: tuple
    confidence_cap: object = None

    def __post_init__(self):
        for value, name in (
                (self.support_id, "support ID"),
                (self.derivation_id, "derivation ID"),
                (self.derivation_version, "derivation version"),
                (self.binding_hash, "support binding hash"),
                (self.witness_hash, "support witness hash")):
            _required_text(value, name)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "provenance_ids", tuple(self.provenance_ids))
        if not self.dependencies:
            raise ValueError("support requires at least one dependency")
        if any(not isinstance(value, DependencyRef) for value in self.dependencies):
            raise TypeError("support dependencies must be DependencyRef values")
        if any(not isinstance(value, str) or not value
               for value in self.provenance_ids):
            raise ValueError("support provenance IDs must be non-empty strings")
        if self.confidence_cap is not None:
            cap = float(self.confidence_cap)
            if not 0.0 <= cap <= 1.0:
                raise ValueError("support confidence cap must be in 0..1")

    @classmethod
    def create(cls, derivation_id, derivation_version, binding,
               dependencies, witness, provenance_ids, confidence_cap=None):
        dependencies = tuple(sorted(dependencies))
        binding_hash = structural_hash(binding)
        witness_hash = structural_hash(witness)
        return cls.from_hashes(
            derivation_id, derivation_version, binding_hash,
            dependencies, witness_hash, provenance_ids, confidence_cap)

    @classmethod
    def from_hashes(cls, derivation_id, derivation_version, binding_hash,
                    dependencies, witness_hash, provenance_ids,
                    confidence_cap=None):
        dependencies = tuple(sorted(dependencies))
        identity_parts = [
            derivation_id,
            derivation_version,
            binding_hash,
            witness_hash,
        ]
        identity_parts.extend(
            value.identity_hash for value in dependencies)
        return cls(
            "support-" + joined_identity_hash(identity_parts)[:32],
            str(derivation_id),
            str(derivation_version),
            binding_hash,
            dependencies,
            witness_hash,
            tuple(sorted(set(provenance_ids))),
            confidence_cap,
        )

    def to_dict(self):
        return {
            "binding_hash": self.binding_hash,
            "confidence_cap": self.confidence_cap,
            "dependencies": [value.to_dict() for value in self.dependencies],
            "derivation_id": self.derivation_id,
            "derivation_version": self.derivation_version,
            "provenance_ids": list(self.provenance_ids),
            "support_id": self.support_id,
            "witness_hash": self.witness_hash,
        }


@dataclass(frozen=True)
class AtomRecord:
    atom_id: str
    key: AtomKey
    authority: AuthorityClass
    truth: object
    validity: ValidityInterval
    supports: tuple
    provenance_ids: tuple
    lifecycle: str
    materialization_key: str
    tags: tuple = field(default_factory=tuple)

    def __post_init__(self):
        _required_text(self.atom_id, "atom ID")
        if not isinstance(self.key, AtomKey):
            raise TypeError("atom record requires AtomKey")
        if self.atom_id != self.key.atom_id:
            raise ValueError("atom ID does not match key")
        if not isinstance(self.authority, AuthorityClass):
            object.__setattr__(self, "authority", AuthorityClass(self.authority))
        if not isinstance(self.validity, ValidityInterval):
            raise TypeError("atom record requires ValidityInterval")
        object.__setattr__(self, "supports", tuple(sorted(
            self.supports, key=lambda value: value.support_id)))
        object.__setattr__(self, "provenance_ids", tuple(self.provenance_ids))
        object.__setattr__(self, "tags", tuple(self.tags))
        if not self.supports:
            raise ValueError("atom record requires at least one support")
        if any(not isinstance(value, SupportRecord) for value in self.supports):
            raise TypeError("atom supports must be SupportRecord values")
        _required_text(self.lifecycle, "atom lifecycle")
        _required_text(self.materialization_key, "materialization key")

    @classmethod
    def create(cls, key, authority, truth, validity, supports,
               provenance_ids, lifecycle="active", tags=(), truth_hash=None):
        supports = tuple(sorted(supports, key=lambda value: value.support_id))
        provenance_ids = tuple(sorted(set(provenance_ids)))
        tags = tuple(sorted(tags))
        truth_hash = truth_hash or structural_hash(truth)
        materialization_key = joined_identity_hash((
            key.atom_id,
            AuthorityClass(authority).value,
            lifecycle,
            truth_hash,
            validity.identity_hash,
        ) + tuple(value.support_id for value in supports)
          + provenance_ids
          + tuple("{}={}".format(*value) for value in tags))
        return cls(
            key.atom_id,
            key,
            authority,
            truth,
            validity,
            supports,
            provenance_ids,
            lifecycle,
            materialization_key,
            tags,
        )

    def to_dict(self):
        return {
            "atom_id": self.atom_id,
            "authority": self.authority.value,
            "key": self.key.to_dict(),
            "lifecycle": self.lifecycle,
            "materialization_key": self.materialization_key,
            "provenance_ids": list(self.provenance_ids),
            "supports": [value.to_dict() for value in self.supports],
            "tags": [list(value) for value in self.tags],
            "truth": self.truth,
            "validity": self.validity.to_dict(),
        }
