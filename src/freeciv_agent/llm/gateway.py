"""Pressure/value/cost-controlled LLM proposal gateway.

The gateway schedules calls; it grants no epistemic authority.  Every
successful response remains a quarantined proposal envelope until the existing
claim router and goal grader execute its declared validation plan.
"""

import math
import re
import threading
import datetime
import time
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure import (
    CostVector,
    Operation,
    PacketBudget,
    PacketCost,
    ResourceKind,
)
from .loop import ConstrainedTurnLoop
from .model import TurnDecision


VALIDATION_ROUTES = frozenset((
    "authoritative-rule-lookup",
    "deterministic-engine-execution",
    "simulation",
    "independent-gameplay-replay",
    "independent-cross-model-evidence",
    "formal-type-check",
    "contradiction-test",
    "human-approval",
))
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:/#-]{1,128}$")


def _identifier(value, name):
    value = str(value)
    if not _IDENTIFIER.match(value):
        raise ValueError("{} must be a typed identifier".format(name))
    return value


def _identifiers(values, name):
    result = tuple(sorted(_identifier(value, name) for value in values))
    if len(result) != len(set(result)):
        raise ValueError("{} values must be unique".format(name))
    return result


def _unit(value, name):
    result = float(value)
    if not 0.0 <= result <= 1.0 or not math.isfinite(result):
        raise ValueError("{} must be in [0,1]".format(name))
    return result


@dataclass(frozen=True)
class ValidationPlan:
    routes: tuple
    maximum_cost: float
    minimum_independent_support: int = 1

    def __post_init__(self):
        routes = _identifiers(self.routes, "validation route")
        if not routes or any(value not in VALIDATION_ROUTES for value in routes):
            raise ValueError("validation plan contains an unsupported route")
        object.__setattr__(self, "routes", routes)
        maximum_cost = float(self.maximum_cost)
        support = int(self.minimum_independent_support)
        if maximum_cost < 0 or not math.isfinite(maximum_cost):
            raise ValueError("validation maximum cost must be nonnegative")
        if support < 1:
            raise ValueError("validation needs independent support")
        object.__setattr__(self, "maximum_cost", maximum_cost)
        object.__setattr__(self, "minimum_independent_support", support)

    def to_dict(self):
        return {
            "maximum_cost": float(self.maximum_cost),
            "minimum_independent_support": int(
                self.minimum_independent_support),
            "routes": list(self.routes),
        }


@dataclass(frozen=True)
class QuarantinePolicy:
    initial_confidence_cap: float
    expiration_turns: int
    maximum_retries: int
    retry_backoff_turns: int = 1

    def __post_init__(self):
        _unit(
            self.initial_confidence_cap,
            "initial confidence cap")
        for value, name, minimum in (
                (self.expiration_turns,
                 "quarantine expiration turns", 1),
                (self.maximum_retries,
                 "maximum retries", 0),
                (self.retry_backoff_turns,
                 "retry backoff turns", 1)):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < minimum):
                raise ValueError(
                    "{} must be an integer >= {}".format(
                        name, minimum))

    def to_dict(self):
        return {
            "expiration_turns": int(self.expiration_turns),
            "initial_confidence_cap": float(
                self.initial_confidence_cap),
            "maximum_retries": int(self.maximum_retries),
            "retry_backoff_turns": int(
                self.retry_backoff_turns),
        }


