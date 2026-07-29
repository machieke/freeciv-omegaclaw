"""Versioned boundary between grounded Impact candidates and controllers."""

from collections import OrderedDict
from dataclasses import dataclass
import time

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from ..pressure.packets import PacketSchedule
from .impact import ImpactCandidate


CONTROLLER_MODES = (
    "canonical",
    "legacy_scalar",
    "scalar_v2",
    "bridge_scalar",
    "unified_flow",
    "unified_shadow",
)


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


@dataclass(frozen=True)
class ControlQuery:
    query_id: str
    snapshot_id: str
    semantic_epoch: int
    legal_actions_digest: str
    current_turn: int
    horizon_turn: int
    active_goals: tuple
    grounded_candidates: tuple
    truth_summaries: tuple
    evidence_summaries: tuple
    context_digest: str
    config_digest: str
    ruleset_digest: str
    expansion_city_target: int
    survival_threat_radius: int
    pressure_generation: int
    lifecycle_clone_generation: int
    normalization_contract_hash: str
    goal_facts: object = None

    def __post_init__(self):
        for value, name in (
                (self.query_id, "control query ID"),
                (self.snapshot_id, "control snapshot ID"),
                (self.legal_actions_digest,
                 "control legal-actions digest"),
                (self.context_digest, "control context digest"),
                (self.config_digest, "control config digest"),
                (self.ruleset_digest, "control ruleset digest"),
                (self.normalization_contract_hash,
                 "normalization contract hash")):
            _required_text(value, name)
        for value, name in (
                (self.semantic_epoch, "semantic epoch"),
                (self.current_turn, "current turn"),
                (self.horizon_turn, "horizon turn"),
                (self.expansion_city_target,
                 "expansion city target"),
                (self.survival_threat_radius,
                 "survival threat radius"),
                (self.pressure_generation,
                 "pressure generation"),
                (self.lifecycle_clone_generation,
                 "clone generation")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be a non-negative integer".format(name))
        if self.horizon_turn < self.current_turn:
            raise ValueError(
                "control horizon cannot precede current turn")
        if any(not isinstance(row, ImpactCandidate)
               for row in self.grounded_candidates):
            raise TypeError(
                "control candidates must be ImpactCandidate")
        keys = [
            row.action_key for row in self.grounded_candidates]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "grounded candidate keys must be unique")
        if (len(set(self.active_goals))
                != len(self.active_goals)
                or any(not isinstance(value, str) or not value
                       for value in self.active_goals)):
            raise ValueError(
                "active goal IDs must be unique")

    @property
    def candidate_keys(self):
        return tuple(
            row.action_key
            for row in self.grounded_candidates)

    @property
    def query_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "active_goals": list(self.active_goals),
            "config_digest": self.config_digest,
            "context_digest": self.context_digest,
            "current_turn": self.current_turn,
            "evidence_summaries": list(
                self.evidence_summaries),
            "expansion_city_target": (
                self.expansion_city_target),
            "grounded_candidates": [
                row.to_dict()
                for row in self.grounded_candidates],
            "horizon_turn": self.horizon_turn,
            "legal_actions_digest": (
                self.legal_actions_digest),
            "lifecycle_clone_generation": (
                self.lifecycle_clone_generation),
            "normalization_contract_hash": (
                self.normalization_contract_hash),
            "pressure_generation": (
                self.pressure_generation),
            "query_id": self.query_id,
            "ruleset_digest": self.ruleset_digest,
            "schema_version": "1.0",
            "semantic_epoch": self.semantic_epoch,
            "snapshot_id": self.snapshot_id,
            "survival_threat_radius": (
                self.survival_threat_radius),
            "truth_summaries": list(
                self.truth_summaries),
        }


