"""Deterministic greedy and bounded-exact identity resource scheduling."""

import math
import time
from dataclasses import dataclass, replace
from enum import Enum
from functools import cached_property
from typing import Optional

from ..events.schema import structural_hash
from .coalitions import RequirementSet
from .resource_claims import (
    ClaimHardness,
    ResourceCapacity,
    ResourceClaim,
)


class ResourceScheduleStatus(str, Enum):
    EXACT = "exact"
    BOUNDED = "bounded"
    GREEDY = "greedy"
    GREEDY_FALLBACK = "greedy_fallback"


@dataclass(frozen=True)
class OperationResourceRequest:
    operation_id: str
    bid: float
    claims: tuple
    requirement_set_id: Optional[str] = None

    def __post_init__(self):
        if not isinstance(
                self.operation_id, str
                ) or not self.operation_id:
            raise ValueError(
                "resource request requires operation ID")
        bid = float(self.bid)
        if not math.isfinite(bid) or bid < 0.0:
            raise ValueError(
                "resource request bid must be finite and non-negative")
        claims = tuple(self.claims)
        if not claims:
            raise ValueError(
                "resource request requires at least one claim")
        if any(not isinstance(
                row, ResourceClaim)
               for row in claims):
            raise TypeError(
                "resource request claims must be ResourceClaim")
        if any(
                row.source_operation_id
                != self.operation_id
                for row in claims):
            raise ValueError(
                "claim operation IDs must match their request")
        claim_ids = [
            row.claim_id for row in claims]
        if len(claim_ids) != len(
                set(claim_ids)):
            raise ValueError(
                "resource request claims must be unique")
        object.__setattr__(
            self, "claims",
            tuple(sorted(
                claims,
                key=lambda row: row.sort_key)))
        if (self.requirement_set_id
                is not None
                and (not isinstance(
                    self.requirement_set_id,
                    str)
                     or not self.requirement_set_id)):
            raise ValueError(
                "requirement set ID must be non-empty or absent")

    @property
    def hard_current_claims(self):
        return tuple(
            row for row in self.claims
            if row.hardness
            == ClaimHardness.HARD_CURRENT)

    @property
    def scheduling_cost(self):
        return max(
            1,
            sum(
                row.quantity
                * row.window.duration
                for row in
                self.hard_current_claims))

    def to_dict(self):
        return {
            "bid": float(self.bid),
            "claims": [
                row.to_dict()
                for row in self.claims],
            "operation_id":
                self.operation_id,
            "requirement_set_id":
                self.requirement_set_id,
        }

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise TypeError("resource request must be an object")
        try:
            return cls(
                operation_id=value["operation_id"],
                bid=value["bid"],
                claims=tuple(
                    ResourceClaim.from_dict(row)
                    for row in value["claims"]),
                requirement_set_id=value.get("requirement_set_id"),
            )
        except KeyError as error:
            raise ValueError(
                "resource request field is missing: {}".format(
                    error.args[0]))


@dataclass(frozen=True)
class ResourceScheduleEntry:
    operation_id: str
    bid: float
    selected: bool
    reason: Optional[str]
    conflict_resource_ids: tuple = ()
    conflicting_operation_ids: tuple = ()

    def __post_init__(self):
        if not isinstance(
                self.operation_id, str
                ) or not self.operation_id:
            raise ValueError(
                "schedule entry requires operation ID")
        if not math.isfinite(
                float(self.bid)):
            raise ValueError(
                "schedule entry bid must be finite")
        if not isinstance(
                self.selected, bool):
            raise TypeError(
                "schedule entry selection must be boolean")
        if self.selected:
            if self.reason is not None:
                raise ValueError(
                    "selected entry cannot have rejection reason")
            if (self.conflict_resource_ids
                    or self.conflicting_operation_ids):
                raise ValueError(
                    "selected entry cannot retain conflicts")
        elif (not isinstance(
                self.reason, str)
              or not self.reason):
            raise ValueError(
                "rejected entry requires reason")
        for rows, name in (
                (self.conflict_resource_ids,
                 "conflict resource IDs"),
                (self.conflicting_operation_ids,
                 "conflicting operation IDs")):
            if (tuple(sorted(set(rows))) != rows
                    or any(
                        not isinstance(value, str)
                        or not value
                        for value in rows)):
                raise ValueError(
                    "{} must be unique sorted strings".format(name))

    def to_dict(self):
        return {
            "bid": float(self.bid),
            "conflict_resource_ids": list(
                self.conflict_resource_ids),
            "conflicting_operation_ids": list(
                self.conflicting_operation_ids),
            "operation_id": self.operation_id,
            "reason": self.reason,
            "selected": self.selected,
        }