@dataclass(frozen=True)
class GatewayRequest:
    request_id: str
    goal_id: str
    atom_id: str
    context: tuple
    known_rule_ids: tuple
    unresolved_premise_ids: tuple
    forbidden_assumption_ids: tuple
    action_budget: int
    time_budget_seconds: float
    expected_relief: float
    useful_proposal_probability: float
    token_limit: int
    latency_cost: float
    token_cost: float
    validation_plan: ValidationPlan
    clone_id: object = None
    requested_schema_id: object = None
    alternative_expected_relief: tuple = ()
    expected_rejection_cost: float = 0.0
    evidence_dependencies: tuple = ()
    quarantine_policy: object = None

    def __post_init__(self):
        for name in ("request_id", "goal_id", "atom_id"):
            object.__setattr__(
                self, name, _identifier(getattr(self, name), name))
        if self.clone_id is not None:
            object.__setattr__(
                self, "clone_id", _identifier(self.clone_id, "clone_id"))
        context = tuple(sorted(
            (_identifier(key, "context key"),
             _identifier(value, "context value"))
            for key, value in self.context))
        if len(context) != len(set(key for key, _ in context)):
            raise ValueError("gateway context keys must be unique")
        object.__setattr__(self, "context", context)
        for name in (
                "known_rule_ids", "unresolved_premise_ids",
                "forbidden_assumption_ids"):
            object.__setattr__(
                self, name, _identifiers(getattr(self, name), name))
        action_budget = int(self.action_budget)
        token_limit = int(self.token_limit)
        time_budget = float(self.time_budget_seconds)
        if action_budget < 0 or token_limit < 1 or time_budget <= 0:
            raise ValueError("gateway budgets are invalid")
        object.__setattr__(self, "action_budget", action_budget)
        object.__setattr__(self, "token_limit", token_limit)
        object.__setattr__(self, "time_budget_seconds", time_budget)
        _unit(self.expected_relief, "expected relief")
        _unit(
            self.useful_proposal_probability,
            "useful proposal probability")
        for name in ("latency_cost", "token_cost"):
            value = float(getattr(self, name))
            if value < 0 or not math.isfinite(value):
                raise ValueError("{} must be nonnegative".format(name))
        if not isinstance(self.validation_plan, ValidationPlan):
            raise TypeError("gateway request needs a ValidationPlan")
        if self.requested_schema_id is not None:
            object.__setattr__(
                self, "requested_schema_id",
                _identifier(
                    self.requested_schema_id,
                    "requested schema ID"))
        alternatives = tuple(sorted(
            (_identifier(key, "alternative kind"),
             _unit(value, "alternative expected relief"))
            for key, value in self.alternative_expected_relief))
        supported_alternatives = frozenset((
            "known-rule", "observation", "retrieval", "simulation"))
        if any(key not in supported_alternatives
               for key, _ in alternatives):
            raise ValueError(
                "unknown alternative relief kind")
        if len(alternatives) != len(set(
                key for key, _ in alternatives)):
            raise ValueError(
                "alternative relief kinds must be unique")
        object.__setattr__(
            self, "alternative_expected_relief", alternatives)
        rejection = float(self.expected_rejection_cost)
        if rejection < 0.0 or not math.isfinite(rejection):
            raise ValueError(
                "expected rejection cost must be non-negative")
        object.__setattr__(
            self, "expected_rejection_cost", rejection)
        object.__setattr__(
            self, "evidence_dependencies",
            _identifiers(
                self.evidence_dependencies,
                "evidence dependency"))
        if (self.quarantine_policy is not None
                and not isinstance(
                    self.quarantine_policy, QuarantinePolicy)):
            raise TypeError(
                "gateway quarantine policy must be QuarantinePolicy")

    def prompt_context(self):
        """Typed high-pressure gap input; no free-form environment text."""
        return {
            "action_budget": int(self.action_budget),
            "clone_id": self.clone_id,
            "context": dict(self.context),
            "forbidden_assumption_ids": list(
                self.forbidden_assumption_ids),
            "known_rule_ids": list(self.known_rule_ids),
            "request_id": self.request_id,
            "target_atom_id": self.atom_id,
            "time_budget_seconds": float(self.time_budget_seconds),
            "unresolved_premise_ids": list(
                self.unresolved_premise_ids),
            "validation_plan": self.validation_plan.to_dict(),
            **({
                "requested_schema_id": self.requested_schema_id,
            } if self.requested_schema_id is not None else {}),
        }

    def to_dict(self):
        value = self.prompt_context()
        value.update({
            "expected_relief": float(self.expected_relief),
            "goal_id": self.goal_id,
            "latency_cost": float(self.latency_cost),
            "token_cost": float(self.token_cost),
            "token_limit": int(self.token_limit),
            "useful_proposal_probability": float(
                self.useful_proposal_probability),
        })
        if self.alternative_expected_relief:
            value["alternative_expected_relief"] = dict(
                self.alternative_expected_relief)
        if self.expected_rejection_cost:
            value["expected_rejection_cost"] = float(
                self.expected_rejection_cost)
        if self.evidence_dependencies:
            value["evidence_dependencies"] = list(
                self.evidence_dependencies)
        if self.quarantine_policy is not None:
            value["quarantine_policy"] = (
                self.quarantine_policy.to_dict())
        return value


