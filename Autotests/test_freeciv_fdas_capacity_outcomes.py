import copy
import json
import os
from types import SimpleNamespace

import pytest

from freeciv_agent.planning import (
    DecisionEpisodeStore,
    FdasEpisodeLearningAdapter,
    FdasRetainedCapacityEpisodeBridge,
    FdasRetainedCapacityOutcomeLabel,
    FdasRetainedCapacityOutcomeLabeler,
    FdasRetainedCapacityOutcomeStore,
    FdasRetainedCapacityTransitionQuery,
    FdasRetainedCapacityTransitionQueryBuilder,
    FdasRetainedCapacityTransitionQueryStore,
)
from freeciv_agent.planning.fdas_capacity_transition_queries import (
    _count_band,
    _horizon_band,
    _size_band,
    _surplus_band,
    _turn_phase,
)
from freeciv_agent.state import ProxyStateDTO
from freeciv_agent.state.atomspace import AtomKey, AtomNamespace, EntityRef


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")


class _Revision(object):
    def __init__(self, snapshot_id, deficit=True, revision_id="revision-proof"):
        self.snapshot_id = snapshot_id
        self.revision_id = revision_id
        key = AtomKey(
            AtomNamespace.DERIVED,
            "city-replacement-capacity-deficit",
            (EntityRef("city", "3"), EntityRef("city", "4")),
            "scope:city:3")
        self._records = {
            key.atom_id: SimpleNamespace(key=key)} if deficit else {}
        self.deficit_atom_id = key.atom_id

    def record(self, atom_id):
        return self._records.get(str(atom_id))


def _payload(turn, product=True, product_at_source=True):
    with open(FIXTURE, encoding="utf-8") as stream:
        payload = copy.deepcopy(json.load(stream))
    payload["turn"] = turn
    target = copy.deepcopy(payload["cities"]["3"])
    target.update({"id": 4, "name": "Target", "tile": 84, "x": 4, "y": 2})
    payload["cities"]["4"] = target
    if product:
        unit = copy.deepcopy(payload["units"]["7"])
        unit.update({
            "id": 9,
            "tile": payload["cities"]["3"]["tile"]
            if product_at_source else 84,
            "type": "Musketeers",
            "type_id": 9,
            "x": payload["cities"]["3"]["x"]
            if product_at_source else 4,
            "y": payload["cities"]["3"]["y"]
            if product_at_source else 2,
        })
        payload["units"]["9"] = unit
    payload["legal_actions"] = []
    return payload


def _snapshot(turn, seq, product=True, product_at_source=True):
    return ProxyStateDTO.parse(
        "fdas-capacity-outcome-proof", seq,
        _payload(turn, product, product_at_source)).to_snapshot()


def _proposal(snapshot, revision):
    return {
        "caused_by": ["cause"],
        "event_id": "retained-capacity-proposal",
        "game_id": snapshot.identity.game_id,
        "payload": {
            "downstream_operation_id": (
                "fdas-replacement-capacity:" + revision.deficit_atom_id),
            "mechanism": (
                "fdas-replacement-capacity-retained-queue-lifecycle"),
            "next_action": {
                "action_type": "city_production",
                "city_id": 3,
                "target": {"production_type": "Musketeers"},
            },
            "operation_digest": "operation-digest-proof",
            "operation_id": "retained-capacity-operation-proof",
            "operation_type": (
                "fdas-shadow:city-replacement-capacity-deficit:"
                "city_production"),
            "goal_ids": ["fdas-goal-capacity-proof"],
            "policy_authority": False,
            "claims": [{
                "exclusive": True,
                "resource": {
                    "kind": "city_production_slot",
                    "owner_id": "city:3",
                },
            }],
            "provenance": [
                "current-authoritative-queue-byte-exact-match",
                "no-queue-action-submitted",
            ],
            "requirement_set": {
                "requirement_set_id": "requirement-set-capacity-proof",
                "premise_ids": ["city:3:owned"],
            },
            "shadow_only": True,
            "snapshot_id": snapshot.snapshot_id,
        },
        "turn": snapshot.turn,
        "type": "operation_proposed",
    }


def _terminal(snapshot, event_type, reason, product_ref=None):
    payload = {
        "mechanism": "fdas-replacement-capacity-retained-queue-lifecycle",
        "operation_id": "retained-capacity-operation-proof",
        "reason_code": reason,
    }
    if product_ref is not None:
        payload.update({
            "product_ref": product_ref,
            "resolution_snapshot_id": snapshot.snapshot_id,
            "resolution_status": "resolved_success",
        })
    return {
        "caused_by": ["cause"],
        "event_id": "retained-capacity-terminal-{}".format(event_type),
        "game_id": snapshot.identity.game_id,
        "payload": payload,
        "turn": snapshot.turn,
        "type": event_type,
    }


