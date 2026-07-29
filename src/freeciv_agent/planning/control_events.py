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


class ControlEventEmitter:
    """Write compact semantic-boundary events, never per-probe/path events."""

    EMITTER_IDENTITY = "unified-control-events/1.0"

    @staticmethod
    def _emit(
            writer, event_type, turn, query,
            decision, parents, summary,
            flow_artifact=None):
        parents = tuple(str(value) for value in parents)
        summary = json.loads(
            canonical_json_bytes(
                dict(summary)).decode("utf-8"))
        payload = {
            "artifact_hash": structural_hash(
                summary),
            "config_digest": query.config_digest,
            "controller_decision_hash":
                decision.decision_hash,
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
        if flow_artifact is not None:
            flow = flow_artifact.get("flow", {})
            pressure = flow_artifact.get(
                "pressure_artifact", {})
            teleology = pressure.get(
                "teleology", {})
            if isinstance(teleology, dict):
                event = self._emit(
                    writer, "teleology_estimated",
                    turn, query, decision, parents, {
                        "artifact_hash":
                            teleology.get(
                                "artifact_hash"),
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
                    }, flow_artifact)
                emitted.append(event)
                parents = (event["event_id"],)
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
                    }, flow_artifact)
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
                    }, flow_artifact)
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
                    }, flow_artifact)
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
                    }, flow_artifact)
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
                        "readout": flow.get(
                            "transport_readout"),
                    }, flow_artifact)
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
                    }, flow_artifact)
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
                    "selected_candidate_key":
                        decision
                        .selected_candidate_key,
                    "typed_advantage":
                        flow_artifact.get(
                            "typed_advantage"),
                }, flow_artifact)
            emitted.append(event)
            parents = (event["event_id"],)
        validation = decision.artifact.get(
            "validation")
        if isinstance(validation, dict):
            event = self._emit(
                writer, "candidate_revalidated",
                turn, query, decision, parents,
                validation, flow_artifact)
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
                }, flow_artifact)
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
            _flow_artifact(decision))
