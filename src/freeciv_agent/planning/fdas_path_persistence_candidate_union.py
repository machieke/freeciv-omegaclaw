"""Membership-only FDAS path persistence over corrected-probe readouts."""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..flow_control import SignalUse, SignalUseLedger
from ..pressure.induction import InductionFeatureQuery
from ..pressure.scalar_baseline import ScalarBaselineConfig
from .fdas import ShadowOperationCandidate
from .fdas_probe_candidate_reachability import (
    FdasProbeCandidateUnion,
)


PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY = (
    "fdas-path-persistence-candidate-union/1.0")


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


def _unit_interval(value, name):
    value = _finite(value, name)
    if not 0.0 <= value <= 1.0:
        raise ValueError("{} must be in [0,1]".format(name))
    return value


def fdas_candidate_corridor_id(candidate, query, snapshot):
    """Return a stable route identity without retaining stale groundings."""
    if not isinstance(candidate, ShadowOperationCandidate):
        raise TypeError("FDAS corridor identity requires shadow candidate")
    if not isinstance(query, InductionFeatureQuery):
        raise TypeError("FDAS corridor identity requires feature query")
    context = dict(query.context)
    actor_id = candidate.action.get(
        "actor_id", candidate.action.get("unit_id"))
    action_type = candidate.action.get("action_type")
    if actor_id is None or not isinstance(action_type, str) or not action_type:
        raise ValueError("FDAS corridor candidate grounding is incomplete")
    topology = {
        "height": int(snapshot.map_height),
        "topology_id": snapshot.map_topology_id,
        "width": int(snapshot.map_width),
        "wrap_x": snapshot.map_wrap_x,
        "wrap_y": snapshot.map_wrap_y,
    }
    material = {
        "action_type": action_type,
        "actor_id": str(actor_id),
        "lifecycle_state": context.get("turn_phase_band", "unknown"),
        "operation_type": candidate.operation.operation_type,
        "ruleset_digest": candidate.operation.ruleset_digest,
        "target_ref": candidate.operation.target_ref,
        "topology": topology,
    }
    return "fdas-path-corridor:" + structural_hash(material)[:32]


def _signal_ledger():
    return SignalUseLedger((
        SignalUse(
            "corrected_bridge_overlap", "path_persistence",
            "instantaneous_membership_signal", False, False),
        SignalUse(
            "smoothed_corridor_reachability", "candidate_union",
            "membership_only", False, False),
        SignalUse(
            "raw_route_momentum", "candidate_union",
            "bounded_membership_only", False, False),
        SignalUse(
            "corridor_dwell_state", "candidate_union",
            "membership_only", False, False),
        SignalUse(
            "typed_advantage", "operation_scoring",
            "add_pre_cost_value_once", True, False),
        SignalUse(
            "operation_cost", "operation_scoring",
            "subtract_once", True, False),
        SignalUse(
            "distributional_risk", "operation_scoring",
            "subtract_scheduler_penalty_once", True, False),
    ))


@dataclass(frozen=True)
class FdasPathPersistenceRouteState:
    route_id: str
    smoothed_reachability: float

    def __post_init__(self):
        if not isinstance(self.route_id, str) or not self.route_id:
            raise ValueError("path persistence route ID is required")
        object.__setattr__(
            self, "smoothed_reachability",
            _unit_interval(
                self.smoothed_reachability,
                "smoothed corridor reachability"))

    def to_dict(self):
        return {
            "route_id": self.route_id,
            "smoothed_reachability": self.smoothed_reachability,
        }


