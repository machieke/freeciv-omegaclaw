from dataclasses import replace
import json

from freeciv.harness.fdas_delayed_induction_live import (
    audit_fdas_delayed_induction_live,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.synthetic import DeterministicIds, fixed_clock
from freeciv_agent.events.writer import EventWriter
from freeciv_agent.planning import (
    CAUSAL_INDUCTION_FEATURE_SCHEMA,
    DURABLE_ACTOR_CITY_DEFENSE_TARGET,
    DURABLE_CITY_COVERAGE_TARGET,
    DecisionEpisode,
    DecisionEpisodeStore,
    EpisodeInductionOutcomeLabel,
    EpisodeInductionOutcomeLabelStore,
    LABEL_SCHEMA_VERSION,
)


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _episode(feature_schema="defense-episode-features/2.0"):
    return DecisionEpisode(
        1,
        "episode-delayed-live",
        "delayed-live-test",
        2,
        "operation-defense",
        "move-defense-unit",
        "revision-before",
        "revision-relief",
        ("pf-impact:survival",),
        (("actor_id", "unit:7"), ("actor_unit_type", "Riflemen"),
         ("city_id", "4"),
         ("induction_feature_schema", feature_schema),
         ("operation_type",
          "fdas-shadow:unit-fortification-opportunity:unit_fortify")),
        ("atom-defense",),
        ("support-defense",),
        ("grounding-route",),
        ("prediction-defense",),
        ("claim-unit",),
        "validation-hash",
        "execution-event",
        {"observed_turn": 14, "actor_activity_after": "fortifying",
         "actor_present_after": True},
        ({"effect": "actor-arrived-at-target"},),
        (("pf-impact:survival", 1.0),),
        "goal-relief-observed",
        ("episode-provenance",),
    )


def _labels(episode, target_id=DURABLE_CITY_COVERAGE_TARGET, window=8):
    due_turn = 14 + window
    material = {
        "due_turn": due_turn,
        "episode_digest": episode.immutable_digest,
        "episode_id": episode.episode_id,
        "game_id": episode.game_id,
        "player_id": episode.player_id,
        "relief_revision_id": episode.after_revision_id,
        "relief_turn": 14,
        "schema_version": LABEL_SCHEMA_VERSION,
        "target_id": target_id,
    }
    pending = EpisodeInductionOutcomeLabel(
        LABEL_SCHEMA_VERSION,
        "outcome-label-" + structural_hash(material)[:24],
        episode.episode_id,
        episode.immutable_digest,
        episode.game_id,
        episode.player_id,
        target_id,
        14,
        due_turn,
        episode.after_revision_id,
        "pending",
        None,
        None,
        None,
        (),
        None,
        ("labeler",),
    )
    observed_value = (
        (("actor_at_city", False), ("actor_id", 7),
         ("actor_present", False), ("city_id", 4))
        if target_id == DURABLE_ACTOR_CITY_DEFENSE_TARGET else
        (("city_id", 4), ("own_unit_count_at_city", 0)))
    reason = (
        "attributed-actor-no-longer-present-at-due-turn"
        if target_id == DURABLE_ACTOR_CITY_DEFENSE_TARGET else
        "authoritative-own-unit-coverage-absent-at-due-turn")
    observed = replace(
        pending,
        status="observed",
        observed_turn=due_turn,
        observed_revision_id="revision-due",
        outcome=False,
        observed_value=observed_value,
        reason=reason,
    )
    return pending, observed


def _fixture(
        tmp_path, target_id=DURABLE_CITY_COVERAGE_TARGET, window=8,
        feature_schema=None):
    episode = _episode(feature_schema or "defense-episode-features/2.0")
    pending, observed = _labels(episode, target_id, window)
    episode_store = DecisionEpisodeStore("episode-store", (episode,))
    episode_store.save(str(tmp_path / "fdas-decision-episodes.json"))
    label_store = EpisodeInductionOutcomeLabelStore(
        "label-store", (observed,))
    label_store.save(str(tmp_path / "fdas-induction-outcome-labels.json"))
    actor_target = target_id == DURABLE_ACTOR_CITY_DEFENSE_TARGET
    causal_features = feature_schema == CAUSAL_INDUCTION_FEATURE_SCHEMA
    config_source = (
        "profile/"
        "dependent_atomspace_defense_actor_persistence_causal_"
        "induction_shadow.yaml"
        if causal_features else
        "profile/"
        "dependent_atomspace_defense_actor_persistence_induction_shadow.yaml"
        if actor_target else
        "profile/dependent_atomspace_defense_delayed_induction_shadow.yaml")
    manifest_source = (
        "profile/"
        "fdas_manifest_defense_actor_persistence_causal_"
        "induction_shadow.json"
        if causal_features else
        "profile/"
        "fdas_manifest_defense_actor_persistence_induction_shadow.json"
        if actor_target else
        "profile/fdas_manifest_defense_delayed_induction_shadow.json")
    _write_json(tmp_path / "manifest.json", {
        "dependent_atomspace": {
            "config": {"learning": {
                "episode_attribution_enabled": True,
                "induced_rule_readout_enabled": False,
                "induction_enabled": True,
            }},
            "config_source": config_source,
            "manifest": {
                "capabilities": {
                    "delayed_induction_outcome_labels": "shadow-live",
                    **({"causal_episode_feature_schema": "shadow-live"}
                       if causal_features else {}),
                },
                "delayed_induction_outcome_diagnostic": {
                    "induced_rule_readout": False,
                    **({"induction_feature_schema": feature_schema}
                       if causal_features else {}),
                    "observation_window_turns": window,
                    "policy_authority": False,
                    "target_id": target_id,
                },
            },
            "manifest_source": manifest_source,
        },
        "source": {"commit": "a" * 40, "dirty": False},
    })
    _write_json(tmp_path / "status.json", {
        "completed": True,
        "fdas_delayed_outcome_labels_observed": 1,
        "fdas_delayed_outcome_labels_opened": 1,
        "fdas_delayed_outcome_labels_pending": 0,
        "fdas_delayed_outcome_negative": 1,
        "fdas_delayed_outcome_positive": 0,
        "horizon_reached": True,
    })
    writer = EventWriter(
        str(tmp_path / "events.jsonl"),
        "delayed-live-test",
        clock=fixed_clock,
        id_factory=DeterministicIds(),
        durable=False,
    )
    root = writer.emit("run_started", 0, {
        "condition_id": "delayed-live",
        "manifest_identity": "manifest-delayed-live",
    })
    atomspace = {
        "component_id": "fdas-episode-control-learning",
        "component_version": "1.0",
        "revision_id": "revision-relief",
        "ruleset_digest": "ruleset",
        "snapshot_id": "snapshot-relief",
        "structural_hash": "a" * 64,
    }
    opened = writer.emit(
        "episode_outcome_label_opened",
        14,
        dict(atomspace, details={
            "label": pending.to_dict(),
            "policy_authority": False,
            "readout_enabled": False,
            "truth_mutated": False,
        }),
        caused_by=(root["event_id"],),
    )
    writer.emit(
        "episode_outcome_label_observed",
        14 + window,
        dict(atomspace, details={
            "label": observed.to_dict(),
            "policy_authority": False,
            "readout_enabled": False,
            "truth_mutated": False,
        }),
        caused_by=(opened["event_id"],),
    )


def test_delayed_induction_live_audit_accepts_exact_non_authorizing_lifecycle(
        tmp_path):
    _fixture(tmp_path)

    report = audit_fdas_delayed_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["labels_observed"] == 1
    assert report["summary"]["labels_negative"] == 1


def test_delayed_induction_live_audit_accepts_actor_persistence_target(
        tmp_path):
    _fixture(
        tmp_path,
        target_id=DURABLE_ACTOR_CITY_DEFENSE_TARGET,
        window=32)

    report = audit_fdas_delayed_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["target_id"] == (
        DURABLE_ACTOR_CITY_DEFENSE_TARGET)
    assert report["summary"]["observation_window_turns"] == 32


def test_delayed_induction_live_audit_accepts_causal_feature_schema(tmp_path):
    _fixture(
        tmp_path,
        target_id=DURABLE_ACTOR_CITY_DEFENSE_TARGET,
        window=32,
        feature_schema=CAUSAL_INDUCTION_FEATURE_SCHEMA)

    report = audit_fdas_delayed_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is True
    assert report["summary"]["induction_feature_schema"] == (
        CAUSAL_INDUCTION_FEATURE_SCHEMA)


def test_delayed_induction_live_audit_rejects_early_event_observation(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in path.read_text(
        encoding="utf-8").splitlines()]
    events[-1]["payload"]["details"]["label"]["observed_turn"] = 21
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in events),
        encoding="utf-8")

    report = audit_fdas_delayed_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "events_match_durable_lifecycle"] is False


def test_delayed_induction_live_audit_rejects_label_store_hash_drift(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "fdas-induction-outcome-labels.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["labels"][0]["reason"] = "tampered"
    _write_json(path, value)

    report = audit_fdas_delayed_induction_live(str(tmp_path))

    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["checks"][
        "stores_are_hash_valid_and_not_quarantined"] is False
