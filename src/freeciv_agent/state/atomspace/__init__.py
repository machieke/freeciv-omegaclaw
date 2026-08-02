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
    ScopeActivationPolicy,
    ScopeActivationRequest,
    ScopeActivationSignal,
    ScopeActivationState,
    ScopeActivator,
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
    ALL_GROUNDING_SPECS,
    CITY_ECONOMY_GROUNDING_SPECS,
    GroundingAuthority,
    GroundingResult,
    GroundingSpec,
    TypedGroundingRegistry,
    UNIT_DEFENSE_GROUNDING_SPECS,
    persistent_defender_type,
)
from .city import (
    CityEconomyPolicy,
    CityEconomyProjector,
    city_economy_predicate_registry,
    city_economy_scopes,
)
from .composite import (
    ActivatedDomainProjector,
    CompositeDomainProjector,
    merge_predicate_registries,
)
from .operations import (
    OperationProjectionSnapshot,
    OperationProjector,
    operation_predicate_registry,
)
from .config import DependentAtomSpaceConfig
from .unit import (
    CityDefensePolicy,
    UnitDefenseProjector,
    unit_defense_predicate_registry,
    unit_defense_scopes,
)
from .region import (
    CityRegionPolicy,
    CityRegionProjector,
    region_predicate_registry,
)
from .episodes import (
    EpisodeProjector,
    episode_predicate_registry,
)
from .corridor import (
    RouteCorridorProjector,
    route_corridor_predicate_registry,
)
from .settlement import (
    SettlementSiteProjector,
    settlement_predicate_registry,
)
from .transport import (
    TransportCapabilityProjector,
    transport_predicate_registry,
)
from .combat import (
    CombatTaskForceProjector,
    combat_predicate_registry,
)
from .recovery import (
    PopulationRecoveryProjector,
    population_recovery_profile,
    population_recovery_predicate_registry,
)
from .belief import (
    BeliefProjector,
    belief_predicate_registry,
)
from .store import (
    DependentAtomSpaceRevision,
    DependentAtomSpaceStore,
    DifferentialVerification,
    MaterializationMetrics,
    RevisionLease,
)
from .transaction import AtomSpaceTransaction
from .diagnostics import AtomSpaceDiagnostics
from .events import AtomSpaceEventEmitter, FDAS_EVENT_TYPES
from .runtime import (
    FdasRuntime,
    FdasRuntimeConfigurationError,
    FdasShadowEvaluation,
    FdasRuntimeUpdate,
    build_runtime,
    load_runtime_declaration,
    validate_runtime_declaration,
)


__all__ = (
    "AtomKey",
    "AtomNamespace",
    "AtomRecord",
    "AtomQuery",
    "AtomSpaceTransaction",
    "AtomSpaceDiagnostics",
    "AtomSpaceEventEmitter",
    "AuthorityClass",
    "ActivatedDomainProjector",
    "ALL_GROUNDING_SPECS",
    "CITY_ECONOMY_GROUNDING_SPECS",
    "CityEconomyPolicy",
    "CityEconomyProjector",
    "CityDefensePolicy",
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
    "FDAS_EVENT_TYPES",
    "FdasRuntime",
    "FdasRuntimeConfigurationError",
    "FdasShadowEvaluation",
    "FdasRuntimeUpdate",
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
    "ScopeActivationPolicy",
    "ScopeActivationRequest",
    "ScopeActivationSignal",
    "ScopeActivationState",
    "ScopeActivator",
    "SupportRecord",
    "SymbolRef",
    "SnapshotDelta",
    "StaleAtomSpaceRevision",
    "ValidityInterval",
    "build_compatible_atomspaces",
    "build_runtime",
    "city_economy_predicate_registry",
    "city_economy_scopes",
    "legacy_predicate_registry",
    "legacy_view_from_revision",
    "load_runtime_declaration",
    "merge_predicate_registries",
    "operation_predicate_registry",
    "project_ruleset_records",
    "ruleset_digest",
    "ruleset_predicate_registry",
    "ruleset_scope",
    "snapshot_scopes",
    "snapshot_dependency_fingerprints",
    "TypedGroundingRegistry",
    "UNIT_DEFENSE_GROUNDING_SPECS",
    "UnitDefenseProjector",
    "CityRegionPolicy", "CityRegionProjector",
    "region_predicate_registry",
    "EpisodeProjector", "episode_predicate_registry",
    "RouteCorridorProjector", "route_corridor_predicate_registry",
    "SettlementSiteProjector", "settlement_predicate_registry",
    "TransportCapabilityProjector", "transport_predicate_registry",
    "CombatTaskForceProjector", "combat_predicate_registry",
    "PopulationRecoveryProjector", "population_recovery_profile",
    "population_recovery_predicate_registry",
    "BeliefProjector", "belief_predicate_registry",
    "unit_defense_predicate_registry",
    "unit_defense_scopes",
    "persistent_defender_type",
    "validate_runtime_declaration",
)
