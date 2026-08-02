"""Fail-closed binding and authoritative return for FDAS observations.

The bridge cannot choose an action.  It may bind a packet-committed
observation only to a byte-identical legacy-selected legal scout move.  An
evidence token is registered only after exact commit revalidation and a fresh
authoritative snapshot proves both the move and its visibility result.
"""

from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure import (
    EvidenceLedger,
    EvidenceToken,
    ObservationEvidenceGate,
    ObservationPolicy,
    ObservationSelectionRecord,
)


_EXPANDED = "visibility-expanded"
_UNCHANGED = "no-visibility-expansion"
_RETURN_SOURCE = "authoritative-player-visibility-delta"


def _identity_value(snapshot, name):
    identity = getattr(snapshot, "identity", None)
    value = getattr(identity, name, None)
    if value is None:
        raise ValueError("observation snapshot lacks {}".format(name))
    return value


@dataclass(frozen=True)
class FdasObservationActionBinding:
    operation_id: str
    goal_id: str
    atom_id: str
    snapshot_id: str
    game_id: str
    player_id: int
    source_seq: int
    legal_actions_digest: str
    action: object
    action_key: str
    outcome_ids: tuple
    packet_schedule_hash: str
    selection_record: ObservationSelectionRecord
    binding_hash: str

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.goal_id, "goal ID"),
                (self.atom_id, "atom ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.game_id, "game ID"),
                (self.legal_actions_digest, "legal-action digest"),
                (self.action_key, "action key"),
                (self.packet_schedule_hash, "packet schedule hash"),
                (self.binding_hash, "binding hash")):
            if not str(value):
                raise ValueError("observation binding requires {}".format(name))
        if not isinstance(self.selection_record, ObservationSelectionRecord):
            raise TypeError("observation binding requires selection record")
        if not self.selection_record.selected:
            raise ValueError("observation binding requires selected operation")
        if self.selection_record.operation_id != self.operation_id:
            raise ValueError("observation binding selection mismatch")
        canonical = canonical_json_bytes(self.action).decode("utf-8")
        if canonical != self.action_key:
            raise ValueError("observation action key is not canonical")
        if tuple(sorted(set(self.outcome_ids))) != self.outcome_ids:
            raise ValueError("observation outcome IDs must be unique and sorted")

    def to_dict(self):
        return {
            "action": self.action,
            "action_key": self.action_key,
            "atom_id": self.atom_id,
            "binding_hash": self.binding_hash,
            "game_id": self.game_id,
            "goal_id": self.goal_id,
            "legal_actions_digest": self.legal_actions_digest,
            "operation_id": self.operation_id,
            "outcome_ids": list(self.outcome_ids),
            "packet_schedule_hash": self.packet_schedule_hash,
            "player_id": int(self.player_id),
            "policy_authority": False,
            "selection_record": self.selection_record.to_dict(),
            "snapshot_id": self.snapshot_id,
            "source_seq": int(self.source_seq),
        }


@dataclass(frozen=True)
class FdasObservationCommitValidation:
    status: str
    reason: object
    binding_hash: str
    current_snapshot_id: str
    result_hash: str

    def __post_init__(self):
        if self.status not in ("committed", "rejected"):
            raise ValueError("unknown observation commit status")
        if self.status == "committed" and self.reason is not None:
            raise ValueError("committed observation cannot have rejection reason")
        if self.status == "rejected" and not self.reason:
            raise ValueError("rejected observation requires reason")

    @property
    def committed(self):
        return self.status == "committed"

    def to_dict(self):
        return {
            "binding_hash": self.binding_hash,
            "current_snapshot_id": self.current_snapshot_id,
            "policy_authority": False,
            "reason": self.reason,
            "result_hash": self.result_hash,
            "status": self.status,
        }