class TokenBudgetLedger(object):
    """Idempotent reservations with hard per-turn and total token caps."""

    def __init__(
            self, per_turn_limit, total_limit, maximum_calls_per_turn=1):
        self.per_turn_limit = int(per_turn_limit)
        self.total_limit = int(total_limit)
        self.maximum_calls_per_turn = int(maximum_calls_per_turn)
        if (self.per_turn_limit < 1 or self.total_limit < self.per_turn_limit
                or self.maximum_calls_per_turn < 1):
            raise ValueError("invalid token budget ledger limits")
        self._lock = threading.RLock()
        self._rows = {}

    @property
    def charged_tokens(self):
        with self._lock:
            return sum(row["charged_tokens"] for row in self._rows.values())

    def _turn_rows(self, turn):
        return tuple(
            row for row in self._rows.values() if row["turn"] == int(turn))

    def available(self, turn):
        with self._lock:
            turn_remaining = self.per_turn_limit - sum(
                row["charged_tokens"] for row in self._turn_rows(turn))
            total_remaining = self.total_limit - self.charged_tokens
            return max(0, min(turn_remaining, total_remaining))

    def reserve(self, call_id, turn, tokens):
        call_id = _identifier(call_id, "call_id")
        turn = int(turn)
        tokens = int(tokens)
        if turn < 0 or tokens < 1:
            raise ValueError("invalid token reservation")
        with self._lock:
            existing = self._rows.get(call_id)
            if existing is not None:
                if existing["turn"] != turn or existing[
                        "reserved_tokens"] != tokens:
                    raise ValueError("token reservation ID collision")
                return False
            if len(self._turn_rows(turn)) >= self.maximum_calls_per_turn:
                return None
            if tokens > self.available(turn):
                return None
            self._rows[call_id] = {
                "actual_tokens": None,
                "call_id": call_id,
                "charged_tokens": tokens,
                "reserved_tokens": tokens,
                "settled": False,
                "turn": turn,
            }
            return True

    def settle(self, call_id, actual_tokens):
        actual_tokens = int(actual_tokens)
        with self._lock:
            row = self._rows.get(str(call_id))
            if row is None:
                raise KeyError("unknown token reservation")
            if actual_tokens < 0 or actual_tokens > row["reserved_tokens"]:
                raise ValueError("actual tokens exceed reservation")
            if row["settled"]:
                if row["actual_tokens"] != actual_tokens:
                    raise ValueError("token settlement mismatch")
                return False
            row["actual_tokens"] = actual_tokens
            row["charged_tokens"] = actual_tokens
            row["settled"] = True
            return True

    def release(self, call_id):
        """Atomically release an unsettled admission reservation."""
        with self._lock:
            row = self._rows.get(str(call_id))
            if row is None:
                return False
            if row["settled"]:
                raise ValueError(
                    "settled token reservation cannot be released")
            del self._rows[str(call_id)]
            return True

    def reservation(self, call_id):
        with self._lock:
            row = self._rows.get(str(call_id))
            return None if row is None else dict(row)

    def snapshot(self):
        with self._lock:
            value = {
                "configuration": {
                    "maximum_calls_per_turn": self.maximum_calls_per_turn,
                    "per_turn_limit": self.per_turn_limit,
                    "total_limit": self.total_limit,
                },
                "reservations": [
                    dict(self._rows[key]) for key in sorted(self._rows)],
            }
            value["charged_tokens"] = sum(
                row["charged_tokens"] for row in self._rows.values())
            value["state_hash"] = structural_hash(value)
            return value

    @property
    def state_hash(self):
        return self.snapshot()["state_hash"]