@dataclass(frozen=True)
class ResourceSchedule:
    requests: tuple
    capacities: tuple
    entries: tuple
    selected_operation_ids: tuple
    status: ResourceScheduleStatus
    explored_nodes: int
    node_budget: Optional[int]
    fallback_reason: Optional[str]
    objective_value: float
    scheduler_identity: str
    latency_ms: float
    shadow_only: bool = True
    policy_authority: bool = False

    def __post_init__(self):
        if any(not isinstance(
                row, OperationResourceRequest)
               for row in self.requests):
            raise TypeError(
                "resource schedule requests have the wrong type")
        if any(not isinstance(
                row, ResourceCapacity)
               for row in self.capacities):
            raise TypeError(
                "resource schedule capacities have the wrong type")
        if any(not isinstance(
                row, ResourceScheduleEntry)
               for row in self.entries):
            raise TypeError(
                "resource schedule entries have the wrong type")
        if not isinstance(
                self.status,
                ResourceScheduleStatus):
            raise TypeError(
                "resource schedule status has the wrong type")
        if (isinstance(self.explored_nodes, bool)
                or not isinstance(
                    self.explored_nodes, int)
                or self.explored_nodes < 0):
            raise ValueError(
                "explored nodes must be non-negative")
        if (self.node_budget is not None
                and (isinstance(
                    self.node_budget, bool)
                     or not isinstance(
                         self.node_budget, int)
                     or self.node_budget < 1)):
            raise ValueError(
                "node budget must be positive or absent")
        if not math.isfinite(
                float(self.objective_value)
                ) or self.objective_value < 0.0:
            raise ValueError(
                "schedule objective must be finite and non-negative")
        if not math.isfinite(
                float(self.latency_ms)
                ) or self.latency_ms < 0.0:
            raise ValueError(
                "schedule latency must be finite and non-negative")
        if (not isinstance(
                self.scheduler_identity, str)
                or not self.scheduler_identity):
            raise ValueError(
                "scheduler identity is required")
        if not self.shadow_only or self.policy_authority:
            raise ValueError(
                "GDO-3 resource schedules are shadow-only")
        selected = tuple(
            row.operation_id
            for row in self.entries
            if row.selected)
        if tuple(sorted(selected)) != (
                self.selected_operation_ids):
            raise ValueError(
                "selected IDs must match sorted selected entries")
        if self.fallback_reason is not None and (
                not isinstance(
                    self.fallback_reason, str)
                or not self.fallback_reason):
            raise ValueError(
                "fallback reason must be non-empty or absent")

    @cached_property
    def decision_digest(self):
        return structural_hash({
            "capacities": [
                row.to_dict()
                for row in self.capacities],
            "entries": [
                row.to_dict()
                for row in self.entries],
            "explored_nodes":
                self.explored_nodes,
            "fallback_reason":
                self.fallback_reason,
            "node_budget": self.node_budget,
            "objective_value":
                float(self.objective_value),
            "policy_authority": False,
            "requests": [
                row.to_dict()
                for row in self.requests],
            "scheduler_identity":
                self.scheduler_identity,
            "selected_operation_ids": list(
                self.selected_operation_ids),
            "shadow_only": True,
            "status": self.status.value,
        })

    def selected_claims(self):
        selected = frozenset(
            self.selected_operation_ids)
        return tuple(sorted(
            (
                claim
                for request in self.requests
                if request.operation_id
                in selected
                for claim in request.claims
            ),
            key=lambda row: row.sort_key))

    def to_dict(self, include_latency=True):
        if not isinstance(include_latency, bool):
            raise TypeError(
                "include_latency must be boolean")
        payload = {
            "capacities": [
                row.to_dict()
                for row in self.capacities],
            "decision_digest":
                self.decision_digest,
            "entries": [
                row.to_dict()
                for row in self.entries],
            "explored_nodes":
                self.explored_nodes,
            "fallback_reason":
                self.fallback_reason,
            "node_budget": self.node_budget,
            "objective_value":
                float(self.objective_value),
            "policy_authority": False,
            "requests": [
                row.to_dict()
                for row in self.requests],
            "scheduler_identity":
                self.scheduler_identity,
            "selected_operation_ids": list(
                self.selected_operation_ids),
            "shadow_only": True,
            "status": self.status.value,
        }
        if include_latency:
            payload["latency_ms"] = float(
                self.latency_ms)
        return payload


