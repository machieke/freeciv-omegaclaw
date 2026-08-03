import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning import (  # noqa: E402
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
    DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    DURABLE_CITY_COVERAGE_TARGET,
    DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
    DEFENSE_CANDIDATE_CHOICE_SURFACE,
    DecisionEpisode,
    DecisionEpisodeStore,
    EPISODE_SCHEMA_VERSION,
    EpisodeInductionOutcomeLabel,
    EpisodeInductionOutcomeLabelStore,
    EpisodeInductionSpec,
    FdasEpisodeInductionAdapter,
    FdasEpisodeInductionHeldoutGate,
    FdasEpisodeInductionShadow,
    FdasDefenseEpisodeRecorder,
    FdasCandidateChoiceSetRecorder,
    FdasCandidateChoiceSetStore,
    FdasPromotedRuleCandidateImpactShadow,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    ShadowOperationCandidate,
    causal_induction_feature_query,
    combine_episode_stores,
    combine_candidate_choice_stores,
    combine_outcome_label_stores,
    export_candidate_choice_calibration,
    unambiguous_defense_choice_surface_candidates,
)
from freeciv_agent.pressure import (  # noqa: E402
    CostVector,
    GoalEffect,
    InductionLedger,
    InductionPromotionApproval,
    PatternMiner,
    Operation,
    OperationScore,
    PromotedRuleCandidateImpactAnalyzer,
    ReplayValidator,
    load_promoted_rule_shadow_artifacts,
)
from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


def _episode(
        index, status, cohort="train", event_id=None, tile="10",
        feature_schema=None, unit_type="Warrior"):
    terminal = status in (
        "goal-relief-observed", "effect-without-goal-relief",
        "no-effect-observed", "confounded-unattributable")
    relieved = status == "goal-relief-observed"
    context = {
        "era": "ancient",
        "actor_tile_before": str(tile),
        "operation_type": "move_defender_to_city",
        "target_tile": "10",
        "terrain": "land",
    }
    if feature_schema is not None:
        context.update({
            "actor_moves_band": "one",
            "actor_unit_type": unit_type,
            "actor_veteran_band": "none",
            "city_disorder": "false",
            "city_size_band": "2-4",
            "induction_feature_schema": feature_schema,
            "other_own_units_at_target_band": "0",
            "own_units_at_target_band": "1",
        })
    if feature_schema == CAUSAL_INDUCTION_FEATURE_SCHEMA:
        context.update({
            "actor_homecity_relation": "target",
            "city_production_class": "unit",
            "economy_operating_gold_band": "positive",
            "empire_city_count_band": "3+",
            "other_fortified_units_at_target_band": "0",
            "turn_phase_band": "32-63",
            "visible_enemy_count_near_city_band": "1",
            "visible_enemy_proximity_band": "near",
        })
    return DecisionEpisode(
        EPISODE_SCHEMA_VERSION,
        "episode-{}-{}".format(cohort, index),
        "episode-induction",
        0,
        "operation-{}-{}".format(cohort, index),
        '{"action_type":"unit_move","actor_id":7}',
        "before-{}-{}".format(cohort, index),
        "after-{}-{}".format(cohort, index) if terminal else None,
        ("pf-impact:survival",),
        tuple(sorted(context.items())),
        ("atom-defense-route",),
        ("support-{}-{}".format(cohort, index),),
        ("grounding-route",),
        ("prediction-route",),
        ("claim-unit-{}".format(index),),
        "validation-current",
        event_id or "execution-{}-{}".format(cohort, index),
        {} if terminal else None,
        ({"effect": "defender-arrived"},) if relieved else (),
        (("pf-impact:survival", 1.0),) if relieved else (),
        status,
        ("fdas-defense-episode-recorder/1.0",),
    )


def _spec(episode):
    return EpisodeInductionSpec(
        episode.episode_id,
        ("era", "terrain"),
        ("operation_type",),
        (("route-grounded", "grounding-route"),),
    )


def _correlated_population(cohort, inverted=False):
    rows = []
    for index in range(16):
        tile = "10" if index % 2 == 0 else "20"
        relieved = (tile == "10") != inverted
        rows.append(_episode(
            index,
            "goal-relief-observed" if relieved else "no-effect-observed",
            cohort=cohort,
            tile=tile))
    return tuple(rows)


