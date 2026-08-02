"""Fail-closed runtime assembly for shadow Functional Dependent AtomSpace.

Component tests construct individual projectors directly.  This module is the
single application boundary that turns a validated configuration declaration
into a coordinated snapshot/ruleset AtomSpace pair.  It deliberately exposes
no action-selection API: authority remains downstream of the separately gated
pressure adapter, commit validator, and execution gate.
"""

from dataclasses import dataclass, replace
import json
import os
import time

import yaml

from ...events.schema import structural_hash
from ...paths import repo_path
from .belief import BeliefProjector
from .city import CityEconomyProjector
from .combat import CombatTaskForceProjector
from .composite import ActivatedDomainProjector, CompositeDomainProjector
from .config import DependentAtomSpaceConfig
from .corridor import RouteCorridorProjector
from .episodes import EpisodeProjector
from .events import AtomSpaceEventEmitter
from .operations import OperationProjector
from .recovery import PopulationRecoveryProjector
from .region import CityRegionProjector
from .ruleset import RulesetAtomSpaceStore, ruleset_digest
from .scopes import (
    ScopeActivationPolicy,
    ScopeActivationSignal,
    ScopeActivator,
)
from .settlement import SettlementSiteProjector
from .store import DependentAtomSpaceStore
from .transport import TransportCapabilityProjector
from .unit import UnitDefenseProjector


DEFAULT_CONFIG_PATH = repo_path("profile", "dependent_atomspace.yaml")
DEFAULT_MANIFEST_PATH = repo_path("profile", "fdas_manifest.json")


class FdasRuntimeConfigurationError(ValueError):
    """The declared runtime cannot be assembled without guessing."""


def _read_object(path, kind):
    path = os.path.abspath(path)
    try:
        with open(path, encoding="utf-8") as stream:
            value = yaml.safe_load(stream) if kind == "yaml" else json.load(stream)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise FdasRuntimeConfigurationError(
            "cannot read FDAS {} {}: {}".format(kind, path, exc))
    if not isinstance(value, dict):
        raise FdasRuntimeConfigurationError(
            "FDAS {} root must be an object".format(kind))
    return value


def load_runtime_declaration(config_path=None, manifest_path=None):
    """Load, validate, and return a manifest-safe FDAS declaration."""
    config_path = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    manifest_path = os.path.abspath(manifest_path or DEFAULT_MANIFEST_PATH)
    config_document = _read_object(config_path, "yaml")
    if set(config_document) != {"dependent_atomspace"}:
        raise FdasRuntimeConfigurationError(
            "FDAS profile must contain only dependent_atomspace")
    manifest = _read_object(manifest_path, "json")
    config = DependentAtomSpaceConfig.from_dict(
        config_document["dependent_atomspace"], manifest)
    material = {
        "config": config.to_dict(),
        "config_source": os.path.relpath(config_path, repo_path()),
        "manifest": manifest,
        "manifest_source": os.path.relpath(manifest_path, repo_path()),
    }
    material["declaration_hash"] = structural_hash(material)
    return material


def validate_runtime_declaration(value):
    """Validate a serialized declaration carried by a run manifest."""
    if not isinstance(value, dict):
        raise FdasRuntimeConfigurationError(
            "FDAS runtime declaration must be an object")
    expected = {
        "config", "config_source", "declaration_hash", "manifest",
        "manifest_source",
    }
    if set(value) != expected:
        raise FdasRuntimeConfigurationError(
            "FDAS runtime declaration keys differ")
    for name in ("config_source", "manifest_source", "declaration_hash"):
        if not isinstance(value[name], str) or not value[name]:
            raise FdasRuntimeConfigurationError(
                "FDAS runtime {} is required".format(name))
    semantic = dict(value)
    claimed_hash = semantic.pop("declaration_hash")
    if structural_hash(semantic) != claimed_hash:
        raise FdasRuntimeConfigurationError(
            "FDAS runtime declaration hash mismatch")
    config = DependentAtomSpaceConfig.from_dict(
        value["config"], value["manifest"])
    return config


def _focus_signals(snapshot, scopes):
    """Fund only scopes already justified by bounded pure projectors.

    Projectors decide whether a detailed scope exists from exact current input.
    This adapter supplies the separate materialization budget identity; it does
    not assert that the triggering condition is true and cannot create atoms.
    """
    reasons = {
        "combat-engagement": ("native-combat-window", 0.90),
        "opponent-belief": ("active-belief-revision", 0.70),
        "population-recovery": ("current-legal-recovery", 0.75),
        "region": ("projector-qualified-region", 0.85),
        "route-corridor": ("current-native-route", 0.80),
        "settlement-site": ("current-legal-settlement", 0.80),
        "task-force": ("grounded-task-force", 0.90),
        "transport": ("current-transport-capability", 0.75),
    }
    parent = "snapshot:{}".format(snapshot.snapshot_id)
    return tuple(
        ScopeActivationSignal(
            scope.scope_id,
            reasons[scope.scope_kind][0],
            "fdas-shadow-materialization-budget",
            reasons[scope.scope_kind][1],
            (parent,),
        )
        for scope in scopes if scope.scope_kind in reasons)


