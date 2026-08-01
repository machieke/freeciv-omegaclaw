import copy
import json
import os
import sys
import tempfile

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    DecisionEpisodeStore,
    FdasCityDefenseOperationAdapter,
    FdasDefenseEpisodeRecorder,
    OperationStore,
)
from freeciv_agent.pressure import (  # noqa: E402
    ClaimHardness,
    GameResourceKind,
    ResourceClaim,
    ResourceRef,
    TurnWindow,
)
from freeciv_agent.state import ProxyStateDTO  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomNamespace,
    AuthorityClass,
    DependentAtomSpaceStore,
    EpisodeProjector,
    episode_predicate_registry,
)


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _payload(turn=12, unit_tile=82, unit_x=2, legal_target_x=3):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    target = copy.deepcopy(payload["cities"]["3"])
    target.update({"id": 4, "name": "Antium", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = target
    payload["turn"] = turn
    payload["units"]["7"].update({
        "tile": unit_tile, "x": unit_x, "y": 2})
    payload["legal_actions"] = [{
        "action_type": "unit_move",
        "actor_id": 7,
        "is_valid": True,
        "target": {"direction": "e", "x": legal_target_x, "y": 2},
    }]
    return payload


def _snapshot(payload, seq):
    return ProxyStateDTO.parse("fdas-episodes", seq, payload).to_snapshot()


def _move(snapshot):
    return next(json.loads(value) for value in snapshot.legal_action_json)


def _operation(action, operation_id="episode-route"):
    return {
        "actor_id": 7,
        "arrival_turn": 14,
        "city_id": 4,
        "claims": [ResourceClaim(
            ResourceRef(
                GameResourceKind.ACTOR, "unit:7", "whole_actor",
                "player:2"),
            1, TurnWindow(12, 13), ClaimHardness.HARD_CURRENT, True,
            operation_id, "current-defence-action").to_dict()],
        "deadline_turn": 15,
        "next_action": action,
        "operation_id": operation_id,
        "operation_type": "move_defender_to_city",
        "provenance": ["native-server-route-eta"],
        "requirement_id": "defense:city:4:deadline:15",
        "support_reason": None,
    }


def _begin_episode(store=None, operation_id="episode-route"):
    before = _snapshot(_payload(), 490)
    operations = OperationStore("fdas-episode-operations")
    adapter = FdasCityDefenseOperationAdapter(operations, "ruleset-proof")
    update = adapter.reconcile(
        before, (_operation(_move(before), operation_id),))[0]
    record = operations.get(update.operation_id)
    episode_store = store or DecisionEpisodeStore("fdas-episode-proof")
    recorder = FdasDefenseEpisodeRecorder(episode_store)
    episode = recorder.begin(
        adapter.binding(update.operation_id), record, before,
        "fdas-revision-before", "validation-proof",
        execution_event_id="execution-accepted",
        source_atom_ids=("atom-garrison-deficit",),
        source_support_ids=("support-garrison-deficit",),
        grounding_result_ids=("grounding-route",),
        resource_claim_ids=("claim-unit-7",),
    )
    return recorder, episode_store, episode


def test_acceptance_effect_and_goal_relief_are_separate_idempotent_states():
    recorder, store, episode = _begin_episode()

    assert episode.outcome_status == "accepted-by-server"
    assert episode.after_revision_id is None
    assert not episode.attributed_effects
    assert not episode.realized_goal_relief

    intermediate = _snapshot(_payload(
        turn=13, unit_tile=83, unit_x=3, legal_target_x=4), 491)
    moved = recorder.observe(
        episode.episode_id, intermediate, "fdas-revision-intermediate")

    assert moved.outcome_status == "immediate-effect-observed"
    assert moved.attributed_effects == ({
        "effect": "actor-tile-changed", "from": 82, "to": 83},)
    assert not moved.realized_goal_relief

    final = _snapshot(_payload(
        turn=14, unit_tile=84, unit_x=4, legal_target_x=4), 492)
    relieved = recorder.observe(
        episode.episode_id, final, "fdas-revision-final")
    replay = recorder.observe(
        episode.episode_id, final, "fdas-revision-final")
    with pytest.raises(ValueError, match="another revision"):
        recorder.observe(
            episode.episode_id, final, "fdas-revision-not-the-final")

    assert relieved.outcome_status == "goal-relief-observed"
    assert relieved.realized_goal_relief == (("pf-impact:survival", 1.0),)
    assert relieved.observed_delta["actor_tile_after"] == 84
    assert replay is relieved
    assert len(store.episodes()) == 1


def test_no_update_is_pending_until_window_closes_then_no_effect():
    recorder, _store, episode = _begin_episode(
        operation_id="episode-no-effect")
    unchanged = _snapshot(_payload(turn=13), 493)

    pending = recorder.observe(
        episode.episode_id, unchanged, "fdas-revision-pending")
    assert recorder.store.pending_for_operation(
        episode.operation_id) == (pending,)
    no_effect = recorder.observe_operation(
        episode.operation_id, unchanged, "fdas-revision-window-closed",
        observation_window_closed=True)

    assert pending.outcome_status == "delayed-effect-pending"
    assert no_effect.outcome_status == "no-effect-observed"
    assert not no_effect.attributed_effects
    assert not no_effect.realized_goal_relief


def test_immediate_effect_without_relief_closes_as_distinct_terminal_state():
    recorder, store, episode = _begin_episode(
        operation_id="episode-effect-no-relief")
    intermediate = _snapshot(_payload(
        turn=13, unit_tile=83, unit_x=3, legal_target_x=4), 497)
    effect = recorder.observe(
        episode.episode_id, intermediate, "fdas-revision-effect")
    terminal = recorder.observe_operation(
        episode.operation_id, intermediate, "fdas-revision-window-closed",
        observation_window_closed=True)
    replay = recorder.observe(
        episode.episode_id, intermediate, "fdas-revision-window-closed",
        observation_window_closed=True)

    assert effect.outcome_status == "immediate-effect-observed"
    assert terminal.outcome_status == "effect-without-goal-relief"
    assert terminal.attributed_effects
    assert not terminal.realized_goal_relief
    assert replay is terminal
    assert store.pending_for_operation(episode.operation_id) == ()


def test_actor_disappearance_is_unattributable_not_goal_relief():
    recorder, _store, episode = _begin_episode(
        operation_id="episode-disappearance")
    payload = _payload(turn=13)
    payload["units"] = {}
    after = _snapshot(payload, 494)

    result = recorder.observe(
        episode.episode_id, after, "fdas-revision-disappearance")

    assert result.outcome_status == "confounded-unattributable"
    assert result.observed_delta["actor_present_after"] is False
    assert not result.realized_goal_relief


def test_episode_store_round_trip_and_corruption_quarantine():
    recorder, expected, episode = _begin_episode(
        operation_id="episode-persistence")
    unchanged = _snapshot(_payload(turn=13), 495)
    recorder.observe(
        episode.episode_id, unchanged, "fdas-revision-persisted",
        observation_window_closed=True)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "episodes.json")
        expected.save(path)
        actual = DecisionEpisodeStore.load(path, "fdas-episode-proof")
        with open(path, "wb") as stream:
            stream.write(b"{not-json\n")
        corrupt = DecisionEpisodeStore.load(path, "fdas-episode-proof")

    assert not actual.quarantined
    assert actual.store_digest == expected.store_digest
    assert actual.get(episode.episode_id).outcome_status == "no-effect-observed"
    assert corrupt.quarantined


def test_episode_projection_is_bounded_structural_and_dependency_backed():
    recorder, store, episode = _begin_episode(
        operation_id="episode-projection")
    final = _snapshot(_payload(
        turn=14, unit_tile=84, unit_x=4, legal_target_x=4), 496)
    recorder.observe(episode.episode_id, final, "fdas-revision-final")

    revision = DependentAtomSpaceStore(
        domain_projector=EpisodeProjector(store)).build(final)
    scopes = tuple(
        value for value in revision.scopes if value.scope_kind == "episode")
    records = tuple(
        value for value in revision.records
        if value.key.namespace == AtomNamespace.EPISODE)
    predicates = {value.key.predicate for value in records}

    assert len(scopes) == 1
    assert scopes[0].maximum_atoms == 500
    assert {
        "episode-action",
        "episode-after-revision",
        "episode-attributed-effect",
        "episode-before-revision",
        "episode-context",
        "episode-execution-event",
        "episode-goal-relief",
        "episode-grounding-result",
        "episode-operation",
        "episode-outcome-status",
        "episode-resource-claim",
        "episode-source-atom",
        "episode-source-support",
        "episode-validation",
    }.issubset(predicates)
    assert all(value.authority == AuthorityClass.CONTROL_MODEL
               for value in records)
    assert all(
        dependency.key.kind == "episode-revision"
        for value in records
        for support in value.supports
        for dependency in support.dependencies)
    relief = next(
        value for value in records
        if value.key.predicate == "episode-goal-relief")
    assert relief.key.arguments[1].entity_id == "pf-impact:survival"


def test_episode_catalog_matches_component_registry():
    with open(os.path.join(REPO, "profile", "fdas_catalog.json"),
              encoding="utf-8") as stream:
        catalog = json.load(stream)
    component = {
        value["name"] for value in catalog["predicates"]
        if (value["namespace"] == "episode"
            and value["status"] == "component-only")}
    scopes = {
        value["kind"]: value["status"] for value in catalog["scopes"]}

    assert component == {
        value for value in episode_predicate_registry().predicates
        if value.startswith("episode-")}
    assert scopes["episode"] == "component-only"
