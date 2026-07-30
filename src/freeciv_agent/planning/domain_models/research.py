"""Grounded research-selection estimates over explicit ruleset dependencies.

The model uses exactly one propagation representation: the decomposed
dependency graph returned by :class:`DependencyOracle`.  Legacy ``tech_want``
is neither read nor applied here.  Selecting a research target is kept
separate from observing that technology in a later authoritative snapshot.
"""

import math
from dataclasses import dataclass

from ...events.schema import canonical_json_bytes, structural_hash
from ...oracle import CrispStateView, DependencyOracle, Goal
from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from .base import DomainEstimateRequest
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    canonical_model_artifact,
)
from .registry import context_key_for_request, residual_losses


@dataclass(frozen=True)
class ResearchDependencyProfile:
    """Explicit current frontier and transitive prerequisites for one goal."""

    strategic_target_tech: str
    status: str
    missing_prerequisite_techs: tuple
    currently_researchable_frontier: tuple
    chain_depth: int
    proof_hash: str
    propagation_mode: str = "decomposed_ruleset_dependency_graph"
    legacy_tech_want_applied: bool = False

    def to_dict(self):
        return {
            "chain_depth": int(self.chain_depth),
            "currently_researchable_frontier": list(
                self.currently_researchable_frontier),
            "legacy_tech_want_applied": bool(
                self.legacy_tech_want_applied),
            "missing_prerequisite_techs": list(
                self.missing_prerequisite_techs),
            "proof_hash": self.proof_hash,
            "propagation_mode": self.propagation_mode,
            "status": self.status,
            "strategic_target_tech": self.strategic_target_tech,
        }


def research_dependency_profile(
        ruleset_ir, snapshot_id, known_techs,
        strategic_target_tech, player="player"):
    """Query the canonical oracle and expose its current tech frontier."""
    target = str(strategic_target_tech or "")
    if not target:
        raise ValueError("strategic research target is required")
    state = CrispStateView(
        str(snapshot_id),
        known_techs=tuple(known_techs),
        player=str(player))
    oracle = DependencyOracle(ruleset_ir)
    try:
        result = oracle.deps(
            Goal.researchable(str(player), target),
            state)
    finally:
        oracle.close()
    nodes = {
        node["node_id"]: node
        for node in result.proof.get("nodes", ())
    }
    frontier = set()
    for row in result.frontier:
        if row.get("blocker_type") != "missing-tech":
            continue
        node = nodes.get(row.get("node_id"), {})
        atom = node.get("atom", {})
        if atom.get("predicate") != "has-tech":
            continue
        arguments = atom.get("args", ())
        if arguments:
            frontier.add(str(arguments[-1]))
    if result.status == "PROVED" and target not in set(known_techs):
        frontier.add(target)
    return ResearchDependencyProfile(
        strategic_target_tech=target,
        status=result.status,
        missing_prerequisite_techs=tuple(
            sorted(result.prerequisite_names)),
        currently_researchable_frontier=tuple(sorted(frontier)),
        chain_depth=int(result.chain_depth),
        proof_hash=structural_hash(result.proof))


def _positive_integer(value):
    return bool(
        not isinstance(value, bool)
        and isinstance(value, int)
        and value > 0)


def _nonnegative_integer(value):
    return bool(
        not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0)


def _turns_at_constant_rate(cost, progress, rate):
    remaining = max(0, int(cost) - int(progress))
    if remaining == 0:
        return 1
    if rate <= 0:
        return None
    return max(1, int(math.ceil(
        float(remaining) / float(rate))))


