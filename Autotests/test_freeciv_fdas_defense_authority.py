import copy
import json
import os

import pytest

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.planning import (
    CandidateInstantiation,
    CandidateOperationFactory,
    DecisionEpisodeStore,
    FdasBoundedDefenseAuthority,
    FdasDefenseActionBinding,
    FdasDefenseEpisodeRecorder,
    GoalFactory,
    ImpactCandidate,
    OperationStore,
)
from freeciv_agent.pressure import DependentAtomPressureAdapter
from freeciv_agent.rulesets.compiler import compile_ruleset
from freeciv_agent.state import ProxyStateDTO
from freeciv_agent.state.atomspace import (
    CityEconomyProjector,
    CompositeDomainProjector,
    DependentAtomSpaceStore,
    FdasRuntime,
    FdasShadowEvaluation,
    RevisionQueryContext,
    UnitDefenseProjector,
    ruleset_digest,
)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append("/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for FDAS defense authority")


@pytest.fixture(scope="module")
def ir():
    return compile_ruleset(_root(), "civ2civ3")


def _case(ir, seq=489):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["legal_actions"].append({
        "type": "unit_fortify", "unit_id": 7, "is_valid": True,
    })
    payload["authoritative"]["source_seq"] = seq
    snapshot = ProxyStateDTO.parse(
        "fdas-defense-authority", seq, payload).to_snapshot()
    digest = ruleset_digest(ir)
    store = DependentAtomSpaceStore(
        domain_projector=CompositeDomainProjector((
            CityEconomyProjector(ir, digest),
            UnitDefenseProjector(ir, digest),
        )))
    revision = store.build(snapshot)
    goals = GoalFactory().instantiate(
        revision,
        store.query_current(snapshot.identity.game_id, snapshot.player_id))
    defense_goal = next(
        value for value in goals
        if value.deficit_predicate == "unit-fortification-opportunity")
    candidates = CandidateOperationFactory(ir, digest).instantiate(
        snapshot, (defense_goal,), revision=revision)
    source = next(
        value for value in candidates
        if value.action.get("action_type") == "unit_fortify")
    pressure = DependentAtomPressureAdapter().evaluate(
        revision, (defense_goal,), (source,))
    instantiation = CandidateInstantiation(
        (source,), 0, (), (), structural_hash(source.candidate_hash))
    explanation = FdasRuntime.explain_shadow_decision(
        revision, RevisionQueryContext(revision), (defense_goal,), (source,),
        instantiation, pressure)
    evaluation = FdasShadowEvaluation(
        snapshot.snapshot_id, revision.revision_id, (defense_goal,), (source,),
        instantiation, pressure, None, explanation, (), 0.0)
    legacy = ImpactCandidate(
        source.action, "city_defense", 1.0,
        "legacy-selected exact fortification")
    return snapshot, revision, evaluation, legacy


def test_bounded_defense_authority_passes_exact_fortification_winner(ir):
    snapshot, revision, evaluation, legacy = _case(ir)

    readout = FdasBoundedDefenseAuthority().evaluate(
        snapshot, revision, evaluation, legacy,
        authority_enabled=True, city_defense_enabled=True)

    assert readout.authorized
    assert readout.authority_slice == (
        "fdas-bounded-defense-fortification/1.0")
    assert readout.action_key == legacy.action_key
    assert readout.checks == (
        "domain-authority-gate",
        "legacy-defense-category-gate",
        "revision-current-evaluation",
        "legacy-winner-fdas-fortification-route-binding",
        "bounded-defense-fortification-contract",
        "authority-pressure-readout",
        "resource-and-packet-schedule",
        "exact-fdas-commit-validation",
    )
    assert readout.scheduling["joint_selected_operation_ids"] == [
        readout.operation_id]
    request = readout.scheduling["resource_schedule"]["requests"][0]
    assert request["claims"][0]["resource"] == {
        "kind": "actor",
        "owner_id": "7",
        "scope": "unit:7",
        "subresource": "current-action",
    }
    assert readout.commit_validation[
        "plan_materialization_authorized"] is True
    assert readout.commit_validation["execution_authority"] is False


