"""Aggregate, versioned event emission for the unified control boundary."""

import json

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from .impact_flow_adapter import (
    ControlDecision,
    ControlOutcomeRecord,
    ControlQuery,
)


CONTROL_EVENT_SCHEMA_VERSION = "1.0"


def _flow_artifact(decision):
    """Return a nested unified-flow artifact without inventing provenance."""
    artifact = decision.artifact
    if not isinstance(artifact, dict):
        return None
    if isinstance(artifact.get("flow"), dict):
        return artifact
    target = artifact.get("target_artifact")
    if (isinstance(target, dict)
            and isinstance(
                target.get("artifact"), dict)):
        return _flow_artifact(
            ControlDecision(
                ordered_candidate_keys=tuple(
                    target.get(
                        "ordered_candidate_keys", ())),
                selected_candidate_key=target.get(
                    "selected_candidate_key"),
                packet_schedule=None,
                controller_mode=str(target.get(
                    "controller_mode", "unified_flow")),
                artifact=target["artifact"],
                health=str(target.get(
                    "health", "unavailable")),
                fallback_chain=tuple(
                    target.get("fallback_chain", ()))))
    advisory = artifact.get("advisory")
    if (isinstance(advisory, dict)
            and isinstance(
                advisory.get("artifact"), dict)):
        nested = advisory["artifact"].get(
            "target_artifact")
        if (isinstance(nested, dict)
                and isinstance(
                    nested.get("artifact"), dict)):
            return nested["artifact"]
    for row in artifact.get(
            "shadow_decisions", ()):
        if (isinstance(row, dict)
                and row.get("controller_mode")
                == "unified_flow"
                and isinstance(
                    row.get("decision"), dict)
                and isinstance(
                    row["decision"].get(
                        "artifact"), dict)):
            return row["decision"]["artifact"]
    return None


def _topology_generation(query, flow_artifact):
    try:
        return int(
            flow_artifact["flow"][
                "factorization"]["view"][
                    "topology_generation"])
    except (KeyError, TypeError, ValueError):
        return int(query.pressure_generation)


def _compact_transport_readout(value):
    if not isinstance(value, dict):
        return value
    selected_id = value.get(
        "selected_operation_id")
    scalar_id = value.get(
        "scalar_selected_operation_id")
    candidates = []
    seen = set()
    rows = value.get(
        "candidate_readouts", ())
    if isinstance(rows, list):
        priority = [
            row for row in rows
            if (isinstance(row, dict)
                and row.get("operation_id")
                in (selected_id, scalar_id))]
        priority.extend(
            row for row in rows[:8]
            if isinstance(row, dict))
        for row in priority:
            operation_id = row.get(
                "operation_id")
            if operation_id in seen:
                continue
            seen.add(operation_id)
            candidates.append(row)
    return {
        "candidate_union": value.get(
            "candidate_union"),
        "candidate_readouts": candidates,
        "candidate_regions": value.get(
            "candidate_regions", ()),
        "disagrees_with_scalar": value.get(
            "disagrees_with_scalar"),
        "maximum_overlap": value.get(
            "maximum_overlap"),
        "scalar_selected_operation_id":
            scalar_id,
        "selected_node_id": value.get(
            "selected_node_id"),
        "selected_operation_id":
            selected_id,
        "selected_overlap": value.get(
            "selected_overlap"),
    }


def _protected_bridge_union(value):
    """Return a logged direct-bridge union without reconstructing it."""
    if not isinstance(value, dict):
        return None
    for row in reversed(
            value.get("goal_selections", ())):
        if not isinstance(row, dict):
            continue
        candidate = row.get(
            "protected_candidate_union")
        if isinstance(candidate, dict):
            return candidate
    return None


def _flow_candidate_key(decision, flow_artifact):
    """Identify the flow proposal even when shadow/advisory falls back."""
    keys = flow_artifact.get(
        "admissible_candidate_keys", ())
    if (isinstance(keys, (list, tuple))
            and len(keys) == 1
            and isinstance(keys[0], str)
            and keys[0]):
        return keys[0]
    return decision.selected_candidate_key


def _flow_selection_disposition(decision):
    artifact = decision.artifact
    if decision.controller_mode == "unified_shadow":
        return "shadow-only"
    if artifact.get("advisory_accepted") is False:
        return "guarded-fallback"
    if artifact.get("advisory_accepted") is True:
        return "advisory-accepted"
    if decision.controller_mode == "unified_flow_live":
        return "live-accepted"
    return "controller-selected"


