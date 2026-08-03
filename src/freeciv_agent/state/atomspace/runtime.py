"""Fail-closed runtime assembly for shadow Functional Dependent AtomSpace.

Component tests construct individual projectors directly.  This module is the
single application boundary that turns a validated configuration declaration
into a coordinated snapshot/ruleset AtomSpace pair.  It deliberately exposes
no action-selection API: authority remains downstream of the separately gated
pressure adapter, commit validator, and execution gate.
"""

from dataclasses import dataclass, replace
import gc
import json
import os
import threading
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


_FDAS_SHADOW_LOCK = threading.RLock()


def _without_cyclic_gc(function):
    """Keep non-deterministic cyclic-GC pauses outside bounded readout."""
    def guarded(*args, **kwargs):
        with _FDAS_SHADOW_LOCK:
            enabled = gc.isenabled()
            if enabled:
                gc.disable()
            try:
                return function(*args, **kwargs)
            finally:
                if enabled:
                    gc.enable()
    return guarded


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

    @property
    def component_projector_ids(self):
        return tuple(getattr(
            self.projector, "component_projector_ids", ()))

    @property
    def incremental_dependency_roots(self):
        return frozenset(getattr(
            self.projector, "incremental_dependency_roots", ()))

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

    def project_incremental(
            self, snapshot, scopes, fingerprints, prior_snapshot,
            prior_revision):
        if hasattr(self.projector, "project_incremental"):
            return self.projector.project_incremental(
                snapshot, scopes, fingerprints, prior_snapshot,
                prior_revision)
        return self.project(snapshot, scopes, fingerprints)

    def incremental_metrics(self, snapshot_id):
        if hasattr(self.projector, "incremental_metrics"):
            return self.projector.incremental_metrics(snapshot_id)
        return {
            "recomputed_projector_ids": (),
            "recomputed_record_count": 0,
            "reused_projector_ids": (),
            "reused_record_count": 0,
            "recomputed_shard_ids": (),
            "recomputed_shard_records": (),
            "reused_shard_ids": (),
            "reused_shard_records": (),
        }


