"""M4 provenance, decay, abduction, calibration, and isolation gates."""

import copy
import json
import os
import random
import sys
import tempfile
from types import SimpleNamespace

import jsonschema
import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.beliefs import (BeliefKey, BeliefStore, Evidence,  # noqa: E402
                                   ContextQuarantineConflict, EvidenceConflict,
                                   OpponentMemory, SelfSupportingProof,
                                   UncertainInference, post_game_calibration)
from freeciv_agent.config import belief_config  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402


def _evidence(provenance="prov-1", predicate="observed-unit", arguments=("enemy", "Phalanx"),
              turn=1, confidence=0.8, strength=1.0):
    return Evidence(
        provenance, "game-1", turn, (3, 4), "visible-map",
        BeliefKey(predicate, tuple(arguments)), strength, confidence,
        "fixed-ai", "civ2civ3", "opponent-model/1.0")


def _store():
    return BeliefStore(belief_config())


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(
        REPO, "..", "..", "..", "Repos", "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for M4 abduction tests")


def test_identical_observation_replay_is_byte_idempotent_and_conflicts_fail():
    stream = [_evidence("p-1"), _evidence("p-2", turn=2, confidence=0.6)]
    once = _store()
    twice = _store()
    for evidence in stream:
        once.observe(evidence)
        twice.observe(evidence)
    for evidence in stream + stream:
        # A second replay is an idempotent no-op.
        twice.observe(evidence)
    assert once.artifact_hash == twice.artifact_hash
    assert [item.to_dict() for item in once.beliefs()] == [item.to_dict() for item in twice.beliefs()]
    with pytest.raises(EvidenceConflict):
        twice.observe(_evidence("p-1", strength=0.0))


def test_one_provenance_across_three_paths_contributes_once():
    store = _store()
    store.observe(_evidence())
    key = BeliefKey("has-tech", ("enemy", "Bronze Working"))
    expected = None
    for path in ("path-c", "path-a", "path-b"):
        belief, _ = store.derive(
            key, ["prov-1"], 1, 0.8, 0.7, path, dampening_lambda=0.1)
        expected = expected or belief.tv
        assert belief.tv == expected
        assert belief.provenance_ids == ("prov-1",)
    assert len(store.get(key).support_paths) == 1


def test_live_belief_revision_uses_weighted_token_union_and_exposes_overlap():
    store = _store()
    first = _evidence("p-1", predicate="left", confidence=0.8, strength=1.0)
    second = _evidence("p-2", predicate="left", confidence=0.8, strength=0.0)
    store.observe(first)
    belief, revision = store.observe(second)
    assert belief.strength == 0.5
    # Two independent c=.8 tokens carry weight 4 each -> c=8/9.
    assert abs(belief.confidence - 8.0 / 9.0) < 1e-12
    right = BeliefKey("right", ("enemy", "Phalanx"))
    store.derive(right, ("p-1",), 1, 1.0, 0.8, "shared")
    overlap = store.lineage_overlap(first.key, right, 1)
    assert 0 < overlap < 1
    assert revision.formula["name"] == "provenance-union"


def test_independent_disagreement_materializes_conflict_and_context_partitions():
    store = _store()
    left = _evidence(
        "left", predicate="enemy-route", arguments=("enemy", "north"),
        confidence=0.8, strength=1.0)
    right = Evidence(
        "right", "game-2", 1, (8, 9), "diplomatic-report", left.key,
        0.0, 0.8, "fixed-ai", "civ2civ3", "opponent-model/1.0")
    store.observe(left)
    aggregate, _ = store.observe(right)

    conflicts = store.conflicts()
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.provenance_ids == ("left", "right")
    assert conflict.overlap == 0.0
    assert conflict.severity == 0.64
    assert conflict.atom()["predicate"] == "Conflict"
    assert aggregate.strength == 0.5

    operations = store.context_quarantine_operations(conflict.conflict_id, 1)
    assert len(operations) == 2
    keep_left = next(
        operation for operation in operations
        if operation.context_id == left.context_id)
    store.apply_context_quarantine(keep_left)
    # Applying the same immutable operation is idempotent.
    store.apply_context_quarantine(keep_left)
    contextual = store.get_in_context(left.key, left.context_id, 1)
    assert contextual.provenance_ids == ("left",)
    assert contextual.tv == {"confidence": 0.8, "strength": 1.0}
    assert len(store.quarantines) == 1

    forged = copy.copy(keep_left)
    object.__setattr__(forged, "target_atom_id", "belief-forged")
    with pytest.raises(ContextQuarantineConflict):
        store.apply_context_quarantine(forged)