class GatewayPacketLedger(object):
    """Atomic whole-packet reservation for compound LLM operations."""

    def __init__(self, budgets):
        budgets = tuple(sorted(
            tuple(budgets), key=lambda row: row.resource.value))
        if not budgets or any(
                not isinstance(row, PacketBudget) for row in budgets):
            raise TypeError(
                "gateway packet ledger requires PacketBudget values")
        resources = [row.resource for row in budgets]
        if len(resources) != len(set(resources)):
            raise ValueError(
                "gateway packet resources must be unique")
        self._available = dict(
            (row.resource, row.available) for row in budgets)
        self._reservations = {}
        self._lock = threading.RLock()

    def reserve(self, call_id, costs):
        call_id = _identifier(call_id, "packet call ID")
        costs = tuple(sorted(
            tuple(costs), key=lambda row: row.resource.value))
        if not costs or any(
                not isinstance(row, PacketCost) for row in costs):
            raise TypeError(
                "gateway packet reservation requires PacketCost")
        resources = [row.resource for row in costs]
        if len(resources) != len(set(resources)):
            raise ValueError(
                "gateway packet costs must be unique")
        with self._lock:
            existing = self._reservations.get(call_id)
            if existing is not None:
                if existing["costs"] != costs:
                    raise ValueError(
                        "gateway packet reservation ID collision")
                return False
            if any(
                    self._available.get(row.resource, 0) < row.quanta
                    for row in costs):
                return None
            for row in costs:
                self._available[row.resource] -= row.quanta
            self._reservations[call_id] = {
                "costs": costs,
                "state": "reserved",
            }
            return True

    def settle(self, call_id):
        with self._lock:
            row = self._reservations.get(str(call_id))
            if row is None:
                raise KeyError(
                    "unknown gateway packet reservation")
            if row["state"] == "settled":
                return False
            if row["state"] != "reserved":
                raise ValueError(
                    "gateway packet reservation is not active")
            row["state"] = "settled"
            return True

    def release(self, call_id):
        with self._lock:
            row = self._reservations.get(str(call_id))
            if row is None:
                return False
            if row["state"] != "reserved":
                raise ValueError(
                    "settled packet reservation cannot be released")
            for cost in row["costs"]:
                self._available[cost.resource] += cost.quanta
            del self._reservations[str(call_id)]
            return True

    def reservation(self, call_id):
        with self._lock:
            row = self._reservations.get(str(call_id))
            if row is None:
                return None
            return {
                "costs": tuple(row["costs"]),
                "state": row["state"],
            }

    def snapshot(self):
        with self._lock:
            value = {
                "available": dict(
                    (resource.value, self._available[resource])
                    for resource in sorted(
                        self._available,
                        key=lambda row: row.value)),
                "reservations": [
                    {
                        "call_id": call_id,
                        "costs": [
                            cost.to_dict()
                            for cost in row["costs"]],
                        "state": row["state"],
                    }
                    for call_id, row in sorted(
                        self._reservations.items())
                ],
            }
            value["state_hash"] = structural_hash(value)
            return value


@dataclass(frozen=True)
class GatewayCallDecision:
    call_id: str
    request: GatewayRequest
    accepted: bool
    reason: object
    expand_pressure: float
    quality: float
    total_cost: float
    operation: object = None
    packet_costs: tuple = ()

    def to_dict(self):
        value = {
            "accepted": bool(self.accepted),
            "call_id": self.call_id,
            "expand_pressure": float(self.expand_pressure),
            "operation": (
                None if self.operation is None else self.operation.to_dict()),
            "quality": float(self.quality),
            "reason": self.reason,
            "request": self.request.to_dict(),
            "total_cost": float(self.total_cost),
        }
        if self.packet_costs:
            value["packet_costs"] = [
                row.to_dict() for row in self.packet_costs]
        return value