def _normalized_inputs(
        requests, capacities,
        requirement_sets, premise_packets):
    requests = tuple(sorted(
        tuple(requests),
        key=lambda row: row.operation_id))
    capacities = tuple(sorted(
        tuple(capacities),
        key=lambda row: row.sort_key))
    requirement_sets = tuple(
        requirement_sets)
    if any(not isinstance(
            row, OperationResourceRequest)
           for row in requests):
        raise TypeError(
            "scheduler requests have the wrong type")
    if any(not isinstance(
            row, ResourceCapacity)
           for row in capacities):
        raise TypeError(
            "scheduler capacities have the wrong type")
    if any(not isinstance(
            row, RequirementSet)
           for row in requirement_sets):
        raise TypeError(
            "scheduler requirements have the wrong type")
    operation_ids = [
        row.operation_id for row in requests]
    if len(operation_ids) != len(
            set(operation_ids)):
        raise ValueError(
            "scheduler operation IDs must be unique")
    capacity_ids = [
        row.capacity_id for row in capacities]
    if len(capacity_ids) != len(
            set(capacity_ids)):
        raise ValueError(
            "scheduler capacities must be unique")
    snapshot_ids = {
        row.snapshot_id for row in capacities}
    if len(snapshot_ids) > 1:
        raise ValueError(
            "scheduler capacities must share one snapshot")
    for index, left in enumerate(
            capacities):
        for right in capacities[
                index + 1:]:
            if (left.resource
                    == right.resource
                    and left.window.overlaps(
                        right.window)):
                raise ValueError(
                    "capacities for one resource cannot overlap")
    requirements = {
        row.requirement_set_id: row
        for row in requirement_sets}
    if len(requirements) != len(
            requirement_sets):
        raise ValueError(
            "scheduler requirement IDs must be unique")
    premise_packets = dict(
        premise_packets or {})
    if any(
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value
            in premise_packets.items()):
        raise ValueError(
            "premise packets require non-negative integer quanta")
    return (
        requests, capacities,
        requirements, premise_packets)


def _requirement_rejection(
        request, requirements,
        premise_packets):
    if request.requirement_set_id is None:
        return None
    requirement = requirements.get(
        request.requirement_set_id)
    if requirement is None:
        return "unknown-requirement-set"
    if not requirement.complete(
            premise_packets):
        return "incomplete-requirement-set"
    return None


def _feasible(
        claims, capacities):
    """Return feasibility and stable conflict attribution for hard claims."""
    hard = tuple(
        row for row in claims
        if row.hardness
        == ClaimHardness.HARD_CURRENT)
    resource_rows = {}
    for claim in hard:
        resource_rows.setdefault(
            claim.resource, []).append(
                claim)
    capacity_rows = {}
    for capacity in capacities:
        capacity_rows.setdefault(
            capacity.resource, []).append(
                capacity)
    reasons = []
    resource_ids = set()
    conflicting_operations = set()
    for resource, rows in sorted(
            resource_rows.items(),
            key=lambda item:
            item[0].sort_key):
        relevant_capacities = (
            capacity_rows.get(
                resource, ()))
        points = sorted(set(
            value
            for row in (
                tuple(rows)
                + tuple(
                    relevant_capacities))
            for value in (
                row.window.start_turn,
                row.window
                .end_turn_exclusive)))
        for left, right in zip(
                points, points[1:]):
            if left == right:
                continue
            active = [
                row for row in rows
                if (row.window.start_turn
                    <= left
                    < row.window
                    .end_turn_exclusive)]
            if not active:
                continue
            available = sum(
                row.quantity
                for row in relevant_capacities
                if (row.window.start_turn
                    <= left
                    and row.window
                    .end_turn_exclusive
                    >= right))
            if available <= 0:
                reasons.append(
                    "missing-authoritative-capacity")
                resource_ids.add(
                    resource.resource_id)
                conflicting_operations.update(
                    row.source_operation_id
                    for row in active)
                continue
            if (len(active) > 1
                    and any(
                        row.exclusive
                        for row in active)):
                reasons.append(
                    "exclusive-resource-conflict")
                resource_ids.add(
                    resource.resource_id)
                conflicting_operations.update(
                    row.source_operation_id
                    for row in active)
                continue
            if sum(
                    row.quantity
                    for row in active
                    ) > available:
                reasons.append(
                    "resource-capacity-exceeded")
                resource_ids.add(
                    resource.resource_id)
                conflicting_operations.update(
                    row.source_operation_id
                    for row in active)
    if reasons:
        precedence = (
            "missing-authoritative-capacity",
            "exclusive-resource-conflict",
            "resource-capacity-exceeded",
        )
        reason = next(
            value for value in precedence
            if value in reasons)
        return (
            False,
            reason,
            tuple(sorted(
                resource_ids)),
            tuple(sorted(
                conflicting_operations)),
        )
    return True, None, (), ()