@dataclass(frozen=True)
class FdasRuntimeUpdate:
    snapshot_id: str
    revision_id: object
    atom_count: int
    scope_count: int
    latency_ms: float
    cold_verification: object = None
    materialization_metrics: object = None

    def to_dict(self):
        return {
            "atom_count": self.atom_count,
            "cold_verification": (
                None if self.cold_verification is None
                else self.cold_verification.to_dict()),
            "latency_ms": self.latency_ms,
            "materialization_metrics": (
                None if self.materialization_metrics is None
                else self.materialization_metrics.to_dict()),
            "revision_id": self.revision_id,
            "scope_count": self.scope_count,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class FdasDecisionExplanation:
    """Canonical revision-bound why/why-not bundle for one shadow readout."""

    revision_id: str
    snapshot_id: str
    status: str
    reason: object
    selected_operation_id: object
    route_kind: str
    goal_routes: tuple
    causal_rules: tuple
    candidate: object
    pressure_operation: object
    schedule: dict
    blockers: tuple
    diagnostics: tuple
    explanation_hash: str

    def __post_init__(self):
        if self.route_kind not in (
                "candidate", "candidate-blocked", "gap", "none"):
            raise ValueError("invalid FDAS decision explanation route kind")
        object.__setattr__(self, "goal_routes", tuple(self.goal_routes))
        object.__setattr__(self, "causal_rules", tuple(self.causal_rules))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self):
        return {
            "blockers": list(self.blockers),
            "candidate": self.candidate,
            "causal_rules": list(self.causal_rules),
            "diagnostics": list(self.diagnostics),
            "explanation_hash": self.explanation_hash,
            "goal_routes": list(self.goal_routes),
            "pressure_operation": self.pressure_operation,
            "reason": self.reason,
            "revision_id": self.revision_id,
            "route_kind": self.route_kind,
            "schedule": dict(self.schedule),
            "selected_operation_id": self.selected_operation_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
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
    decision_explanation: FdasDecisionExplanation
    stage_latency_ms: tuple
    latency_ms: float

    def __post_init__(self):
        stages = tuple(sorted(
            (str(name), float(value))
            for name, value in self.stage_latency_ms))
        if any(value < 0.0 for _name, value in stages):
            raise ValueError("FDAS stage latency cannot be negative")
        object.__setattr__(self, "stage_latency_ms", stages)

    def to_dict(self):
        return {
            "candidate_count": len(self.candidates),
            "candidate_instantiation": self.candidate_instantiation.to_dict(),
            "comparison": (
                None if self.comparison is None
                else self.comparison.to_dict()),
            "decision_explanation": self.decision_explanation.to_dict(),
            "goal_count": len(self.goals),
            "latency_ms": self.latency_ms,
            "pressure": self.pressure.to_dict(),
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "stage_latency_ms": dict(self.stage_latency_ms),
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
        self._authority_adapter = None
        self._authority_domain = None
        self._post_projection_reconciler = None
        self._last_cold_verification_turn = {}

    @property
    def enabled(self):
        return self.config.enabled

    @property
    def shadow_pressure_config(self):
        if self._pressure_adapter is None:
            raise FdasRuntimeConfigurationError(
                "FDAS shadow pressure adapter is not configured")
        return self._pressure_adapter.config

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
            "shadow_refresh_policy": self.config.shadow_refresh_policy,
        }

    def _sample_cold_verification(self, snapshot):
        rate = self.config.cold_verify_sample_rate
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True
        game_key = (
            str(snapshot.identity.game_id), int(snapshot.player_id))
        if self._last_cold_verification_turn.get(game_key) == snapshot.turn:
            return False
        sample = int(structural_hash([
            "fdas-cold-verification/2.0",
            snapshot.identity.game_id,
            snapshot.player_id,
            snapshot.turn,
        ])[:13], 16) / float(16 ** 13)
        selected = sample < rate
        if selected:
            self._last_cold_verification_turn[game_key] = snapshot.turn
        return selected

    def replace(self, snapshot):
        """Install one snapshot and sample incremental/cold parity."""
        started = time.perf_counter()
        prior_snapshot, prior_revision = self.snapshot_store.current_pair(
            snapshot.identity.game_id, snapshot.player_id)
        verification = None
        prepared_revision = None
        if (self.enabled and prior_snapshot is not None
                and self._sample_cold_verification(snapshot)):
            prepared_revision, verification = (
                self.dependent_store.prepare_verified_incremental(
                snapshot, prior_snapshot, prior_revision)
            )
            if not verification.equivalent:
                raise RuntimeError(
                    "FDAS incremental/cold mismatch: {}; diagnostics: {}"
                    .format(
                        verification.mismatch_categories,
                        dict(verification.diagnostics)))
        if prepared_revision is None:
            self.snapshot_store.replace(snapshot)
        else:
            self.snapshot_store.replace_prepared(
                snapshot, prepared_revision,
                expected_prior_revision_id=prior_revision.revision_id)
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if self._post_projection_reconciler is not None:
            changed = self._post_projection_reconciler(snapshot, revision)
            if not isinstance(changed, bool):
                raise RuntimeError(
                    "FDAS source reconciler must return a boolean")
            if changed:
                revision = self.snapshot_store.rematerialize_dependent(
                    snapshot.identity.game_id, snapshot.player_id)
        return FdasRuntimeUpdate(
            snapshot.snapshot_id,
            None if revision is None else revision.revision_id,
            0 if revision is None else len(revision.records),
            0 if revision is None else len(revision.scopes),
            (time.perf_counter() - started) * 1000.0,
            verification,
            None if revision is None else revision.metrics,
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
            None,
            revision.metrics,
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

    def configure_authority(self, authority_adapter, authority_domain):
        """Install the separately gated bounded authority readout."""
        if not self.enabled or not self.config.authority_enabled:
            raise FdasRuntimeConfigurationError(
                "FDAS authority adapter requires enabled authority config")
        if authority_adapter is None:
            raise FdasRuntimeConfigurationError(
                "FDAS authority adapter is required")
        domains = self.config.section("domain_authority")
        if authority_domain not in domains or not domains[authority_domain]:
            raise FdasRuntimeConfigurationError(
                "FDAS authority adapter domain is not enabled")
        self._authority_adapter = authority_adapter
        self._authority_domain = authority_domain
        return self

    def configure_post_projection_reconciler(self, reconciler):
        """Install one non-authorizing durable-source reconciliation hook."""
        if not self.enabled:
            raise FdasRuntimeConfigurationError(
                "disabled FDAS cannot configure source reconciliation")
        if not callable(reconciler):
            raise FdasRuntimeConfigurationError(
                "FDAS source reconciler must be callable")
        self._post_projection_reconciler = reconciler
        return self

    @staticmethod
    def explain_shadow_decision(
            revision, query, goals, candidates, instantiation, pressure):
        """Join proof, candidate, pressure, resource, and schedule evidence."""
        selected_id = pressure.schedule.get("selected_operation_id")
        candidate = next((
            value for value in candidates
            if value.operation.operation_id == selected_id), None)
        pressure_operation = next((
            value for value in pressure.context.operations
            if value.operation_id == selected_id), None)
        selected_is_gap = (
            selected_id is not None
            and str(selected_id).startswith("fdas-expand-gap:"))
        if (selected_id is not None and candidate is None
                and not selected_is_gap):
            raise RuntimeError(
                "selected FDAS operation has no candidate or gap route")
        if selected_id is not None and pressure_operation is None:
            raise RuntimeError(
                "selected FDAS operation lacks pressure evidence")
        if candidate is not None:
            route_kind = (
                "candidate-blocked" if candidate.blockers else "candidate")
            goal_ids = tuple(candidate.operation.goal_ids)
            candidate_value = candidate.to_dict()
            blockers = tuple(candidate.blockers)
            atom_id = dict(pressure.context.candidate_atom_ids).get(
                selected_id)
        elif selected_is_gap:
            route_kind = "gap"
            goal_ids = tuple(
                goal_id for goal_id, effect
                in (pressure_operation.goal_effects
                    if pressure_operation is not None else ())
                if float(effect) > 0.0)
            candidate_value = None
            blockers = ("no-current-legal-causal-route",)
            gap_atoms = dict(pressure.context.gap_atom_ids)
            atom_id = next((
                value for goal_id, value in gap_atoms.items()
                if goal_id in goal_ids), None)
        else:
            route_kind = "none"
            goal_ids = ()
            candidate_value = None
            blockers = tuple(sorted(set(
                ([pressure.reason] if pressure.reason else [])
                + list(pressure.context.diagnostics)
                + list(instantiation.diagnostics))))
            atom_id = None
        goal_by_id = dict((value.goal.goal_id, value) for value in goals)
        goal_routes = []
        for goal_id in sorted(set(goal_ids)):
            goal = goal_by_id.get(goal_id)
            if goal is None:
                raise RuntimeError(
                    "selected FDAS operation references an inactive goal")
            deficit_explanation = query.explain(goal.deficit_atom_id)
            goal_routes.append({
                "deficit_atom_id": goal.deficit_atom_id,
                "deficit_explanation": deficit_explanation,
                "deficit_predicate": goal.deficit_predicate,
                "explanation_hash": goal.explanation_hash,
                "global_goal_kind": goal.global_goal_kind,
                "goal": goal.goal.to_dict(),
                "scope_id": goal.scope_id,
                "target_key": goal.target_key.to_dict(),
            })
        causal_rules = tuple(
            value.to_dict() for value in pressure.context.graph.rules
            if atom_id is not None and atom_id in value.premise_ids)
        if selected_id is not None and (
                not goal_routes or atom_id is None or not causal_rules):
            raise RuntimeError(
                "selected FDAS operation has incomplete causal evidence")
        diagnostics = tuple(sorted(set(
            pressure.context.diagnostics + instantiation.diagnostics)))
        schedule_evidence = {
            "allocations": [
                value for value in pressure.schedule.get("allocations", ())
                if value.get("operation_id") == selected_id],
            "pressure_hash": pressure.schedule.get("pressure_hash"),
            "reason": pressure.schedule.get("reason"),
            "scores": [
                value for value in pressure.schedule.get("scores", ())
                if value.get("operation", {}).get("operation_id")
                == selected_id],
            "selected_operation_id": selected_id,
            "solver_identity": pressure.schedule.get("solver_identity"),
            "status": pressure.schedule.get("status"),
            "structural_hash": pressure.schedule.get("structural_hash"),
        }
        if (selected_id is not None
                and len(schedule_evidence["scores"]) != 1):
            raise RuntimeError(
                "selected FDAS operation lacks unique scheduler evidence")
        semantic = {
            "blockers": list(blockers),
            "candidate": candidate_value,
            "causal_rules": list(causal_rules),
            "diagnostics": list(diagnostics),
            "goal_routes": goal_routes,
            "pressure_operation": (
                None if pressure_operation is None
                else pressure_operation.to_dict()),
            "reason": pressure.reason,
            "revision_id": revision.revision_id,
            "route_kind": route_kind,
            "schedule": schedule_evidence,
            "selected_operation_id": selected_id,
            "snapshot_id": revision.snapshot_id,
            "status": pressure.status,
        }
        return FdasDecisionExplanation(
            revision.revision_id, revision.snapshot_id, pressure.status,
            pressure.reason, selected_id, route_kind, tuple(goal_routes),
            causal_rules, candidate_value,
            semantic["pressure_operation"], schedule_evidence, blockers,
            diagnostics, structural_hash(semantic))

    @_without_cyclic_gc
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
        stage_started = started
        stage_latency = []
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS shadow evaluation requires the current revision")
        query = self.dependent_store.query_current(
            snapshot.identity.game_id, snapshot.player_id)
        now = time.perf_counter()
        stage_latency.append((
            "revision_query", (now - stage_started) * 1000.0))
        stage_started = now
        goals = self._goal_factory.instantiate(revision, query)
        now = time.perf_counter()
        stage_latency.append((
            "goal_instantiation", (now - stage_started) * 1000.0))
        stage_started = now
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
        now = time.perf_counter()
        stage_latency.append((
            "candidate_instantiation", (now - stage_started) * 1000.0))
        stage_started = now
        candidates = instantiation.candidates
        pressure = self._pressure_adapter.evaluate(
            revision, goals, candidates)
        now = time.perf_counter()
        stage_latency.append((
            "pressure_evaluation", (now - stage_started) * 1000.0))
        stage_started = now
        decision_explanation = self.explain_shadow_decision(
            revision, query, goals, candidates, instantiation, pressure)
        now = time.perf_counter()
        stage_latency.append((
            "decision_explanation", (now - stage_started) * 1000.0))
        stage_started = now
        comparison = None
        if legacy_candidates is not None:
            from ...planning import compare_shadow_candidates
            comparison = compare_shadow_candidates(
                snapshot, legacy_candidates, candidates, goals)
        now = time.perf_counter()
        stage_latency.append((
            "legacy_comparison", (now - stage_started) * 1000.0))
        return FdasShadowEvaluation(
            snapshot.snapshot_id, revision.revision_id, goals, candidates,
            instantiation, pressure, comparison, decision_explanation,
            tuple(stage_latency), (now - started) * 1000.0)

    def shadow_operation_scores(self, evaluation):
        """Reconstruct exact typed scores behind one shadow artifact."""
        if not isinstance(evaluation, FdasShadowEvaluation):
            raise TypeError("FDAS typed scores require shadow evaluation")
        if self._pressure_adapter is None:
            raise FdasRuntimeConfigurationError(
                "FDAS shadow pressure adapter is not configured")
        pressure = evaluation.pressure
        if pressure.status != "complete":
            return ()
        scores = self._pressure_adapter.scheduler.score_all(
            pressure.context.operations, pressure.pressure_result)
        if [value.to_dict() for value in scores] != pressure.schedule.get(
                "scores"):
            raise RuntimeError(
                "typed FDAS scores differ from emitted schedule")
        selected = next(
            (value.operation_id for value in scores if value.admissible), None)
        if selected != pressure.schedule.get("selected_operation_id"):
            raise RuntimeError(
                "typed FDAS score winner differs from emitted schedule")
        return scores

    def evaluate_authority(self, snapshot, shadow_evaluation,
                           legacy_candidate):
        """Evaluate the configured authority slice or return no readout."""
        if not self.config.authority_enabled:
            return None
        if self._authority_adapter is None:
            raise FdasRuntimeConfigurationError(
                "enabled FDAS authority is not configured")
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS authority requires the current revision")
        domains = self.config.section("domain_authority")
        if self._authority_domain == "city_stability":
            return self._authority_adapter.evaluate(
                snapshot, revision, shadow_evaluation, legacy_candidate,
                authority_enabled=self.config.authority_enabled,
                city_stability_enabled=domains["city_stability"])
        if self._authority_domain == "city_defense":
            return self._authority_adapter.evaluate(
                snapshot, revision, shadow_evaluation, legacy_candidate,
                authority_enabled=self.config.authority_enabled,
                city_defense_enabled=domains["city_defense"])
        raise FdasRuntimeConfigurationError(
            "configured FDAS authority domain has no runtime adapter")

    def authority_relevant(self, legacy_candidate):
        """Test the configured domain gate before rich materialization."""
        if not self.config.authority_enabled or self._authority_adapter is None:
            return False
        return bool(self._authority_adapter.relevant(legacy_candidate))

    def authority_candidate(self, snapshot, shadow_evaluation, readout):
        """Return the exact candidate bound by a current authority readout."""
        if self._authority_domain != "city_defense":
            raise FdasRuntimeConfigurationError(
                "authority candidate recovery is limited to city defense")
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS authority candidate requires the current revision")
        return self._authority_adapter.candidate_from_readout(
            snapshot, revision, shadow_evaluation, readout)

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

    def emit_authority(self, writer, snapshot, readout, caused_by=()):
        """Emit a revision-bound authority/fallback event."""
        if readout is None or self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.revision_id != readout.revision_id:
            raise RuntimeError(
                "FDAS authority evidence is not revision-current")
        return self.event_emitter.emit_authority_readout(
            writer, snapshot.turn, revision, readout,
            ruleset_digest=self.ruleset_digest,
            caused_by=tuple(caused_by))

    def emit_episode_component(
            self, writer, snapshot, event_type, details, caused_by=()):
        """Emit one learning event bound to the current FDAS revision."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS episode evidence is not snapshot-current")
        return self.event_emitter.emit_component(
            writer, event_type, snapshot.turn, revision, details,
            caused_by=tuple(caused_by), ruleset_digest=self.ruleset_digest,
            component_id="fdas-episode-control-learning",
            component_version="1.0")

    def emit_induced_rule_candidate_impact(
            self, writer, snapshot, details, caused_by=()):
        """Emit a revision-bound, explicitly non-authorizing impact readout."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS candidate impact evidence is not snapshot-current")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-induced-rule-candidate-impact",
            component_version="1.0")

    def emit_induced_rule_candidate_choice_set(
            self, writer, snapshot, choice_set, transition, caused_by=()):
        """Emit one revision-bound, censored-alternative choice artifact."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if revision is None or revision.snapshot_id != snapshot.snapshot_id:
            raise RuntimeError(
                "FDAS candidate choice evidence is not snapshot-current")
        details = {
            "action_selection_changed": False,
            "candidate_choice_set": choice_set.to_dict(),
            "nonselected_outcome_semantics": "censored-not-negative",
            "policy_authority": False,
            "readout_authority": False,
            "transition": str(transition),
            "truth_mutated": False,
        }
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-induced-rule-candidate-choice-set",
            component_version="1.0")

    def emit_calibrated_candidate_union(
            self, writer, snapshot, candidate_union,
            calibration_artifact_hash, confirmation_report_hash,
            caused_by=()):
        """Emit calibrated recall membership without selection authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_union.snapshot_id != snapshot.snapshot_id
                or candidate_union.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS calibrated candidate union is not revision-current")
        for value, name in (
                (calibration_artifact_hash, "calibration artifact hash"),
                (confirmation_report_hash, "confirmation report hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("FDAS {} is required".format(name))
        details = candidate_union.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "capacity_solver_enabled",
                "flow_advection_enabled", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS calibrated candidate union grants undeclared authority")
        if details.get("scalar_final_score_authority") is not True:
            raise RuntimeError(
                "FDAS calibrated candidate union displaced scalar authority")
        details.update({
            "calibration_artifact_hash": calibration_artifact_hash,
            "confirmation_report_hash": confirmation_report_hash,
        })
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-calibrated-candidate-union",
            component_version="1.0")

    def emit_decision_safe_candidate_readout(
            self, writer, snapshot, readout, caused_by=()):
        """Emit an uncertainty-separated grounded preference without authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or readout.snapshot_id != snapshot.snapshot_id
                or readout.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS decision-safe candidate readout is not revision-current")
        details = readout.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS decision-safe candidate readout grants authority")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-decision-safe-candidate-readout",
            component_version="1.0")

    def emit_grounded_transition_candidate_union(
            self, writer, snapshot, candidate_union,
            calibration_artifact_hash, confirmation_report_hash,
            caused_by=()):
        """Emit confirmed grounded-transition recall without authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_union.snapshot_id != snapshot.snapshot_id
                or candidate_union.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS grounded transition union is not revision-current")
        for value, name in (
                (calibration_artifact_hash, "calibration artifact hash"),
                (confirmation_report_hash, "confirmation report hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("FDAS {} is required".format(name))
        details = candidate_union.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "capacity_solver_enabled",
                "flow_advection_enabled", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS grounded transition union grants undeclared authority")
        if details.get("scalar_final_score_authority") is not True:
            raise RuntimeError(
                "FDAS grounded transition union displaced scalar authority")
        details.update({
            "calibration_artifact_hash": calibration_artifact_hash,
            "calibration_model_kind": "grounded-transition",
            "confirmation_report_hash": confirmation_report_hash,
        })
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-grounded-transition-candidate-union",
            component_version="1.0")

    def emit_scalar_baseline_candidate_readout(
            self, writer, snapshot, readout, caused_by=()):
        """Emit a protected scalar-baseline preference without authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or readout.snapshot_id != snapshot.snapshot_id
                or readout.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS scalar-baseline readout is not revision-current")
        details = readout.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS scalar-baseline readout grants undeclared authority")
        if details.get("control_semantics") != (
                "protected-fdas-scalar-top-1"):
            raise RuntimeError(
                "FDAS scalar-baseline control semantics differ")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-scalar-baseline-candidate-readout",
            component_version="1.0")

    def emit_coordinated_replacement_lifecycle(
            self, writer, snapshot, update, store_digest, caused_by=()):
        """Emit one current, non-authorizing replacement lifecycle update."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        details = update.to_dict()
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or details.get("snapshot_id") != snapshot.snapshot_id):
            raise RuntimeError(
                "FDAS coordinated replacement update is not revision-current")
        if not isinstance(store_digest, str) or not store_digest:
            raise ValueError(
                "FDAS coordinated replacement store digest is required")
        details.update({
            "action_selection_changed": False,
            "identity": "fdas-coordinated-replacement-lifecycle/1.0",
            "policy_authority": False,
            "readout_authority": False,
            "store_digest": store_digest,
            "truth_mutated": False,
        })
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-coordinated-replacement-lifecycle",
            component_version="1.0")

    def emit_decision_safe_candidate_filter(
            self, writer, snapshot, candidate_filter, caused_by=()):
        """Emit exact pre-union safety exclusions without action authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_filter.snapshot_id != snapshot.snapshot_id
                or candidate_filter.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS decision-safe candidate filter is not revision-current")
        details = candidate_filter.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS decision-safe candidate filter grants authority")
        if (details.get("candidate_surface_preserved") is not True
                or details.get("calibrated_union_input_filtered") is not True):
            raise RuntimeError(
                "FDAS decision-safe candidate filter semantics differ")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-decision-safe-candidate-filter",
            component_version="1.0")

    def emit_target_scoped_candidate_filter(
            self, writer, snapshot, candidate_filter, caused_by=()):
        """Emit exact scalar-target scoping without action authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_filter.snapshot_id != snapshot.snapshot_id
                or candidate_filter.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS target-scoped candidate filter is not revision-current")
        details = candidate_filter.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS target-scoped candidate filter grants authority")
        if (details.get("candidate_surface_preserved") is not True
                or details.get("calibrated_union_input_filtered") is not True):
            raise RuntimeError(
                "FDAS target-scoped candidate filter semantics differ")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-target-scoped-candidate-filter",
            component_version="1.0")

    def emit_probe_candidate_union(
            self, writer, snapshot, candidate_union, caused_by=()):
        """Emit corrected-probe membership without ranking authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_union.snapshot_id != snapshot.snapshot_id
                or candidate_union.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS probe candidate union is not revision-current")
        details = candidate_union.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "capacity_solver_enabled",
                "flow_advection_enabled", "policy_authority",
                "readout_authority", "truth_mutated")):
            raise RuntimeError(
                "FDAS probe candidate union grants undeclared authority")
        if details.get("scalar_final_score_authority") is not True:
            raise RuntimeError(
                "FDAS probe candidate union displaced scalar authority")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-probe-candidate-union",
            component_version="1.0")

    def emit_path_persistence_union(
            self, writer, snapshot, candidate_union, caused_by=()):
        """Emit temporal candidate retention without action authority."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or candidate_union.snapshot_id != snapshot.snapshot_id
                or candidate_union.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS path persistence union is not revision-current")
        details = candidate_union.to_dict()
        if any(details.get(name) is not False for name in (
                "action_selection_changed", "capacity_solver_enabled",
                "flow_advection_enabled", "path_persistence_authority",
                "policy_authority", "readout_authority",
                "source_sink_flow_enabled", "truth_mutated")):
            raise RuntimeError(
                "FDAS path persistence union grants undeclared authority")
        if details.get("scalar_final_score_authority") is not True:
            raise RuntimeError(
                "FDAS path persistence union displaced scalar authority")
        return self.event_emitter.emit_component(
            writer, "atomspace_shadow_decision", snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-path-persistence-candidate-union",
            component_version="1.0")

    def emit_alternative_outcome_collection(
            self, writer, snapshot, readout, caused_by=()):
        """Emit a safe randomized assignment with explicit authority scope."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or readout.snapshot_id != snapshot.snapshot_id
                or readout.revision_id != revision.revision_id):
            raise RuntimeError(
                "FDAS alternative collection readout is not revision-current")
        details = readout.to_dict()
        if any(details.get(name) is not False for name in (
                "assignment_executed", "claim_eligible",
                "source_sink_flow_enabled", "truth_mutated")):
            raise RuntimeError(
                "FDAS alternative collection escaped its declared scope")
        if details.get("outcome_update_scope") != "control-model-only":
            raise RuntimeError(
                "FDAS alternative collection escaped control-model scope")
        eligible = details.get("status") in (
            "eligible-shadow", "eligible-randomized-diagnostic")
        if (eligible
                and (details.get("selection_policy_kind") != "stochastic"
                     or details.get("selection_propensity") is None)):
            raise RuntimeError(
                "FDAS eligible alternative collection lacks propensity")
        configured_actual = bool(
            details.get("config", {}).get("mode")
            == "randomized-diagnostic")
        actual = details.get("status") == "eligible-randomized-diagnostic"
        if (details.get("policy_authority") is not actual
                or details.get("action_selection_changed") is not bool(
                    actual and details.get("assigned_arm") == "treatment")
                or (details.get("status") == "eligible-shadow"
                    and configured_actual)
                or (actual and not configured_actual)):
            raise RuntimeError(
                "FDAS alternative collection authority semantics differ")
        return self.event_emitter.emit_component(
            writer,
            ("atomspace_authority_decision"
             if configured_actual else "atomspace_shadow_decision"),
            snapshot.turn, revision,
            details, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-safe-alternative-outcome-collection",
            component_version="3.0")

    def emit_alternative_outcome_execution(
            self, writer, snapshot, assignment, accepted,
            execution_event_id, authority_catalog_reprojected,
            episode_id=None, caused_by=()):
        """Link one diagnostic assignment to execution and its episode."""
        if self.event_emitter is None:
            return None
        revision = self.snapshot_store.current_dependent_revision(
            snapshot.identity.game_id, snapshot.player_id)
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id
                or assignment.snapshot_id != snapshot.snapshot_id
                or assignment.revision_id != revision.revision_id
                or assignment.status
                != "eligible-randomized-diagnostic"
                or not assignment.policy_authority
                or assignment.claim_eligible
                or assignment.truth_mutated):
            raise RuntimeError(
                "FDAS alternative execution lacks current assignment authority")
        if not isinstance(accepted, bool):
            raise TypeError("FDAS alternative execution status must be boolean")
        if not isinstance(authority_catalog_reprojected, bool):
            raise TypeError(
                "FDAS alternative execution reprojection status must be "
                "boolean")
        if (not isinstance(execution_event_id, str)
                or not execution_event_id):
            raise ValueError(
                "FDAS alternative execution requires an event identity")
        if accepted:
            if not isinstance(episode_id, str) or not episode_id:
                raise ValueError(
                    "accepted FDAS alternative execution requires an episode")
        elif episode_id is not None:
            raise ValueError(
                "rejected FDAS alternative execution cannot link an episode")
        semantic = {
            "action_selection_changed": (
                assignment.action_selection_changed),
            "assigned_action_key": assignment.assigned_action_key,
            "assigned_arm": assignment.assigned_arm,
            "assigned_operation_id": assignment.assigned_operation_id,
            "assignment_executed": accepted,
            "assignment_execution_attempted": True,
            "assignment_result_hash": assignment.result_hash,
            "authority_catalog_reprojected": (
                authority_catalog_reprojected),
            "claim_eligible": False,
            "episode_id": episode_id,
            "execution_event_id": execution_event_id,
            "outcome_update_scope": "control-model-only",
            "policy_authority": True,
            "selection_policy_kind": "stochastic",
            "selection_propensity": assignment.selection_propensity,
            "status": (
                "execution-accepted-episode-linked"
                if accepted else "execution-rejected"),
            "truth_mutated": False,
        }
        semantic["result_hash"] = structural_hash(semantic)
        return self.event_emitter.emit_component(
            writer, "atomspace_authority_decision", snapshot.turn, revision,
            semantic, caused_by=tuple(caused_by),
            ruleset_digest=self.ruleset_digest,
            component_id="fdas-safe-alternative-outcome-execution",
            component_version="1.1")


def build_runtime(declaration, ruleset_ir=None, belief_store=None,
                  operation_records_source=None,
                  operation_bindings_source=None,
                  operation_requirement_contexts_source=None,
                  episode_source=None):
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
        projectors.append(CityRegionProjector())
    if projection["route_corridors"]:
        projectors.append(RouteCorridorProjector())
    if projection["settlement_sites"]:
        projectors.append(SettlementSiteProjector(ruleset_ir, digest))
    if (any(projection[name] for name in (
            "combat", "population_recovery", "transport"))
            and ruleset_ir is None):
        raise FdasRuntimeConfigurationError(
            "combat, population recovery, and transport projection require "
            "compiled ruleset IR")
    if projection["transport"]:
        projectors.append(TransportCapabilityProjector(ruleset_ir, digest))
    if projection["combat"]:
        projectors.append(CombatTaskForceProjector(ruleset_ir, digest))
    if projection["population_recovery"]:
        projectors.append(PopulationRecoveryProjector(ruleset_ir, digest))
    if projection["operations"]:
        if operation_records_source is None:
            raise FdasRuntimeConfigurationError(
                "operation projection requires a durable record source")
        projectors.append(OperationProjector(
            operation_records_source,
            bindings_source=operation_bindings_source,
            requirement_contexts_source=(
                operation_requirement_contexts_source)))
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
        include_legacy_projection=projection["legacy_compatibility"],
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
        if config.authority_enabled:
            from ...planning import (
                FdasBoundedCityAuthority,
                FdasBoundedDefenseAuthority,
            )
            domains = config.section("domain_authority")
            active_domains = tuple(sorted(
                name for name, enabled in domains.items() if enabled))
            if active_domains == ("city_stability",):
                runtime.configure_authority(
                    FdasBoundedCityAuthority(), "city_stability")
            elif active_domains == ("city_defense",):
                runtime.configure_authority(
                    FdasBoundedDefenseAuthority(), "city_defense")
            else:
                raise FdasRuntimeConfigurationError(
                    "no bounded runtime adapter for FDAS authority domains "
                    "{}".format(active_domains))
    return runtime