def _delayed_population(cohort, inverted=False):
    episodes = []
    labels = []
    for index in range(16):
        unit_type = "Warrior" if index % 2 == 0 else "Archer"
        outcome = (unit_type == "Warrior") != inverted
        episode = _episode(
            index,
            "goal-relief-observed",
            cohort=cohort,
            feature_schema="defense-episode-features/2.0",
            unit_type=unit_type)
        material = {
            "due_turn": 9,
            "episode_digest": episode.immutable_digest,
            "episode_id": episode.episode_id,
            "game_id": episode.game_id,
            "player_id": episode.player_id,
            "relief_revision_id": episode.after_revision_id,
            "relief_turn": 1,
            "schema_version": 1,
            "target_id": DURABLE_CITY_COVERAGE_TARGET,
        }
        labels.append(EpisodeInductionOutcomeLabel(
            1,
            "outcome-label-" + structural_hash(material)[:24],
            episode.episode_id,
            episode.immutable_digest,
            episode.game_id,
            episode.player_id,
            DURABLE_CITY_COVERAGE_TARGET,
            1,
            9,
            episode.after_revision_id,
            "observed",
            9,
            "assessment-{}-{}".format(cohort, index),
            outcome,
            (("city_owned_and_present", True),
             ("city_id", 4),
             ("own_unit_count_at_city", 1 if outcome else 0)),
            "synthetic-delayed-component-fixture",
            ("assessment-provenance-{}-{}".format(cohort, index),)))
        episodes.append(episode)
    return tuple(episodes), tuple(labels)


def test_only_attributable_terminal_episode_is_encoded_without_authority():
    relieved = _episode(0, "goal-relief-observed")
    no_effect = _episode(1, "no-effect-observed")
    effect_only = _episode(2, "effect-without-goal-relief")
    pending = _episode(3, "delayed-effect-pending")
    confounded = _episode(4, "confounded-unattributable")
    store = DecisionEpisodeStore(
        "fdas-induction", (relieved, no_effect, effect_only, pending,
                           confounded))
    adapter = FdasEpisodeInductionAdapter(store)

    positive = adapter.encode(_spec(relieved))
    negative = adapter.encode(_spec(no_effect))
    transition_without_relief = adapter.encode(_spec(effect_only))
    abstentions = tuple(adapter.encode(_spec(value)) for value in (
        pending, confounded))

    assert positive.accepted and positive.induction_episode.outcome is True
    assert negative.accepted and negative.induction_episode.outcome is False
    assert transition_without_relief.accepted
    assert transition_without_relief.induction_episode.outcome is False
    assert positive.induction_episode.context == (
        ("era", "ancient"), ("terrain", "land"))
    assert positive.induction_episode.features == (
        "context:operation_type=move_defender_to_city", "route-grounded")
    assert positive.truth_mutated is False
    assert positive.policy_authority is False
    assert not any(value.accepted for value in abstentions)
    assert all(value.induction_episode is None for value in abstentions)


def test_shadow_induction_uses_bounded_cross_game_features_when_available():
    episode = _episode(
        0, "goal-relief-observed",
        feature_schema="defense-episode-features/2.0")
    store = DecisionEpisodeStore("fdas-feature-v2", (episode,))
    shadow = FdasEpisodeInductionShadow(
        store, InductionLedger(identity="fdas-feature-v2"))

    encoded = shadow.adapter.encode(shadow._spec(episode))

    assert encoded.accepted is True
    assert encoded.induction_episode.context == (
        ("induction_feature_schema", "defense-episode-features/2.0"),
        ("operation_type", "move_defender_to_city"),
    )
    assert "context:actor_unit_type=Warrior" in (
        encoded.induction_episode.features)
    assert not any(
        "tile" in value for value in encoded.induction_episode.features)


def test_causal_schema_excludes_exact_actor_type_and_uses_lifecycle_features():
    episode = _episode(
        0, "goal-relief-observed",
        feature_schema=CAUSAL_INDUCTION_FEATURE_SCHEMA,
        unit_type="One-off Ruleset Unit")
    shadow = FdasEpisodeInductionShadow(
        DecisionEpisodeStore("fdas-causal-features", (episode,)),
        InductionLedger(identity="fdas-causal-features"))

    encoded = shadow.adapter.encode(shadow._spec(episode))

    assert encoded.accepted is True
    assert encoded.induction_episode.context == (
        ("induction_feature_schema", CAUSAL_INDUCTION_FEATURE_SCHEMA),
        ("operation_type", "move_defender_to_city"),
    )
    assert "context:actor_homecity_relation=target" in (
        encoded.induction_episode.features)
    assert "context:visible_enemy_proximity_band=near" in (
        encoded.induction_episode.features)
    assert not any(
        "actor_unit_type" in value
        for value in encoded.induction_episode.features)


def test_causal_candidate_query_matches_episode_features_without_outcome():
    episode = _episode(
        0, "goal-relief-observed",
        feature_schema=CAUSAL_INDUCTION_FEATURE_SCHEMA)
    store = DecisionEpisodeStore("fdas-candidate-query", (episode,))
    shadow = FdasEpisodeInductionShadow(
        store, InductionLedger(identity="fdas-candidate-query"))
    base = shadow._spec(episode)
    encoded = shadow.adapter.encode(base)
    query = causal_induction_feature_query(
        "candidate-query",
        episode.context_signature,
        base.outcome_target,
        ("candidate-hash", "snapshot-id"))

    assert query.context == encoded.induction_episode.context
    assert query.features == encoded.induction_episode.features
    assert query.provenance_ids == ("candidate-hash", "snapshot-id")
    assert "outcome" not in query.to_dict()