@dataclass(frozen=True)
class GatewayProposalEnvelope:
    call_id: str
    proposal: object
    model: str
    prompt_hash: str
    timestamp: str
    context: tuple
    initial_truth: tuple
    validation_plan: ValidationPlan
    input_tokens: int
    output_tokens: int
    correction_attempts: int
    requested_schema_id: object = None
    proposal_content_digest: object = None
    evidence_dependencies: tuple = ()
    expires_turn: object = None
    maximum_retries: int = 0
    retry_after_turn: object = None
    lifecycle: str = "quarantined"

    def __post_init__(self):
        if self.lifecycle != "quarantined":
            raise ValueError("LLM proposal envelopes always enter quarantine")
        if self.requested_schema_id is not None:
            _identifier(
                self.requested_schema_id,
                "requested schema ID")
        if (self.proposal_content_digest is not None
                and (not isinstance(
                    self.proposal_content_digest, str)
                     or len(self.proposal_content_digest) != 64)):
            raise ValueError(
                "proposal content digest must be SHA-256")
        _identifiers(
            self.evidence_dependencies,
            "evidence dependency")
        for value, name in (
                (self.expires_turn, "expiration turn"),
                (self.retry_after_turn, "retry turn")):
            if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "{} must be non-negative".format(name))
        if (isinstance(self.maximum_retries, bool)
                or not isinstance(self.maximum_retries, int)
                or self.maximum_retries < 0):
            raise ValueError(
                "maximum retries must be non-negative")

    @property
    def total_tokens(self):
        return int(self.input_tokens) + int(self.output_tokens)

    def to_dict(self):
        value = {
            "call_id": self.call_id,
            "content": self.proposal.to_dict(),
            "context": dict(self.context),
            "correction_attempts": int(self.correction_attempts),
            "initial_truth": dict(self.initial_truth),
            "lifecycle": self.lifecycle,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "timestamp": self.timestamp,
            "token_usage": {
                "input": int(self.input_tokens),
                "output": int(self.output_tokens),
                "total": self.total_tokens,
            },
            "validation_plan": self.validation_plan.to_dict(),
        }
        if self.requested_schema_id is not None:
            value["requested_schema_id"] = (
                self.requested_schema_id)
        if self.proposal_content_digest is not None:
            value["proposal_content_digest"] = (
                self.proposal_content_digest)
        if self.evidence_dependencies:
            value["evidence_dependencies"] = list(
                self.evidence_dependencies)
        if self.expires_turn is not None:
            value["expiration_and_retry"] = {
                "expires_turn": int(self.expires_turn),
                "maximum_retries": int(self.maximum_retries),
                "retry_after_turn": int(self.retry_after_turn),
            }
        return value


@dataclass(frozen=True)
class GatewayProbeResult:
    call_id: str
    creates_bridge: bool
    bridge_score: float
    lifecycle: str
    promoted: bool = False

    def __post_init__(self):
        if not self.call_id:
            raise ValueError("gateway probe requires call ID")
        if not isinstance(self.creates_bridge, bool):
            raise TypeError(
                "gateway probe bridge flag must be boolean")
        _unit(self.bridge_score, "bridge score")
        if self.lifecycle != "quarantined":
            raise ValueError(
                "gateway probe cannot change quarantine lifecycle")
        if self.promoted:
            raise ValueError(
                "gateway probe cannot promote a proposal")

    def to_dict(self):
        return {
            "bridge_score": float(self.bridge_score),
            "call_id": self.call_id,
            "creates_bridge": bool(self.creates_bridge),
            "lifecycle": self.lifecycle,
            "promoted": False,
        }


@dataclass(frozen=True)
class GatewayInvocation:
    call_id: str
    status: str
    envelope: object
    charged_tokens: int
    ledger_hash: str
    error: object = None

    def to_dict(self):
        return {
            "call_id": self.call_id,
            "charged_tokens": int(self.charged_tokens),
            "envelope": (
                None if self.envelope is None else self.envelope.to_dict()),
            "error": self.error,
            "ledger_hash": self.ledger_hash,
            "status": self.status,
        }


@dataclass(frozen=True)
class GatewayTurnOutcome:
    gateway_decision: GatewayCallDecision
    invocation: object
    turn_decision: TurnDecision


def estimated_tokens(value):
    """Deterministic conservative UTF-8 token estimate for local budgeting."""
    if not isinstance(value, (bytes, str)):
        value = canonical_json_bytes(value)
    elif isinstance(value, str):
        value = value.encode("utf-8")
    return max(1, int(math.ceil(len(value) / 4.0)))