def test_bounded_defense_authority_fails_closed(ir):
    snapshot, revision, evaluation, legacy = _case(ir)
    authority = FdasBoundedDefenseAuthority()

    disabled = authority.evaluate(
        snapshot, revision, evaluation, legacy,
        authority_enabled=False, city_defense_enabled=False)
    assert disabled.status == "disabled"
    assert disabled.reason == "fdas-city-defense-authority-disabled"

    missing = authority.evaluate(
        snapshot, revision, evaluation, None,
        authority_enabled=True, city_defense_enabled=True)
    assert missing.status == "fallback"
    assert missing.reason == "legacy-selected-candidate-unavailable"

    wrong_category = authority.evaluate(
        snapshot, revision, evaluation,
        ImpactCandidate(
            legacy.action, "unit_movement", 1.0, "not defense"),
        authority_enabled=True, city_defense_enabled=True)
    assert wrong_category.status == "fallback"
    assert wrong_category.reason == "legacy-winner-is-not-city-defense"

    stale = authority.evaluate(
        snapshot, revision,
        FdasShadowEvaluation(
            evaluation.snapshot_id, "stale-revision", evaluation.goals,
            evaluation.candidates, evaluation.candidate_instantiation,
            evaluation.pressure, evaluation.comparison,
            evaluation.decision_explanation, (), 0.0),
        legacy, authority_enabled=True, city_defense_enabled=True)
    assert stale.status == "fallback"
    assert stale.reason == "fdas-evaluation-not-current"

    unsafe_source = copy.deepcopy(evaluation.candidates[0])
    unsafe_source = type(unsafe_source)(
        unsafe_source.operation, unsafe_source.action,
        unsafe_source.action_key, unsafe_source.resource_keys,
        unsafe_source.legal_bound, unsafe_source.authority_eligible,
        unsafe_source.blockers + ("protected-source-garrison",),
        unsafe_source.provenance,
        structural_hash([unsafe_source.candidate_hash, "unsafe"]))
    unsafe_evaluation = FdasShadowEvaluation(
        evaluation.snapshot_id, evaluation.revision_id, evaluation.goals,
        (unsafe_source,), evaluation.candidate_instantiation,
        evaluation.pressure, evaluation.comparison,
        evaluation.decision_explanation, (), 0.0)
    unsafe = authority.evaluate(
        snapshot, revision, unsafe_evaluation, legacy,
        authority_enabled=True, city_defense_enabled=True)
    assert unsafe.status == "fallback"
    assert unsafe.reason == "candidate-has-noncontractual-blockers"


def test_authorized_fortification_episode_separates_acceptance_and_relief(ir):
    snapshot, revision, evaluation, legacy = _case(ir)
    authority = FdasBoundedDefenseAuthority()
    readout = authority.evaluate(
        snapshot, revision, evaluation, legacy,
        authority_enabled=True, city_defense_enabled=True)
    promoted, reason = authority._promote(
        evaluation.candidates[0], snapshot, revision, evaluation.goals)
    assert reason is None
    assert readout.authorized
    assert authority.candidate_from_readout(
        snapshot, revision, evaluation, readout) == promoted

    automatic_store = DecisionEpisodeStore(
        "fdas-defense-authority-automatic-episodes")
    automatic = FdasDefenseEpisodeRecorder(
        automatic_store).begin_authorized(
            promoted, readout, evaluation, snapshot, revision,
            "action-result-automatic")
    assert automatic.operation_id == promoted.operation.operation_id
    assert automatic.source_atom_ids == (
        evaluation.goals[0].deficit_atom_id,)
    assert automatic.grounding_result_ids == (
        evaluation.candidate_instantiation.instantiation_hash,)
    assert automatic.outcome_status == "accepted-by-server"

    operations = OperationStore("fdas-defense-authority-episode-operations")
    record = operations.propose(
        promoted.operation, snapshot.snapshot_id, snapshot.turn)
    binding_material = {
        "action": promoted.action,
        "action_key": promoted.action_key,
        "domain_operation_id": promoted.operation.operation_id,
        "legal_actions_digest": snapshot.legal_actions_digest,
        "legal_bound": True,
        "operation_id": promoted.operation.operation_id,
        "snapshot_id": snapshot.snapshot_id,
    }
    binding = FdasDefenseActionBinding(
        promoted.operation.operation_id,
        promoted.operation.operation_id,
        snapshot.snapshot_id,
        snapshot.legal_actions_digest,
        promoted.action,
        promoted.action_key,
        True,
        structural_hash(binding_material),
    )
    episodes = DecisionEpisodeStore("fdas-defense-authority-episodes")
    recorder = FdasDefenseEpisodeRecorder(episodes)
    goal = evaluation.goals[0]
    source = revision.record(goal.deficit_atom_id)
    episode = recorder.begin(
        binding, record, snapshot, revision.revision_id,
        readout.commit_validation["result_hash"],
        execution_event_id="action-result-accepted",
        source_atom_ids=(goal.deficit_atom_id,),
        source_support_ids=tuple(
            value.support_id for value in source.supports),
        resource_claim_ids=tuple(
            structural_hash(claim)
            for request in readout.scheduling["resource_schedule"]["requests"]
            for claim in request["claims"]),
    )

    assert episode.outcome_status == "accepted-by-server"
    assert not episode.attributed_effects
    assert not episode.realized_goal_relief

    with open(FIXTURE, encoding="utf-8") as stream:
        after_payload = copy.deepcopy(json.load(stream))
    after_payload["units"]["7"]["activity"] = "fortifying"
    after_payload["authoritative"]["source_seq"] = 490
    after = ProxyStateDTO.parse(
        "fdas-defense-authority", 490, after_payload).to_snapshot()
    relieved = recorder.observe(
        episode.episode_id, after, "fdas-revision-after-fortify")

    assert relieved.outcome_status == "goal-relief-observed"
    assert relieved.attributed_effects == ({
        "effect": "actor-fortified", "tile": 82},)
    assert relieved.realized_goal_relief == ((goal.goal.goal_id, 1.0),)