class GroundedResearchTransitionModel:
    """Model an advertised target selection without inventing learned tech."""

    model_id = "grounded_research_selection"
    model_version = "1.0"
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(request, DomainEstimateRequest)
            and request.action_type == "tech_research")

    def _abstain(
            self, request, reason_code,
            missing_fields=(), artifact_extra=None):
        artifact = {
            "availability": {
                "research_target_selectable_now": None,
                "technology_known_now": False,
                "requires_completion_observation": True,
            },
            "completion_eta": None,
            "dependency_profile": None,
            "immediate_target_tech": None,
            "legal_action": (
                dict(request.legal_action)
                if isinstance(request.legal_action, dict) else None),
            "missing_fields": list(sorted(set(missing_fields))),
            "reason_code": reason_code,
            "research_switch_cost": None,
            "schema_version": "1.0",
            "supported_subset":
                "advertised-currently-researchable-target-selection",
            "unknown_mass": 1.0,
        }
        artifact.update(artifact_extra or {})
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=request.stable_operation_id,
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id, self.model_version),
                calibration_group="research:unsupported",
                residual_goal_losses=residual_losses(request)),
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.ABSTAIN,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=(
                "server-advertised-action",
                "missing-grounded-research-input",
            ),
            abstention_reason=reason_code,
            model_artifact_json=canonical_model_artifact(artifact))

    def estimate(self, request):
        if not self.supports(request):
            return self._abstain(
                request, "unsupported-action-type", ("action_type",))
        action = request.legal_action
        snapshot = request.snapshot
        target = action.get("target")
        tech_name = (
            target.get("tech_name")
            if isinstance(target, dict) else None)
        advertised = bool(
            isinstance(action, dict)
            and canonical_json_bytes(action).decode("utf-8")
            in set(getattr(snapshot, "legal_action_json", ())))
        option = (
            snapshot.research_option(tech_name)
            if (
                isinstance(tech_name, str)
                and callable(getattr(
                    snapshot, "research_option", None)))
            else None)
        research = getattr(snapshot, "research", None)
        projection = getattr(request.candidate, "projection", None) or {}
        strategic_target = str(
            projection.get("strategic_target_tech", tech_name or ""))
        missing = []
        if not advertised:
            missing.append("advertised_legal_action")
        if not isinstance(tech_name, str) or not tech_name:
            missing.append("target.tech_name")
        if option is None:
            missing.append("advertised_research_option")
        elif not _positive_integer(option.tech_cost):
            missing.append("research_option.tech_cost")
        if research is None or research.available is not True:
            missing.append("authoritative_research_state")
        else:
            if not _nonnegative_integer(research.beakers_per_turn):
                missing.append("research.beakers_per_turn")
            if not isinstance(research.known_techs, tuple):
                missing.append("research.known_techs")
        if not strategic_target:
            missing.append("strategic_target_tech")
        if missing:
            return self._abstain(
                request, "research-input-missing", tuple(missing),
                artifact_extra={
                    "availability": {
                        "research_target_selectable_now": advertised,
                        "technology_known_now": False,
                        "requires_completion_observation": True,
                    },
                    "immediate_target_tech": tech_name,
                })
        if tech_name in set(research.known_techs):
            return self._abstain(
                request, "research-target-already-known",
                artifact_extra={
                    "immediate_target_tech": tech_name,
                })

        dependency = research_dependency_profile(
            request.ruleset_ir,
            snapshot.snapshot_id,
            research.known_techs,
            strategic_target,
            player="player")
        if dependency.status not in ("PROVED", "BLOCKED"):
            return self._abstain(
                request, "strategic-research-target-unreachable",
                artifact_extra={
                    "dependency_profile": dependency.to_dict(),
                    "immediate_target_tech": tech_name,
                })
        if tech_name not in set(
                dependency.currently_researchable_frontier):
            return self._abstain(
                request,
                "immediate-target-not-on-current-dependency-frontier",
                artifact_extra={
                    "dependency_profile": dependency.to_dict(),
                    "immediate_target_tech": tech_name,
                })

        current_turn = int(snapshot.turn)
        current_target = research.target_name
        same_target = bool(current_target == tech_name)
        rate = int(research.beakers_per_turn)
        if same_target:
            if (
                    not _positive_integer(research.cost)
                    or not _nonnegative_integer(research.progress)
            ):
                return self._abstain(
                    request, "current-research-progress-missing",
                    ("research.cost", "research.progress"),
                    artifact_extra={
                        "dependency_profile": dependency.to_dict(),
                        "immediate_target_tech": tech_name,
                    })
            target_cost = int(research.cost)
            progress_lower = int(research.progress)
            progress_upper = progress_lower
            earliest_eta = _turns_at_constant_rate(
                target_cost, progress_upper, rate)
            latest_eta = earliest_eta
            switch_cost = {
                "current_progress_at_risk": 0,
                "history_fields_available": True,
                "missing_history_fields": [],
                "reason": "target-already-current",
                "starting_progress_lower": progress_lower,
                "starting_progress_upper": progress_upper,
                "status": "none",
            }
            eta_status = (
                "current-target-constant-rate"
                if latest_eta is not None
                else "stalled-current-output")
        else:
            target_cost = int(option.tech_cost)
            progress_lower = 0
            progress_upper = target_cost
            earliest_eta = 1
            latest_eta = _turns_at_constant_rate(
                target_cost, 0, rate)
            switch_cost = {
                "current_progress_at_risk": (
                    int(research.progress)
                    if _nonnegative_integer(research.progress)
                    else None),
                "history_fields_available": False,
                "missing_history_fields": [
                    "bulbs_researched_saved_for_target",
                    "bulbs_researching_saved",
                    "free_bulbs",
                    "researching_saved",
                ],
                "reason":
                    "freeciv-research-switch-history-not-in-snapshot-v1",
                "starting_progress_lower": progress_lower,
                "starting_progress_upper": progress_upper,
                "status": "unresolved",
            }
            eta_status = (
                "switch-interval-constant-rate"
                if latest_eta is not None
                else "switch-latest-stalled-current-output")

        earliest_turn = (
            current_turn + earliest_eta
            if earliest_eta is not None else None)
        latest_turn = (
            current_turn + latest_eta
            if latest_eta is not None else None)
        horizon = int(request.horizon_turn)
        completion_eta = {
            "assumptions": [
                "current-net-beaker-rate-remains-constant",
                "no-free-tech-or-research-grant",
                "server-research-completion-order",
            ],
            "earliest_completion_turn": earliest_turn,
            "earliest_turns": earliest_eta,
            "guaranteed_by_request_horizon": bool(
                latest_turn is not None
                and latest_turn <= horizon),
            "latest_completion_turn": latest_turn,
            "latest_turns": latest_eta,
            "possible_by_request_horizon": bool(
                earliest_turn is not None
                and earliest_turn <= horizon),
            "projection_authority":
                "deterministic-current-rate-bound",
            "request_horizon_turn": horizon,
            "status": eta_status,
        }
        artifact = {
            "availability": {
                "research_target_selectable_now": True,
                "technology_known_now": False,
                "requires_completion_observation": True,
            },
            "completion_eta": completion_eta,
            "current_research": {
                "beakers_per_turn": rate,
                "progress": research.progress,
                "target_name": current_target,
            },
            "dependency_profile": dependency.to_dict(),
            "immediate_target_tech": tech_name,
            "legal_action": dict(action),
            "missing_fields": [],
            "reason_code": None,
            "research_switch_cost": switch_cost,
            "schema_version": "1.0",
            "strategic_target_tech": strategic_target,
            "supported_subset":
                "advertised-currently-researchable-target-selection",
            "target_cost": {
                "authoritative_advertised_cost": int(option.tech_cost),
                "effective_projection_cost": target_cost,
            },
            "technology_completion_created": False,
            "unknown_mass": 0.0,
        }
        outcome = PredictedOutcome(
            outcome_id="{}:research-selected".format(
                request.stable_operation_id),
            probability=1.0,
            next_truth_summaries=(),
            # Selection does not itself satisfy any prerequisite or strategic
            # objective. Completion is observed in a later snapshot.
            next_goal_features=tuple(request.goal_losses),
            resource_delta=(
                ("research_slot:player:current_target", -1.0),),
            completion_turn=float(current_turn),
            adverse_loss=0.0,
            provenance=(
                "server-advertised-action",
                "authoritative-research-option-cost",
                "compiled-ruleset-dependency-proof",
                "research-selection-not-tech-completion",
            ))
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=request.stable_operation_id,
                outcomes=(outcome,),
                residual_probability=0.0,
                model_id="{}/{}".format(
                    self.model_id, self.model_version),
                calibration_group="research:{}:{}".format(
                    "immediate"
                    if strategic_target == tech_name
                    else "dependency",
                    "retain" if same_target else "switch"),
                residual_goal_losses=residual_losses(request)),
            context_key=context_key_for_request(request),
            authority=EstimateAuthority.DETERMINISTIC_DERIVED,
            confidence=1.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=self.model_version,
            provenance=(
                "server-advertised-action",
                "authoritative-research-option",
                "canonical-dependency-oracle",
                "decomposed-ruleset-dependency-graph",
            ),
            model_artifact_json=canonical_model_artifact(artifact))