def _candidate_impact_fixture():
    with open(FIXTURE, encoding="utf-8") as stream:
        snapshot = ProxyStateDTO.parse(
            "fdas-candidate-impact", 901, json.load(stream)).to_snapshot()
    operation_type = (
        "fdas-shadow:unit-fortification-opportunity:unit_fortify")
    spec = OperationSpec(
        1, "candidate-fortify", operation_type, ("goal-defense",),
        (OperationParticipant("actor", "unit:7", "unit", True),),
        "city:3",
        (OperationStep(
            "candidate-step", "unit_fortify", "actor", "city:3",
            "candidate-requirements", "candidate-complete", 1),),
        snapshot.turn, snapshot.turn + 1, 0.0,
        ("candidate-impact-test",), "ruleset-test")
    action = {"action_type": "unit_fortify", "actor_id": 7}
    action_key = json.dumps(
        action, sort_keys=True, separators=(",", ":"))
    candidate = ShadowOperationCandidate(
        spec, action, action_key, ("unit:7",), True, False, (),
        ("candidate-impact-test",), "candidate-hash-fortify")
    pressure_operation = Operation(
        spec.operation_id, "candidate-atom", "act",
        CostVector(compute=1.0), causal_kind="causal")
    score = OperationScore(
        pressure_operation, True, None, 1.0, 1.0, 1.0, 0.0,
        (GoalEffect("goal-defense", 1.0, 1.0, 1.0, 1.0),))
    bundle = load_promoted_rule_shadow_artifacts(
        os.path.join(REPO, "docs", "freeciv", "evidence",
                     "fdas-pr29-causal-induction-holdout-engine.json"),
        os.path.join(REPO, "docs", "freeciv", "evidence",
                     "fdas-pr30-promoted-rule-consolidation.json"))
    recorder = FdasDefenseEpisodeRecorder(
        DecisionEpisodeStore("candidate-impact-test"),
        induction_feature_schema=CAUSAL_INDUCTION_FEATURE_SCHEMA)
    evaluator = FdasPromotedRuleCandidateImpactShadow(
        recorder,
        PromotedRuleCandidateImpactAnalyzer(bundle.readout),
        DURABLE_ACTOR_CITY_DEFENSE_TARGET)
    return snapshot, candidate, score, evaluator


def test_live_candidate_impact_is_category_scoped_and_action_preserving():
    snapshot, candidate, score, evaluator = _candidate_impact_fixture()

    evaluated = evaluator.evaluate(
        snapshot, (candidate,), (score,), candidate.operation.operation_id)

    assert evaluated.status == "evaluated"
    assert evaluated.scoped_candidate_count == 1
    assert evaluated.impact.complete_prediction_coverage is True
    assert evaluated.impact.actual_selected_operation_id == (
        candidate.operation.operation_id)
    assert evaluated.global_baseline_selected_operation_id == (
        candidate.operation.operation_id)
    assert evaluated.to_dict()["action_selection_changed"] is False
    assert evaluated.to_dict()["truth_mutated"] is False
    assert evaluated.to_dict()["policy_authority"] is False
    assert evaluated.to_dict()["readout_authority"] is False
    assert evaluated.impact.rows[0].feature_query.to_dict() == (
        evaluated.impact.rows[0].to_dict()["feature_query"])
    assert "outcome" not in evaluated.impact.rows[0].to_dict()[
        "feature_query"]

    outside_spec = replace(
        candidate.operation, operation_type="fdas-shadow:other:unit_fortify")
    outside = replace(candidate, operation=outside_spec)
    abstained = evaluator.evaluate(
        snapshot, (outside,), (score,), outside.operation.operation_id)
    assert abstained.status == "abstained"
    assert abstained.reason == (
        "no_admissible_candidate_in_approved_action_category")
    assert abstained.impact is None