def _shared_single_winner_resource(
        requests, capacities):
    """Return a shared saturated resource proving at most one request fits.

    Current FreeCiv action sets commonly contain dozens of alternatives that
    all consume one unit of the same one-unit action budget.  Recognizing that
    cardinality proof avoids an exponential search without approximating the
    optimum.
    """
    if len(requests) < 2:
        return None
    quantities = []
    common_keys = None
    request_rows = []
    for request in requests:
        by_key = {}
        for claim in request.claims:
            if claim.hardness != (
                    ClaimHardness
                    .HARD_CURRENT):
                continue
            key = (
                claim.resource,
                claim.window.start_turn,
                claim.window
                .end_turn_exclusive)
            by_key[key] = (
                by_key.get(key, 0)
                + claim.quantity)
        keys = set(by_key)
        common_keys = (
            keys
            if common_keys is None
            else common_keys
            .intersection(keys))
        request_rows.append(by_key)
        if not common_keys:
            return None
    capacity_by_resource = {}
    for capacity in capacities:
        capacity_by_resource.setdefault(
            capacity.resource, []).append(
                capacity)
    for key in sorted(
            common_keys,
            key=lambda row: (
                row[0].sort_key,
                row[1], row[2])):
        resource, start, end = key
        rows = capacity_by_resource.get(
            resource, ())
        points = sorted(set(
            (start, end)
            + tuple(
                value
                for row in rows
                for value in (
                    max(
                        start,
                        row.window
                        .start_turn),
                    min(
                        end,
                        row.window
                        .end_turn_exclusive))
                if start < value < end)))
        segment_capacities = [
            sum(
                row.quantity
                for row in rows
                if (row.window.start_turn
                    <= left
                    and row.window
                    .end_turn_exclusive
                    >= right))
            for left, right in zip(
                points, points[1:])
            if left < right
        ]
        if not segment_capacities:
            continue
        available = min(
            segment_capacities)
        quantities = sorted(
            row[key]
            for row in request_rows)
        if (available > 0
                and quantities[0]
                + quantities[1]
                > available):
            return resource
    return None


def _entry(
        request, selected, reason=None,
        resource_ids=(),
        conflicting_operation_ids=()):
    conflicts = tuple(sorted(
        value
        for value
        in set(conflicting_operation_ids)
        if value != request.operation_id))
    return ResourceScheduleEntry(
        operation_id=request.operation_id,
        bid=request.bid,
        selected=selected,
        reason=reason,
        conflict_resource_ids=tuple(sorted(
            set(resource_ids))),
        conflicting_operation_ids=(
            conflicts))


def _schedule(
        requests, capacities, entries,
        status, explored_nodes,
        node_budget, fallback_reason,
        scheduler_identity, started):
    entries = tuple(sorted(
        entries,
        key=lambda row: row.operation_id))
    selected_ids = tuple(
        row.operation_id
        for row in entries
        if row.selected)
    bid_by_id = {
        row.operation_id: row.bid
        for row in requests}
    return ResourceSchedule(
        requests=requests,
        capacities=capacities,
        entries=entries,
        selected_operation_ids=(
            selected_ids),
        status=status,
        explored_nodes=explored_nodes,
        node_budget=node_budget,
        fallback_reason=fallback_reason,
        objective_value=sum(
            bid_by_id[value]
            for value in selected_ids),
        scheduler_identity=(
            scheduler_identity),
        latency_ms=(
            time.perf_counter()
            - started) * 1000.0)


