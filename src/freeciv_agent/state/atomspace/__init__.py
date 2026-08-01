"""Typed component-only Functional Dependent AtomSpace foundation."""

from .compatibility import (
    build_compatible_atomspaces,
    legacy_view_from_revision,
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
)
from .predicates import (
    PredicateRegistry,
    PredicateSpec,
    legacy_predicate_registry,
)
from .scopes import (
    ScopeSpec,
    snapshot_scopes,
)
from .store import (
    DependentAtomSpaceRevision,
    DependentAtomSpaceStore,
)
from .transaction import AtomSpaceTransaction


__all__ = (
    "AtomKey",
    "AtomNamespace",
    "AtomRecord",
    "AtomSpaceTransaction",
    "AuthorityClass",
    "DependencyKey",
    "DependencyRef",
    "DependentAtomSpaceRevision",
    "DependentAtomSpaceStore",
    "EntityRef",
    "PredicateRegistry",
    "PredicateSpec",
    "ScopeSpec",
    "SupportRecord",
    "SymbolRef",
    "ValidityInterval",
    "build_compatible_atomspaces",
    "legacy_predicate_registry",
    "legacy_view_from_revision",
    "snapshot_scopes",
)