def test_candidate_choice_set_censors_nonselected_and_labels_only_selected():
    snapshot, candidate, score, evaluator = _candidate_impact_fixture()
    alternative_spec = replace(
        candidate.operation,
        operation_id="candidate-fortify-alternative",
        participants=(OperationParticipant(
            "actor", "unit:8", "unit", True),))
    alternative_action = {"action_type": "unit_fortify", "actor_id": 8}
    alternative = replace(
        candidate,
        operation=alternative_spec,
        action=alternative_action,
        action_key=json.dumps(
            alternative_action, sort_keys=True, separators=(",", ":")),
        candidate_hash="candidate-hash-alternative")
    alternative_score = replace(
        score,
        operation=replace(
            score.operation,
            operation_id=alternative_spec.operation_id,
            atom_id="candidate-atom-alternative"),
        priority=0.9,
        value=0.9)
    evaluated = evaluator.evaluate(
        snapshot, (candidate, alternative), (score, alternative_score),
        candidate.operation.operation_id)
    store = FdasCandidateChoiceSetStore("choice-set-test")
    recorder = FdasCandidateChoiceSetRecorder(store)

    choice_set = recorder.capture(
        evaluated, (candidate, alternative), snapshot, "revision-before",
        candidate.action_key, ("approved-artifact-hash",))
    rows = dict((row.operation_id, row) for row in choice_set.choices)

    assert choice_set.selected_operation_id == candidate.operation.operation_id
    assert rows[candidate.operation.operation_id].selection_role == "selected"
    assert rows[alternative.operation.operation_id].selection_role == (
        "nonselected-censored")
    assert all("outcome" not in row.feature_query.to_dict()
               for row in choice_set.choices)
    assert choice_set.observed_outcome is None

    linked = recorder.record_execution(
        choice_set.choice_set_id, True, "execution-event", "episode-selected")
    material = {
        "due_turn": 44,
        "episode_digest": "episode-digest",
        "episode_id": "episode-selected",
        "game_id": snapshot.identity.game_id,
        "player_id": snapshot.player_id,
        "relief_revision_id": "relief-revision",
        "relief_turn": 12,
        "schema_version": 1,
        "target_id": DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    }
    label = EpisodeInductionOutcomeLabel(
        1, "outcome-label-" + structural_hash(material)[:24],
        "episode-selected", "episode-digest", snapshot.identity.game_id,
        snapshot.player_id, DURABLE_ACTOR_CITY_DEFENSE_TARGET,
        12, 44, "relief-revision", "observed", 44,
        "observed-revision", True,
        (("actor_present", True),), "selected-candidate-observed",
        ("label-provenance",))
    observed = recorder.observe_outcome("episode-selected", label)

    assert linked.outcome_status == "pending-observation"
    assert observed.outcome_status == "observed"
    assert observed.observed_outcome is True
    assert dict((row.operation_id, row.selection_role)
                for row in observed.choices)[alternative.operation.operation_id] == (
                    "nonselected-censored")

    exported = export_candidate_choice_calibration(
        store, evaluated.operation_type, evaluated.outcome_target)
    assert len(exported.examples) == 1
    assert exported.examples[0].outcome is True
    assert exported.nonselected_censored_count == 1
    assert exported.selected_pending_or_censored_count == 0
    assert exported.to_dict()["policy_authority"] is False
    assert exported.to_dict()["readout_authority"] is False
    assert exported.to_dict()["truth_mutated"] is False
    assert "game-id:" + snapshot.identity.game_id in (
        exported.examples[0].provenance_ids)
    assert "selected-actor-id:7" in exported.examples[0].provenance_ids
    assert "selected-action-type:unit_fortify" in (
        exported.examples[0].provenance_ids)
    assert (
        "selected-operation-type:fdas-shadow:unit-fortification-opportunity:"
        "unit_fortify") in exported.examples[0].provenance_ids
    assert all(
        alternative.operation.operation_id not in value.provenance_ids
        for value in exported.examples)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "choices.json")
        store.save(path)
        loaded = FdasCandidateChoiceSetStore.load(path, "choice-set-test")
        assert loaded.store_digest == store.store_digest
        assert loaded.get(choice_set.choice_set_id) == observed
        with open(path, encoding="utf-8") as stream:
            corrupted = json.load(stream)
        corrupted["choice_sets"][0]["choices"][1][
            "selection_role"] = "selected"
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(corrupted, stream)
        quarantined = FdasCandidateChoiceSetStore.load(
            path, "choice-set-test")
        assert quarantined.quarantined is True
        assert quarantined.quarantine_reason.startswith(
            "candidate-choice-store-load-failed:")

    independent = replace(
        observed,
        choice_set_id="choice-set-independent",
        game_id="fdas-candidate-impact-independent",
        evaluation_result_hash="independent-evaluation",
        execution_event_id="independent-execution",
        selected_episode_id="independent-episode",
        outcome_label_id="independent-label")
    other_store = FdasCandidateChoiceSetStore(
        "choice-set-other", (independent,))
    cohort = combine_candidate_choice_stores(
        (store, other_store), "choice-set-cohort")

    assert len(cohort.choice_sets()) == 2
    assert len(export_candidate_choice_calibration(
        cohort, evaluated.operation_type,
        evaluated.outcome_target).examples) == 2
    with pytest.raises(ValueError, match="identities overlap"):
        combine_candidate_choice_stores(
            (store, store), "choice-set-overlap")