def _open_label(store=None):
    snapshot = _snapshot(10, 500)
    revision = _Revision(snapshot.snapshot_id)
    store = store or FdasRetainedCapacityOutcomeStore("capacity-proof")
    labeler = FdasRetainedCapacityOutcomeLabeler(store)
    label = labeler.open(
        _proposal(snapshot, revision), revision,
        snapshot.identity.game_id, snapshot.player_id)
    return labeler, label, snapshot


def test_retained_capacity_outcome_opens_idempotently_without_authority():
    labeler, label, snapshot = _open_label()
    revision = _Revision(snapshot.snapshot_id)

    repeated = labeler.open(
        _proposal(snapshot, revision), revision,
        snapshot.identity.game_id, snapshot.player_id)

    assert repeated == label
    assert label.status == "pending_product"
    assert label.source_city_id == 3
    assert label.target_city_id == 4
    assert label.production_target_name == "Musketeers"
    material = label.to_dict()
    assert all(material[name] is False for name in (
        "action_selection_changed", "induction_readout", "policy_authority",
        "readout_authority", "transition_value_estimated", "truth_mutated"))


def test_retained_capacity_product_waits_for_durable_exact_relief():
    labeler, pending, _snapshot_at_open = _open_label()
    product = _snapshot(14, 501)
    waiting = labeler.observe_lifecycle_event(
        _terminal(product, "operation_completed",
                  "authoritative-product-identity-observed", "unit:9"),
        product, "revision-product")

    assert waiting.status == "pending_relief"
    assert waiting.product_turn == 14
    assert waiting.due_turn == 46
    before = _snapshot(45, 502)
    assert labeler.observe_due_relief(
        waiting.label_id, before,
        _Revision(before.snapshot_id, deficit=False,
                  revision_id="revision-before")) == waiting

    due = _snapshot(46, 503)
    observed = labeler.observe_due_relief(
        waiting.label_id, due,
        _Revision(due.snapshot_id, deficit=False,
                  revision_id="revision-due"))

    assert observed.status == "observed"
    assert observed.outcome is True
    assert observed.outcome_kind == "durable-capacity-relief"
    assert observed.reason == "retained-capacity-relief-durable-at-due-turn"
    assert all(dict(observed.observed_value).values())


def test_retained_capacity_product_without_durable_unit_is_negative():
    labeler, _pending, _snapshot_at_open = _open_label()
    product = _snapshot(14, 504)
    waiting = labeler.observe_lifecycle_event(
        _terminal(product, "operation_completed",
                  "authoritative-product-identity-observed", "unit:9"),
        product, "revision-product")
    due = _snapshot(46, 505, product=False)

    observed = labeler.observe_due_relief(
        waiting.label_id, due,
        _Revision(due.snapshot_id, deficit=False,
                  revision_id="revision-negative"))

    assert observed.outcome is False
    assert "product-present" in observed.reason
    assert dict(observed.observed_value)["deficit_absent"] is True
    assert dict(observed.observed_value)["product_present"] is False


def test_retained_capacity_divergence_is_immediate_terminal_no_progress():
    labeler, pending, snapshot = _open_label()
    event = _terminal(
        snapshot, "operation_abandoned",
        "production-target-diverged-before-product-observation")

    observed = labeler.observe_lifecycle_event(
        event, snapshot, "revision-diverged")

    assert observed.status == "observed"
    assert observed.outcome is False
    assert observed.outcome_kind == "terminal-no-progress"
    assert observed.product_ref is None
    assert dict(observed.observed_value) == {
        "event_type": "operation_abandoned",
        "reason_code": (
            "production-target-diverged-before-product-observation"),
    }


def test_retained_capacity_store_survives_restart_and_quarantines_corruption(
        tmp_path):
    identity = "capacity-restart-proof"
    store = FdasRetainedCapacityOutcomeStore(identity)
    _labeler, label, _snapshot_at_open = _open_label(store)
    path = tmp_path / "capacity-outcomes.json"
    store.save(str(path))

    restarted = FdasRetainedCapacityOutcomeStore.load(str(path), identity)

    assert restarted.quarantined is False
    assert restarted.get(label.label_id) == label
    material = label.to_dict()
    material["policy_authority"] = True
    with pytest.raises(ValueError, match="grants authority"):
        FdasRetainedCapacityOutcomeLabel.from_dict(material)

    value = json.loads(path.read_text(encoding="utf-8"))
    value["store_digest"] = "corrupted"
    path.write_text(json.dumps(value), encoding="utf-8")
    quarantined = FdasRetainedCapacityOutcomeStore.load(str(path), identity)
    assert quarantined.quarantined is True


