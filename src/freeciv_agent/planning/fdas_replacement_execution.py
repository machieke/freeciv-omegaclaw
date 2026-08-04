"""Claim-ineligible bounded execution pilot for one replacement chain."""

from dataclasses import dataclass, replace
import json
import os
import tempfile

from ..events.schema import canonical_json_bytes, structural_hash
from .fdas_replacement import FdasCoordinatedReplacementAdapter
from .fdas_replacement_readout import (
    FdasCoordinatedReplacementReadout,
    coordinated_replacement_pair_order_key,
)
from .operations import (
    OperationAuthorityKind,
    OperationAuthorityReadout,
    OperationState,
    TERMINAL_OPERATION_STATES,
)


REPLACEMENT_EXECUTION_SCHEMA_VERSION = 1
REPLACEMENT_EXECUTION_TREATMENT_ID = (
    "fdas-coordinated-replacement-bounded-execution-pilot/1.0")
REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT = (
    "game-first-grounded-coordinated-replacement-chain/1.0")


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


@dataclass(frozen=True)
class FdasReplacementExecutionAttempt:
    attempt_index: int
    operation_id: str
    operation_spec_digest: str
    step_index: int
    step_id: str
    turn: int
    snapshot_id: str
    legal_actions_digest: str
    action_key: str
    accepted: bool
    result_event_id: str
    reason: str
    state_digest: str

    def __post_init__(self):
        for value, name in (
                (self.attempt_index, "attempt index"),
                (self.step_index, "step index"),
                (self.turn, "turn")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("replacement execution {} is invalid".format(
                    name))
        for value, name in (
                (self.operation_id, "operation ID"),
                (self.operation_spec_digest, "operation spec digest"),
                (self.step_id, "step ID"),
                (self.snapshot_id, "snapshot ID"),
                (self.legal_actions_digest, "legal-action digest"),
                (self.action_key, "action key"),
                (self.result_event_id, "result event ID"),
                (self.reason, "reason"),
                (self.state_digest, "state digest")):
            _required_text(value, name)
        if not isinstance(self.accepted, bool):
            raise TypeError("replacement execution acceptance must be boolean")
        if self.state_digest != structural_hash(self._semantic()):
            raise ValueError("replacement execution attempt digest differs")

    def _semantic(self):
        return {
            "accepted": self.accepted,
            "action_key": self.action_key,
            "attempt_index": self.attempt_index,
            "legal_actions_digest": self.legal_actions_digest,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "reason": self.reason,
            "result_event_id": self.result_event_id,
            "snapshot_id": self.snapshot_id,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "turn": self.turn,
        }

    def to_dict(self):
        return {
            **self._semantic(),
            "claim_eligible": False,
            "randomized": False,
            "state_digest": self.state_digest,
            "truth_mutated": False,
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            value["attempt_index"], value["operation_id"],
            value["operation_spec_digest"], value["step_index"],
            value["step_id"], value["turn"], value["snapshot_id"],
            value["legal_actions_digest"], value["action_key"],
            value["accepted"], value["result_event_id"], value["reason"],
            value["state_digest"])


@dataclass(frozen=True)
class FdasReplacementExecutionAssignment:
    schema_version: int
    assignment_id: str
    treatment_id: str
    assignment_unit: str
    experiment_id: str
    game_id: str
    player_id: int
    operation_id: str
    operation_spec_digest: str
    replacement_actor_id: int
    reinforcement_actor_id: int
    source_city_id: int
    target_city_id: int
    assignment_turn: int
    assignment_snapshot_id: str
    attempts: tuple
    terminal_state: object
    terminal_reason: object

    def __post_init__(self):
        if self.schema_version != REPLACEMENT_EXECUTION_SCHEMA_VERSION:
            raise ValueError("unsupported replacement execution schema")
        if self.treatment_id != REPLACEMENT_EXECUTION_TREATMENT_ID:
            raise ValueError("replacement execution treatment differs")
        if self.assignment_unit != REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT:
            raise ValueError("replacement execution assignment unit differs")
        for value, name in (
                (self.assignment_id, "assignment ID"),
                (self.experiment_id, "experiment ID"),
                (self.game_id, "game ID"),
                (self.operation_id, "operation ID"),
                (self.operation_spec_digest, "operation spec digest"),
                (self.assignment_snapshot_id, "assignment snapshot ID")):
            _required_text(value, name)
        for value, name in (
                (self.player_id, "player ID"),
                (self.replacement_actor_id, "replacement actor ID"),
                (self.reinforcement_actor_id, "reinforcement actor ID"),
                (self.source_city_id, "source city ID"),
                (self.target_city_id, "target city ID"),
                (self.assignment_turn, "assignment turn")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("replacement execution {} is invalid".format(
                    name))
        attempts = tuple(self.attempts)
        if any(not isinstance(value, FdasReplacementExecutionAttempt)
               for value in attempts):
            raise TypeError("replacement execution attempts are untyped")
        if tuple(value.attempt_index for value in attempts) != tuple(
                range(len(attempts))):
            raise ValueError("replacement execution attempts are not contiguous")
        if any(value.operation_id != self.operation_id
               or value.operation_spec_digest != self.operation_spec_digest
               for value in attempts):
            raise ValueError("replacement execution attempt identity differs")
        object.__setattr__(self, "attempts", attempts)
        if self.terminal_state is None:
            if self.terminal_reason is not None:
                raise ValueError("nonterminal execution has terminal reason")
        else:
            if self.terminal_state not in tuple(
                    value.value for value in TERMINAL_OPERATION_STATES):
                raise ValueError("replacement execution terminal state differs")
            _required_text(self.terminal_reason, "terminal reason")
        expected = "replacement-execution-assignment-" + structural_hash(
            self.identity_material)[:24]
        if self.assignment_id != expected:
            raise ValueError("replacement execution assignment identity differs")

    @property
    def identity_material(self):
        return {
            "assignment_snapshot_id": self.assignment_snapshot_id,
            "assignment_turn": self.assignment_turn,
            "assignment_unit": self.assignment_unit,
            "experiment_id": self.experiment_id,
            "game_id": self.game_id,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "player_id": self.player_id,
            "reinforcement_actor_id": self.reinforcement_actor_id,
            "replacement_actor_id": self.replacement_actor_id,
            "schema_version": self.schema_version,
            "source_city_id": self.source_city_id,
            "target_city_id": self.target_city_id,
            "treatment_id": self.treatment_id,
        }

    @property
    def state_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def to_dict(self, include_digest=True):
        value = dict(self.identity_material)
        value.update({
            "assigned_arm": "treatment",
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "claim_eligible": False,
            "randomized": False,
            "terminal_reason": self.terminal_reason,
            "terminal_state": self.terminal_state,
            "truth_mutated": False,
        })
        value["assignment_id"] = self.assignment_id
        if include_digest:
            value["state_digest"] = self.state_digest
        return value

    @classmethod
    def from_dict(cls, value):
        if (value.get("assigned_arm") != "treatment"
                or value.get("claim_eligible") is not False
                or value.get("randomized") is not False
                or value.get("truth_mutated") is not False):
            raise ValueError("replacement execution assignment boundary differs")
        assignment = cls(
            value["schema_version"], value["assignment_id"],
            value["treatment_id"], value["assignment_unit"],
            value["experiment_id"], value["game_id"], value["player_id"],
            value["operation_id"], value["operation_spec_digest"],
            value["replacement_actor_id"], value["reinforcement_actor_id"],
            value["source_city_id"], value["target_city_id"],
            value["assignment_turn"], value["assignment_snapshot_id"],
            tuple(FdasReplacementExecutionAttempt.from_dict(row)
                  for row in value.get("attempts", ())),
            value.get("terminal_state"), value.get("terminal_reason"))
        if (value.get("state_digest") is not None
                and value["state_digest"] != assignment.state_digest):
            raise ValueError("replacement execution assignment digest differs")
        return assignment


class FdasReplacementExecutionStore(object):
    """Atomic one-assignment treatment store."""

    STORE_IDENTITY = "fdas-replacement-execution-store/1.0"

    def __init__(self, persistence_identity, assignment=None,
                 quarantine_reason=None):
        _required_text(persistence_identity, "execution store identity")
        if assignment is not None and not isinstance(
                assignment, FdasReplacementExecutionAssignment):
            raise TypeError("replacement execution store assignment is untyped")
        if quarantine_reason is not None:
            _required_text(quarantine_reason, "execution quarantine reason")
        self.persistence_identity = persistence_identity
        self.assignment = assignment
        self.quarantine_reason = quarantine_reason

    @property
    def quarantined(self):
        return self.quarantine_reason is not None

    @property
    def store_digest(self):
        return structural_hash(self.to_dict(include_digest=False))

    def record(self, assignment):
        if self.quarantined:
            raise ValueError("quarantined replacement execution store")
        if not isinstance(assignment, FdasReplacementExecutionAssignment):
            raise TypeError("replacement execution assignment is untyped")
        if self.assignment is None:
            self.assignment = assignment
            return assignment
        if self.assignment.assignment_id != assignment.assignment_id:
            raise ValueError("replacement execution cannot reassign a game")
        if self.assignment.identity_material != assignment.identity_material:
            raise ValueError("replacement execution assignment changed")
        if self.assignment.terminal_state is not None and self.assignment != assignment:
            raise ValueError("terminal replacement execution is immutable")
        if len(assignment.attempts) < len(self.assignment.attempts):
            raise ValueError("replacement execution attempts cannot retract")
        self.assignment = assignment
        return assignment

    def to_dict(self, include_digest=True):
        value = {
            "assignment": (
                None if self.assignment is None else self.assignment.to_dict()),
            "persistence_identity": self.persistence_identity,
            "quarantine_reason": self.quarantine_reason,
            "schema_version": REPLACEMENT_EXECUTION_SCHEMA_VERSION,
            "store_identity": self.STORE_IDENTITY,
        }
        if include_digest:
            value["store_digest"] = self.store_digest
        return value

    def save(self, path):
        if self.quarantined:
            raise ValueError("quarantined replacement execution store")
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".fdas-replacement-execution-", suffix=".json",
            dir=directory or None)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(self.to_dict()))
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path, persistence_identity):
        if not os.path.exists(path):
            return cls(persistence_identity)
        try:
            with open(path, "rb") as stream:
                value = json.loads(stream.read().decode("utf-8"))
            if (value.get("store_identity") != cls.STORE_IDENTITY
                    or value.get("schema_version")
                    != REPLACEMENT_EXECUTION_SCHEMA_VERSION
                    or value.get("persistence_identity")
                    != persistence_identity):
                raise ValueError("replacement execution store identity differs")
            assignment = value.get("assignment")
            store = cls(
                persistence_identity,
                None if assignment is None else
                FdasReplacementExecutionAssignment.from_dict(assignment),
                value.get("quarantine_reason"))
            if (value.get("store_digest") is not None
                    and value["store_digest"] != store.store_digest):
                raise ValueError("replacement execution store digest differs")
            return store
        except (KeyError, OSError, TypeError, UnicodeError, ValueError,
                json.JSONDecodeError) as error:
            return cls(
                persistence_identity,
                quarantine_reason=(
                    "replacement-execution-store-load-failed:{}".format(error)))