@dataclass(frozen=True)
class ControlDecision:
    ordered_candidate_keys: tuple
    selected_candidate_key: object
    packet_schedule: object
    controller_mode: str
    artifact: dict
    health: str
    fallback_chain: tuple

    def __post_init__(self):
        if (len(set(self.ordered_candidate_keys))
                != len(self.ordered_candidate_keys)
                or any(not isinstance(value, str) or not value
                       for value
                       in self.ordered_candidate_keys)):
            raise ValueError(
                "ordered candidate keys must be unique")
        if self.selected_candidate_key is not None:
            _required_text(
                self.selected_candidate_key,
                "selected candidate key")
            if (not self.ordered_candidate_keys
                    or self.ordered_candidate_keys[0]
                    != self.selected_candidate_key):
                raise ValueError(
                    "selected candidate must be first")
        if (self.packet_schedule is not None
                and not isinstance(
                    self.packet_schedule, PacketSchedule)):
            raise TypeError(
                "control packet schedule has wrong type")
        _required_text(
            self.controller_mode, "controller mode")
        if not isinstance(self.artifact, dict):
            raise TypeError(
                "control artifact must be a dictionary")
        if self.health not in (
                "healthy", "fallback", "abstain",
                "unavailable", "unhealthy"):
            raise ValueError(
                "unknown control health")
        if any(not isinstance(value, str) or not value
               for value in self.fallback_chain):
            raise ValueError(
                "fallback chain must contain mode names")

    @property
    def decision_hash(self):
        material = self.to_dict()
        artifact = dict(material["artifact"])
        # Wall timing and measured memory are observational telemetry, not
        # part of the deterministic controller decision.
        artifact.pop("controller_telemetry", None)
        material["artifact"] = artifact
        return structural_hash(material)

    def to_dict(self):
        return {
            "artifact": dict(self.artifact),
            "controller_mode": self.controller_mode,
            "fallback_chain": list(self.fallback_chain),
            "health": self.health,
            "ordered_candidate_keys": list(
                self.ordered_candidate_keys),
            "packet_schedule": (
                self.packet_schedule.to_dict()
                if self.packet_schedule is not None
                else None),
            "schema_version": "1.0",
            "selected_candidate_key": (
                self.selected_candidate_key),
        }


@dataclass(frozen=True)
class ControlOutcomeRecord:
    decision_hash: str
    controller_mode: str
    selected_candidate_key: object
    executed_candidate_key: object
    effect_observed: object
    counterfactual_status: str
    before_snapshot_id: object
    after_snapshot_id: object
    execution_result_digest: str

    def to_dict(self):
        return {
            "after_snapshot_id": self.after_snapshot_id,
            "before_snapshot_id": self.before_snapshot_id,
            "controller_mode": self.controller_mode,
            "counterfactual_status": (
                self.counterfactual_status),
            "decision_hash": self.decision_hash,
            "effect_observed": self.effect_observed,
            "executed_candidate_key": (
                self.executed_candidate_key),
            "execution_result_digest": (
                self.execution_result_digest),
            "selected_candidate_key": (
                self.selected_candidate_key),
        }


@dataclass(frozen=True)
class ShadowBudgetConfig:
    per_controller_ms: float = 500.0
    total_ms: float = 1500.0
    maximum_artifact_bytes: int = 4 * 1024 * 1024

    def __post_init__(self):
        for value, name in (
                (self.per_controller_ms,
                 "per-controller shadow budget"),
                (self.total_ms, "total shadow budget")):
            value = float(value)
            if value <= 0.0:
                raise ValueError(
                    "{} must be positive".format(name))
        if (isinstance(self.maximum_artifact_bytes, bool)
                or not isinstance(
                    self.maximum_artifact_bytes, int)
                or self.maximum_artifact_bytes < 1):
            raise ValueError(
                "shadow artifact budget must be positive")


class CanonicalUtilityController:
    """Historical utility ordering and final safe fallback."""

    MODE = "canonical"

    def decide(self, query, snapshot):
        del snapshot
        rows = tuple(sorted(
            query.grounded_candidates,
            key=lambda row: (
                -float(row.utility),
                row.category, row.action_key)))
        keys = tuple(row.action_key for row in rows)
        return ControlDecision(
            ordered_candidate_keys=keys,
            selected_candidate_key=(
                keys[0] if keys else None),
            packet_schedule=None,
            controller_mode=self.MODE,
            artifact={
                "controller_identity":
                    "canonical-impact-utility/1.0",
                "query_hash": query.query_hash,
            },
            health="healthy",
            fallback_chain=())