def test_candidate_choice_set_without_in_scope_selection_is_all_censored():
    snapshot, candidate, score, evaluator = _candidate_impact_fixture()
    evaluated = evaluator.evaluate(
        snapshot, (candidate,), (score,), candidate.operation.operation_id)
    recorder = FdasCandidateChoiceSetRecorder(
        FdasCandidateChoiceSetStore("choice-set-no-selection"))

    choice_set = recorder.capture(
        evaluated, (candidate,), snapshot, "revision-before",
        '{"action_type":"city_production","city_id":3}')

    assert choice_set.selected_operation_id is None
    assert choice_set.execution_status == "not-applicable"
    assert choice_set.outcome_status == "censored-no-selection"
    assert all(row.selection_role == "nonselected-censored"
               for row in choice_set.choices)
    assert choice_set.observed_outcome is None


def test_defense_choice_surface_captures_move_and_fortify_without_estimates():
    snapshot, fortify, fortify_score, evaluator = _candidate_impact_fixture()
    move_action = {
        "action_type": "unit_move", "actor_id": 7,
        "target": {"direction": "e", "x": 3, "y": 2}}
    move_action_key = json.dumps(
        move_action, sort_keys=True, separators=(",", ":"))
    move_spec = replace(
        fortify.operation,
        operation_id="candidate-garrison-move",
        operation_type="fdas-shadow:city-garrison-deficit:unit_move",
        steps=(replace(
            fortify.operation.steps[0], step_id="candidate-move-step",
            action_type="unit_move"),))
    move = replace(
        fortify, operation=move_spec, action=move_action,
        action_key=move_action_key, candidate_hash="candidate-hash-move")
    move_score = replace(
        fortify_score,
        operation=replace(
            fortify_score.operation,
            operation_id=move_spec.operation_id,
            atom_id="candidate-atom-move"),
        priority=1.2, value=1.2)
    legal_snapshot = replace(
        snapshot,
        legal_action_json=tuple(sorted(
            snapshot.legal_action_json
            + (fortify.action_key, move.action_key))))
    queries = {}
    for candidate in (move, fortify):
        context = evaluator.recorder.context_for_operation(
            candidate.operation, legal_snapshot)
        if candidate == move:
            assert dict(context)["goal_relief_due_turn"] == str(
                candidate.operation.expiry_turn)
        queries[candidate.operation.operation_id] = (
            causal_induction_feature_query(
                "query-" + candidate.operation.operation_id,
                context, DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET,
                (candidate.candidate_hash, legal_snapshot.snapshot_id)))
    recorder = FdasCandidateChoiceSetRecorder(
        FdasCandidateChoiceSetStore("defense-choice-surface-test"))

    choice_set = recorder.capture_defense_surface(
        (move, fortify), (move_score, fortify_score), legal_snapshot,
        "surface-revision", fortify.action_key,
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET, queries,
        global_baseline_selected_operation_id=move.operation.operation_id,
        provenance_ids=("declaration-hash:test",))
    rows = dict((row.operation_id, row) for row in choice_set.choices)

    assert choice_set.operation_type == DEFENSE_CANDIDATE_CHOICE_SURFACE
    assert choice_set.selected_operation_id == fortify.operation.operation_id
    assert choice_set.category_baseline_selected_operation_id == (
        move.operation.operation_id)
    assert len(choice_set.choices) == 2
    assert rows[fortify.operation.operation_id].selection_role == "selected"
    assert rows[move.operation.operation_id].selection_role == (
        "nonselected-censored")
    assert all(row.estimated is False for row in choice_set.choices)
    assert all(row.priority_delta == 0.0 for row in choice_set.choices)
    assert all(row.estimate_reason == "unmodeled-action-stratum"
               for row in choice_set.choices)
    assert all("outcome" not in row.feature_query.to_dict()
               for row in choice_set.choices)

    no_selection_recorder = FdasCandidateChoiceSetRecorder(
        FdasCandidateChoiceSetStore(
            "defense-choice-surface-no-selection-test"))
    no_selection = no_selection_recorder.capture_defense_surface(
        (move, fortify), (move_score, fortify_score), legal_snapshot,
        "surface-no-selection-revision",
        '{"action_type":"unit_move","actor_id":99}',
        DURABLE_SELECTED_ACTOR_CITY_DEFENSE_TARGET, queries,
        global_baseline_selected_operation_id=move.operation.operation_id)
    assert no_selection.selected_operation_id is None
    assert no_selection.execution_status == "not-applicable"
    assert no_selection.outcome_status == "censored-no-selection"
    assert all(row.selection_role == "nonselected-censored"
               for row in no_selection.choices)

    duplicate_move = replace(
        move,
        operation=replace(
            move.operation, operation_id="candidate-garrison-move-duplicate"),
        candidate_hash="candidate-hash-move-duplicate")
    unambiguous, ambiguous = (
        unambiguous_defense_choice_surface_candidates(
            (move, duplicate_move, fortify),
            legal_snapshot.legal_action_json))
    assert tuple(value.operation.operation_id for value in unambiguous) == (
        fortify.operation.operation_id,)
    assert ambiguous == (move.action_key,)