def test_retained_capacity_positive_encodes_goal_relief_without_learning():
    labeler, _pending, opened_snapshot = _open_label()
    product = _snapshot(14, 506)
    waiting = labeler.observe_lifecycle_event(
        _terminal(product, "operation_completed",
                  "authoritative-product-identity-observed", "unit:9"),
        product, "revision-product")
    due = _snapshot(46, 507)
    observed = labeler.observe_due_relief(
        waiting.label_id, due,
        _Revision(due.snapshot_id, deficit=False,
                  revision_id="revision-positive"))
    episode_store = DecisionEpisodeStore("capacity-episode-positive")
    bridge = FdasRetainedCapacityEpisodeBridge(episode_store)
    proposal = _proposal(
        opened_snapshot, _Revision(opened_snapshot.snapshot_id))

    episode = bridge.encode(observed, proposal)
    repeated = bridge.encode(observed, proposal)

    assert repeated == episode
    assert episode.outcome_status == "goal-relief-observed"
    assert dict(episode.realized_goal_relief) == {
        "fdas-goal-capacity-proof": 1.0}
    assert episode.prediction_ids == ()
    assert episode.execution_event_id is None
    assert dict(episode.context_signature)["action_submitted"] == "false"
    learning = FdasEpisodeLearningAdapter(episode_store, ())
    result = learning.apply(episode.episode_id)
    assert result.applied is False
    assert result.reason == "episode-requires-one-current-control-prediction"
    assert learning.metrics().calibration_sample_count == 0


def test_retained_capacity_product_without_relief_encodes_effect_only():
    labeler, _pending, opened_snapshot = _open_label()
    product = _snapshot(14, 508)
    waiting = labeler.observe_lifecycle_event(
        _terminal(product, "operation_completed",
                  "authoritative-product-identity-observed", "unit:9"),
        product, "revision-product")
    due = _snapshot(46, 509, product=False)
    observed = labeler.observe_due_relief(
        waiting.label_id, due,
        _Revision(due.snapshot_id, deficit=False,
                  revision_id="revision-negative"))
    bridge = FdasRetainedCapacityEpisodeBridge(
        DecisionEpisodeStore("capacity-episode-negative"))

    episode = bridge.encode(
        observed, _proposal(
            opened_snapshot, _Revision(opened_snapshot.snapshot_id)))

    assert episode.outcome_status == "effect-without-goal-relief"
    assert episode.realized_goal_relief == ()
    assert episode.attributed_effects == ({
        "effect": "exact-retained-capacity-product-observed",
        "product_ref": "unit:9",
        "product_snapshot_id": product.snapshot_id,
        "product_turn": 14,
        "production_target_name": "Musketeers",
    },)


def test_retained_capacity_terminal_divergence_encodes_no_effect():
    labeler, _pending, opened_snapshot = _open_label()
    observed = labeler.observe_lifecycle_event(
        _terminal(
            opened_snapshot, "operation_abandoned",
            "production-target-diverged-before-product-observation"),
        opened_snapshot, "revision-diverged")
    bridge = FdasRetainedCapacityEpisodeBridge(
        DecisionEpisodeStore("capacity-episode-no-effect"))

    episode = bridge.encode(
        observed, _proposal(
            opened_snapshot, _Revision(opened_snapshot.snapshot_id)))

    assert episode.outcome_status == "no-effect-observed"
    assert episode.attributed_effects == ()
    assert episode.realized_goal_relief == ()
    assert episode.observed_delta["product_ref"] is None


def test_retained_capacity_episode_bridge_rejects_pending_or_submitted_claim():
    _labeler, pending, opened_snapshot = _open_label()
    bridge = FdasRetainedCapacityEpisodeBridge(
        DecisionEpisodeStore("capacity-episode-rejection"))
    proposal = _proposal(
        opened_snapshot, _Revision(opened_snapshot.snapshot_id))

    with pytest.raises(ValueError, match="terminal label"):
        bridge.encode(pending, proposal)
    proposal["payload"]["provenance"].remove("no-queue-action-submitted")
    terminal = _terminal(
        opened_snapshot, "operation_abandoned",
        "production-target-diverged-before-product-observation")
    observed = _labeler.observe_lifecycle_event(
        terminal, opened_snapshot, "revision-diverged")
    with pytest.raises(ValueError, match="proposal evidence differs"):
        bridge.encode(observed, proposal)

    duplicated = _proposal(
        opened_snapshot, _Revision(opened_snapshot.snapshot_id))
    duplicated["payload"]["claims"] *= 2
    with pytest.raises(ValueError, match="resource claims are duplicated"):
        bridge.encode(observed, duplicated)