class GreedyIdentityScheduler:
    """Stable density-first scheduler with identity-aware conflict checks."""

    SCHEDULER_IDENTITY = (
        "freeciv-greedy-identity-scheduler/1.0")

    def schedule(
            self, requests, capacities,
            requirement_sets=(),
            premise_packets=None):
        started = time.perf_counter()
        (
            requests, capacities,
            requirements, premise_packets,
        ) = _normalized_inputs(
            requests, capacities,
            requirement_sets,
            premise_packets)
        ranked = sorted(
            requests,
            key=lambda row: (
                -float(row.bid)
                / row.scheduling_cost,
                -float(row.bid),
                row.operation_id))
        selected_claims = []
        entries = []
        for request in ranked:
            reason = _requirement_rejection(
                request, requirements,
                premise_packets)
            if reason is not None:
                entries.append(
                    _entry(
                        request, False,
                        reason))
                continue
            if request.bid <= 0.0:
                entries.append(
                    _entry(
                        request, False,
                        "nonpositive-operation-bid"))
                continue
            feasible, reason, resource_ids, conflicts = (
                _feasible(
                    tuple(selected_claims)
                    + request.claims,
                    capacities))
            if not feasible:
                entries.append(
                    _entry(
                        request, False,
                        reason, resource_ids,
                        conflicts))
                continue
            selected_claims.extend(
                request.claims)
            entries.append(
                _entry(
                    request, True))
        return _schedule(
            requests, capacities, entries,
            ResourceScheduleStatus.GREEDY,
            explored_nodes=len(requests),
            node_budget=None,
            fallback_reason=None,
            scheduler_identity=(
                self.SCHEDULER_IDENTITY),
            started=started)