class ControlEventEmitter:
    """Write compact semantic-boundary events, never per-probe/path events."""

    EMITTER_IDENTITY = "unified-control-events/1.0"

    def __init__(self):
        # Completed asynchronous shadow batches may remain cached and be
        # surfaced by more than one decision.  A request is one observation,
        # so emit it once per run-scoped emitter.
        self._emitted_domain_request_ids = set()
        self._emitted_resource_batch_ids = set()
        # Capacity events describe changes across decisions.  Index by the
        # stable resource identity rather than snapshot-scoped capacity ID.
        self._last_resource_capacity = {}

    @staticmethod
    def _resource_schedule_artifact(pressure):
        if not isinstance(pressure, dict):
            return None
        artifact = pressure.get(
            "identity_resource_schedule")
        if not isinstance(artifact, dict):
            return None
        schedule = artifact.get("exact")
        if not isinstance(schedule, dict):
            return None
        return artifact, schedule

    @staticmethod
    def _resource_snapshot_id(schedule):
        snapshot_ids = sorted(set(
            str(row.get("snapshot_id"))
            for row in schedule.get(
                "capacities", ())
            if isinstance(row, dict)
            and row.get("snapshot_id")))
        if len(snapshot_ids) == 1:
            return snapshot_ids[0]
        if snapshot_ids:
            return structural_hash(
                snapshot_ids)
        return "capacityless-shadow"

    @staticmethod
    def _resource_claim_payload(
            schedule, claim, disposition,
            reason=None, entry=None,
            snapshot_id=None):
        entry = (
            entry
            if isinstance(entry, dict)
            else {})
        return {
            "claim_id":
                structural_hash(claim),
            "conflict_resource_ids":
                list(entry.get(
                    "conflict_resource_ids",
                    ())),
            "conflicting_operation_ids":
                list(entry.get(
                    "conflicting_operation_ids",
                    ())),
            "disposition": disposition,
            "event_schema_version":
                CONTROL_EVENT_SCHEMA_VERSION,
            "exclusive": bool(
                claim["exclusive"]),
            "hardness": claim["hardness"],
            "operation_id":
                claim[
                    "source_operation_id"],
            "quantity": int(
                claim["quantity"]),
            "reason": reason,
            "resource": claim["resource"],
            "schedule_digest":
                schedule["decision_digest"],
            "scheduler_identity":
                schedule[
                    "scheduler_identity"],
            "shadow_only": True,
            "snapshot_id": (
                snapshot_id
                or ControlEventEmitter
                ._resource_snapshot_id(
                    schedule)),
            "source_step_id":
                claim["source_step_id"],
            "window": claim["window"],
        }

    def emit_resource_schedule_artifacts(
            self, writer, turn, schedule,
            caused_by=()):
        """Emit full identity/window resource evidence for one shadow schedule."""
        if not isinstance(schedule, dict):
            return ()
        parents = tuple(caused_by)
        emitted = []
        for capacity in schedule.get(
                "capacities", ()):
            if not isinstance(capacity, dict):
                continue
            resource = capacity.get(
                "resource")
            window = capacity.get(
                "window")
            if (not isinstance(resource, dict)
                    or not isinstance(
                        window, dict)):
                continue
            resource_id = structural_hash(
                resource)
            capacity_id = structural_hash(
                capacity)
            previous = (
                self
                ._last_resource_capacity
                .get(resource_id))
            if (previous is not None
                    and previous[
                        "capacity_id"]
                    == capacity_id):
                continue
            event = writer.emit(
                "resource_capacity_changed",
                turn, {
                    "authority":
                        capacity["authority"],
                    "capacity_id":
                        capacity_id,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "previous_capacity_id":
                        (
                            previous[
                                "capacity_id"]
                            if previous
                            is not None
                            else None),
                    "previous_quantity":
                        (
                            previous[
                                "quantity"]
                            if previous
                            is not None
                            else None),
                    "quantity": int(
                        capacity[
                            "quantity"]),
                    "reason": (
                        "snapshot-changed"
                        if previous
                        is not None
                        else
                        "initial-observation"),
                    "resource": resource,
                    "shadow_only": True,
                    "snapshot_id":
                        capacity[
                            "snapshot_id"],
                    "window": window,
                }, caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
            self._last_resource_capacity[
                resource_id] = {
                    "capacity_id":
                        capacity_id,
                    "quantity": int(
                        capacity[
                            "quantity"]),
                }
        entries = {
            row["operation_id"]: row
            for row in schedule.get(
                "entries", ())
            if isinstance(row, dict)
            and isinstance(
                row.get(
                    "operation_id"),
                str)
        }
        snapshot_id = (
            self._resource_snapshot_id(
                schedule))
        for request in schedule.get(
                "requests", ()):
            if not isinstance(request, dict):
                continue
            operation_id = request.get(
                "operation_id")
            entry = entries.get(
                operation_id, {})
            selected = bool(
                entry.get(
                    "selected", False))
            reason = (
                None
                if selected
                else str(
                    entry.get(
                        "reason")
                    or "scheduler-rejected"))
            for claim in request.get(
                    "claims", ()):
                if not isinstance(claim, dict):
                    continue
                requested = writer.emit(
                    "resource_claim_requested",
                    turn,
                    self._resource_claim_payload(
                        schedule, claim,
                        "requested",
                        entry=entry,
                        snapshot_id=(
                            snapshot_id)),
                    caused_by=list(parents))
                emitted.append(
                    requested)
                parents = (
                    requested[
                        "event_id"],)
                event_type = (
                    "resource_claim_reserved"
                    if selected
                    else
                    "resource_claim_rejected")
                disposition = (
                    "reserved"
                    if selected
                    else "rejected")
                result = writer.emit(
                    event_type, turn,
                    self._resource_claim_payload(
                        schedule, claim,
                        disposition,
                        reason=reason,
                        entry=entry,
                        snapshot_id=(
                            snapshot_id)),
                    caused_by=list(parents))
                emitted.append(result)
                parents = (
                    result["event_id"],)
        return tuple(emitted)

    @staticmethod
    def emit_city_defense_operations(
            writer, turn, artifact,
            caused_by=()):
        """Emit the shadow proposal graph and exact assignment readout."""
        if not isinstance(artifact, dict):
            return ()
        analysis = artifact.get(
            "analysis")
        assignment = artifact.get(
            "assignment")
        if (not isinstance(analysis, dict)
                or not isinstance(
                    assignment, dict)):
            return ()
        entries = {
            row.get("operation_id"): row
            for row in assignment.get(
                "entries", ())
            if isinstance(row, dict)
            and isinstance(
                row.get("operation_id"),
                str)
        }
        assignment_digest = (
            assignment.get(
                "decision_digest"))
        snapshot_id = str(
            analysis.get(
                "snapshot_id")
            or "unknown-city-defense-snapshot")
        parents = tuple(caused_by)
        emitted = []
        operations = sorted(
            (
                row for row
                in analysis.get(
                    "operations", ())
                if isinstance(row, dict)
                and isinstance(
                    row.get(
                        "operation_id"),
                    str)
            ),
            key=lambda row:
            row["operation_id"])
        for operation in operations:
            operation_id = (
                operation[
                    "operation_id"])
            entry = entries.get(
                operation_id, {})
            selected = bool(
                entry.get(
                    "selected", False))
            reason = entry.get(
                "reason")
            if reason is None:
                reason = operation.get(
                    "support_reason")
            payload = {
                "actor_id": (
                    None
                    if operation.get(
                        "actor_id")
                    is None
                    else str(
                        operation[
                            "actor_id"])),
                "assignment_digest":
                    assignment_digest,
                "bid": float(
                    operation.get(
                        "bid", 0.0)),
                "claims": list(
                    operation.get(
                        "claims", ())),
                "deadline_turn":
                    operation.get(
                        "deadline_turn"),
                "event_schema_version":
                    CONTROL_EVENT_SCHEMA_VERSION,
                "expected_prevented_loss":
                    float(
                        operation.get(
                            "expected_prevented_loss",
                            0.0)),
                "next_action":
                    operation.get(
                        "next_action"),
                "operation_digest":
                    structural_hash(
                        operation),
                "operation_id":
                    operation_id,
                "operation_type": str(
                    operation.get(
                        "operation_type")
                    or "unknown"),
                "opportunity_cost":
                    float(
                        operation.get(
                            "opportunity_cost",
                            0.0)),
                "policy_authority":
                    False,
                "provenance": list(
                    operation.get(
                        "provenance")
                    or (
                        "city-defense-shadow",)),
                "reason_code": (
                    None
                    if selected
                    else str(
                        reason
                        or "not-selected")),
                "requirement_id":
                    operation.get(
                        "requirement_id"),
                "selected": selected,
                "shadow_only": True,
                "snapshot_id":
                    snapshot_id,
                "state": "proposed",
                "target_id": (
                    "city:{}".format(
                        operation[
                            "city_id"])
                    if operation.get(
                        "city_id")
                    is not None
                    else None),
            }
            proposed = writer.emit(
                "operation_proposed",
                turn, payload,
                caused_by=list(parents))
            emitted.append(
                proposed)
            parents = (
                proposed[
                    "event_id"],)
            if not selected:
                continue
            selected_payload = dict(
                payload)
            selected_payload[
                "state"] = (
                    "step_selected")
            selected_payload[
                "reason_code"] = None
            selected_event = writer.emit(
                "operation_step_selected",
                turn,
                selected_payload,
                caused_by=list(parents))
            emitted.append(
                selected_event)
            parents = (
                selected_event[
                    "event_id"],)
        return tuple(emitted)

    def emit_resource_schedule_results(
            self, writer, turn, artifacts,
            caused_by=()):
        """Emit completed resource batches once, including final drains."""
        parents = tuple(caused_by)
        emitted = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            batch_id = artifact.get(
                "batch_id")
            schedule = artifact.get(
                "exact")
            if (not isinstance(batch_id, str)
                    or not batch_id
                    or batch_id in
                    self._emitted_resource_batch_ids
                    or not isinstance(
                        schedule, dict)):
                continue
            entries = tuple(
                row
                for row in schedule.get(
                    "entries", ())
                if isinstance(row, dict))
            event = writer.emit(
                "resource_schedule_decided",
                turn, {
                    "artifact_hash":
                        artifact[
                            "artifact_hash"],
                    "batch_id": batch_id,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "exact_status":
                        schedule["status"],
                    "fallback_reason":
                        schedule.get(
                            "fallback_reason"),
                    "packet_committed_operation_ids":
                        list(artifact.get(
                            "packet_committed_operation_ids",
                            ())),
                    "packet_exact_selection_equal":
                        bool(artifact.get(
                            "packet_exact_selection_equal",
                            False)),
                    "policy_authority": False,
                    "rejected_operation_count":
                        sum(
                            not row.get(
                                "selected",
                                False)
                            for row in entries),
                    "request_count": int(
                        artifact.get(
                            "request_count",
                            len(schedule.get(
                                "requests", ())))),
                    "schedule_digest":
                        schedule[
                            "decision_digest"],
                    "scheduler_identity":
                        schedule[
                            "scheduler_identity"],
                    "selected_operation_ids":
                        list(schedule.get(
                            "selected_operation_ids",
                            ())),
                    "shadow_only": True,
                }, caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
            details = (
                self.emit_resource_schedule_artifacts(
                    writer, turn, schedule,
                    caused_by=parents))
            emitted.extend(details)
            if details:
                parents = (
                    details[-1][
                        "event_id"],)
            operation_events = (
                self
                .emit_city_defense_operations(
                    writer, turn,
                    artifact.get(
                        "city_defense"),
                    caused_by=parents))
            emitted.extend(
                operation_events)
            if operation_events:
                parents = (
                    operation_events[-1][
                        "event_id"],)
            self._emitted_resource_batch_ids.add(
                batch_id)
        return tuple(emitted)

    @staticmethod
    def emit_resource_releases(
            writer, turn, reservations,
            ledger_digest, scheduler_identity,
            caused_by=()):
        """Emit release/expiry rows returned by a reservation ledger."""
        parents = tuple(caused_by)
        emitted = []
        for reservation in reservations:
            state = getattr(
                getattr(
                    reservation,
                    "state", None),
                "value", None)
            if state not in (
                    "released", "expired"):
                continue
            for claim in getattr(
                    reservation, "claims", ()):
                claim_payload = (
                    claim.to_dict())
                payload = {
                    "claim_id":
                        claim.claim_id,
                    "conflict_resource_ids":
                        [],
                    "conflicting_operation_ids":
                        [],
                    "disposition": state,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "exclusive":
                        claim.exclusive,
                    "hardness":
                        claim.hardness.value,
                    "operation_id":
                        reservation
                        .operation_id,
                    "quantity":
                        claim.quantity,
                    "reason":
                        reservation.reason,
                    "resource":
                        claim_payload[
                            "resource"],
                    "schedule_digest":
                        ledger_digest,
                    "scheduler_identity":
                        scheduler_identity,
                    "shadow_only": True,
                    "snapshot_id":
                        reservation
                        .snapshot_id,
                    "source_step_id":
                        claim.source_step_id,
                    "window":
                        claim_payload[
                            "window"],
                }
                event = writer.emit(
                    "resource_claim_released",
                    turn, payload,
                    caused_by=list(parents))
                emitted.append(event)
                parents = (
                    event["event_id"],)
        return tuple(emitted)

    def emit_domain_estimate_artifacts(
            self, writer, turn, artifacts,
            caused_by=()):
        """Emit completed shadow rows once, including final drained batches."""
        parents = tuple(caused_by)
        emitted = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            for row in artifact.get(
                    "estimates", ()):
                if not isinstance(row, dict):
                    continue
                event_type = row.get(
                    "event_type")
                payload = row.get(
                    "event_payload")
                if (event_type not in (
                        "domain_estimate_emitted",
                        "domain_estimate_abstained")
                        or not isinstance(payload, dict)):
                    continue
                request_id = payload.get(
                    "request_id",
                    row.get("request_id"))
                if (not isinstance(request_id, str)
                        or not request_id
                        or request_id in
                        self._emitted_domain_request_ids):
                    continue
                event = writer.emit(
                    event_type, turn, payload,
                    caused_by=list(parents))
                self._emitted_domain_request_ids.add(
                    request_id)
                emitted.append(event)
                parents = (event["event_id"],)
        return tuple(emitted)

    @staticmethod
    def _emit(
            writer, event_type, turn, query,
            decision, parents, summary,
            flow_artifact=None,
            decision_hash=None):
        parents = tuple(str(value) for value in parents)
        summary = json.loads(
            canonical_json_bytes(
                dict(summary)).decode("utf-8"))
        payload = {
            "artifact_hash": structural_hash(
                summary),
            "config_digest": query.config_digest,
            "controller_decision_hash":
                (decision_hash
                 if decision_hash is not None
                 else decision.decision_hash),
            "event_schema_version":
                CONTROL_EVENT_SCHEMA_VERSION,
            "parent_event_ids": list(parents),
            "query_id": query.query_id,
            "semantic_epoch":
                query.semantic_epoch,
            "summary": summary,
            "topology_generation":
                _topology_generation(
                    query, flow_artifact),
        }
        return writer.emit(
            event_type, turn, payload,
            caused_by=list(parents))

    def emit_decision(
            self, writer, turn, query,
            decision, caused_by=()):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "control events require ControlQuery")
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "control events require ControlDecision")
        parents = tuple(caused_by)
        emitted = []
        flow_artifact = _flow_artifact(
            decision)
        # A unified artifact contains probe, projection, transport, and packet
        # blocks. Its semantic hash is intentionally comprehensive, but
        # recomputing it for every event in the same causal chain made
        # observability more expensive than the controller itself.
        decision_hash = decision.decision_hash
        direct_ranker = (
            decision.artifact.get(
                "ranker_artifact")
            if isinstance(
                decision.artifact, dict)
            else None)
        pressure = (
            flow_artifact.get(
                "pressure_artifact", {})
            if flow_artifact is not None
            else direct_ranker
            if isinstance(direct_ranker, dict)
            else {})
        direct_bridge = (
            direct_ranker.get("bridge")
            if (
                flow_artifact is None
                and isinstance(direct_ranker, dict)
                and isinstance(
                    direct_ranker.get("bridge"),
                    dict))
            else None)
        domain_estimates = (
            pressure.get("domain_estimates")
            if isinstance(pressure, dict)
            else None)
        if isinstance(domain_estimates, dict):
            domain_events = (
                self.emit_domain_estimate_artifacts(
                    writer, turn,
                    (domain_estimates,),
                    caused_by=parents))
            emitted.extend(domain_events)
            if domain_events:
                parents = (
                    domain_events[-1][
                        "event_id"],)
        resource_artifacts = (
            self._resource_schedule_artifact(
                pressure))
        if resource_artifacts is not None:
            resource_events = (
                self.emit_resource_schedule_results(
                    writer, turn,
                    (resource_artifacts[0],),
                    caused_by=parents))
            emitted.extend(
                resource_events)
            if resource_events:
                parents = (
                    resource_events[-1][
                        "event_id"],)
        teleology = (
            pressure.get("teleology", {})
            if isinstance(pressure, dict)
            else {})
        if isinstance(teleology, dict) and teleology:
            event = self._emit(
                writer, "teleology_estimated",
                turn, query, decision, parents, {
                    "artifact_hash":
                        teleology.get(
                            "artifact_hash"),
                    "calibration":
                        teleology.get(
                            "calibration"),
                    "estimator_hierarchy":
                        teleology.get(
                            "estimator_hierarchy",
                            ()),
                    "goal_count": len(
                        teleology.get(
                            "goal_losses", ())),
                    "operation_count": len(
                        teleology.get(
                            "operation_estimates",
                            ())),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
            calibration = teleology.get(
                "calibration", {})
            if (isinstance(calibration, dict)
                    and calibration.get(
                        "model") is not None):
                estimates = tuple(
                    row.get("transition_value")
                    for row in teleology.get(
                        "operation_estimates", ())
                    if isinstance(row, dict)
                    and isinstance(
                        row.get(
                            "transition_value"),
                        dict))
                event = self._emit(
                    writer,
                    "transition_value_estimated",
                    turn, query, decision, parents, {
                        "abstained_operation_count":
                            sum(
                                not row.get(
                                    "calibrated",
                                    False)
                                for row in estimates),
                        "all_candidate_support":
                            calibration.get(
                                "all_candidate_support",
                                False),
                        "authority_active":
                            calibration.get(
                                "authority_active",
                                False),
                        "authority_requested":
                            calibration.get(
                                "authority_requested",
                                False),
                        "gate_reason":
                            calibration.get(
                                "gate_reason"),
                        "model":
                            calibration.get("model"),
                        "operation_count":
                            len(estimates),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
        path_persistence = (
            pressure.get("path_persistence")
            if isinstance(pressure, dict)
            else None)
        if isinstance(path_persistence, dict):
            event = self._emit(
                writer,
                "path_persistence_applied",
                turn, query, decision, parents, {
                    "artifact_hash":
                        path_persistence.get(
                            "artifact_hash"),
                    "authority_active":
                        path_persistence.get(
                            "authority_active",
                            False),
                    "decision":
                        path_persistence.get(
                            "decision"),
                    "fallback_reason":
                        path_persistence.get(
                            "fallback_reason"),
                    "maximum_priority_regret":
                        path_persistence.get(
                            "maximum_priority_regret"),
                    "priority_regret":
                        path_persistence.get(
                            "priority_regret"),
                    "reordered":
                        path_persistence.get(
                            "reordered", False),
                    "scalar_corridor":
                        path_persistence.get(
                            "scalar_corridor"),
                    "selected_corridor":
                        path_persistence.get(
                            "selected_corridor"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        if direct_bridge is not None:
            potential_summary = direct_bridge.get(
                "potential_summary")
            potential_rows = (
                (potential_summary,)
                if isinstance(
                    potential_summary, dict)
                else potential_summary
                if isinstance(
                    potential_summary, (list, tuple))
                else None)
            if potential_rows is not None:
                event = self._emit(
                    writer, "bridge_estimated",
                    turn, query, decision, parents, {
                        "controller_mode":
                            decision.controller_mode,
                        "goal_summaries":
                            potential_rows,
                        "normalization_contract":
                            query
                            .normalization_contract_hash,
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            probe_batches = []
            goal_readouts = []
            for goal_row in direct_bridge.get(
                    "goal_selections", ()):
                if not isinstance(goal_row, dict):
                    continue
                goal_id = goal_row.get(
                    "goal_id")
                for side in (
                        "forward", "backward"):
                    probe = goal_row.get(
                        "{}_probe".format(side))
                    if not isinstance(probe, dict):
                        continue
                    probe_batches.append({
                        "artifact_hash":
                            probe.get(
                                "artifact_hash"),
                        "goal_id": goal_id,
                        "health":
                            probe.get("health"),
                        "meet_count":
                            probe.get(
                                "meet_count"),
                        "path_count":
                            probe.get(
                                "path_count"),
                        "side": side,
                    })
                selection = goal_row.get(
                    "selection")
                if isinstance(selection, dict):
                    goal_readouts.append({
                        "fallback_reason":
                            selection.get(
                                "fallback_reason"),
                        "fallback_required":
                            selection.get(
                                "fallback_required",
                                False),
                        "goal_id": goal_id,
                        "selected_operation_count":
                            len(selection.get(
                                "selected_operation_node_ids",
                                ())),
                    })
            if probe_batches:
                event = self._emit(
                    writer,
                    "probe_block_completed",
                    turn, query, decision, parents, {
                        "batches": probe_batches,
                        "controller_mode":
                            decision.controller_mode,
                        "goal_readouts":
                            goal_readouts,
                        "readout_source":
                            "protected-bridge-scalar",
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            if direct_bridge.get(
                    "fallback_required") is True:
                event = self._emit(
                    writer,
                    "controller_fallback",
                    turn, query, decision, parents, {
                        "controller_identity":
                            direct_bridge.get(
                                "controller_identity"),
                        "controller_mode":
                            decision.controller_mode,
                        "effective_candidate_key":
                            decision
                            .selected_candidate_key,
                        "fallback_chain": list(
                            decision.fallback_chain),
                        "reason":
                            direct_bridge.get(
                                "fallback_reason"),
                        "readout_source":
                            "protected-bridge-scalar",
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            candidate_union = (
                _protected_bridge_union(
                    direct_bridge))
            if candidate_union is not None:
                scalar = direct_bridge.get(
                    "scalar_decision", {})
                scalar_id = (
                    scalar.get(
                        "selected_route_id")
                    if isinstance(scalar, dict)
                    else None)
                selected_id = direct_bridge.get(
                    "selected_operation_id")
                calibration = (
                    teleology.get(
                        "calibration", {})
                    if isinstance(
                        teleology, dict)
                    else {})
                event = self._emit(
                    writer,
                    "flow_candidate_selected",
                    turn, query, decision, parents, {
                        "calibrated": bool(
                            calibration.get(
                                "authority_active",
                                False)),
                        "confidence": 0.0,
                        "effective_candidate_key":
                            decision
                            .selected_candidate_key,
                        "readout_source":
                            "protected-bridge-scalar",
                        "selected_candidate_key":
                            decision
                            .selected_candidate_key,
                        "selection_disposition":
                            _flow_selection_disposition(
                                decision),
                        "transport_readout": {
                            "candidate_regions": [],
                            "candidate_readouts": [],
                            "candidate_union":
                                candidate_union,
                            "disagrees_with_scalar":
                                selected_id != scalar_id,
                            "maximum_overlap": None,
                            "scalar_selected_operation_id":
                                scalar_id,
                            "selected_node_id": None,
                            "selected_operation_id":
                                selected_id,
                            "selected_overlap": None,
                        },
                        "typed_advantage": None,
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
        if flow_artifact is not None:
            flow = flow_artifact.get("flow", {})
            potential_summary = flow.get(
                "potential_summary")
            if isinstance(potential_summary, list):
                event = self._emit(
                    writer, "bridge_estimated",
                    turn, query, decision, parents, {
                        "goal_summaries":
                            potential_summary,
                        "normalization_contract":
                            query
                            .normalization_contract_hash,
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            probe_batches = flow.get(
                "probe_batches", ())
            if isinstance(probe_batches, list):
                event = self._emit(
                    writer,
                    "probe_block_completed",
                    turn, query, decision, parents, {
                        "batches": [
                            {
                                "artifact_hash":
                                    row.get(
                                        "artifact_hash"),
                                "health": row.get(
                                    "health"),
                                "path_count": len(
                                    row.get(
                                        "paths", ())),
                                "side": row.get(
                                    "side"),
                            }
                            for row in probe_batches
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            currents = flow.get(
                "requested_currents", ())
            if isinstance(currents, list):
                event = self._emit(
                    writer,
                    "path_current_deposited",
                    turn, query, decision, parents, {
                        "currents": [
                            {
                                "commodity_id":
                                    row.get(
                                        "commodity_id"),
                                "current_hash":
                                    structural_hash(row),
                                "probe_effective_sample_size":
                                    row.get(
                                        "probe_effective_sample_size"),
                                "successful_probe_count":
                                    row.get(
                                        "successful_probe_count"),
                            }
                            for row in currents
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            projections = flow.get(
                "projection_results", ())
            if isinstance(projections, list):
                event = self._emit(
                    writer, "flow_projected",
                    turn, query, decision, parents, {
                        "projections": [
                            {
                                "balance_residual":
                                    row.get(
                                        "balance_residual"),
                                "component_count":
                                    row.get(
                                        "component_count"),
                                "health": row.get(
                                    "health"),
                                "iterations": row.get(
                                    "iterations"),
                                "requested_current_hash":
                                    row.get(
                                        "requested_current_hash"),
                                "solver": row.get(
                                    "solver"),
                            }
                            for row in projections
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            transport = flow.get(
                "transport")
            if isinstance(transport, dict):
                final_state = transport.get(
                    "final_state", {})
                event = self._emit(
                    writer, "attention_advected",
                    turn, query, decision, parents, {
                        "backward_total":
                            final_state.get(
                                "backward_total"),
                        "edge_updates":
                            transport.get(
                                "edge_updates"),
                        "forward_total":
                            final_state.get(
                                "forward_total"),
                        "microsteps":
                            transport.get(
                                "microsteps"),
                        "readout":
                            _compact_transport_readout(
                                flow.get(
                                    "transport_readout")),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            packet = flow.get(
                "packet_decision")
            if isinstance(packet, dict):
                event = self._emit(
                    writer, "packet_reserved",
                    turn, query, decision, parents, {
                        "candidate_authority":
                            packet.get(
                                "candidate_authority"),
                        "packet_schedule":
                            packet.get(
                                "packet_schedule"),
                        "revalidation":
                            packet.get(
                                "revalidation"),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            event = self._emit(
                writer, "flow_candidate_selected",
                turn, query, decision, parents, {
                    "admissible_candidate_keys":
                        flow_artifact.get(
                            "admissible_candidate_keys",
                            ()),
                    "calibrated":
                        flow_artifact.get(
                            "calibrated", False),
                    "confidence":
                        flow_artifact.get(
                            "confidence", 0.0),
                    "effective_candidate_key":
                        decision
                        .selected_candidate_key,
                    "selected_candidate_key":
                        _flow_candidate_key(
                            decision,
                            flow_artifact),
                    "selection_disposition":
                        _flow_selection_disposition(
                            decision),
                    "transport_readout":
                        _compact_transport_readout(
                            flow.get(
                                "transport_readout")),
                    "typed_advantage":
                        flow_artifact.get(
                            "typed_advantage"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        validation = decision.artifact.get(
            "validation")
        if isinstance(validation, dict):
            event = self._emit(
                writer, "candidate_revalidated",
                turn, query, decision, parents,
                validation, flow_artifact,
                decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        if (decision.health in (
                "fallback", "unhealthy")
                or decision.fallback_chain):
            event = self._emit(
                writer, "controller_fallback",
                turn, query, decision, parents, {
                    "fallback_chain": list(
                        decision.fallback_chain),
                    "gate_reasons":
                        decision.artifact.get(
                            "gate_reasons", ()),
                    "health": decision.health,
                    "advisory_candidate_key":
                        decision.artifact.get(
                            "advisory_candidate_key"),
                    "advisory_candidate_terminal":
                        decision.artifact.get(
                            "advisory_candidate_terminal"),
                    "fallback_candidate_key":
                        decision.artifact.get(
                            "fallback_candidate_key"),
                    "fallback_candidate_terminal":
                        decision.artifact.get(
                            "fallback_candidate_terminal"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
        return tuple(emitted)

    def emit_outcome(
            self, writer, turn, query,
            decision, outcome, caused_by=()):
        if not isinstance(outcome, ControlOutcomeRecord):
            raise TypeError(
                "control outcome event has wrong type")
        return self._emit(
            writer, "control_outcome_recorded",
            turn, query, decision, caused_by,
            outcome.to_dict(),
            _flow_artifact(decision),
            outcome.decision_hash)

    def emit_transition_value_update(
            self, writer, turn, query,
            decision, update, caused_by=()):
        from ..pressure.transition_value import (
            TransitionValueUpdate,
        )
        if not isinstance(
                update, TransitionValueUpdate):
            raise TypeError(
                "transition value event has wrong type")
        return self._emit(
            writer, "transition_value_updated",
            turn, query, decision, caused_by,
            update.to_dict(),
            _flow_artifact(decision),
            decision.decision_hash)