@dataclass(frozen=True)
class FdasObservationAuthoritativeReturn:
    operation_id: str
    binding_hash: str
    before_snapshot_id: str
    after_snapshot_id: str
    action_event_id: str
    outcome_id: str
    new_visible_tile_ids: tuple
    evidence_token: EvidenceToken
    return_hash: str

    def to_dict(self):
        return {
            "action_event_id": self.action_event_id,
            "after_snapshot_id": self.after_snapshot_id,
            "before_snapshot_id": self.before_snapshot_id,
            "binding_hash": self.binding_hash,
            "evidence_token": self.evidence_token.to_dict(),
            "new_visible_tile_ids": list(self.new_visible_tile_ids),
            "operation_id": self.operation_id,
            "outcome_id": self.outcome_id,
            "policy_authority": False,
            "return_hash": self.return_hash,
            "truth_mutated_only_after_authoritative_return": True,
        }


@dataclass(frozen=True)
class FdasObservationReturnAbstention:
    operation_id: str
    binding_hash: str
    before_snapshot_id: str
    after_snapshot_id: str
    action_event_id: str
    reason: str
    observed_visible_tile_ids: tuple
    abstention_hash: str

    def to_dict(self):
        return {
            "abstention_hash": self.abstention_hash,
            "action_event_id": self.action_event_id,
            "after_snapshot_id": self.after_snapshot_id,
            "before_snapshot_id": self.before_snapshot_id,
            "binding_hash": self.binding_hash,
            "evidence_registered": False,
            "observed_visible_tile_ids": list(
                self.observed_visible_tile_ids),
            "operation_id": self.operation_id,
            "policy_authority": False,
            "reason": self.reason,
            "truth_mutated": False,
        }