def test_context_and_evidence_features_must_be_linked_to_episode():
    episode = _episode(0, "goal-relief-observed")
    adapter = FdasEpisodeInductionAdapter(
        DecisionEpisodeStore("fdas-induction", (episode,)))

    missing_context = adapter.encode(EpisodeInductionSpec(
        episode.episode_id, ("unknown",), ("operation_type",)))
    unlinked_evidence = adapter.encode(EpisodeInductionSpec(
        episode.episode_id, ("era",), ("operation_type",),
        (("invented-feature", "not-linked"),)))

    assert not missing_context.accepted
    assert missing_context.reason.startswith("episode-context-keys-missing")
    assert not unlinked_evidence.accepted
    assert unlinked_evidence.reason.startswith(
        "episode-feature-evidence-unlinked")


def test_actor_persistence_target_abstains_for_non_fortification_episode():
    episode = _episode(
        0, "goal-relief-observed",
        feature_schema="defense-episode-features/2.0")
    base = FdasEpisodeInductionShadow._spec(episode)
    result = FdasEpisodeInductionAdapter(
        DecisionEpisodeStore("actor-target-ineligible", (episode,))).encode(
            EpisodeInductionSpec(
                base.episode_id,
                base.context_keys,
                base.feature_context_keys,
                base.linked_features,
                DURABLE_ACTOR_CITY_DEFENSE_TARGET))

    assert result.accepted is False
    assert result.reason == "episode-not-eligible-for-outcome-target"


def test_shared_execution_lineage_rejects_independent_training_claim():
    episodes = tuple(
        _episode(index, "goal-relief-observed", event_id="shared-event")
        for index in range(2))
    adapter = FdasEpisodeInductionAdapter(
        DecisionEpisodeStore("fdas-induction", episodes))
    rows = tuple(adapter.encode(_spec(value)).induction_episode
                 for value in episodes)

    with pytest.raises(ValueError, match="not independent"):
        PatternMiner(minimum_support=2).mine(rows, "route-relieves-goal")


def test_encoded_training_and_disjoint_holdout_obey_quarantine_lifecycle():
    training = tuple(
        _episode(
            index,
            "goal-relief-observed" if index % 2 == 0
            else "no-effect-observed")
        for index in range(8))
    heldout = tuple(
        _episode(
            index,
            "goal-relief-observed" if index % 2 == 0
            else "no-effect-observed",
            cohort="holdout")
        for index in range(8))
    store = DecisionEpisodeStore("fdas-induction", training + heldout)
    adapter = FdasEpisodeInductionAdapter(store)
    training_rows = tuple(
        adapter.encode(_spec(value)).induction_episode for value in training)
    heldout_rows = tuple(
        adapter.encode(_spec(value)).induction_episode for value in heldout)

    proposals = PatternMiner(
        minimum_support=4, maximum_antecedents=1,
        minimum_residual=0.0).mine(training_rows, "route-relieves-goal")
    assert proposals
    proposal = proposals[0]
    ledger = InductionLedger(identity="fdas-episode-induction")
    assert ledger.propose(proposal)
    assert ledger.status(proposal.proposal_id) == "quarantined"
    assert ledger.promoted_rules() == ()

    validation = ReplayValidator(
        minimum_samples=8, minimum_activations=4,
        minimum_brier_improvement=0.0,
        minimum_calibration_improvement=0.0).validate(
            proposal, heldout_rows)
    approval = (
        InductionPromotionApproval.issue(
            proposal, validation, "a" * 64, "b" * 64)
        if validation.verdict == "promoted" else None)
    ledger.record_validation(validation, approval=approval)
    assert ledger.status(proposal.proposal_id) in ("promoted", "demoted")
    if validation.verdict == "promoted":
        assert ledger.promoted_rules() == (proposal,)
    else:
        assert ledger.promoted_rules() == ()


def test_live_shadow_mines_only_quarantined_rules_and_replay_is_idempotent():
    episodes = tuple(
        _episode(
            index,
            "goal-relief-observed" if index < 2 else "no-effect-observed",
            tile="10" if index < 2 else "20")
        for index in range(4))
    store = DecisionEpisodeStore("fdas-induction-shadow", episodes)
    ledger = InductionLedger(identity="fdas-induction-shadow")
    shadow = FdasEpisodeInductionShadow(
        store,
        ledger,
        PatternMiner(
            minimum_support=2,
            maximum_antecedents=1,
            minimum_residual=0.05))

    first = shadow.evaluate()
    first_hash = ledger.state_hash
    second = shadow.evaluate()

    assert first.proposals
    assert first.newly_quarantined_proposal_ids
    assert not first.duplicate_proposal_ids
    assert all(
        ledger.status(proposal_id) == "quarantined"
        for proposal_id in first.newly_quarantined_proposal_ids)
    assert ledger.promoted_rules() == ()
    assert first.truth_mutated is False
    assert first.policy_authority is False
    assert second.newly_quarantined_proposal_ids == ()
    assert second.duplicate_proposal_ids == tuple(
        sorted(value.proposal_id for value in first.proposals))
    assert ledger.state_hash == first_hash