@dataclass(frozen=True)
class FdasReplacementExecutionDecision:
    status: str
    reason: str
    assignment: object
    authority: object
    lifecycle_updates: tuple
    assignment_created: bool

    def __post_init__(self):
        if self.status not in ("unassigned", "authorized", "abstained", "terminal"):
            raise ValueError("replacement execution decision status differs")
        _required_text(self.reason, "execution decision reason")
        if self.assignment is not None and not isinstance(
                self.assignment, FdasReplacementExecutionAssignment):
            raise TypeError("replacement execution decision assignment is untyped")
        if self.authority is not None and not isinstance(
                self.authority, OperationAuthorityReadout):
            raise TypeError("replacement execution authority is untyped")
        if (self.status == "authorized") != (self.authority is not None):
            raise ValueError("replacement execution authority status differs")
        object.__setattr__(self, "lifecycle_updates", tuple(
            self.lifecycle_updates))

    def to_dict(self):
        return {
            "assignment": (
                None if self.assignment is None else self.assignment.to_dict()),
            "assignment_created": self.assignment_created,
            "authority": (
                None if self.authority is None else self.authority.to_dict()),
            "claim_eligible": False,
            "identity": REPLACEMENT_EXECUTION_TREATMENT_ID,
            "policy_authority": self.authority is not None,
            "randomized": False,
            "reason": self.reason,
            "status": self.status,
            "truth_mutated": False,
        }


