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