def test_live_shadow_abstains_when_training_lineage_is_not_independent():
    episodes = tuple(
        _episode(
            index,
            "goal-relief-observed" if index < 2 else "no-effect-observed",
            event_id="shared-execution",
            tile="10" if index < 2 else "20")
        for index in range(4))
    ledger = InductionLedger(identity="fdas-induction-shadow")
    result = FdasEpisodeInductionShadow(
        DecisionEpisodeStore("fdas-induction-shadow", episodes),
        ledger,
        PatternMiner(
            minimum_support=2,
            maximum_antecedents=1,
            minimum_residual=0.05)).evaluate()

    assert result.mining_reason == "training-provenance-not-independent"
    assert result.proposals == ()
    assert ledger.snapshot()["proposals"] == {}


def test_heldout_gate_promotes_only_with_disjoint_versioned_approval(tmp_path):
    training = DecisionEpisodeStore(
        "fdas-induction-training",
        _correlated_population("training"))
    holdout = DecisionEpisodeStore(
        "fdas-induction-holdout",
        _correlated_population("holdout"))
    ledger_path = tmp_path / "heldout-ledger.json"
    ledger = InductionLedger(
        str(ledger_path), identity="fdas-induction-heldout")
    gate = FdasEpisodeInductionHeldoutGate(
        training, holdout, ledger)

    first = gate.evaluate()
    state_hash = ledger.state_hash
    second = gate.evaluate()
    persisted = InductionLedger(
        str(ledger_path), identity="fdas-induction-heldout")

    assert first.proposals
    assert first.promoted_rule_ids
    assert not first.demoted_rule_ids
    assert len(first.approvals) == len(first.promoted_rule_ids)
    assert all(
        value.to_dict()["policy_authority"] is False
        and value.to_dict()["readout_authority"] is False
        for value in first.approvals)
    assert first.truth_mutated is False
    assert first.policy_authority is False
    assert first.readout_authority is False
    assert len(persisted.promoted_rules()) == len(first.promoted_rule_ids)
    assert persisted.state_hash == state_hash == ledger.state_hash
    assert second.newly_quarantined_proposal_ids == ()
    assert second.newly_validated_ids == ()
    assert set(second.duplicate_proposal_ids) == set(
        first.promoted_rule_ids)
    assert len(second.duplicate_validation_ids) == len(
        first.promoted_rule_ids)


def test_heldout_gate_demotes_out_of_sample_reversal_without_approval():
    training = DecisionEpisodeStore(
        "fdas-induction-training",
        _correlated_population("training"))
    holdout = DecisionEpisodeStore(
        "fdas-induction-reversed-holdout",
        _correlated_population("holdout", inverted=True))
    ledger = InductionLedger(identity="fdas-induction-demotion")

    result = FdasEpisodeInductionHeldoutGate(
        training, holdout, ledger).evaluate()

    assert result.proposals
    assert result.demoted_rule_ids
    assert not result.promoted_rule_ids
    assert result.approvals == ()
    assert ledger.promoted_rules() == ()


def test_heldout_gate_rejects_episode_partition_overlap():
    episodes = _correlated_population("shared")
    training = DecisionEpisodeStore("training-partition", episodes)
    holdout = DecisionEpisodeStore("holdout-partition", episodes)
    gate = FdasEpisodeInductionHeldoutGate(
        training, holdout,
        InductionLedger(identity="fdas-induction-overlap"))

    with pytest.raises(ValueError, match="episode overlap"):
        gate.evaluate()


def test_heldout_gate_validates_revision_bound_delayed_target():
    training_episodes, training_labels = _delayed_population("training")
    holdout_episodes, holdout_labels = _delayed_population("holdout")
    training = DecisionEpisodeStore(
        "delayed-training-episodes", training_episodes)
    holdout = DecisionEpisodeStore(
        "delayed-holdout-episodes", holdout_episodes)
    training_outcomes = EpisodeInductionOutcomeLabelStore(
        "delayed-training-labels", training_labels)
    holdout_outcomes = EpisodeInductionOutcomeLabelStore(
        "delayed-holdout-labels", holdout_labels)
    ledger = InductionLedger(identity="delayed-heldout-gate")

    result = FdasEpisodeInductionHeldoutGate(
        training,
        holdout,
        ledger,
        outcome_target=DURABLE_CITY_COVERAGE_TARGET,
        training_outcome_label_store=training_outcomes,
        holdout_outcome_label_store=holdout_outcomes).evaluate()

    assert result.promoted_rule_ids
    assert not result.demoted_rule_ids
    assert len(result.approvals) == len(result.promoted_rule_ids)
    assert all(
        value.consequent == DURABLE_CITY_COVERAGE_TARGET
        for value in result.proposals)
    assert all(
        ("outcome_target", DURABLE_CITY_COVERAGE_TARGET)
        in value.induction_episode.context
        for value in result.training_encoding_results)
    assert result.truth_mutated is False
    assert result.policy_authority is False
    assert result.readout_authority is False