class ImpactRankerController:
    """Compatibility wrapper around an existing Impact pressure ranker."""

    def __init__(self, mode, ranker):
        if mode not in (
                "legacy_scalar", "scalar_v2",
                "bridge_scalar"):
            raise ValueError(
                "ranker controller mode is invalid")
        if not hasattr(ranker, "rank"):
            raise TypeError(
                "impact ranker must expose rank")
        self.mode = mode
        self.ranker = ranker

    def decide(self, query, snapshot):
        rows, artifact = self.ranker.rank(
            snapshot,
            query.grounded_candidates,
            query.expansion_city_target,
            query.horizon_turn,
            query.survival_threat_radius,
            _goal_facts=query.goal_facts)
        rows = tuple(rows)
        keys = tuple(row.action_key for row in rows)
        packet_schedule = None
        serialized_artifact = artifact
        if isinstance(artifact, dict):
            candidate = artifact.get(
                "_packet_schedule_object")
            if isinstance(candidate, PacketSchedule):
                packet_schedule = candidate
            serialized_artifact = dict(artifact)
            serialized_artifact.pop(
                "_packet_schedule_object", None)
        return ControlDecision(
            ordered_candidate_keys=keys,
            selected_candidate_key=(
                keys[0] if keys else None),
            packet_schedule=packet_schedule,
            controller_mode=self.mode,
            artifact={
                "controller_identity":
                    "impact-ranker-wrapper/1.0",
                "query_hash": query.query_hash,
                "ranker_artifact": serialized_artifact,
            },
            health="healthy",
            fallback_chain=())


class LegacyImpactPressureController(ImpactRankerController):
    def __init__(self, ranker):
        super().__init__("legacy_scalar", ranker)


class ScalarV2Controller(ImpactRankerController):
    def __init__(self, ranker):
        super().__init__("scalar_v2", ranker)


class BridgeScalarImpactController(ImpactRankerController):
    def __init__(self, ranker):
        super().__init__("bridge_scalar", ranker)


class UnifiedFlowController:
    """Narrow interface for a later flow engine; unavailable by default."""

    MODE = "unified_flow"

    def __init__(self, engine):
        if not callable(engine):
            raise TypeError(
                "unified flow engine must be callable")
        self.engine = engine

    def decide(self, query, snapshot):
        result = self.engine(query, snapshot)
        if not isinstance(result, ControlDecision):
            raise TypeError(
                "unified flow engine must return ControlDecision")
        return result