class BoundedExactScheduler:
    """Exact branch-and-bound with deterministic whole-result fallback."""

    SCHEDULER_IDENTITY = (
        "freeciv-bounded-exact-resource-scheduler/1.0")

    def __init__(
            self, node_budget=100000,
            time_budget_ms=None):
        if (isinstance(node_budget, bool)
                or not isinstance(
                    node_budget, int)
                or node_budget < 1):
            raise ValueError(
                "exact scheduler node budget must be positive")
        if time_budget_ms is not None:
            time_budget_ms = float(
                time_budget_ms)
            if (not math.isfinite(
                    time_budget_ms)
                    or time_budget_ms <= 0.0):
                raise ValueError(
                    "time budget must be positive or absent")
        self.node_budget = node_budget
        self.time_budget_ms = (
            time_budget_ms)

    def _fallback(
            self, requests, capacities,
            requirement_sets,
            premise_packets, reason,
            explored_nodes, started):
        greedy = GreedyIdentityScheduler().schedule(
            requests, capacities,
            requirement_sets=(
                requirement_sets),
            premise_packets=(
                premise_packets))
        return replace(
            greedy,
            status=(
                ResourceScheduleStatus
                .GREEDY_FALLBACK),
            # A wall-clock timeout can cross its boundary at a different
            # search node under unrelated host load.  The fallback decision
            # remains deterministic, so do not let that observational count
            # perturb its semantic digest.
            explored_nodes=(
                0
                if reason == "time-budget-exhausted"
                else explored_nodes),
            node_budget=self.node_budget,
            fallback_reason=reason,
            scheduler_identity=(
                self.SCHEDULER_IDENTITY),
            latency_ms=(
                time.perf_counter()
                - started) * 1000.0)

    def schedule(
            self, requests, capacities,
            requirement_sets=(),
            premise_packets=None):
        started = time.perf_counter()
        requirement_sets = tuple(
            requirement_sets)
        (
            requests, capacities,
            requirements, premise_packets,
        ) = _normalized_inputs(
            requests, capacities,
            requirement_sets,
            premise_packets)
        pre_entries = {}
        eligible = []
        for request in requests:
            reason = _requirement_rejection(
                request, requirements,
                premise_packets)
            if reason is None and (
                    request.bid <= 0.0):
                reason = (
                    "nonpositive-operation-bid")
            if reason is None:
                (
                    feasible, reason,
                    resource_ids, conflicts,
                ) = _feasible(
                    request.claims,
                    capacities)
            else:
                resource_ids = ()
                conflicts = ()
            if reason is not None:
                pre_entries[
                    request.operation_id] = (
                        _entry(
                            request, False,
                            reason,
                            resource_ids,
                            conflicts))
            else:
                eligible.append(
                    request)
        eligible = tuple(sorted(
            eligible,
            key=lambda row: (
                -float(row.bid),
                row.operation_id)))
        single_winner_resource = (
            _shared_single_winner_resource(
                eligible, capacities))
        if (single_winner_resource is not None
                and self.node_budget > 1):
            winner = eligible[0]
            entries = list(
                pre_entries.values())
            entries.append(
                _entry(
                    winner, True))
            for request in eligible[1:]:
                (
                    feasible, reason,
                    resource_ids, conflicts,
                ) = _feasible(
                    winner.claims
                    + request.claims,
                    capacities)
                if feasible:
                    raise AssertionError(
                        "single-winner proof admitted a second request")
                entries.append(
                    _entry(
                        request, False,
                        reason,
                        resource_ids,
                        conflicts))
            return _schedule(
                requests, capacities,
                entries,
                ResourceScheduleStatus.EXACT,
                explored_nodes=1,
                node_budget=(
                    self.node_budget),
                fallback_reason=None,
                scheduler_identity=(
                    self
                    .SCHEDULER_IDENTITY),
                started=started)
        suffix = [0.0] * (
            len(eligible) + 1)
        for index in range(
                len(eligible) - 1,
                -1, -1):
            suffix[index] = (
                suffix[index + 1]
                + float(
                    eligible[index].bid))
        explored_nodes = 0
        budget_exhausted = [None]
        best_value = [-1.0]
        best_ids = [()]

        def visit(index, selected, claims, value):
            if budget_exhausted[0] is not None:
                return
            if explored_nodes_state[0] >= (
                    self.node_budget):
                budget_exhausted[0] = (
                    "node-budget-exhausted")
                return
            if (self.time_budget_ms
                    is not None
                    and (
                        time.perf_counter()
                        - started) * 1000.0
                    >= self.time_budget_ms):
                budget_exhausted[0] = (
                    "time-budget-exhausted")
                return
            explored_nodes_state[0] += 1
            if value + suffix[index] < (
                    best_value[0] - 1e-12):
                return
            if index == len(eligible):
                identity = tuple(sorted(
                    selected))
                if (value > best_value[0]
                        + 1e-12
                        or (abs(
                            value
                            - best_value[0])
                            <= 1e-12
                            and (
                                not best_ids[0]
                                or identity
                                < best_ids[0]))):
                    best_value[0] = value
                    best_ids[0] = identity
                return
            request = eligible[index]
            feasible, _, _, _ = (
                _feasible(
                    tuple(claims)
                    + request.claims,
                    capacities))
            if feasible:
                visit(
                    index + 1,
                    selected
                    + (request.operation_id,),
                    claims + list(
                        request.claims),
                    value
                    + float(request.bid))
            visit(
                index + 1,
                selected,
                claims,
                value)

        explored_nodes_state = [0]
        visit(0, (), [], 0.0)
        explored_nodes = (
            explored_nodes_state[0])
        if budget_exhausted[0] is not None:
            return self._fallback(
                requests, capacities,
                requirement_sets,
                premise_packets,
                budget_exhausted[0],
                explored_nodes,
                started)

        selected_ids = frozenset(
            best_ids[0])
        selected_claims = tuple(
            claim
            for request in eligible
            if request.operation_id
            in selected_ids
            for claim in request.claims)
        entries = list(
            pre_entries.values())
        for request in eligible:
            if request.operation_id in (
                    selected_ids):
                entries.append(
                    _entry(
                        request, True))
                continue
            (
                feasible, reason,
                resource_ids, conflicts,
            ) = _feasible(
                selected_claims
                + request.claims,
                capacities)
            entries.append(
                _entry(
                    request, False,
                    (
                        "not-selected-tie-break"
                        if feasible else reason),
                    resource_ids,
                    conflicts))
        return _schedule(
            requests, capacities, entries,
            ResourceScheduleStatus.EXACT,
            explored_nodes=explored_nodes,
            node_budget=self.node_budget,
            fallback_reason=None,
            scheduler_identity=(
                self.SCHEDULER_IDENTITY),
            started=started)