class _ConfiguredBudgetProjector(object):
    """Apply checked runtime budgets to pure projector scope contracts."""

    projector_id = "fdas-configured-budget-projector"
    version = "1.0"

    def __init__(self, projector, materialization):
        self.projector = projector
        self.materialization = dict(materialization)
        self.predicate_registry = projector.predicate_registry

    def scopes(self, snapshot):
        scopes = []
        for scope in self.projector.scopes(snapshot):
            if scope.scope_kind == "city-facts":
                configured_maximum = self.materialization[
                    "maximum_atoms_per_city_scope"]
            elif scope.scope_kind == "unit-facts":
                configured_maximum = self.materialization[
                    "maximum_atoms_per_unit_scope"]
            elif scope.scope_kind in (
                    "combat-engagement", "opponent-belief",
                    "population-recovery", "region", "route-corridor",
                    "settlement-site", "task-force", "transport"):
                configured_maximum = self.materialization[
                    "maximum_atoms_per_region_scope"]
            else:
                configured_maximum = self.materialization[
                    "maximum_atoms_global"]
            maximum_atoms = min(scope.maximum_atoms, configured_maximum)
            scopes.append(replace(
                scope,
                maximum_atoms=maximum_atoms,
                maximum_rule_fires=min(
                    scope.maximum_rule_fires,
                    self.materialization["maximum_rule_fires_per_scope"]),
                maximum_groundings=min(
                    scope.maximum_groundings,
                    self.materialization["maximum_groundings_per_scope"]),
                maximum_expansion_depth=min(
                    scope.maximum_expansion_depth,
                    self.materialization["maximum_expansion_depth"]),
            ))
        return tuple(scopes)

    def extend_fingerprints(self, fingerprints):
        return self.projector.extend_fingerprints(fingerprints)

    def project(self, snapshot, scopes, fingerprints):
        return self.projector.project(snapshot, scopes, fingerprints)