def _utc_now():
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class PressureLLMGateway(object):
    """Canonical LLM-call quality gate and quarantined invocation boundary."""

    def __init__(
            self, model, prompt_version, minimum_expand_pressure=0.05,
            minimum_quality=0.01, initial_confidence=0.05, epsilon=1e-9,
            clock=None, engine_live=False,
            maximum_alternative_relief=0.20):
        self.model = _identifier(model, "model")
        self.prompt_version = _identifier(prompt_version, "prompt_version")
        self.minimum_expand_pressure = float(minimum_expand_pressure)
        self.minimum_quality = float(minimum_quality)
        self.initial_confidence = _unit(
            initial_confidence, "initial confidence")
        self.epsilon = float(epsilon)
        self.clock = clock
        if not isinstance(engine_live, bool):
            raise TypeError("engine_live must be boolean")
        self.engine_live = engine_live
        self.maximum_alternative_relief = _unit(
            maximum_alternative_relief,
            "maximum alternative relief")
        if (self.minimum_expand_pressure < 0 or self.minimum_quality < 0
                or self.epsilon <= 0):
            raise ValueError("invalid LLM gateway thresholds")

    @staticmethod
    def _validation_resources(validation_plan):
        resources = set()
        for route in validation_plan.routes:
            if route in (
                    "simulation",
                    "independent-gameplay-replay",
                    "independent-cross-model-evidence"):
                resources.add(ResourceKind.SIMULATION)
            elif route == "human-approval":
                resources.add(ResourceKind.OBSERVATION)
            else:
                resources.add(ResourceKind.EXACT_RULE)
        return tuple(sorted(resources, key=lambda row: row.value))

    def _packet_costs(self, request):
        return tuple(sorted(
            (
                PacketCost(ResourceKind.EXPANSION, 1),
                PacketCost(ResourceKind.LLM_TOKEN, 1),
            ) + tuple(
                PacketCost(resource, 1)
                for resource in self._validation_resources(
                    request.validation_plan)),
            key=lambda row: row.resource.value))

    def _live_contract_error(self, request, packet_ledger):
        if not self.engine_live:
            return None
        if packet_ledger is None:
            return "typed_packets_required"
        if request.requested_schema_id is None:
            return "typed_output_schema_required"
        if request.quarantine_policy is None:
            return "quarantine_policy_required"
        if self.initial_confidence > (
                request.quarantine_policy.initial_confidence_cap):
            return "initial_confidence_exceeds_request_cap"
        alternatives = dict(request.alternative_expected_relief)
        required = frozenset((
            "known-rule", "observation",
            "retrieval", "simulation"))
        if set(alternatives) != required:
            return "alternative_relief_declarations_required"
        if max(alternatives.values()) > self.maximum_alternative_relief:
            return "lower_cost_alternative_available"
        return None

    def admit(
            self, request, pressure_result, ledger, turn,
            packet_ledger=None):
        if not isinstance(request, GatewayRequest):
            raise TypeError("gateway admission needs GatewayRequest")
        if not isinstance(ledger, TokenBudgetLedger):
            raise TypeError("gateway admission needs TokenBudgetLedger")
        pressure = pressure_result.pressure(
            request.goal_id, request.atom_id).value("expand")
        total_cost = (
            request.latency_cost + request.token_cost * request.token_limit
            + request.validation_plan.maximum_cost
            + (1.0 - request.useful_proposal_probability)
            * request.expected_rejection_cost)
        quality = (
            pressure * request.useful_proposal_probability
            * request.expected_relief / (total_cost + self.epsilon))
        call_id = "llm-call-" + structural_hash([
            request.to_dict(), pressure_result.artifact_hash, int(turn)])[:24]
        contract_error = self._live_contract_error(
            request, packet_ledger)
        if contract_error is not None:
            return GatewayCallDecision(
                call_id, request, False, contract_error,
                pressure, quality, total_cost)
        if pressure < self.minimum_expand_pressure:
            return GatewayCallDecision(
                call_id, request, False, "insufficient_expand_pressure",
                pressure, quality, total_cost)
        if quality < self.minimum_quality:
            return GatewayCallDecision(
                call_id, request, False, "quality_below_cost_threshold",
                pressure, quality, total_cost)
        reserved = ledger.reserve(call_id, turn, request.token_limit)
        if reserved is None:
            return GatewayCallDecision(
                call_id, request, False, "token_budget_exhausted",
                pressure, quality, total_cost)
        packet_costs = (
            self._packet_costs(request)
            if self.engine_live else ())
        if packet_costs:
            packet_reserved = packet_ledger.reserve(
                call_id, packet_costs)
            if packet_reserved is None:
                ledger.release(call_id)
                return GatewayCallDecision(
                    call_id, request, False,
                    "compound_packet_budget_exhausted",
                    pressure, quality, total_cost)
        operation = Operation(
            "invoke-" + call_id, request.atom_id, "expand",
            CostVector(
                compute=request.token_cost * request.token_limit,
                latency=request.latency_cost,
                risk=(
                    request.validation_plan.maximum_cost
                    + (1.0 - request.useful_proposal_probability)
                    * request.expected_rejection_cost)),
            causal_kind="diagnostic",
            success_probability=request.useful_proposal_probability,
            relief_scale=request.expected_relief,
            information_gain=request.useful_proposal_probability,
            future_option_value=request.expected_relief,
            payload={
                "call_id": call_id,
                "proposal_authority": "quarantine-only",
                "request": request.to_dict(),
            },
            packet_costs=packet_costs)
        return GatewayCallDecision(
            call_id, request, True, None, pressure, quality, total_cost,
            operation, packet_costs)

    def invoke(
            self, decision, proposer, ledger, state_summary,
            plan_status=None, invalidations=None,
            packet_ledger=None):
        if not isinstance(decision, GatewayCallDecision) or not decision.accepted:
            raise ValueError("only an accepted gateway decision can invoke")
        reservation = ledger.reservation(decision.call_id)
        if reservation is None or reservation["settled"]:
            raise ValueError("gateway call has no active token reservation")
        if decision.packet_costs:
            if packet_ledger is None:
                raise ValueError(
                    "gateway call requires packet ledger")
            packet_reservation = packet_ledger.reservation(
                decision.call_id)
            if (packet_reservation is None
                    or packet_reservation["state"] != "reserved"):
                raise ValueError(
                    "gateway call has no active packet reservation")
            packet_ledger.settle(decision.call_id)
        request = decision.request
        expansion = request.prompt_context()
        budgets = {
            "max_claims": 20,
            "max_goals": 5,
            "max_output_tokens": request.token_limit,
            "reserved_total_tokens": request.token_limit,
        }
        document = proposer.input_document(
            state_summary, plan_status, invalidations, budgets,
            expansion_request=expansion)
        input_tokens = estimated_tokens(document)
        if input_tokens >= request.token_limit:
            ledger.settle(decision.call_id, request.token_limit)
            return GatewayInvocation(
                decision.call_id, "rejected", None, request.token_limit,
                ledger.state_hash, "prompt_exceeds_token_reservation")
        try:
            proposal, corrections = proposer.propose(
                state_summary, plan_status, invalidations, budgets,
                expansion_request=expansion)
            output_tokens = estimated_tokens(proposal.to_dict())
            total_tokens = input_tokens + output_tokens
            if total_tokens > request.token_limit:
                ledger.settle(decision.call_id, request.token_limit)
                return GatewayInvocation(
                    decision.call_id, "quarantined", None,
                    request.token_limit, ledger.state_hash,
                    "response_exceeds_token_reservation")
            ledger.settle(decision.call_id, total_tokens)
            timestamp = self.clock() if self.clock is not None else _utc_now()
            envelope = GatewayProposalEnvelope(
                decision.call_id, proposal, self.model,
                structural_hash(document), timestamp, request.context,
                (("confidence", self.initial_confidence), ("strength", 0.5)),
                request.validation_plan, input_tokens, output_tokens,
                corrections,
                requested_schema_id=request.requested_schema_id,
                proposal_content_digest=structural_hash(
                    proposal.to_dict()),
                evidence_dependencies=request.evidence_dependencies,
                expires_turn=(
                    reservation["turn"]
                    + request.quarantine_policy.expiration_turns
                    if request.quarantine_policy is not None
                    else None),
                maximum_retries=(
                    request.quarantine_policy.maximum_retries
                    if request.quarantine_policy is not None
                    else 0),
                retry_after_turn=(
                    reservation["turn"]
                    + request.quarantine_policy.retry_backoff_turns
                    if request.quarantine_policy is not None
                    else None))
            return GatewayInvocation(
                decision.call_id, "quarantined_pending_validation",
                envelope, total_tokens, ledger.state_hash)
        except Exception as exc:
            ledger.settle(decision.call_id, request.token_limit)
            return GatewayInvocation(
                decision.call_id, "failed", None, request.token_limit,
                ledger.state_hash,
                "{}: {}".format(type(exc).__name__, exc))

    @staticmethod
    def probe(envelope, bridge_score):
        if not isinstance(envelope, GatewayProposalEnvelope):
            raise TypeError(
                "gateway probe requires proposal envelope")
        score = _unit(bridge_score, "bridge score")
        return GatewayProbeResult(
            envelope.call_id, score > 0.0, score,
            envelope.lifecycle, promoted=False)

    @staticmethod
    def emit_decision(writer, turn, decision, ledger, caused_by=()):
        return writer.emit("llm_call_scheduled", turn, {
            "decision": decision.to_dict(),
            "ledger_hash": ledger.state_hash,
        }, caused_by=caused_by)

    @staticmethod
    def emit_invocation(writer, turn, invocation, caused_by=()):
        return writer.emit(
            "llm_gateway_result", turn, invocation.to_dict(),
            caused_by=caused_by)