def _transition_query_fixture(turn=10, deadline=74):
    snapshot = _snapshot(turn, 600 + turn)
    revision = _Revision(snapshot.snapshot_id, revision_id="revision-query")
    proposal = _proposal(snapshot, revision)
    proposal["payload"]["deadline_turn"] = deadline
    store = FdasRetainedCapacityOutcomeStore("capacity-query-label")
    label = FdasRetainedCapacityOutcomeLabeler(store).open(
        proposal, revision, snapshot.identity.game_id, snapshot.player_id)
    return proposal, label, snapshot, revision


def test_retained_capacity_transition_query_is_proposal_time_abstention():
    proposal, label, snapshot, revision = _transition_query_fixture()

    query = FdasRetainedCapacityTransitionQueryBuilder.build(
        proposal, label, snapshot, revision)
    repeated = FdasRetainedCapacityTransitionQueryBuilder.build(
        proposal, label, snapshot, revision)

    assert repeated == query
    assert query.status == "abstained"
    assert query.reason == "insufficient-independent-calibration-evidence"
    assert (query.estimate, query.interval_lower, query.interval_upper,
            query.model_id) == (None, None, None, None)
    features = dict(query.features)
    assert features["action_category"] == "city_production"
    assert features["lifecycle_state"] == "retained-authoritative-queue"
    assert features["production_target"] == "musketeers"
    assert features["turn_phase_band"] == "0-39"
    assert features["completion_horizon_band"] == "33-64"
    assert features["cross_city_deficit"] == "true"
    assert features["exact_queue_match"] == "true"
    assert FdasRetainedCapacityTransitionQuery.from_dict(
        query.to_dict()) == query
    assert all(query.to_dict()[name] is False for name in (
        "action_selection_changed", "learning_authority",
        "policy_authority", "readout_authority",
        "transition_value_estimated", "truth_mutated"))


@pytest.mark.parametrize("value,expected", (
    (0, "0-39"), (39, "0-39"), (40, "40-79"),
    (79, "40-79"), (80, "80+")))
def test_retained_capacity_transition_turn_bands(value, expected):
    assert _turn_phase(value) == expected


@pytest.mark.parametrize("value,expected", (
    (1, "1-16"), (16, "1-16"), (17, "17-32"), (32, "17-32"),
    (33, "33-64"), (64, "33-64"), (65, "65+")))
def test_retained_capacity_transition_horizon_bands(value, expected):
    assert _horizon_band(value) == expected


@pytest.mark.parametrize("function,value,expected", (
    (_size_band, 1, "1"), (_size_band, 4, "2-4"),
    (_size_band, 5, "5-8"), (_size_band, 9, "9+"),
    (_surplus_band, -1, "negative"), (_surplus_band, 0, "zero"),
    (_surplus_band, 4, "1-4"), (_surplus_band, 5, "5+"),
    (_count_band, 0, "0"), (_count_band, 2, "2"),
    (_count_band, 3, "3+")))
def test_retained_capacity_transition_categorical_bands(
        function, value, expected):
    assert function(value) == expected


def test_retained_capacity_transition_query_fails_closed_on_stale_inputs():
    proposal, label, snapshot, revision = _transition_query_fixture()

    with pytest.raises(ValueError, match="snapshot differs"):
        FdasRetainedCapacityTransitionQueryBuilder.build(
            proposal, label, _snapshot(11, 701), revision)
    with pytest.raises(ValueError, match="revision differs"):
        FdasRetainedCapacityTransitionQueryBuilder.build(
            proposal, label, snapshot,
            _Revision(snapshot.snapshot_id, deficit=False))
    changed = copy.deepcopy(proposal)
    changed["payload"]["deadline_turn"] = label.proposed_turn
    with pytest.raises(ValueError, match="deadline differs"):
        FdasRetainedCapacityTransitionQueryBuilder.build(
            changed, label, snapshot, revision)


def test_retained_capacity_transition_query_store_roundtrip_and_quarantine(
        tmp_path):
    proposal, label, snapshot, revision = _transition_query_fixture()
    query = FdasRetainedCapacityTransitionQueryBuilder.build(
        proposal, label, snapshot, revision)
    store = FdasRetainedCapacityTransitionQueryStore("capacity-query-store")

    assert store.record(query) == query
    assert store.record(query) == query
    path = tmp_path / "capacity-transition-queries.json"
    store.save(str(path))
    loaded = FdasRetainedCapacityTransitionQueryStore.load(
        str(path), "capacity-query-store")
    assert loaded.quarantined is False
    assert loaded.queries() == (query,)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["store_digest"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    quarantined = FdasRetainedCapacityTransitionQueryStore.load(
        str(path), "capacity-query-store")
    assert quarantined.quarantined is True