@dataclass(frozen=True)
class FdasRuntimeUpdate:
    snapshot_id: str
    revision_id: object
    atom_count: int
    scope_count: int
    latency_ms: float
    cold_verification: object = None

    def to_dict(self):
        return {
            "atom_count": self.atom_count,
            "cold_verification": (
                None if self.cold_verification is None
                else self.cold_verification.to_dict()),
            "latency_ms": self.latency_ms,
            "revision_id": self.revision_id,
            "scope_count": self.scope_count,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class FdasShadowEvaluation:
    snapshot_id: str
    revision_id: str
    goals: tuple
    candidates: tuple
    candidate_instantiation: object
    pressure: object
    comparison: object
    latency_ms: float

    def to_dict(self):
        return {
            "candidate_count": len(self.candidates),
            "candidate_instantiation": self.candidate_instantiation.to_dict(),
            "comparison": (
                None if self.comparison is None
                else self.comparison.to_dict()),
            "goal_count": len(self.goals),
            "latency_ms": self.latency_ms,
            "pressure": self.pressure.to_dict(),
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
        }


class FdasRuntime(object):
    """Coordinated, read-only rich projection runtime."""

    RUNTIME_IDENTITY = "fdas-shadow-runtime/1.0"

    def __init__(self, declaration, snapshot_store, dependent_store,
                 ruleset_revision=None, domain_projector=None,
                 event_emitter=None, projector_ids=(), ruleset_digest_value=None):
        self.declaration = dict(declaration)
        self.config = validate_runtime_declaration(self.declaration)
        self.snapshot_store = snapshot_store
        self.dependent_store = dependent_store
        self.ruleset_revision = ruleset_revision
        self.domain_projector = domain_projector
        self.event_emitter = event_emitter
        self.projector_ids = tuple(projector_ids)
        self.ruleset_digest = ruleset_digest_value
        self._goal_factory = None
        self._candidate_factory = None
        self._pressure_adapter = None

    @property
    def enabled(self):
        return self.config.enabled

    def activation_payload(self):
        return {
            "authority_enabled": self.config.authority_enabled,
            "declaration_hash": self.declaration["declaration_hash"],
            "enabled": self.config.enabled,
            "manifest_status": self.declaration["manifest"]["status"],
            "policy_authority": self.declaration["manifest"][
                "policy_authority"],
            "projector_ids": list(self.projector_ids),
            "ruleset_revision_id": (
                None if self.ruleset_revision is None
                else self.ruleset_revision.revision_id),
            "runtime_identity": self.RUNTIME_IDENTITY,
            "shadow_enabled": self.config.shadow_enabled,
        }

    def _sample_cold_verification(self, snapshot):
        rate = self.config.cold_verify_sample_rate
        if rate <= 0.0:
            return False
        sample = int(structural_hash([
            "fdas-cold-verification/1.0", snapshot.snapshot_id,
        ])[:13], 16) / float(16 ** 13)
        return sample < rate

    def replace(self, snapshot):
        """Install one snapshot and sample incremental/cold parity."""
        started = time.perf_counter()
        prior_snapshot, prior_revision = self.snapshot_store.current_pair(
            snapshot.identity.game_id, snapshot.player_id)
        verification = None
        if (self.enabled and prior_snapshot is not None
                and self._sample_cold_verification(snapshot)):
            verification = self.dependent_store.verify_incremental(
                snapshot, prior_snapshot, prior_revision)
            if not verification.equivalent:
                raise RuntimeError(
                    "FDAS incremental/cold mismatch: {}".format(
                        verification.mismatch_categories))
        self.snapshot_store.replace(snapshot)
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        return FdasRuntimeUpdate(
            snapshot.snapshot_id,
            None if revision is None else revision.revision_id,
            0 if revision is None else len(revision.records),
            0 if revision is None else len(revision.scopes),
            (time.perf_counter() - started) * 1000.0,
            verification,
        )

    def rematerialize(self, game_id, player_id):
        """Refresh durable non-snapshot sources at the current identity."""
        started = time.perf_counter()
        revision = self.snapshot_store.rematerialize_dependent(
            game_id, player_id)
        return FdasRuntimeUpdate(
            revision.snapshot_id, revision.revision_id,
            len(revision.records), len(revision.scopes),
            (time.perf_counter() - started) * 1000.0,
        )

    def configure_shadow_evaluation(
            self, goal_factory, candidate_factory, pressure_adapter):
        """Install the non-authorizing goal/candidate/pressure readout."""
        if not self.enabled:
            raise FdasRuntimeConfigurationError(
                "disabled FDAS cannot configure shadow evaluation")
        if any(value is None for value in (
                goal_factory, candidate_factory, pressure_adapter)):
            raise FdasRuntimeConfigurationError(
                "FDAS shadow evaluation requires all factories")
        self._goal_factory = goal_factory
        self._candidate_factory = candidate_factory
        self._pressure_adapter = pressure_adapter
        return self

    def evaluate_shadow(self, snapshot, legacy_candidates=()):
        """Evaluate local FDAS routes without returning an executable action."""
        if not self.enabled:
            return None
        if any(value is None for value in (
                self._goal_factory, self._candidate_factory,
                self._pressure_adapter)):
            raise FdasRuntimeConfigurationError(
                "FDAS shadow evaluation is not configured")
        started = time.perf_counter()
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS shadow evaluation requires the current revision")
        query = self.dependent_store.query_current(
            snapshot.identity.game_id, snapshot.player_id)
        goals = self._goal_factory.instantiate(revision, query)
        legacy_candidates = (
            None if legacy_candidates is None else tuple(legacy_candidates))
        from ...planning import legacy_shadow_goal_routes
        instantiation = self._candidate_factory.instantiate_report(
            snapshot, goals, revision=revision,
            protected_action_keys=(
                () if legacy_candidates is None else tuple(
                    candidate.action_key for candidate in legacy_candidates)),
            protected_goal_routes=(
                () if legacy_candidates is None else
                legacy_shadow_goal_routes(legacy_candidates)))
        candidates = instantiation.candidates
        pressure = self._pressure_adapter.evaluate(
            revision, goals, candidates)
        comparison = None
        if legacy_candidates is not None:
            from ...planning import compare_shadow_candidates
            comparison = compare_shadow_candidates(
                snapshot, legacy_candidates, candidates)
        return FdasShadowEvaluation(
            snapshot.snapshot_id, revision.revision_id, goals, candidates,
            instantiation, pressure, comparison,
            (time.perf_counter() - started) * 1000.0)

    def emit_current(self, writer, snapshot, caused_by=(), prior_revision=None):
        """Emit bounded causal evidence for the current rich revision."""
        if not self.enabled or self.event_emitter is None:
            return ()
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError("FDAS runtime revision is not snapshot-current")
        activation = None
        if isinstance(self.domain_projector, ActivatedDomainProjector):
            activation = self.domain_projector.activation(snapshot.snapshot_id)
        events = self.event_emitter.emit_revision(
            writer, snapshot.turn, revision,
            prior_revision=prior_revision,
            activation=activation,
            ruleset_digest=self.ruleset_digest,
            caused_by=tuple(caused_by),
        )
        return events

    def emit_shadow(self, writer, snapshot, evaluation, caused_by=()):
        """Emit bounded causal evidence for a read-only shadow decision."""
        if not self.enabled or self.event_emitter is None:
            return ()
        if (not isinstance(evaluation, FdasShadowEvaluation)
                or evaluation.snapshot_id != snapshot.snapshot_id):
            raise RuntimeError(
                "FDAS shadow evidence is not snapshot-current")
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.revision_id != evaluation.revision_id):
            raise RuntimeError(
                "FDAS shadow evidence is not revision-current")
        return self.event_emitter.emit_shadow_evaluation(
            writer, snapshot.turn, revision, evaluation,
            ruleset_digest=self.ruleset_digest,
            caused_by=tuple(caused_by))