class FdasCoordinatedReplacementExecutionPilot(object):
    """Own and execute no more than one exact replacement operation."""

    PILOT_IDENTITY = REPLACEMENT_EXECUTION_TREATMENT_ID

    def __init__(self, adapter, store, experiment_id, game_id, player_id):
        if not isinstance(adapter, FdasCoordinatedReplacementAdapter):
            raise TypeError("replacement execution pilot requires adapter")
        if not isinstance(store, FdasReplacementExecutionStore):
            raise TypeError("replacement execution pilot requires store")
        _required_text(experiment_id, "replacement execution experiment ID")
        _required_text(game_id, "replacement execution game ID")
        if isinstance(player_id, bool) or not isinstance(player_id, int):
            raise ValueError("replacement execution player ID is invalid")
        self.adapter = adapter
        self.store = store
        self.experiment_id = experiment_id
        self.game_id = game_id
        self.player_id = player_id

    def _record(self, assignment):
        record = self.adapter.store.get(assignment.operation_id)
        if (record is None
                or record.spec.spec_digest != assignment.operation_spec_digest):
            raise ValueError("replacement execution operation identity differs")
        return record

    def _new_assignment(self, pair, snapshot):
        record = self.adapter.store.get(pair.lifecycle_operation_id)
        if (record is None
                or record.progress.state != OperationState.RESERVABLE):
            raise ValueError("replacement execution pair is not reservable")
        material = {
            "assignment_snapshot_id": snapshot.snapshot_id,
            "assignment_turn": int(snapshot.turn),
            "assignment_unit": REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT,
            "experiment_id": self.experiment_id,
            "game_id": self.game_id,
            "operation_id": record.spec.operation_id,
            "operation_spec_digest": record.spec.spec_digest,
            "player_id": self.player_id,
            "reinforcement_actor_id": pair.reinforcement_actor_id,
            "replacement_actor_id": pair.replacement_actor_id,
            "schema_version": REPLACEMENT_EXECUTION_SCHEMA_VERSION,
            "source_city_id": pair.source_city_id,
            "target_city_id": pair.target_city_id,
            "treatment_id": REPLACEMENT_EXECUTION_TREATMENT_ID,
        }
        return FdasReplacementExecutionAssignment(
            REPLACEMENT_EXECUTION_SCHEMA_VERSION,
            "replacement-execution-assignment-" +
            structural_hash(material)[:24],
            REPLACEMENT_EXECUTION_TREATMENT_ID,
            REPLACEMENT_EXECUTION_ASSIGNMENT_UNIT,
            self.experiment_id, self.game_id, self.player_id,
            record.spec.operation_id, record.spec.spec_digest,
            pair.replacement_actor_id, pair.reinforcement_actor_id,
            pair.source_city_id, pair.target_city_id,
            int(snapshot.turn), snapshot.snapshot_id, (), None, None)

    def _authority(self, assignment, record, snapshot, candidate_catalog=()):
        binding = self.adapter.binding(record.spec.operation_id)
        context = self.adapter.requirement_context(record.spec.operation_id)
        step = record.spec.steps[record.progress.current_step_index]
        if (record.progress.state != OperationState.ACTIVE
                or binding is None or context is None
                or binding.snapshot_id != snapshot.snapshot_id
                or binding.legal_actions_digest
                != snapshot.legal_actions_digest
                or binding.action_key not in snapshot.legal_action_json
                or canonical_json_bytes(binding.action).decode("utf-8")
                != binding.action_key
                or not binding.legal_bound
                or context.snapshot_id != snapshot.snapshot_id
                or context.blocked_premises
                or context.operation_id != record.spec.operation_id
                or context.requirement_set.requirement_set_id
                != step.requirement_set_id
                or len(context.resource_claims) != 2
                or any(claim.source_operation_id != record.spec.operation_id
                       or claim.source_step_id != step.step_id
                       or claim.window.start_turn > snapshot.turn
                       or claim.window.end_turn_exclusive <= snapshot.turn
                       for claim in context.resource_claims)):
            raise ValueError("replacement execution current-step proof differs")
        participants = dict(
            (value.role, int(value.actor_id)) for value in record.spec.participants)
        source = snapshot.city(assignment.source_city_id)
        guard_role = (
            "reinforcement" if record.progress.current_step_index == 0
            else "replacement")
        guard = snapshot.unit(participants[guard_role])
        if (source is None or source.owner != snapshot.player_id
                or source.tile is None or guard is None
                or guard.owner != snapshot.player_id
                or guard.tile != source.tile):
            raise ValueError("replacement execution source coverage differs")
        catalog_categories = tuple(sorted(set(
            value.category for value in tuple(candidate_catalog)
            if getattr(value, "action_key", None) == binding.action_key)))
        if len(catalog_categories) > 1:
            raise ValueError(
                "replacement execution planner category is ambiguous")
        candidate_category = (
            catalog_categories[0] if catalog_categories
            else "city_garrison_move")
        return OperationAuthorityReadout(
            OperationAuthorityKind.CITY_DEFENSE,
            record.spec.operation_id, record.spec.operation_type,
            dict(binding.action), binding.action_key, candidate_category,
            snapshot.snapshot_id, snapshot.legal_actions_digest, 1000.0,
            (
                self.PILOT_IDENTITY,
                "assignment:" + assignment.assignment_id,
                "claim-eligible:false",
                "forced-treatment",
                "operation-spec:" + assignment.operation_spec_digest,
                "step:" + step.step_id,
                "truth-authority:false",
            ))

    @staticmethod
    def _attempt_budget_blocker(assignment, record, snapshot):
        step = record.spec.steps[record.progress.current_step_index]
        participants = dict(
            (value.role, int(value.actor_id))
            for value in record.spec.participants)
        actor = snapshot.unit(participants[step.actor_role])
        target_city_id = int(step.target_ref.split(":", 1)[1])
        target = snapshot.city(target_city_id)
        route = (
            None if actor is None or actor.tile is None
            or target is None or target.tile is None else
            snapshot.movement_route(actor.unit_id, target.tile))
        remaining = step.maximum_attempts - record.progress.attempt_count
        if (route is None or not route.reachable
                or route.origin_tile != actor.tile
                or route.destination_tile != target.tile
                or route.turn != snapshot.turn
                or route.source_seq > snapshot.identity.source_seq):
            return "selected-step-route-unavailable-for-attempt-budget"
        if route.path_length > remaining:
            return (
                "selected-step-route-length-{}-exceeds-remaining-attempts-{}"
                .format(route.path_length, remaining))
        if assignment.operation_id != record.spec.operation_id:
            return "selected-step-assignment-operation-differs"
        return None

    def evaluate(self, snapshot, readout, candidate_catalog=()):
        if not isinstance(readout, FdasCoordinatedReplacementReadout):
            raise TypeError("replacement execution requires grounded readout")
        if (snapshot.identity.game_id != self.game_id
                or snapshot.player_id != self.player_id):
            raise ValueError("replacement execution snapshot identity differs")
        assignment = self.store.assignment
        created = False
        updates = ()
        if assignment is None:
            if not readout.pairs:
                return FdasReplacementExecutionDecision(
                    "unassigned", "no-grounded-chain-yet", None, None, (), False)
            pair = sorted(
                readout.pairs,
                key=coordinated_replacement_pair_order_key)[0]
            assignment = self.store.record(self._new_assignment(pair, snapshot))
            created = True
        if (assignment.game_id != self.game_id
                or assignment.player_id != self.player_id
                or assignment.experiment_id != self.experiment_id):
            raise ValueError("replacement execution assignment context differs")
        record = self._record(assignment)
        if record.progress.state in TERMINAL_OPERATION_STATES:
            if assignment.terminal_state is None:
                assignment = self.store.record(replace(
                    assignment,
                    terminal_state=record.progress.state.value,
                    terminal_reason=record.progress.terminal_reason))
            return FdasReplacementExecutionDecision(
                "terminal", "selected-operation-{}".format(
                    record.progress.state.value), assignment, None, (), created)
        if assignment.terminal_state is not None:
            raise ValueError("terminal replacement assignment has live operation")
        if record.progress.state in (
                OperationState.RESERVABLE, OperationState.RESERVED):
            updates = self.adapter.reactivate_for_execution(
                record.spec.operation_id, snapshot)
            record = self._record(assignment)
        if record.progress.state != OperationState.ACTIVE:
            return FdasReplacementExecutionDecision(
                "abstained", "selected-operation-{}".format(
                    record.progress.state.value), assignment, None,
                    updates, created)
        attempt_budget_blocker = self._attempt_budget_blocker(
            assignment, record, snapshot)
        if attempt_budget_blocker is not None:
            budget_update = self.adapter.fail_execution(
                record.spec.operation_id, snapshot, attempt_budget_blocker)
            assignment = self.store.record(replace(
                assignment, terminal_state=OperationState.FAILED.value,
                terminal_reason=attempt_budget_blocker))
            return FdasReplacementExecutionDecision(
                "terminal", attempt_budget_blocker, assignment, None,
                tuple(updates) + (budget_update,), created)
        authority = self._authority(
            assignment, record, snapshot, candidate_catalog)
        return FdasReplacementExecutionDecision(
            "authorized", "selected-current-step-authorized",
            assignment, authority, updates, created)

    def record_outcome(
            self, snapshot, action, accepted, result_event_id, reason=None):
        assignment = self.store.assignment
        if assignment is None or assignment.terminal_state is not None:
            raise ValueError("replacement execution has no live assignment")
        record = self._record(assignment)
        step_index = record.progress.current_step_index
        step = record.spec.steps[step_index]
        action_key = canonical_json_bytes(action).decode("utf-8")
        update = self.adapter.record_execution_outcome(
            record.spec.operation_id, snapshot, action, bool(accepted), reason)
        attempt_material = {
            "accepted": bool(accepted),
            "action_key": action_key,
            "attempt_index": len(assignment.attempts),
            "legal_actions_digest": snapshot.legal_actions_digest,
            "operation_id": assignment.operation_id,
            "operation_spec_digest": assignment.operation_spec_digest,
            "reason": (
                "accepted-awaiting-authoritative-predicate" if accepted else
                str(reason or "replacement-step-action-rejected")),
            "result_event_id": str(result_event_id),
            "snapshot_id": snapshot.snapshot_id,
            "step_id": step.step_id,
            "step_index": step_index,
            "turn": int(snapshot.turn),
        }
        attempt = FdasReplacementExecutionAttempt(
            **attempt_material,
            state_digest=structural_hash(attempt_material))
        terminal_state = None if accepted else OperationState.FAILED.value
        terminal_reason = None if accepted else attempt.reason
        assignment = self.store.record(replace(
            assignment, attempts=assignment.attempts + (attempt,),
            terminal_state=terminal_state, terminal_reason=terminal_reason))
        return assignment, attempt, update
