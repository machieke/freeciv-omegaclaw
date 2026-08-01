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
from .ruleset import (
    RulesetAtomSpaceStore,
    project_ruleset_records,
    ruleset_digest,
    ruleset_predicate_registry,
    ruleset_scope,
)
from .grounding import (
    CITY_ECONOMY_GROUNDING_SPECS,
    GroundingAuthority,
    GroundingResult,
    GroundingSpec,
    TypedGroundingRegistry,
)
from .city import (
    CityEconomyPolicy,
    CityEconomyProjector,
    city_economy_predicate_registry,
    city_economy_scopes,
)
from .composite import (
    CompositeDomainProjector,
    merge_predicate_registries,
)
from .operations import (
    OperationProjectionSnapshot,
    OperationProjector,
    operation_predicate_registry,
)
from .config import DependentAtomSpaceConfig
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
    "CITY_ECONOMY_GROUNDING_SPECS",
    "CityEconomyPolicy",
    "CityEconomyProjector",
    "CompositeDomainProjector",
    "CollectionChange",
    "DependencyKey",
    "DependencyRef",
    "DependencyIndex",
    "DerivationContext",
    "DerivationRegistry",
    "DerivationRun",
    "DerivationSpec",
    "DependentAtomSpaceRevision",
    "DependentAtomSpaceConfig",
    "DependentAtomSpaceStore",
    "DifferentialVerification",
    "EntityRef",
    "GroundingAuthority",
    "GroundingResult",
    "GroundingSpec",
    "InvalidationResult",
    "MaterializationMetrics",
    "OperationProjectionSnapshot",
    "OperationProjector",
    "PredicateRegistry",
    "PredicateSpec",
    "ProjectionBatch",
    "RevisionLease",
    "RevisionQueryContext",
    "RulesetAtomSpaceStore",
    "ScopeSpec",
    "SupportRecord",
    "SymbolRef",
    "SnapshotDelta",
    "StaleAtomSpaceRevision",
    "ValidityInterval",
    "build_compatible_atomspaces",
    "city_economy_predicate_registry",
    "city_economy_scopes",
    "legacy_predicate_registry",
    "legacy_view_from_revision",
    "merge_predicate_registries",
    "operation_predicate_registry",
    "project_ruleset_records",
    "ruleset_digest",
    "ruleset_predicate_registry",
    "ruleset_scope",
    "snapshot_scopes",
    "snapshot_dependency_fingerprints",
    "TypedGroundingRegistry",
)
