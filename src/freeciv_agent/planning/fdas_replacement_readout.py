"""Decision-safe recall of grounded coordinated defender replacements."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .fdas import ShadowOperationCandidate
from .fdas_replacement import FdasCoordinatedReplacementAdapter
from .operations import OperationState


COORDINATED_REPLACEMENT_READOUT_IDENTITY = (
    "fdas-coordinated-replacement-candidate-readout/1.0")
_DIRECT_MOVE_TYPE = "fdas-shadow:city-garrison-deficit:unit_move"
_REPLACEMENT_TYPE = "fdas-defense:coordinated-replacement"


def coordinated_replacement_pair_order_key(pair):
    """Order stable logical identity before arm-local operation hashes."""
    return (
        pair.replacement_actor_id,
        pair.reinforcement_actor_id,
        pair.source_city_id,
        pair.target_city_id,
        pair.lifecycle_operation_id,
    )


@dataclass(frozen=True)
class FdasCoordinatedReplacementPair:
    replacement_operation_id: str
    lifecycle_operation_id: str
    direct_operation_id: str
    replacement_action_key: str
    direct_action_key: str
    replacement_actor_id: int
    reinforcement_actor_id: int
    source_city_id: int
    target_city_id: int
    replacement_estimated_turns: int
    reinforcement_estimated_turns: int
    combined_estimated_turns: int
    replacement_movement_cost: int
    reinforcement_movement_cost: int
    combined_movement_cost: int
    requirement_context_hash: str
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.replacement_operation_id, "replacement operation ID"),
                (self.lifecycle_operation_id, "lifecycle operation ID"),
                (self.direct_operation_id, "direct operation ID"),
                (self.replacement_action_key, "replacement action key"),
                (self.direct_action_key, "direct action key"),
                (self.requirement_context_hash, "requirement context hash"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("replacement pair {} is required".format(name))
        for name in (
                "replacement_actor_id", "reinforcement_actor_id",
                "source_city_id", "target_city_id",
                "replacement_estimated_turns",
                "reinforcement_estimated_turns", "combined_estimated_turns",
                "replacement_movement_cost", "reinforcement_movement_cost",
                "combined_movement_cost"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("replacement pair {} is invalid".format(name))
        if (self.replacement_estimated_turns < 1
                or self.reinforcement_estimated_turns < 1
                or self.combined_estimated_turns
                != self.replacement_estimated_turns
                + self.reinforcement_estimated_turns
                or self.combined_movement_cost
                != self.replacement_movement_cost
                + self.reinforcement_movement_cost):
            raise ValueError("replacement pair route composition differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("replacement pair hash differs")

    def _semantic(self):
        return {
            "combined_estimated_turns": self.combined_estimated_turns,
            "combined_movement_cost": self.combined_movement_cost,
            "direct_action_key": self.direct_action_key,
            "direct_operation_id": self.direct_operation_id,
            "direct_unsafe_reason": "protected-source-garrison",
            "lifecycle_operation_id": self.lifecycle_operation_id,
            "replacement_action_key": self.replacement_action_key,
            "replacement_actor_id": self.replacement_actor_id,
            "replacement_estimated_turns": self.replacement_estimated_turns,
            "replacement_movement_cost": self.replacement_movement_cost,
            "replacement_operation_id": self.replacement_operation_id,
            "reinforcement_actor_id": self.reinforcement_actor_id,
            "reinforcement_estimated_turns": (
                self.reinforcement_estimated_turns),
            "reinforcement_movement_cost": self.reinforcement_movement_cost,
            "requirement_context_hash": self.requirement_context_hash,
            "safe_chain_grounded": True,
            "source_city_id": self.source_city_id,
            "target_city_id": self.target_city_id,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


@dataclass(frozen=True)
class FdasCoordinatedReplacementReadout:
    status: str
    reason: str
    snapshot_id: str
    revision_id: str
    replacement_candidate_count: int
    direct_candidate_count: int
    pairs: tuple
    rejected: tuple
    result_hash: str

    def __post_init__(self):
        if self.status not in ("eligible-shadow", "abstained"):
            raise ValueError("replacement readout status is invalid")
        for value, name in (
                (self.reason, "reason"), (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "replacement readout {} is required".format(name))
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value < 0 for value in (
                   self.replacement_candidate_count,
                   self.direct_candidate_count)):
            raise ValueError("replacement readout counts are invalid")
        pairs = tuple(self.pairs)
        rejected = tuple(sorted(set(str(value) for value in self.rejected)))
        if any(not isinstance(value, FdasCoordinatedReplacementPair)
               for value in pairs):
            raise TypeError("replacement readout pairs are untyped")
        if any(not value for value in rejected):
            raise ValueError("replacement readout rejection is invalid")
        if ((self.status == "eligible-shadow") != bool(pairs)):
            raise ValueError("replacement readout eligibility differs")
        object.__setattr__(self, "pairs", pairs)
        object.__setattr__(self, "rejected", rejected)
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("replacement readout hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "candidate_recall_changed": bool(self.pairs),
            "direct_candidate_count": self.direct_candidate_count,
            "identity": COORDINATED_REPLACEMENT_READOUT_IDENTITY,
            "pairs": [value.to_dict() for value in self.pairs],
            "policy_authority": False,
            "readout_authority": False,
            "reason": self.reason,
            "rejected": list(self.rejected),
            "replacement_candidate_count": (
                self.replacement_candidate_count),
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "transition_value_estimated": False,
            "truth_mutated": False,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


class FdasCoordinatedReplacementReadoutEvaluator:
    """Recall a safe two-step chain without assigning transition value."""

    def __init__(self, adapter):
        if not isinstance(adapter, FdasCoordinatedReplacementAdapter):
            raise TypeError("replacement readout requires lifecycle adapter")
        self.adapter = adapter

    @staticmethod
    def _city_id(value):
        if not isinstance(value, str) or not value.startswith("city:"):
            return None
        try:
            return int(value.split(":", 1)[1])
        except ValueError:
            return None

    @staticmethod
    def _route_valid(route, snapshot, origin, destination):
        return bool(
            route is not None and route.reachable
            and route.authority == "freeciv-server-pathfinder"
            and route.schema_version == "1.0"
            and route.turn == snapshot.turn
            and route.source_seq <= snapshot.identity.source_seq
            and route.origin_tile == origin
            and route.destination_tile == destination
            and route.estimated_turns >= 1)

    def _readout(self, snapshot, revision, replacements, directs,
                 pairs=(), rejected=()):
        status = "eligible-shadow" if pairs else "abstained"
        reason = (
            "grounded-safe-chain-recalled" if pairs else
            "no-grounded-safe-chain")
        semantic = {
            "action_selection_changed": False,
            "candidate_recall_changed": bool(pairs),
            "direct_candidate_count": len(directs),
            "identity": COORDINATED_REPLACEMENT_READOUT_IDENTITY,
            "pairs": [value.to_dict() for value in pairs],
            "policy_authority": False,
            "readout_authority": False,
            "reason": reason,
            "rejected": sorted(set(str(value) for value in rejected)),
            "replacement_candidate_count": len(replacements),
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
            "transition_value_estimated": False,
            "truth_mutated": False,
        }
        return FdasCoordinatedReplacementReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            len(replacements), len(directs), tuple(pairs),
            tuple(semantic["rejected"]), structural_hash(semantic))

    def evaluate(self, snapshot, revision, candidates):
        if (revision is None
                or revision.snapshot_id != snapshot.snapshot_id):
            raise ValueError("replacement readout requires current revision")
        candidates = tuple(candidates)
        if any(not isinstance(value, ShadowOperationCandidate)
               for value in candidates):
            raise TypeError("replacement readout requires shadow candidates")
        replacements = tuple(
            value for value in candidates
            if value.operation.operation_type == _REPLACEMENT_TYPE)
        directs = tuple(
            value for value in candidates
            if value.operation.operation_type == _DIRECT_MOVE_TYPE)
        pairs = []
        rejected = []
        for candidate in replacements:
            operation_id = candidate.operation.operation_id
            record = self.adapter.active_record_for(candidate.operation)
            if record is None:
                rejected.append(operation_id + ":active-lifecycle-unavailable")
                continue
            binding = self.adapter.binding(record.spec.operation_id)
            context = self.adapter.requirement_context(record.spec.operation_id)
            if (record.progress.state != OperationState.RESERVABLE
                    or binding is None or context is None
                    or context.snapshot_id != snapshot.snapshot_id
                    or context.blocked_premises
                    or binding.snapshot_id != snapshot.snapshot_id
                    or binding.action_key != candidate.action_key
                    or not binding.legal_bound):
                rejected.append(operation_id + ":current-step-not-reservable")
                continue
            participants = dict(
                (value.role, int(value.actor_id))
                for value in candidate.operation.participants)
            source_city_id = self._city_id(
                candidate.operation.steps[0].target_ref)
            target_city_id = self._city_id(candidate.operation.target_ref)
            replacement_id = participants.get("replacement")
            reinforcement_id = participants.get("reinforcement")
            direct_matches = tuple(
                value for value in directs
                if (value.operation.target_ref == candidate.operation.target_ref
                    and value.action.get("actor_id") == reinforcement_id
                    and value.legal_bound
                    and value.action_key in snapshot.legal_action_json
                    and "protected-source-garrison" in value.blockers))
            if len(direct_matches) != 1:
                rejected.append(
                    operation_id + ":protected-direct-control-count:{}".format(
                        len(direct_matches)))
                continue
            direct = direct_matches[0]
            source_city = snapshot.city(source_city_id)
            target_city = snapshot.city(target_city_id)
            replacement = snapshot.unit(replacement_id)
            reinforcement = snapshot.unit(reinforcement_id)
            if (source_city is None or target_city is None
                    or source_city.tile is None or target_city.tile is None
                    or replacement is None or reinforcement is None
                    or replacement.tile is None
                    or reinforcement.tile != source_city.tile):
                rejected.append(operation_id + ":participant-state-unavailable")
                continue
            replacement_route = snapshot.movement_route(
                replacement_id, source_city.tile)
            reinforcement_route = snapshot.movement_route(
                reinforcement_id, target_city.tile)
            if not self._route_valid(
                    replacement_route, snapshot, replacement.tile,
                    source_city.tile):
                rejected.append(operation_id + ":replacement-route-invalid")
                continue
            if not self._route_valid(
                    reinforcement_route, snapshot, reinforcement.tile,
                    target_city.tile):
                rejected.append(operation_id + ":reinforcement-route-invalid")
                continue
            if (record.spec.steps[0].maximum_attempts
                    != replacement_route.path_length + 1
                    or record.spec.steps[1].maximum_attempts
                    != reinforcement_route.path_length + 1):
                rejected.append(
                    operation_id + ":route-attempt-budget-mismatch")
                continue
            values = {
                "combined_estimated_turns": (
                    replacement_route.estimated_turns
                    + reinforcement_route.estimated_turns),
                "combined_movement_cost": (
                    replacement_route.total_movement_cost
                    + reinforcement_route.total_movement_cost),
                "direct_action_key": direct.action_key,
                "direct_operation_id": direct.operation.operation_id,
                "lifecycle_operation_id": record.spec.operation_id,
                "replacement_action_key": candidate.action_key,
                "replacement_actor_id": replacement_id,
                "replacement_estimated_turns": (
                    replacement_route.estimated_turns),
                "replacement_movement_cost": (
                    replacement_route.total_movement_cost),
                "replacement_operation_id": operation_id,
                "reinforcement_actor_id": reinforcement_id,
                "reinforcement_estimated_turns": (
                    reinforcement_route.estimated_turns),
                "reinforcement_movement_cost": (
                    reinforcement_route.total_movement_cost),
                "requirement_context_hash": context.context_hash,
                "source_city_id": source_city_id,
                "target_city_id": target_city_id,
            }
            semantic = {
                **values,
                "direct_unsafe_reason": "protected-source-garrison",
                "safe_chain_grounded": True,
            }
            pairs.append(FdasCoordinatedReplacementPair(
                **values, result_hash=structural_hash(semantic)))
        return self._readout(
            snapshot, revision, replacements, directs,
            tuple(sorted(pairs, key=lambda value: (
                value.replacement_operation_id, value.direct_operation_id))),
            tuple(rejected))