class PressureGatedTurnLoop(object):
    """End-to-end loop in which a rejected gateway decision makes no LLM call."""

    def __init__(
            self, gateway, proposer, router, grader, token_ledger,
            timeout_seconds=30.0, packet_ledger=None):
        if not isinstance(gateway, PressureLLMGateway):
            raise TypeError("pressure-gated loop needs PressureLLMGateway")
        if not isinstance(token_ledger, TokenBudgetLedger):
            raise TypeError("pressure-gated loop needs TokenBudgetLedger")
        self.gateway = gateway
        self.proposer = proposer
        self.token_ledger = token_ledger
        if (packet_ledger is not None
                and not isinstance(
                    packet_ledger, GatewayPacketLedger)):
            raise TypeError(
                "pressure-gated loop packet ledger must be "
                "GatewayPacketLedger")
        self.packet_ledger = packet_ledger
        self.turn_loop = ConstrainedTurnLoop(
            proposer, router, grader, timeout_seconds)

    def run(
            self, gateway_request, pressure_result, turn, state_summary,
            crisp_state, numeric_snapshot, plan_status=None,
            invalidations=None):
        started = time.perf_counter()
        decision = self.gateway.admit(
            gateway_request, pressure_result, self.token_ledger, turn,
            packet_ledger=self.packet_ledger)
        if not decision.accepted:
            skipped = TurnDecision(
                "NO_EXPANSION", None, None, (), (),
                (time.perf_counter() - started) * 1000.0,
                fallback_action={"type": "end_turn"},
                error=decision.reason)
            return GatewayTurnOutcome(decision, None, skipped)
        invocation = self.gateway.invoke(
            decision, self.proposer, self.token_ledger, state_summary,
            plan_status, invalidations,
            packet_ledger=self.packet_ledger)
        if invocation.envelope is None:
            failed = TurnDecision(
                "SAFE_FALLBACK", None, None, (), (),
                (time.perf_counter() - started) * 1000.0,
                fallback_action={"type": "end_turn"},
                error=invocation.error)
            return GatewayTurnOutcome(decision, invocation, failed)
        evaluated = self.turn_loop.evaluate(
            invocation.envelope.proposal, crisp_state, numeric_snapshot,
            started)
        return GatewayTurnOutcome(decision, invocation, evaluated)