def test_correlated_duplicate_benchmark_has_zero_overlap_errors():
    """Many paths rooted in one token remain one contribution in any order."""
    expected_state = None
    for seed in range(64):
        store = _store()
        store.observe(_evidence())
        paths = ["duplicate-path-{:03d}".format(index) for index in range(128)]
        random.Random(seed).shuffle(paths)
        target = BeliefKey("has-tech", ("enemy", "Construction"))
        for path in paths:
            store.derive(
                target, ("prov-1",), 1, 0.9, 0.8, path,
                dampening_lambda=0.1)
        belief = store.get(target)
        assert belief.provenance_ids == ("prov-1",)
        assert len(belief.support_paths) == 1
        assert store.conflicts() == ()
        state = (belief.tv, belief.provenance_ids, belief.support_paths)
        expected_state = expected_state or state
        assert state == expected_state


def test_adversarial_deduction_rejects_self_supporting_cycles():
    store = _store()
    observed, _ = store.observe(_evidence(
        predicate="route-seed", arguments=("enemy",)))
    inference = UncertainInference(SimpleNamespace(rules=()), store)
    route_a, _ = inference.deduce(
        "route-a", ("enemy",), (observed,), 1, "seed-to-a")
    route_b, _ = inference.deduce(
        "route-b", ("enemy",), (route_a,), 1, "a-to-b")
    with pytest.raises(SelfSupportingProof):
        inference.deduce(
            "route-a", ("enemy",), (route_b,), 1, "b-to-a")
    with pytest.raises(SelfSupportingProof):
        store.derive(
            observed.key, ("prov-1",), 1, 1.0, 0.8, "identity")
    assert store.get(observed.key) == observed


def test_decay_crosses_actionable_threshold_and_never_refreshes_from_derivation():
    store = _store()
    store.observe(_evidence(predicate="at", arguments=("enemy", 3, 3)))
    threat = BeliefKey("threat-at", (3, 3))
    store.derive(threat, ["prov-1"], 2, 1.0, 0.8, "threat", dampening_lambda=0.1)
    assert store.get(threat).confidence > belief_config()["actionable_threshold"]
    store.decay_to(7)
    assert store.get(threat).confidence < belief_config()["actionable_threshold"]
    assert store.get(BeliefKey("at", ("enemy", 3, 3))).confidence == 0.0


def test_abduction_uses_only_compiled_rule_prerequisites_and_remains_uncertain():
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")
    unit = next(rule for rule in ir.rules if rule.target_kind == "unit"
                and any(req.kind == "Tech" for req in rule.antecedents))
    store = _store()
    store.observe(_evidence(arguments=("enemy", unit.rule_name)))
    config = belief_config()
    results = UncertainInference(ir, store).abduce_prerequisites(
        "unit", unit.rule_name, "enemy", ["prov-1"], 1,
        config["abduction_strength"], config["abduction_confidence"])
    direct = {str(req.name) for req in unit.antecedents if req.kind == "Tech" and req.present}
    inferred = {belief.key.arguments[-1] for belief, _ in results}
    assert direct.issubset(inferred)
    assert results and all(not belief.crisp for belief, _ in results)
    assert all(belief.confidence <= config["abduction_confidence"] for belief, _ in results)