def build_runtime(declaration, ruleset_ir=None, belief_store=None,
                  operation_records_source=None, episode_source=None):
    """Assemble the exact configured projector set or fail closed."""
    from ..store import SnapshotStore

    config = validate_runtime_declaration(declaration)
    projection = config.section("projection")
    learning = config.section("learning")
    if not config.enabled:
        dependent_store = DependentAtomSpaceStore(
            revision_retention=config.revision_retention)
        return FdasRuntime(
            declaration,
            SnapshotStore(dependent_atomspace_store=dependent_store),
            dependent_store,
        )
    if not projection["world"] or not projection["empire"]:
        raise FdasRuntimeConfigurationError(
            "enabled FDAS requires world and empire projection")
    if projection["ruleset"] and ruleset_ir is None:
        raise FdasRuntimeConfigurationError(
            "ruleset projection requires compiled ruleset IR")
    digest = ruleset_digest(ruleset_ir) if ruleset_ir is not None else None
    projectors = []
    if projection["city"] or projection["economy"] or projection["research"]:
        projectors.append(CityEconomyProjector(ruleset_ir, digest))
    if projection["unit"]:
        if ruleset_ir is None:
            raise FdasRuntimeConfigurationError(
                "unit projection requires compiled ruleset IR")
        projectors.append(UnitDefenseProjector(ruleset_ir, digest))
    if projection["region"]:
        if ruleset_ir is None:
            raise FdasRuntimeConfigurationError(
                "region projection requires compiled ruleset IR")
        projectors.extend((
            CityRegionProjector(),
            RouteCorridorProjector(),
            SettlementSiteProjector(ruleset_ir, digest),
            TransportCapabilityProjector(ruleset_ir, digest),
            CombatTaskForceProjector(ruleset_ir, digest),
            PopulationRecoveryProjector(ruleset_ir, digest),
        ))
    if projection["operations"]:
        if operation_records_source is None:
            raise FdasRuntimeConfigurationError(
                "operation projection requires a durable record source")
        projectors.append(OperationProjector(operation_records_source))
    if projection["beliefs"]:
        if belief_store is None:
            raise FdasRuntimeConfigurationError(
                "belief projection requires a belief store")
        projectors.append(BeliefProjector(belief_store))
    if learning["episode_attribution_enabled"]:
        if episode_source is None:
            raise FdasRuntimeConfigurationError(
                "episode attribution requires a durable episode source")
        projectors.append(EpisodeProjector(episode_source))
    if not projectors:
        raise FdasRuntimeConfigurationError(
            "enabled FDAS requires at least one rich domain projector")

    materialization = config.section("materialization")
    composite = _ConfiguredBudgetProjector(
        CompositeDomainProjector(tuple(projectors)), materialization)
    policy = ScopeActivationPolicy(
        focused_scope_ttl_turns=materialization[
            "focused_scope_ttl_turns"])
    activated = ActivatedDomainProjector(
        composite, ScopeActivator(policy), _focus_signals)
    dependent_store = DependentAtomSpaceStore(
        revision_retention=config.revision_retention,
        domain_projector=activated,
        maximum_atoms=materialization["maximum_atoms_global"],
    )
    ruleset_revision = (
        RulesetAtomSpaceStore().build(ruleset_ir)
        if projection["ruleset"] else None)
    events = config.section("events")
    emitter = AtomSpaceEventEmitter(
        support_level=events["support_level"],
        maximum_detail_events=min(
            2000,
            materialization["maximum_atoms_global"]),
    )
    runtime = FdasRuntime(
        declaration,
        SnapshotStore(dependent_atomspace_store=dependent_store),
        dependent_store,
        ruleset_revision=ruleset_revision,
        domain_projector=activated,
        event_emitter=emitter,
        projector_ids=tuple(value.projector_id for value in projectors),
        ruleset_digest_value=digest,
    )
    if ruleset_ir is not None:
        from ...planning import CandidateOperationFactory, GoalFactory
        from ...pressure import DependentAtomPressureAdapter
        runtime.configure_shadow_evaluation(
            GoalFactory(), CandidateOperationFactory(ruleset_ir, digest),
            DependentAtomPressureAdapter())
    return runtime