def test_episode_cohort_combines_verified_disjoint_stores():
    left = DecisionEpisodeStore(
        "source-left", _correlated_population("left")[:4])
    right = DecisionEpisodeStore(
        "source-right", _correlated_population("right")[:4])

    cohort = combine_episode_stores((left, right), "combined-cohort")

    assert cohort.persistence_identity == "combined-cohort"
    assert len(cohort.episodes()) == 8
    assert cohort.quarantined is False


def test_episode_cohort_rejects_duplicate_source_identity_and_episode_ids():
    left = DecisionEpisodeStore(
        "source-shared", _correlated_population("left")[:4])
    same_identity = DecisionEpisodeStore(
        "source-shared", _correlated_population("right")[:4])
    duplicate_episodes = DecisionEpisodeStore(
        "source-distinct", left.episodes())

    with pytest.raises(ValueError, match="source identities overlap"):
        combine_episode_stores((left, same_identity), "combined-cohort")
    with pytest.raises(ValueError, match="IDs overlap"):
        combine_episode_stores((left, duplicate_episodes), "combined-cohort")


def test_outcome_label_cohort_combines_only_verified_disjoint_sources():
    _left_episodes, left_labels = _delayed_population("labels-left")
    _right_episodes, right_labels = _delayed_population("labels-right")
    left = EpisodeInductionOutcomeLabelStore(
        "labels-source-left", left_labels)
    right = EpisodeInductionOutcomeLabelStore(
        "labels-source-right", right_labels)

    combined = combine_outcome_label_stores(
        (left, right), "labels-combined")

    assert len(combined.labels()) == len(left_labels) + len(right_labels)
    assert combined.quarantined is False
    with pytest.raises(ValueError, match="source identities overlap"):
        combine_outcome_label_stores(
            (left, EpisodeInductionOutcomeLabelStore(
                "labels-source-left", right_labels)),
            "labels-duplicate-source")


def test_holdout_runner_consumes_explicit_delayed_label_partitions(tmp_path):
    training_episodes, training_labels = _delayed_population("cli-training")
    holdout_episodes, holdout_labels = _delayed_population("cli-holdout")
    paths = {
        "training": tmp_path / "training-episodes.json",
        "holdout": tmp_path / "holdout-episodes.json",
        "training_labels": tmp_path / "training-labels.json",
        "holdout_labels": tmp_path / "holdout-labels.json",
        "ledger": tmp_path / "ledger.json",
        "report": tmp_path / "report.json",
    }
    DecisionEpisodeStore(
        "cli-training-episodes", training_episodes).save(
            str(paths["training"]))
    DecisionEpisodeStore(
        "cli-holdout-episodes", holdout_episodes).save(
            str(paths["holdout"]))
    EpisodeInductionOutcomeLabelStore(
        "cli-training-labels", training_labels).save(
            str(paths["training_labels"]))
    EpisodeInductionOutcomeLabelStore(
        "cli-holdout-labels", holdout_labels).save(
            str(paths["holdout_labels"]))
    command = [
        sys.executable,
        os.path.join(REPO, "scripts", "freeciv",
                     "run_fdas_induction_holdout.py"),
        "--training-store", str(paths["training"]),
        "--holdout-store", str(paths["holdout"]),
        "--training-outcome-label-store", str(paths["training_labels"]),
        "--holdout-outcome-label-store", str(paths["holdout_labels"]),
        "--outcome-target", DURABLE_CITY_COVERAGE_TARGET,
        "--ledger", str(paths["ledger"]),
        "--output", str(paths["report"]),
        "--minimum-samples", "4",
        "--minimum-activations", "2",
    ]

    result = subprocess.run(
        command, cwd=REPO, text=True, capture_output=True, timeout=30)
    report = json.loads(paths["report"].read_text(encoding="utf-8"))

    assert result.returncode == 0, result.stderr
    assert report["acceptance"]["accepted"] is True
    assert report["configuration"]["outcome_target"] == (
        DURABLE_CITY_COVERAGE_TARGET)
    assert report["training_outcome_label_sources"][0]["observed_labels"]
    assert report["holdout_outcome_label_sources"][0]["observed_labels"]
    assert report["result"]["promoted_rule_ids"]

    holdout_label_index = command.index("--holdout-outcome-label-store")
    outcome_target_index = command.index("--outcome-target")
    missing_partition = subprocess.run(
        command[:holdout_label_index] + command[outcome_target_index:],
        cwd=REPO, text=True, capture_output=True, timeout=30)
    assert missing_partition.returncode != 0
    assert "requires both label partitions" in missing_partition.stderr