class ImpactControlAdapter:
    """Narrow boundary between grounded Impact candidates and control engines."""

    ADAPTER_IDENTITY = "impact-control-adapter/1.0"

    def __init__(
            self, legacy_ranker=None,
            scalar_v2_ranker=None,
            bridge_scalar_ranker=None,
            unified_flow_engine=None,
            shadow_budget=None):
        self.controllers = {
            "canonical": CanonicalUtilityController(),
        }
        if legacy_ranker is not None:
            self.controllers["legacy_scalar"] = (
                LegacyImpactPressureController(
                    legacy_ranker))
        if scalar_v2_ranker is not None:
            self.controllers["scalar_v2"] = (
                ScalarV2Controller(scalar_v2_ranker))
        if bridge_scalar_ranker is not None:
            self.controllers["bridge_scalar"] = (
                BridgeScalarImpactController(
                    bridge_scalar_ranker))
        if unified_flow_engine is not None:
            self.controllers["unified_flow"] = (
                UnifiedFlowController(
                    unified_flow_engine))
        self.shadow_budget = (
            shadow_budget if shadow_budget is not None
            else ShadowBudgetConfig())
        if not isinstance(
                self.shadow_budget, ShadowBudgetConfig):
            raise TypeError(
                "shadow budget has wrong type")
        self._snapshots = OrderedDict()
        self.maximum_owned_queries = 128
        self._outcomes = []

    def build_query(
            self, snapshot, candidates,
            expansion_city_target, horizon_turn,
            survival_threat_radius, goal_facts,
            pressure_generation=0,
            lifecycle_clone_generation=0,
            normalization_contract_hash="unversioned",
            controller_config=None,
            ruleset_digest=None,
            truth_summaries=(),
            evidence_summaries=()):
        candidates = tuple(candidates)
        if any(not isinstance(row, ImpactCandidate)
               for row in candidates):
            raise TypeError(
                "control query requires ImpactCandidate")
        snapshot_id = str(snapshot.snapshot_id)
        legal_digest = str(
            snapshot.legal_actions_digest)
        current_turn = int(snapshot.turn)
        horizon_turn = int(horizon_turn)
        goal_facts = (
            dict(goal_facts)
            if isinstance(goal_facts, dict)
            else goal_facts)
        active_goals = tuple(sorted(
            str(value) for value in (
                goal_facts.keys()
                if isinstance(goal_facts, dict)
                else ())))
        context_material = (
            snapshot.event_payload()
            if hasattr(snapshot, "event_payload")
            else {
                "legal_actions_digest": legal_digest,
                "snapshot_id": snapshot_id,
                "turn": current_turn,
            })
        context_digest = structural_hash(
            context_material)
        config_digest = structural_hash(
            controller_config or {})
        if ruleset_digest is None:
            ruleset_digest = structural_hash({
                "ruleset": getattr(
                    snapshot, "ruleset", None),
                "ruleset_name": getattr(
                    snapshot, "ruleset_name", None),
            })
        semantic_material = {
            "active_goals": list(active_goals),
            "candidate_keys": sorted(
                row.action_key for row in candidates),
            "config_digest": config_digest,
            "context_digest": context_digest,
            "legal_actions_digest": legal_digest,
            "lifecycle_clone_generation": int(
                lifecycle_clone_generation),
            "normalization_contract_hash": (
                normalization_contract_hash),
            "pressure_generation": int(
                pressure_generation),
            "ruleset_digest": ruleset_digest,
            "snapshot_id": snapshot_id,
        }
        semantic_hash = structural_hash(
            semantic_material)
        semantic_epoch = int(
            semantic_hash[:16], 16)
        query_id = "impact-control-query:{}".format(
            structural_hash(dict(
                semantic_material,
                current_turn=current_turn,
                horizon_turn=horizon_turn)))
        query = ControlQuery(
            query_id=query_id,
            snapshot_id=snapshot_id,
            semantic_epoch=semantic_epoch,
            legal_actions_digest=legal_digest,
            current_turn=current_turn,
            horizon_turn=horizon_turn,
            active_goals=active_goals,
            grounded_candidates=candidates,
            truth_summaries=tuple(
                truth_summaries),
            evidence_summaries=tuple(
                evidence_summaries),
            context_digest=context_digest,
            config_digest=config_digest,
            ruleset_digest=str(ruleset_digest),
            expansion_city_target=int(
                expansion_city_target),
            survival_threat_radius=int(
                survival_threat_radius),
            pressure_generation=int(
                pressure_generation),
            lifecycle_clone_generation=int(
                lifecycle_clone_generation),
            normalization_contract_hash=str(
                normalization_contract_hash),
            goal_facts=goal_facts)
        self._snapshots[query.query_id] = snapshot
        self._snapshots.move_to_end(
            query.query_id)
        while len(self._snapshots) > (
                self.maximum_owned_queries):
            self._snapshots.popitem(last=False)
        return query

    @staticmethod
    def _validate_decision(query, decision):
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "controller must return ControlDecision")
        advertised = frozenset(query.candidate_keys)
        if (set(decision.ordered_candidate_keys)
                - advertised):
            raise ValueError(
                "controller added unadvertised candidate")
        if (decision.selected_candidate_key is not None
                and decision.selected_candidate_key
                not in advertised):
            raise ValueError(
                "controller selected unadvertised candidate")

    @staticmethod
    def _snapshot_hash(snapshot):
        material = (
            snapshot.event_payload()
            if hasattr(snapshot, "event_payload")
            else {
                "legal_actions_digest":
                    snapshot.legal_actions_digest,
                "snapshot_id": snapshot.snapshot_id,
                "turn": snapshot.turn,
            })
        return structural_hash(material)

    def _shadow_decision(self, query, snapshot):
        canonical = self.controllers[
            "canonical"].decide(query, snapshot)
        snapshot_before = self._snapshot_hash(
            snapshot)
        candidates_before = structural_hash([
            row.to_dict()
            for row in query.grounded_candidates])
        started_total = time.perf_counter()
        shadows = []
        telemetry = {}
        for mode in (
                "scalar_v2", "bridge_scalar",
                "unified_flow"):
            elapsed_total_ms = (
                time.perf_counter() - started_total
            ) * 1000.0
            controller = self.controllers.get(mode)
            if controller is None:
                shadows.append({
                    "controller_mode": mode,
                    "counterfactual_status":
                        "unknown-counterfactual",
                    "decision": None,
                    "health": "unavailable",
                    "packet_conserved": None,
                    "spendable": False,
                })
                continue
            if elapsed_total_ms > (
                    self.shadow_budget.total_ms):
                shadows.append({
                    "controller_mode": mode,
                    "counterfactual_status":
                        "unknown-counterfactual",
                    "decision": None,
                    "health": "budget-skipped",
                    "packet_conserved": None,
                    "spendable": False,
                })
                continue
            started = time.perf_counter()
            try:
                decision = controller.decide(
                    query, snapshot)
                self._validate_decision(
                    query, decision)
                elapsed_ms = (
                    time.perf_counter() - started
                ) * 1000.0
                packet_conserved = (
                    decision.packet_schedule.conserved
                    if decision.packet_schedule is not None
                    else True)
                health = (
                    decision.health
                    if (elapsed_ms <=
                        self.shadow_budget.per_controller_ms
                        and packet_conserved)
                    else "unhealthy")
                shadows.append({
                    "controller_mode": mode,
                    "counterfactual_status":
                        "unknown-counterfactual",
                    "decision": decision.to_dict(),
                    "health": health,
                    "packet_conserved": (
                        packet_conserved),
                    "spendable": False,
                })
                telemetry[mode] = {
                    "latency_ms": elapsed_ms,
                    "latency_budget_ms": (
                        self.shadow_budget.per_controller_ms),
                }
            except Exception as error:
                elapsed_ms = (
                    time.perf_counter() - started
                ) * 1000.0
                shadows.append({
                    "controller_mode": mode,
                    "counterfactual_status":
                        "unknown-counterfactual",
                    "decision": None,
                    "error_type": type(error).__name__,
                    "health": "unhealthy",
                    "packet_conserved": None,
                    "spendable": False,
                })
                telemetry[mode] = {
                    "latency_ms": elapsed_ms,
                    "latency_budget_ms": (
                        self.shadow_budget.per_controller_ms),
                }
        snapshot_after = self._snapshot_hash(
            snapshot)
        candidates_after = structural_hash([
            row.to_dict()
            for row in query.grounded_candidates])
        semantic_artifact = {
            "candidate_set_unchanged": (
                candidates_before == candidates_after),
            "canonical_live_decision": (
                canonical.to_dict()),
            "controller_identity":
                "impact-unified-shadow/1.0",
            "live_execution_ledger_writes": 0,
            "query_hash": query.query_hash,
            "shadow_decisions": shadows,
            "shadow_packets_spendable": False,
            "snapshot_unchanged": (
                snapshot_before == snapshot_after),
        }
        artifact_bytes = len(
            canonical_json_bytes(semantic_artifact))
        total_ms = (
            time.perf_counter() - started_total
        ) * 1000.0
        telemetry["artifact_bytes"] = artifact_bytes
        telemetry["artifact_budget_bytes"] = (
            self.shadow_budget.maximum_artifact_bytes)
        telemetry["total_latency_ms"] = total_ms
        telemetry["total_latency_budget_ms"] = (
            self.shadow_budget.total_ms)
        semantic_artifact["controller_telemetry"] = telemetry
        invariants_healthy = all((
            semantic_artifact["candidate_set_unchanged"],
            semantic_artifact["snapshot_unchanged"],
            artifact_bytes <= (
                self.shadow_budget.maximum_artifact_bytes),
            total_ms <= self.shadow_budget.total_ms,
        ))
        semantic_artifact["shadow_invariants_healthy"] = (
            invariants_healthy)
        return ControlDecision(
            ordered_candidate_keys=(
                canonical.ordered_candidate_keys),
            selected_candidate_key=(
                canonical.selected_candidate_key),
            packet_schedule=None,
            controller_mode="unified_shadow",
            artifact=semantic_artifact,
            health=(
                "healthy" if invariants_healthy
                else "unhealthy"),
            fallback_chain=())

    def rank_or_schedule(self, query, mode):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "adapter requires ControlQuery")
        if mode not in CONTROLLER_MODES:
            raise ValueError(
                "unknown impact controller mode")
        snapshot = self._snapshots.get(query.query_id)
        if snapshot is None:
            raise ValueError(
                "control query is not owned by this adapter")
        if mode == "unified_shadow":
            decision = self._shadow_decision(
                query, snapshot)
            self._validate_decision(
                query, decision)
            return decision
        controller = self.controllers.get(mode)
        if controller is None:
            canonical = self.controllers[
                "canonical"].decide(query, snapshot)
            return ControlDecision(
                ordered_candidate_keys=(
                    canonical.ordered_candidate_keys),
                selected_candidate_key=(
                    canonical.selected_candidate_key),
                packet_schedule=None,
                controller_mode="canonical",
                artifact={
                    "fallback_reason":
                        "requested-controller-unavailable",
                    "query_hash": query.query_hash,
                    "requested_mode": mode,
                },
                health="fallback",
                fallback_chain=(mode, "canonical"))
        try:
            decision = controller.decide(
                query, snapshot)
            self._validate_decision(query, decision)
            return decision
        except Exception as error:
            if mode == "canonical":
                raise
            canonical = self.controllers[
                "canonical"].decide(query, snapshot)
            return ControlDecision(
                ordered_candidate_keys=(
                    canonical.ordered_candidate_keys),
                selected_candidate_key=(
                    canonical.selected_candidate_key),
                packet_schedule=None,
                controller_mode="canonical",
                artifact={
                    "fallback_reason":
                        "controller-error",
                    "requested_mode": mode,
                    "error_type": type(error).__name__,
                    "query_hash": query.query_hash,
                },
                health="fallback",
                fallback_chain=(mode, "canonical"))

    def record_outcome(
            self, decision, before, after,
            execution_result):
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "outcome requires ControlDecision")
        execution_result = dict(
            execution_result or {})
        executed_key = execution_result.get(
            "executed_candidate_key")
        selected_executed = (
            executed_key is not None
            and executed_key
            == decision.selected_candidate_key)
        effect = execution_result.get(
            "effect_observed")
        if effect is not None:
            effect = bool(effect)
        record = ControlOutcomeRecord(
            decision_hash=decision.decision_hash,
            controller_mode=decision.controller_mode,
            selected_candidate_key=(
                decision.selected_candidate_key),
            executed_candidate_key=executed_key,
            effect_observed=(
                effect if selected_executed else None),
            counterfactual_status=(
                "observed-selected-execution"
                if selected_executed
                else "unknown-counterfactual"),
            before_snapshot_id=getattr(
                before, "snapshot_id", None),
            after_snapshot_id=getattr(
                after, "snapshot_id", None),
            execution_result_digest=structural_hash(
                execution_result))
        self._outcomes.append(record)
        return record

    @property
    def outcome_records(self):
        return tuple(self._outcomes)
