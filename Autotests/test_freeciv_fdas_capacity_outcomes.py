import copy
import json
import os
from types import SimpleNamespace

import pytest

from freeciv_agent.planning import (
    FdasRetainedCapacityOutcomeLabel,
    FdasRetainedCapacityOutcomeLabeler,
    FdasRetainedCapacityOutcomeStore,
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
            "policy_authority": False,
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