class FdasObservationExecutionBridge(object):
    """Bind selected visibility tests to legacy moves and gate their return."""

    BRIDGE_IDENTITY = "fdas-observation-execution-bridge/1.0"

    def __init__(self, evidence_gate=None):
        self.evidence_gate = evidence_gate or ObservationEvidenceGate(
            EvidenceLedger())
        if not isinstance(self.evidence_gate, ObservationEvidenceGate):
            raise TypeError("observation bridge requires evidence gate")

    @property
    def evidence_ledger(self):
        return self.evidence_gate.evidence_ledger

    @staticmethod
    def _selected(decision):
        selected_ids = tuple(decision.get("selected_operation_ids", ()))
        if len(selected_ids) != 1:
            raise ValueError("observation binding requires one packet commit")
        operation_id = selected_ids[0]
        operations = tuple(
            value for value in decision.get("operations", ())
            if value.operation_id == operation_id)
        records = tuple(
            value for value in decision.get("selection_records", ())
            if value.operation_id == operation_id and value.selected)
        reservations = tuple(
            value for value in decision["packet_schedule"].reservations
            if value.operation_id == operation_id and value.state == "committed")
        if len(operations) != 1 or len(records) != 1 or len(reservations) != 1:
            raise ValueError(
                "selected observation lacks unique operation/record/reservation")
        return operations[0], records[0]

    def bind(self, decision, snapshot, legacy_action):
        operation, record = self._selected(decision)
        action = dict(legacy_action)
        if (action.get("action_type") != "unit_move"
                or isinstance(action.get("actor_id"), bool)
                or not isinstance(action.get("actor_id"), int)
                or not isinstance(action.get("target"), dict)
                or set(action["target"]) != {"x", "y"}
                or any(isinstance(action["target"][key], bool)
                       or not isinstance(action["target"][key], int)
                       for key in ("x", "y"))):
            raise ValueError("observation bridge accepts exact unit_move only")
        action_key = canonical_json_bytes(action).decode("utf-8")
        if action_key not in snapshot.legal_action_json:
            raise ValueError("legacy-selected observation action is not legal")
        value = operation.payload.get("expected_information_value", {})
        test = value.get("test", {})
        if test.get("execution_kind", "observation") != "observation":
            raise ValueError("simulation cannot bind to observation action")
        outcome_ids = tuple(sorted(
            str(row["outcome_id"]) for row in test.get("outcomes", ())))
        if outcome_ids != tuple(sorted((_EXPANDED, _UNCHANGED))):
            raise ValueError(
                "visibility binding requires complete visibility outcomes")
        packet_hash = structural_hash(
            decision["packet_schedule"].to_dict())
        semantic = {
            "action": action,
            "atom_id": operation.atom_id,
            "bridge_identity": self.BRIDGE_IDENTITY,
            "game_id": str(_identity_value(snapshot, "game_id")),
            "goal_id": record.goal_id,
            "legal_actions_digest": str(snapshot.legal_actions_digest),
            "operation_id": operation.operation_id,
            "outcome_ids": list(outcome_ids),
            "packet_schedule_hash": packet_hash,
            "player_id": int(snapshot.player_id),
            "snapshot_id": snapshot.snapshot_id,
            "source_seq": int(_identity_value(snapshot, "source_seq")),
        }
        binding = FdasObservationActionBinding(
            operation.operation_id,
            record.goal_id,
            operation.atom_id,
            snapshot.snapshot_id,
            str(_identity_value(snapshot, "game_id")),
            int(snapshot.player_id),
            int(_identity_value(snapshot, "source_seq")),
            str(snapshot.legal_actions_digest),
            action,
            action_key,
            outcome_ids,
            packet_hash,
            record,
            structural_hash(semantic))
        self.evidence_gate.record_selection(record)
        return binding

    @staticmethod
    def revalidate(binding, current_snapshot, legacy_action):
        if not isinstance(binding, FdasObservationActionBinding):
            raise TypeError("observation commit requires binding")
        action_key = canonical_json_bytes(legacy_action).decode("utf-8")
        reason = None
        if current_snapshot.snapshot_id != binding.snapshot_id:
            reason = "observation-snapshot-changed"
        elif int(_identity_value(current_snapshot, "source_seq")) != \
                binding.source_seq:
            reason = "observation-source-sequence-changed"
        elif str(current_snapshot.legal_actions_digest) != \
                binding.legal_actions_digest:
            reason = "observation-legal-set-changed"
        elif action_key != binding.action_key:
            reason = "legacy-selected-observation-action-changed"
        elif binding.action_key not in current_snapshot.legal_action_json:
            reason = "observation-action-no-longer-legal"
        semantic = {
            "binding_hash": binding.binding_hash,
            "current_legal_actions_digest": str(
                current_snapshot.legal_actions_digest),
            "current_snapshot_id": current_snapshot.snapshot_id,
            "reason": reason,
            "status": "committed" if reason is None else "rejected",
            "validator": "fdas-observation-commit-validator/1.0",
        }
        return FdasObservationCommitValidation(
            semantic["status"], reason, binding.binding_hash,
            current_snapshot.snapshot_id, structural_hash(semantic))

    def authoritative_return(
            self, binding, validation, before_snapshot, after_snapshot,
            action_result):
        if not isinstance(binding, FdasObservationActionBinding):
            raise TypeError("observation return requires binding")
        if (not isinstance(validation, FdasObservationCommitValidation)
                or not validation.committed
                or validation.binding_hash != binding.binding_hash):
            raise ValueError("observation return lacks committed validation")
        if before_snapshot.snapshot_id != binding.snapshot_id:
            raise ValueError("observation return before snapshot mismatch")
        if (str(_identity_value(before_snapshot, "game_id")) != binding.game_id
                or int(before_snapshot.player_id) != binding.player_id
                or int(_identity_value(before_snapshot, "source_seq"))
                != binding.source_seq
                or str(before_snapshot.legal_actions_digest)
                != binding.legal_actions_digest):
            raise ValueError("observation return before authority mismatch")
        if (str(_identity_value(after_snapshot, "game_id")) != binding.game_id
                or int(after_snapshot.player_id) != binding.player_id):
            raise ValueError("observation return authority identity mismatch")
        if int(_identity_value(after_snapshot, "source_seq")) <= \
                binding.source_seq:
            raise ValueError("observation return is not a fresh snapshot")
        action = binding.action
        target = action["target"]
        target_tile = (
            int(target["y"]) * int(after_snapshot.map_width)
            + int(target["x"]))
        actor = after_snapshot.unit(action["actor_id"])
        if actor is None or actor.tile != target_tile:
            raise ValueError("authoritative snapshot does not prove scout move")
        if (int(after_snapshot.map_width) != int(before_snapshot.map_width)
                or int(after_snapshot.map_height)
                != int(before_snapshot.map_height)):
            raise ValueError("observation return map identity changed")
        new_tiles = tuple(sorted(
            set(after_snapshot.visible_tile_ids)
            - set(before_snapshot.visible_tile_ids)))
        outcome_id = _EXPANDED if new_tiles else _UNCHANGED
        if outcome_id not in binding.outcome_ids:
            raise ValueError("authoritative outcome was not predeclared")
        if (not isinstance(action_result, dict)
                or action_result.get("status") != "accepted"
                or not str(action_result.get("event_id") or "")):
            raise ValueError(
                "observation return requires accepted action result")
        action_event_id = str(action_result["event_id"])
        return_material = {
            "action_event_id": str(action_event_id),
            "after_snapshot_id": after_snapshot.snapshot_id,
            "before_snapshot_id": before_snapshot.snapshot_id,
            "binding_hash": binding.binding_hash,
            "new_visible_tile_ids": list(new_tiles),
            "operation_id": binding.operation_id,
            "outcome_id": outcome_id,
            "source_seq": int(_identity_value(after_snapshot, "source_seq")),
        }
        return_hash = structural_hash(return_material)
        policy = ObservationPolicy(
            binding.goal_id,
            "observe",
            binding.selection_record.priority,
            propensity=binding.selection_record.propensity)
        token = EvidenceToken(
            "observation-return-" + return_hash[:24],
            1.0 if new_tiles else 0.0,
            1.0,
            int(after_snapshot.turn),
            decay_class="visibility",
            source=_RETURN_SOURCE,
            observation_policy=policy)
        registered = self.evidence_gate.authoritative_return(
            binding.operation_id, token, authoritative=True)
        result = FdasObservationAuthoritativeReturn(
            binding.operation_id,
            binding.binding_hash,
            before_snapshot.snapshot_id,
            after_snapshot.snapshot_id,
            str(action_event_id),
            outcome_id,
            new_tiles,
            registered,
            return_hash)
        return result

    @staticmethod
    def abstain_return(
            binding, validation, before_snapshot, after_snapshot,
            action_result, reason):
        """Record a fresh but unattributable return without evidence."""
        allowed = frozenset((
            "actor-removed-before-observation-proof",
            "action-endpoint-not-reached",
        ))
        if reason not in allowed:
            raise ValueError("unknown observation return abstention")
        if not isinstance(binding, FdasObservationActionBinding):
            raise TypeError("observation abstention requires binding")
        if (not isinstance(validation, FdasObservationCommitValidation)
                or not validation.committed
                or validation.binding_hash != binding.binding_hash):
            raise ValueError("observation abstention lacks committed validation")
        if (before_snapshot.snapshot_id != binding.snapshot_id
                or str(_identity_value(before_snapshot, "game_id"))
                != binding.game_id
                or int(before_snapshot.player_id) != binding.player_id
                or int(_identity_value(before_snapshot, "source_seq"))
                != binding.source_seq):
            raise ValueError("observation abstention before authority mismatch")
        if (str(_identity_value(after_snapshot, "game_id")) != binding.game_id
                or int(after_snapshot.player_id) != binding.player_id
                or int(_identity_value(after_snapshot, "source_seq"))
                <= binding.source_seq):
            raise ValueError("observation abstention lacks fresh authority")
        if (not isinstance(action_result, dict)
                or action_result.get("status") != "accepted"
                or not str(action_result.get("event_id") or "")):
            raise ValueError(
                "observation abstention requires accepted action result")
        material = {
            "action_event_id": str(action_result["event_id"]),
            "after_snapshot_id": after_snapshot.snapshot_id,
            "before_snapshot_id": before_snapshot.snapshot_id,
            "binding_hash": binding.binding_hash,
            "observed_visible_tile_ids": list(
                after_snapshot.visible_tile_ids),
            "operation_id": binding.operation_id,
            "reason": reason,
            "source_seq": int(_identity_value(after_snapshot, "source_seq")),
        }
        return FdasObservationReturnAbstention(
            binding.operation_id,
            binding.binding_hash,
            before_snapshot.snapshot_id,
            after_snapshot.snapshot_id,
            str(action_result["event_id"]),
            reason,
            tuple(sorted(set(after_snapshot.visible_tile_ids))),
            structural_hash(material))