def test_declared_config_schema_and_static_parameter_audit():
    config = belief_config()
    schema = json.load(open(os.path.join(
        REPO, "schemas", "freeciv-beliefs", "v1", "config.schema.json"), encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(config)
    source = "\n".join(open(os.path.join(SRC, "freeciv_agent", "beliefs", name),
                            encoding="utf-8").read()
                         for name in os.listdir(os.path.join(SRC, "freeciv_agent", "beliefs"))
                         if name.endswith(".py"))
    assert "0.1" not in source  # lambda comes from configuration or an explicit logged call.
    assert "confidence=0.8" not in source
    assert "default_probability=0.5" not in source
    assert "probability >= 0.5" not in source
    assert set(config["sweep"]) == {
        "dampening_lambda", "actionable_threshold", "decay_window_multiplier"}


def test_post_game_calibration_50_fixed_opponent_games_and_live_truth_guard():
    predictions = []
    truth = {}
    # Ten predictions per bucket across 50 distinct fixed-opponent games. The
    # empirical rates equal their 0.1-bucket midpoints within one sample.
    for bucket in range(10):
        strength = bucket / 10.0 + 0.05
        true_count = round(strength * 10)
        for sample in range(10):
            store = _store()
            evidence = _evidence(
                "p-{}-{}".format(bucket, sample), predicate="prediction",
                arguments=("game-{}".format(sample * 5 + bucket % 5), bucket),
                strength=strength, confidence=0.8)
            belief, _ = store.observe(evidence)
            predictions.append(belief)
            truth[belief.atom_id] = sample < true_count
    with pytest.raises(PermissionError):
        post_game_calibration(predictions, truth)
    report = post_game_calibration(predictions, truth, post_game=True)
    assert report["samples"] == 100
    assert all(row["sufficient_sample"] for row in report["buckets"])
    assert all(row["absolute_error"] <= 0.15 for row in report["buckets"])


def test_opponent_memory_never_mixes_identity_ruleset_or_model_populations():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "memory.json")
        memory = OpponentMemory(path)
        memory.record("ai-1", "civ2civ3", "v1", "has-tech", True, True)
        memory.record("ai-1", "classic", "v1", "has-tech", True, False)
        memory.record("ai-1", "civ2civ3", "v2", "has-tech", True, False)
        memory.save()
        loaded = OpponentMemory(path).to_dict()
        assert len(loaded["populations"]) == 3


def test_opponent_memory_reads_only_prior_scoped_games_and_persists_deterministically():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "memory.json")
        memory = OpponentMemory(path)
        assert memory.estimate("ai-1", "civ2civ3", "v1", "has-tech:Espionage") is None
        memory.record("ai-1", "civ2civ3", "v1", "has-tech:Espionage", True, True)
        memory.record("ai-1", "civ2civ3", "v1", "has-tech:Espionage", True, False)
        estimate = memory.estimate(
            "ai-1", "civ2civ3", "v1", "has-tech:Espionage")
        assert estimate["samples"] == 2
        assert estimate["empirical_frequency"] == 0.5
        assert memory.estimate(
            "ai-1", "classic", "v1", "has-tech:Espionage") is None
        memory.save()
        first = open(path, "rb").read()
        OpponentMemory(path).save()
        assert open(path, "rb").read() == first


def test_opponent_memory_prediction_pools_prior_scoped_outcomes():
    with tempfile.TemporaryDirectory() as directory:
        memory = OpponentMemory(os.path.join(directory, "memory.json"))
        config = belief_config()
        options = (config["induction_default_probability"],
                   config["induction_decision_threshold"],
                   config["induction_minimum_samples"])
        cold = memory.predict("ai-1", "classic", "v1", "has-tech:Writing", *options)
        assert cold == {"predicted": True, "probability": 0.5, "samples": 0}
        memory.record("ai-1", "classic", "v1", "has-tech:Writing", True, False)
        memory.record("ai-1", "classic", "v1", "has-tech:Writing", False, False)
        learned = memory.predict("ai-1", "classic", "v1", "has-tech:Writing", *options)
        assert learned == {"predicted": False, "probability": 0.0, "samples": 2}
        assert memory.predict(
            "ai-1", "civ2civ3", "v1", "has-tech:Writing", *options)["samples"] == 0


def test_observation_and_revision_events_are_schema_valid_and_causal():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "belief-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "d_uncertain_monitor", "manifest_identity": "m"})
        _, observation, revision = _store().emit_observation(
            _evidence(), writer, [root["event_id"]])
        report = validate_file(path)
        assert revision["caused_by"] == [observation["event_id"]]
        assert report.valid, report.to_dict()


def test_conflict_and_context_quarantine_events_are_schema_valid_and_causal():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "conflict-test", durable=False)
        root = writer.emit("run_started", 0, {
            "condition_id": "d_uncertain_monitor", "manifest_identity": "m"})
        store = _store()
        left = _evidence(
            "left", predicate="enemy-route", arguments=("enemy",),
            confidence=0.8, strength=1.0)
        right = Evidence(
            "right", "game-2", 1, (8, 9), "diplomatic-report", left.key,
            0.0, 0.8, "fixed-ai", "civ2civ3", "opponent-model/1.0")
        _, left_observation, left_revision = store.emit_observation(
            left, writer, [root["event_id"]])
        _, right_observation, right_revision = store.emit_observation(
            right, writer, [left_revision["event_id"]])
        conflict = store.conflicts()[0]
        conflict_event = store.emit_conflict(
            conflict.conflict_id, writer,
            [right_observation["event_id"], right_revision["event_id"]])
        operation = next(
            row for row in store.context_quarantine_operations(
                conflict.conflict_id, 1)
            if row.context_id == left.context_id)
        quarantine_event = store.emit_context_quarantine(
            operation, writer, [conflict_event["event_id"]])
        report = validate_file(path)
        assert conflict_event["payload"]["conflict_atom"]["predicate"] == "Conflict"
        assert quarantine_event["caused_by"] == [conflict_event["event_id"]]
        assert report.valid, report.to_dict()
