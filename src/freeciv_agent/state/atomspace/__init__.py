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
from .delta import (
    CollectionChange,
    SnapshotDelta,
    snapshot_dependency_fingerprints,
)
from .dependencies import (
    DependencyIndex,
    InvalidationResult,
)
from .derivations import (
    DerivationContext,
    DerivationRegistry,
    DerivationRun,
    DerivationSpec,
    ProjectionBatch,
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
from .query import (
    AtomQuery,
    RevisionQueryContext,
    StaleAtomSpaceRevision,
)
from .store import (
    DependentAtomSpaceRevision,
    DependentAtomSpaceStore,
    DifferentialVerification,
    MaterializationMetrics,
    RevisionLease,
)
from .transaction import AtomSpaceTransaction


__all__ = (
    "AtomKey",
    "AtomNamespace",
    "AtomRecord",
    "AtomQuery",
    "AtomSpaceTransaction",
    "AuthorityClass",
    "CollectionChange",
    "DependencyKey",
    "DependencyRef",
    "DependencyIndex",
    "DerivationContext",
    "DerivationRegistry",
    "DerivationRun",
    "DerivationSpec",
    "DependentAtomSpaceRevision",
    "DependentAtomSpaceStore",
    "DifferentialVerification",
    "EntityRef",
    "InvalidationResult",
    "MaterializationMetrics",
    "PredicateRegistry",
    "PredicateSpec",
    "ProjectionBatch",
    "RevisionLease",
    "RevisionQueryContext",
    "ScopeSpec",
    "SupportRecord",
    "SymbolRef",
    "SnapshotDelta",
    "StaleAtomSpaceRevision",
    "ValidityInterval",
    "build_compatible_atomspaces",
    "legacy_predicate_registry",
    "legacy_view_from_revision",
    "snapshot_scopes",
    "snapshot_dependency_fingerprints",
)
