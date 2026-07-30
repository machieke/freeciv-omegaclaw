"""Grounded research selection, dependency, and switch-bound tests."""

import json
import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import canonical_json_bytes  # noqa: E402
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedResearchTransitionModel,
    research_dependency_profile,
)
from freeciv_agent.rulesets.ir import Requirement, Rule  # noqa: E402
from freeciv_agent.state import ResearchOptionState, ResearchState  # noqa: E402


def _requirement(name):
    return Requirement(
        "Tech", name, "Player", True,
        "symbolic", "has-tech",
        ("$player", name),
        {
            "file": "synthetic/techs.ruleset",
            "field": "reqs",
            "line": 1,
            "section": "advance_{}".format(
                name.lower()),
        })


def _rule(name, requirements=()):
    return Rule(
        "synthetic:tech:{}".format(name),
        "tech", name, name,
        "researchable", ("$player", name),
        tuple(_requirement(row) for row in requirements),
        tuple(), {"cost": {"value": 20}}, False,
        {
            "file": "synthetic/techs.ruleset",
            "field": "name",
            "line": 1,
            "section": "advance_{}".format(
                name.lower()),
        })


def _ruleset():
    return SimpleNamespace(rules=(
        _rule("Applied", ("Foundation",)),
        _rule("Foundation"),
        _rule("Unrelated"),
    ))


def _action(tech="Foundation"):
    return {
        "action_type": "tech_research",
        "actor_id": 0,
        "target": {"tech_name": tech},
    }


def _snapshot(
        action=None, current="Foundation",
        progress=4, cost=20, rate=4,
        option_cost=20, known=()):
    action = action or _action()
    option = ResearchOptionState(
        tech_name=action["target"]["tech_name"],
        tech_id=7,
        tech_cost=option_cost,
        action_json=canonical_json_bytes(
            action).decode("utf-8"))
    research = ResearchState(
        known_techs=tuple(sorted(known)),
        target_id=7 if current else None,
        target_name=current,
        progress=progress,
        cost=cost,
        beakers_per_turn=rate,
        available=True)
    return SimpleNamespace(
        player_id=0,
        turn=10,
        snapshot_id="snapshot-research",
        legal_actions_digest="legal-research",
        legal_action_json=(
            canonical_json_bytes(action).decode("utf-8"),),
        research=research,
        research_option=lambda name: (
            option if name == option.tech_name else None))


def _request(
        snapshot, action=None,
        strategic="Applied", horizon=30):
    action = action or _action()
    return DomainEstimateRequest(
        request_id="r" * 64,
        snapshot=snapshot,
        ruleset_ir=_ruleset(),
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category="research_strategy",
            utility=5.0,
            rationale="grounded research test",
            projection={
                "strategic_target_tech": strategic,
            }),
        goal_losses=(("pf-impact:science", 3.0),),
        operation_context=None,
        validity=EstimateValidity(
            "snapshot-research",
            "legal-research",
            "ruleset", 10, 10),
        horizon_turn=horizon)


def test_dependency_profile_exposes_only_current_research_frontier():
    profile = research_dependency_profile(
        _ruleset(), "snapshot", (),
        "Applied")

    assert profile.status == "BLOCKED"
    assert profile.missing_prerequisite_techs == (
        "Foundation",)
    assert profile.currently_researchable_frontier == (
        "Foundation",)
    assert profile.propagation_mode == (
        "decomposed_ruleset_dependency_graph")
    assert not profile.legacy_tech_want_applied


def test_current_dependency_selection_has_exact_eta_but_no_tech_completion():
    action = _action("Foundation")
    estimate = GroundedResearchTransitionModel().estimate(
        _request(_snapshot(action), action))
    artifact = estimate.to_dict()["model_artifact"]

    assert estimate.authority == (
        EstimateAuthority.DETERMINISTIC_DERIVED)
    assert estimate.transition.residual_probability == 0.0
    assert artifact["completion_eta"]["earliest_turns"] == 4
    assert artifact["completion_eta"]["latest_turns"] == 4
    assert artifact["research_switch_cost"]["status"] == "none"
    assert artifact["technology_completion_created"] is False
    assert artifact["availability"]["technology_known_now"] is False
    assert estimate.transition.outcomes[0].next_goal_features == (
        ("pf-impact:science", 3.0),)


def test_switch_cost_is_explicitly_unresolved_and_eta_is_bounded():
    action = _action("Foundation")
    snapshot = _snapshot(
        action, current="Unrelated",
        progress=8, cost=30, rate=5,
        option_cost=20)
    estimate = GroundedResearchTransitionModel().estimate(
        _request(snapshot, action))
    artifact = json.loads(
        estimate.model_artifact_json)

    assert estimate.authority == (
        EstimateAuthority.DETERMINISTIC_DERIVED)
    assert artifact["completion_eta"]["earliest_turns"] == 1
    assert artifact["completion_eta"]["latest_turns"] == 4
    assert artifact["research_switch_cost"][
        "current_progress_at_risk"] == 8
    assert artifact["research_switch_cost"][
        "history_fields_available"] is False
    assert artifact["research_switch_cost"]["status"] == "unresolved"
    assert (
        "bulbs_researching_saved"
        in artifact["research_switch_cost"][
            "missing_history_fields"])


def test_action_off_strategic_frontier_abstains_decision_safely():
    action = _action("Unrelated")
    estimate = GroundedResearchTransitionModel().estimate(
        _request(
            _snapshot(
                action, current="Unrelated",
                progress=0, cost=20),
            action,
            strategic="Applied"))

    assert estimate.authority == EstimateAuthority.ABSTAIN
    assert estimate.abstention_reason == (
        "immediate-target-not-on-current-dependency-frontier")
    assert estimate.transition.residual_probability == 1.0


def test_research_estimate_is_byte_deterministic_and_never_reads_tech_want():
    action = _action("Foundation")
    request = _request(_snapshot(action), action)
    model = GroundedResearchTransitionModel()
    first = model.estimate(request).to_dict()
    second = model.estimate(request).to_dict()

    assert first == second
    dependency = first["model_artifact"][
        "dependency_profile"]
    assert dependency["legacy_tech_want_applied"] is False
    assert dependency["propagation_mode"] == (
        "decomposed_ruleset_dependency_graph")
