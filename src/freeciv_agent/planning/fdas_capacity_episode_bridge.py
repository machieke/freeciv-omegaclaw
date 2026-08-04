"""Observation-only bridge from retained-capacity labels to episodes."""

from ..events.schema import structural_hash
from .fdas_capacity_outcomes import (
    FdasRetainedCapacityOutcomeLabel,
    RETAINED_CAPACITY_OUTCOME_TARGET,
)
from .fdas_episodes import (
    DecisionEpisode,
    DecisionEpisodeStore,
    EPISODE_SCHEMA_VERSION,
)


RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY = (
    "fdas-retained-capacity-episode-bridge/1.0")
_MECHANISM = "fdas-replacement-capacity-retained-queue-lifecycle"
_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_RELIEF_KEYS = frozenset((
    "deficit_absent", "product_at_source", "product_owned",
    "product_present", "product_type_matches",
    "source_city_owned_and_present", "target_city_owned_and_present",
))


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _one_provenance(label, prefix):
    values = tuple(
        value.split(":", 1)[1] for value in label.provenance_ids
        if value.startswith(prefix + ":"))
    if len(values) != 1 or not values[0]:
        raise ValueError("retained capacity label lacks one {}".format(prefix))
    return values[0]


class FdasRetainedCapacityEpisodeBridge(object):
    """Encode terminal observation semantics without enabling learning."""

    BRIDGE_IDENTITY = RETAINED_CAPACITY_EPISODE_BRIDGE_IDENTITY

    def __init__(self, store):
        if not isinstance(store, DecisionEpisodeStore):
            raise TypeError("retained capacity episode bridge needs a store")
        self.store = store

    @staticmethod
    def _validate(label, proposal_event):
        if not isinstance(label, FdasRetainedCapacityOutcomeLabel):
            raise TypeError("retained capacity episode needs a typed label")
        if label.status != "observed":
            raise ValueError("retained capacity episode requires terminal label")
        if label.target_id != RETAINED_CAPACITY_OUTCOME_TARGET:
            raise ValueError("retained capacity episode target differs")
        if not isinstance(proposal_event, dict):
            raise TypeError("retained capacity episode needs proposal evidence")
        payload = proposal_event.get("payload", {})
        if (proposal_event.get("type") != "operation_proposed"
                or payload.get("mechanism") != _MECHANISM
                or payload.get("operation_type") != _OPERATION_TYPE
                or payload.get("operation_id") != label.operation_id
                or payload.get("operation_digest") != label.operation_digest
                or proposal_event.get("game_id") != label.game_id
                or proposal_event.get("turn") != label.proposed_turn
                or payload.get("snapshot_id") != label.proposed_snapshot_id
                or payload.get("policy_authority") is not False
                or payload.get("shadow_only") is not True
                or "no-queue-action-submitted" not in payload.get(
                    "provenance", ())):
            raise ValueError("retained capacity proposal evidence differs")
        if ("proposal-event:" + _required_text(
                proposal_event.get("event_id"), "proposal event ID")
                not in label.provenance_ids):
            raise ValueError("retained capacity proposal provenance differs")
        next_action = payload.get("next_action")
        requirement_set = payload.get("requirement_set")
        goal_ids = tuple(payload.get("goal_ids", ()))
        if (not isinstance(next_action, dict)
                or next_action.get("action_type") != "city_production"
                or not isinstance(next_action.get("target"), dict)
                or next_action["target"].get("production_type")
                    != label.production_target_name
                or not isinstance(requirement_set, dict)
                or not goal_ids
                or any(not isinstance(value, str) or not value
                       for value in goal_ids)
                or len(goal_ids) != len(set(goal_ids))):
            raise ValueError("retained capacity episode grounding differs")
        claims = tuple(payload.get("claims", ()))
        if any(not isinstance(value, dict) for value in claims):
            raise ValueError("retained capacity episode claims differ")
        return payload, next_action, requirement_set, goal_ids, claims

    def encode(self, label, proposal_event):
        """Record one idempotent terminal episode with no model prediction."""
        if self.store.quarantined:
            raise ValueError("quarantined episode store cannot encode capacity")
        payload, action, requirement_set, goal_ids, claims = self._validate(
            label, proposal_event)
        before_revision_id = _one_provenance(label, "proposal-revision")
        after_revision_id = _required_text(
            label.observed_revision_id, "capacity outcome revision ID")
        action_key = structural_hash(action)
        requirement_set_id = _required_text(
            requirement_set.get("requirement_set_id"), "requirement set ID")
        context = tuple(sorted({
            "action_submitted": "false",
            "episode_domain": "retained-replacement-capacity",
            "operation_type": _OPERATION_TYPE,
            "outcome_target": RETAINED_CAPACITY_OUTCOME_TARGET,
            "production_target_name": label.production_target_name,
            "proposed_turn": str(label.proposed_turn),
            "queue_acceptance": "already-authoritative-observed",
            "requirement_set_id": requirement_set_id,
            "selection_policy_authority": "false",
            "source_city_id": str(label.source_city_id),
            "target_city_id": str(label.target_city_id),
        }.items()))
        episode_material = {
            "action_key": action_key,
            "before_revision_id": before_revision_id,
            "bridge_identity": self.BRIDGE_IDENTITY,
            "operation_id": label.operation_id,
            "schema_version": EPISODE_SCHEMA_VERSION,
        }
        delta = {
            "action_submitted": False,
            "label_id": label.label_id,
            "observed_turn": label.observed_turn,
            "observed_value": dict(label.observed_value),
            "outcome_kind": label.outcome_kind,
            "product_ref": label.product_ref,
            "product_turn": label.product_turn,
            "queue_acceptance": "already-authoritative-observed",
            "reason": label.reason,
            "relief_due_turn": label.due_turn,
        }
        effects = ()
        relief = ()
        if label.outcome_kind == "terminal-no-progress":
            terminal_values = dict(label.observed_value)
            if (label.outcome is not False or label.product_ref is not None
                    or frozenset(terminal_values) != {
                        "event_type", "reason_code"}
                    or terminal_values.get("event_type") not in (
                        "operation_abandoned", "operation_expired",
                        "operation_failed")
                    or not isinstance(terminal_values.get("reason_code"), str)
                    or not terminal_values["reason_code"]):
                raise ValueError("terminal no-progress episode differs")
            outcome_status = "no-effect-observed"
        elif label.outcome_kind == "durable-capacity-relief":
            if not isinstance(label.product_ref, str):
                raise ValueError("capacity effect lacks exact product")
            relief_values = dict(label.observed_value)
            if (frozenset(relief_values) != _RELIEF_KEYS
                    or label.outcome is not all(relief_values.values())):
                raise ValueError("durable capacity relief evidence differs")
            effects = ({
                "effect": "exact-retained-capacity-product-observed",
                "product_ref": label.product_ref,
                "product_snapshot_id": label.product_snapshot_id,
                "product_turn": label.product_turn,
                "production_target_name": label.production_target_name,
            },)
            if label.outcome is True:
                outcome_status = "goal-relief-observed"
                relief = tuple((goal_id, 1.0) for goal_id in goal_ids)
            elif label.outcome is False:
                outcome_status = "effect-without-goal-relief"
            else:
                raise ValueError("durable capacity outcome differs")
        else:
            raise ValueError("retained capacity outcome kind differs")
        resource_claim_ids = tuple(sorted(
            "resource-claim:" + structural_hash(value) for value in claims))
        if len(resource_claim_ids) != len(set(resource_claim_ids)):
            raise ValueError("retained capacity resource claims are duplicated")
        grounding_ids = tuple(sorted((
            "operation-digest:" + label.operation_digest,
            "requirement-set:" + requirement_set_id,
        )))
        provenance = tuple(sorted(set(label.provenance_ids + (
            self.BRIDGE_IDENTITY,
            "action-submitted:false",
            "learning-authority:false",
            "outcome-label:" + label.label_id,
            "prediction-readout:false",
            "proposal-event:" + proposal_event["event_id"],
            "queue-acceptance:already-authoritative-observed",
        ))))
        episode = DecisionEpisode(
            EPISODE_SCHEMA_VERSION,
            "episode-" + structural_hash(episode_material)[:32],
            label.game_id,
            label.player_id,
            label.operation_id,
            action_key,
            before_revision_id,
            after_revision_id,
            tuple(goal_ids),
            context,
            (label.deficit_atom_id,),
            (),
            grounding_ids,
            (),
            resource_claim_ids,
            structural_hash(requirement_set),
            None,
            delta,
            effects,
            relief,
            outcome_status,
            provenance,
        )
        prior = self.store.get(episode.episode_id)
        if prior is not None:
            if prior != episode:
                raise ValueError("retained capacity episode identity collision")
            return prior
        return self.store.record(episode)