@dataclass(frozen=True)
class FdasPathPersistenceReadout:
    operation_id: str
    operation_type: str
    route_id: str
    baseline_rank: int
    instantaneous_reachability: float
    smoothed_reachability: float
    route_momentum: float
    dwell_bonus: float
    persistence_score: float
    probe_member: bool
    persistence_selected: bool

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.operation_type, "operation type"),
                (self.route_id, "route ID")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "path persistence {} is required".format(name))
        if (isinstance(self.baseline_rank, bool)
                or not isinstance(self.baseline_rank, int)
                or self.baseline_rank < 1):
            raise ValueError("path persistence baseline rank is invalid")
        for name in (
                "instantaneous_reachability", "smoothed_reachability"):
            object.__setattr__(
                self, name,
                _unit_interval(getattr(self, name), name.replace("_", " ")))
        for name in ("route_momentum", "dwell_bonus", "persistence_score"):
            object.__setattr__(
                self, name, _finite(getattr(self, name), name.replace("_", " ")))
        if self.dwell_bonus < 0.0:
            raise ValueError("path persistence dwell bonus is negative")
        expected = (
            self.smoothed_reachability
            + self.route_momentum + self.dwell_bonus)
        if abs(self.persistence_score - expected) > 1e-12:
            raise ValueError("path persistence score composition differs")
        for name in ("probe_member", "persistence_selected"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError("path persistence membership must be boolean")

    def to_dict(self):
        return {
            "baseline_rank": self.baseline_rank,
            "dwell_bonus": self.dwell_bonus,
            "instantaneous_reachability": self.instantaneous_reachability,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "persistence_score": self.persistence_score,
            "persistence_selected": self.persistence_selected,
            "probe_member": self.probe_member,
            "route_id": self.route_id,
            "route_momentum": self.route_momentum,
            "smoothed_reachability": self.smoothed_reachability,
        }


@dataclass(frozen=True)
class FdasPathPersistenceMember:
    operation_id: str
    reasons: tuple

    def __post_init__(self):
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("path persistence member requires operation ID")
        reasons = tuple(sorted(str(value) for value in self.reasons))
        if (not reasons or any(not value for value in reasons)
                or len(reasons) != len(set(reasons))
                or set(reasons) - {
                    "calibrated-transition-recall",
                    "path-persistence-recall",
                    "probe-informed-reachability",
                    "scalar-top-k",
                    "scalar-winner",
                }):
            raise ValueError("path persistence member reasons are invalid")
        object.__setattr__(self, "reasons", reasons)

    def to_dict(self):
        return {
            "operation_id": self.operation_id,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class FdasPathPersistenceCandidateUnion:
    snapshot_id: str
    revision_id: str
    turn: int
    probe_union_result_hash: str
    baseline_selected_operation_id: str
    base_probe_operation_ids: tuple
    config: ScalarBaselineConfig
    maximum_reachability_regret: float
    state_before_hash: str
    state_after_hash: str
    expired_route_ids: tuple
    members: tuple
    readouts: tuple
    persistence_selected_operation_id: object
    persistence_selected_route_id: object
    persistence_added_operation_ids: tuple
    retained_by_smoothing: bool
    retained_by_dwell: bool
    retained_by_hysteresis: bool
    regret_rejected: bool
    reachability_regret: float
    switch_cause: str
    fallback_required: bool
    fallback_reason: object
    signal_ledger: SignalUseLedger
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.probe_union_result_hash, "probe union hash"),
                (self.baseline_selected_operation_id, "baseline selection"),
                (self.state_before_hash, "state-before hash"),
                (self.state_after_hash, "state-after hash"),
                (self.switch_cause, "switch cause"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("path persistence {} is required".format(name))
        if isinstance(self.turn, bool) or not isinstance(self.turn, int):
            raise ValueError("path persistence turn is invalid")
        if not isinstance(self.config, ScalarBaselineConfig):
            raise TypeError("path persistence requires typed config")
        regret_bound = _finite(
            self.maximum_reachability_regret,
            "maximum reachability regret")
        regret = _finite(self.reachability_regret, "reachability regret")
        if regret_bound < 0.0 or regret < 0.0:
            raise ValueError("path persistence regret is negative")
        object.__setattr__(self, "maximum_reachability_regret", regret_bound)
        object.__setattr__(self, "reachability_regret", regret)
        for name in (
                "retained_by_smoothing", "retained_by_dwell",
                "retained_by_hysteresis",
                "regret_rejected", "fallback_required"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError("path persistence state must be boolean")
        if (self.fallback_required != (self.fallback_reason is not None)
                or sum((
                    self.retained_by_smoothing,
                    self.retained_by_dwell,
                    self.retained_by_hysteresis)) > 1):
            raise ValueError("path persistence fallback or retention differs")
        if ((self.persistence_selected_operation_id is None)
                != (self.persistence_selected_route_id is None)):
            raise ValueError("path persistence selection identity differs")
        if not isinstance(self.signal_ledger, SignalUseLedger):
            raise TypeError("path persistence requires signal ledger")
        protected = {
            "corrected_bridge_overlap", "smoothed_corridor_reachability",
            "raw_route_momentum", "corridor_dwell_state",
        }
        if any(value.used_in_final_score for value in self.signal_ledger.uses
               if value.signal_name in protected):
            raise ValueError("path persistence signal gained score authority")
        if (not self.members or any(
                not isinstance(value, FdasPathPersistenceMember)
                for value in self.members)
                or not self.readouts or any(
                    not isinstance(value, FdasPathPersistenceReadout)
                    for value in self.readouts)):
            raise TypeError("path persistence union collections are invalid")
        member_ids = tuple(value.operation_id for value in self.members)
        readout_ids = tuple(value.operation_id for value in self.readouts)
        base_ids = tuple(self.base_probe_operation_ids)
        additions = tuple(self.persistence_added_operation_ids)
        if any(len(values) != len(set(values)) for values in (
                member_ids, readout_ids, base_ids, additions)):
            raise ValueError("path persistence IDs must be unique")
        if (not base_ids or set(base_ids) - set(member_ids)
                or set(member_ids) - set(readout_ids)
                or set(additions) - set(member_ids)
                or set(additions).intersection(base_ids)
                or len(additions) > 1
                or len(member_ids) > len(base_ids) + 1
                or self.baseline_selected_operation_id != base_ids[0]):
            raise ValueError("path persistence membership differs")
        readout_by_id = dict((value.operation_id, value)
                             for value in self.readouts)
        member_by_id = dict((value.operation_id, value)
                            for value in self.members)
        if (tuple(sorted(readout_ids,
                         key=lambda value: readout_by_id[value].baseline_rank))
                != readout_ids
                or tuple(sorted(member_ids,
                                key=lambda value:
                                readout_by_id[value].baseline_rank))
                != member_ids):
            raise ValueError("path persistence scalar ordering differs")
        selected_id = self.persistence_selected_operation_id
        if selected_id is not None and (
                selected_id not in member_by_id
                or not readout_by_id[selected_id].persistence_selected
                or "path-persistence-recall" not in
                member_by_id[selected_id].reasons):
            raise ValueError("path persistence selected member differs")
        if any(value.persistence_selected != (
                value.operation_id == selected_id) for value in self.readouts):
            raise ValueError("path persistence readout selection differs")
        expected_additions = (
            () if selected_id is None or selected_id in base_ids
            else (selected_id,))
        if additions != expected_additions:
            raise ValueError("path persistence addition differs")
        if self.fallback_required and (selected_id is not None or additions):
            raise ValueError("path persistence fallback retained selection")
        if self.regret_rejected and regret <= regret_bound:
            raise ValueError("path persistence regret rejection is invalid")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("path persistence result hash differs")

    @property
    def operation_ids(self):
        return tuple(value.operation_id for value in self.members)

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "base_probe_operation_ids": list(self.base_probe_operation_ids),
            "baseline_selected_operation_id": (
                self.baseline_selected_operation_id),
            "capacity_solver_enabled": False,
            "config": self.config.to_dict(),
            "expired_route_ids": list(self.expired_route_ids),
            "fallback_reason": self.fallback_reason,
            "fallback_required": self.fallback_required,
            "flow_advection_enabled": False,
            "identity": PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY,
            "maximum_reachability_regret": (
                self.maximum_reachability_regret),
            "members": [value.to_dict() for value in self.members],
            "path_persistence_authority": False,
            "persistence_added_operation_ids": list(
                self.persistence_added_operation_ids),
            "persistence_selected_operation_id": (
                self.persistence_selected_operation_id),
            "persistence_selected_route_id": (
                self.persistence_selected_route_id),
            "policy_authority": False,
            "probe_union_result_hash": self.probe_union_result_hash,
            "reachability_regret": self.reachability_regret,
            "readout_authority": False,
            "readouts": [value.to_dict() for value in self.readouts],
            "regret_rejected": self.regret_rejected,
            "retained_by_smoothing": self.retained_by_smoothing,
            "retained_by_dwell": self.retained_by_dwell,
            "retained_by_hysteresis": self.retained_by_hysteresis,
            "revision_id": self.revision_id,
            "scalar_final_score_authority": True,
            "signal_ledger": self.signal_ledger.to_dict(),
            "snapshot_id": self.snapshot_id,
            "source_sink_flow_enabled": False,
            "state_after_hash": self.state_after_hash,
            "state_before_hash": self.state_before_hash,
            "switch_cause": self.switch_cause,
            "truth_mutated": False,
            "turn": self.turn,
        }

    def to_dict(self):
        value = self._semantic()
        value["result_hash"] = self.result_hash
        return value


class FdasPathPersistenceCandidateController:
    """Retain one near-tied current corridor in protected membership only."""

    CONTROLLER_IDENTITY = "fdas-membership-path-persistence/1.0"

    def __init__(self, config=None, maximum_reachability_regret=0.05):
        self.config = config or ScalarBaselineConfig(
            diversity_floor=0.0)
        if not isinstance(self.config, ScalarBaselineConfig):
            raise TypeError("path persistence controller requires typed config")
        self.maximum_reachability_regret = _finite(
            maximum_reachability_regret, "maximum reachability regret")
        if self.maximum_reachability_regret < 0.0:
            raise ValueError("maximum reachability regret is negative")
        self.reset()

    def reset(self):
        self._routes = {}
        self._selected_route_id = None
        self._selected_since_turn = None
        self._last_turn = None
        self._last_input_hash = None
        self._last_result = None

    def _state(self):
        semantic = {
            "controller_identity": self.CONTROLLER_IDENTITY,
            "last_turn": self._last_turn,
            "routes": [
                self._routes[value].to_dict()
                for value in sorted(self._routes)],
            "selected_route_id": self._selected_route_id,
            "selected_since_turn": self._selected_since_turn,
        }
        semantic["state_hash"] = structural_hash(semantic)
        return semantic

    def build_union(
            self, probe_union, candidates, feature_queries, snapshot,
            revision_id):
        if not isinstance(probe_union, FdasProbeCandidateUnion):
            raise TypeError("path persistence requires probe union")
        candidates = tuple(candidates)
        if (not candidates or any(
                not isinstance(value, ShadowOperationCandidate)
                for value in candidates)):
            raise TypeError("path persistence requires shadow candidates")
        if not isinstance(feature_queries, dict):
            raise TypeError("path persistence requires feature queries")
        candidate_by_id = dict(
            (value.operation.operation_id, value) for value in candidates)
        probe_readout_by_id = dict(
            (value.operation_id, value) for value in probe_union.readouts)
        if (len(candidate_by_id) != len(candidates)
                or set(candidate_by_id) != set(probe_readout_by_id)
                or set(candidate_by_id) != set(feature_queries)
                or probe_union.snapshot_id != snapshot.snapshot_id
                or probe_union.revision_id != str(revision_id)):
            raise ValueError("path persistence input surface differs")
        input_hash = structural_hash({
            "feature_queries": dict(
                (value, feature_queries[value].to_dict())
                for value in sorted(feature_queries)),
            "probe_union_result_hash": probe_union.result_hash,
            "revision_id": str(revision_id),
        })
        if input_hash == self._last_input_hash and self._last_result is not None:
            return self._last_result
        turn = int(snapshot.turn)
        reset_reason = None
        if self._last_turn is not None and turn < self._last_turn:
            self.reset()
            reset_reason = "turn-regression-reset"
        before = self._state()

        route_by_id = dict(
            (operation_id, fdas_candidate_corridor_id(
                candidate_by_id[operation_id], feature_queries[operation_id],
                snapshot))
            for operation_id in candidate_by_id)
        operations_by_route = {}
        for operation_id, route_id in route_by_id.items():
            operations_by_route.setdefault(route_id, []).append(operation_id)
        current_routes = frozenset(operations_by_route)
        expired = tuple(sorted(set(self._routes) - current_routes))
        self._routes = dict(
            (key, value) for key, value in self._routes.items()
            if key in current_routes)
        previous_selected = self._selected_route_id
        if self._selected_route_id not in current_routes:
            self._selected_route_id = None
            self._selected_since_turn = None

        instantaneous = {}
        representative = {}
        for route_id, operation_ids in operations_by_route.items():
            ordered = sorted(
                operation_ids,
                key=lambda value: (
                    -probe_readout_by_id[value].location_eligibility,
                    probe_readout_by_id[value].baseline_rank,
                    value))
            representative[route_id] = ordered[0]
            instantaneous[route_id] = max(
                probe_readout_by_id[value].location_eligibility
                for value in operation_ids)
        route_scores = {}
        for route_id in sorted(current_routes):
            value = instantaneous[route_id]
            previous = self._routes.get(
                route_id, FdasPathPersistenceRouteState(route_id, value))
            smoothed = (
                self.config.smoothing * value
                + (1.0 - self.config.smoothing)
                * previous.smoothed_reachability)
            momentum = self.config.route_momentum * (
                smoothed - previous.smoothed_reachability)
            dwell = (
                self.config.dwell_bonus
                if route_id == self._selected_route_id else 0.0)
            route_scores[route_id] = (
                smoothed, momentum, dwell, smoothed + momentum + dwell)
            self._routes[route_id] = FdasPathPersistenceRouteState(
                route_id, smoothed)

        fallback_required = bool(
            probe_union.fallback_required
            or not route_scores
            or max(instantaneous.values() or (0.0,)) <= 0.0)
        fallback_reason = (
            "probe-union-fallback" if probe_union.fallback_required else
            "no-current-corridor" if not route_scores else
            "no-positive-reachability" if fallback_required else None)
        retained_by_dwell = False
        retained_by_hysteresis = False
        retained_by_smoothing = False
        regret_rejected = False
        selected_route = None
        switch_cause = reset_reason or "initial-selection"
        reachability_regret = 0.0
        if not fallback_required:
            instantaneous_best = min(
                current_routes,
                key=lambda value: (-instantaneous[value], value))
            selected_route = min(
                current_routes,
                key=lambda value: (-route_scores[value][3], value))
            current = self._selected_route_id
            if current is not None and selected_route != current:
                age = turn - int(self._selected_since_turn)
                if age < self.config.minimum_dwell_steps:
                    selected_route = current
                    retained_by_dwell = True
                    switch_cause = "retained-by-dwell"
                elif (route_scores[selected_route][3]
                      < route_scores[current][3]
                      + self.config.switch_margin):
                    selected_route = current
                    retained_by_hysteresis = True
                    switch_cause = "retained-by-hysteresis"
            reachability_regret = max(
                0.0, instantaneous[instantaneous_best]
                - instantaneous[selected_route])
            if (selected_route != instantaneous_best
                    and reachability_regret
                    > self.maximum_reachability_regret):
                selected_route = instantaneous_best
                retained_by_dwell = False
                retained_by_hysteresis = False
                regret_rejected = True
                switch_cause = "reachability-regret-rejected"
            elif (selected_route != instantaneous_best
                  and not retained_by_dwell
                  and not retained_by_hysteresis):
                retained_by_smoothing = True
                switch_cause = "retained-by-smoothing"
            elif selected_route == previous_selected:
                switch_cause = (
                    switch_cause if retained_by_dwell
                    or retained_by_hysteresis else "corridor-retained")
            elif previous_selected is None:
                switch_cause = (
                    "previous-corridor-expired" if expired else
                    switch_cause)
            else:
                switch_cause = "corridor-switched"
            if selected_route != self._selected_route_id:
                self._selected_route_id = selected_route
                self._selected_since_turn = turn
        else:
            self._selected_route_id = None
            self._selected_since_turn = None
            self._routes = {}
            switch_cause = fallback_reason
        self._last_turn = turn
        selected_operation = (
            representative[selected_route]
            if selected_route is not None else None)

        base_ids = probe_union.operation_ids
        readouts = []
        for probe_readout in probe_union.readouts:
            operation_id = probe_readout.operation_id
            route_id = route_by_id[operation_id]
            smoothed, momentum, dwell, total = route_scores.get(
                route_id, (
                    probe_readout.location_eligibility, 0.0, 0.0,
                    probe_readout.location_eligibility))
            readouts.append(FdasPathPersistenceReadout(
                operation_id=operation_id,
                operation_type=probe_readout.operation_type,
                route_id=route_id,
                baseline_rank=probe_readout.baseline_rank,
                instantaneous_reachability=(
                    probe_readout.location_eligibility),
                smoothed_reachability=smoothed,
                route_momentum=momentum,
                dwell_bonus=dwell,
                persistence_score=total,
                probe_member=operation_id in base_ids,
                persistence_selected=(
                    operation_id == selected_operation)))
        readouts = tuple(sorted(readouts, key=lambda value: value.baseline_rank))
        probe_member_by_id = dict(
            (value.operation_id, value) for value in probe_union.members)
        member_ids = frozenset(base_ids).union(
            () if selected_operation is None else (selected_operation,))
        members = []
        for readout in readouts:
            if readout.operation_id not in member_ids:
                continue
            reasons = set(
                probe_member_by_id[readout.operation_id].reasons
                if readout.operation_id in probe_member_by_id else ())
            if readout.operation_id == selected_operation:
                reasons.add("path-persistence-recall")
            members.append(FdasPathPersistenceMember(
                readout.operation_id, tuple(reasons)))
        members = tuple(members)
        additions = (
            () if selected_operation is None or selected_operation in base_ids
            else (selected_operation,))
        ledger = _signal_ledger()
        after = self._state()
        semantic = {
            "action_selection_changed": False,
            "base_probe_operation_ids": list(base_ids),
            "baseline_selected_operation_id": (
                probe_union.baseline_selected_operation_id),
            "capacity_solver_enabled": False,
            "config": self.config.to_dict(),
            "expired_route_ids": list(expired),
            "fallback_reason": fallback_reason,
            "fallback_required": fallback_required,
            "flow_advection_enabled": False,
            "identity": PATH_PERSISTENCE_CANDIDATE_UNION_IDENTITY,
            "maximum_reachability_regret": (
                self.maximum_reachability_regret),
            "members": [value.to_dict() for value in members],
            "path_persistence_authority": False,
            "persistence_added_operation_ids": list(additions),
            "persistence_selected_operation_id": selected_operation,
            "persistence_selected_route_id": selected_route,
            "policy_authority": False,
            "probe_union_result_hash": probe_union.result_hash,
            "reachability_regret": reachability_regret,
            "readout_authority": False,
            "readouts": [value.to_dict() for value in readouts],
            "regret_rejected": regret_rejected,
            "retained_by_smoothing": retained_by_smoothing,
            "retained_by_dwell": retained_by_dwell,
            "retained_by_hysteresis": retained_by_hysteresis,
            "revision_id": str(revision_id),
            "scalar_final_score_authority": True,
            "signal_ledger": ledger.to_dict(),
            "snapshot_id": snapshot.snapshot_id,
            "source_sink_flow_enabled": False,
            "state_after_hash": after["state_hash"],
            "state_before_hash": before["state_hash"],
            "switch_cause": switch_cause,
            "truth_mutated": False,
            "turn": turn,
        }
        result = FdasPathPersistenceCandidateUnion(
            snapshot_id=snapshot.snapshot_id,
            revision_id=str(revision_id),
            turn=turn,
            probe_union_result_hash=probe_union.result_hash,
            baseline_selected_operation_id=(
                probe_union.baseline_selected_operation_id),
            base_probe_operation_ids=base_ids,
            config=self.config,
            maximum_reachability_regret=(
                self.maximum_reachability_regret),
            state_before_hash=before["state_hash"],
            state_after_hash=after["state_hash"],
            expired_route_ids=expired,
            members=members,
            readouts=readouts,
            persistence_selected_operation_id=selected_operation,
            persistence_selected_route_id=selected_route,
            persistence_added_operation_ids=additions,
            retained_by_smoothing=retained_by_smoothing,
            retained_by_dwell=retained_by_dwell,
            retained_by_hysteresis=retained_by_hysteresis,
            regret_rejected=regret_rejected,
            reachability_regret=reachability_regret,
            switch_cause=switch_cause,
            fallback_required=fallback_required,
            fallback_reason=fallback_reason,
            signal_ledger=ledger,
            result_hash=structural_hash(semantic))
        self._last_input_hash = input_hash
        self._last_result = result
        return result
