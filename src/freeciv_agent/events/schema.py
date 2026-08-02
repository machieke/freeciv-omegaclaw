"""V0 JSON Schema loading and validation."""

import copy
import hashlib
import json
import os

import jsonschema

from ..paths import repo_path


SCHEMA_VERSION = "1.0"
SCHEMA_DIR = repo_path("schemas", "freeciv-events", "v1")
ENVELOPE_PATH = os.path.join(SCHEMA_DIR, "envelope.schema.json")
PAYLOADS_PATH = os.path.join(SCHEMA_DIR, "payloads.schema.json")

KNOWN_EVENT_TYPES = (
    "run_started",
    "run_completed",
    "ruleset_compiled",
    "state_snapshot",
    "technology_catalog",
    "technology_progress",
    "production_state",
    "unit_lifecycle",
    "observation",
    "revision",
    "belief_conflict",
    "context_quarantine",
    "llm_proposal",
    "goal_selection",
    "verification",
    "quarantine",
    "pln_query",
    "pln_result",
    "pressure_propagated",
    "operation_scored",
    "conductance_updated",
    "teleology_estimated",
    "domain_estimate_emitted",
    "domain_estimate_abstained",
    "resource_schedule_decided",
    "resource_claim_requested",
    "resource_claim_reserved",
    "resource_claim_rejected",
    "resource_claim_released",
    "resource_capacity_changed",
    "operation_proposed",
    "operation_reserved",
    "operation_activated",
    "operation_step_selected",
    "operation_step_revalidated",
    "operation_step_committed",
    "operation_blocked",
    "operation_repaired",
    "operation_suspended",
    "operation_completed",
    "operation_failed",
    "operation_abandoned",
    "operation_expired",
    "transition_value_estimated",
    "transition_value_updated",
    "path_persistence_applied",
    "reverse_operator_applied",
    "requirement_set_materialized",
    "bridge_estimated",
    "probe_block_completed",
    "path_current_deposited",
    "flow_projected",
    "attention_advected",
    "packet_reserved",
    "packet_returned",
    "flow_candidate_selected",
    "candidate_revalidated",
    "controller_fallback",
    "control_outcome_recorded",
    "selection_coverage_sample",
    "rule_proposed",
    "rule_validated",
    "llm_call_scheduled",
    "llm_gateway_result",
    "rule_parameter_updated",
    "atomspace_revision_started",
    "snapshot_delta_computed",
    "projection_batch_applied",
    "atom_support_added",
    "atom_support_retracted",
    "atom_invalidated",
    "atom_rederived",
    "atomspace_revision_committed",
    "scope_activation_requested",
    "scope_materialized",
    "scope_budget_exhausted",
    "grounding_evaluated",
    "grounding_cache_hit",
    "derivation_fired",
    "derivation_unknown",
    "completeness_witness_used",
    "goal_instantiated",
    "goal_resolved",
    "operation_projected",
    "operation_candidate_instantiated",
    "operation_candidate_rejected",
    "pressure_graph_built",
    "atomspace_shadow_decision",
    "atomspace_authority_decision",
    "episode_opened",
    "episode_effect_observed",
    "episode_relief_attributed",
    "conductance_sample_recorded",
    "induced_rule_quarantined",
    "induced_rule_promoted",
    "induced_rule_demoted",
    "plan_created",
    "monitor_trigger",
    "plan_invalidated",
    "plan_step_executed",
    "action_sent",
    "action_result",
    "grounded_check",
    "metric_sample",
    "logging_gap",
)


def canonical_json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")


def structural_hash(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


_ENVELOPE_SCHEMA = _load(ENVELOPE_PATH)
_PAYLOADS_SCHEMA = _load(PAYLOADS_PATH)
_FORMAT_CHECKER = jsonschema.FormatChecker()
_ENVELOPE_VALIDATOR = jsonschema.Draft202012Validator(
    _ENVELOPE_SCHEMA, format_checker=_FORMAT_CHECKER)
_PAYLOAD_VALIDATORS = {}


def _inline_payload_schema(value, trail=()):
    """Resolve the published payload schema's acyclic local references once."""
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise ValueError("payload schema reference siblings are unsupported")
            prefix = "#/$defs/"
            reference = value["$ref"]
            if not reference.startswith(prefix):
                raise ValueError(
                    "payload schema reference must be local: {}".format(reference))
            name = reference[len(prefix):]
            if name in trail:
                raise ValueError(
                    "cyclic payload schema reference: {}".format(
                        " -> ".join(trail + (name,))))
            try:
                target = _PAYLOADS_SCHEMA["$defs"][name]
            except KeyError:
                raise ValueError(
                    "unknown payload schema reference: {}".format(reference))
            return _inline_payload_schema(target, trail + (name,))
        return dict(
            (key, _inline_payload_schema(item, trail))
            for key, item in value.items())
    if isinstance(value, list):
        return [_inline_payload_schema(item, trail) for item in value]
    return value


def _payload_validator(event_type):
    if event_type not in KNOWN_EVENT_TYPES:
        return None
    if event_type not in _PAYLOAD_VALIDATORS:
        payload_schema = _inline_payload_schema(
            _PAYLOADS_SCHEMA["$defs"][event_type], (event_type,))
        payload_schema["$schema"] = _PAYLOADS_SCHEMA["$schema"]
        _PAYLOAD_VALIDATORS[event_type] = jsonschema.Draft202012Validator(
            payload_schema, format_checker=_FORMAT_CHECKER)
    return _PAYLOAD_VALIDATORS[event_type]


def _errors(validator, value, prefix):
    result = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path)
        result.append({
            "path": prefix + (("." + path) if path else ""),
            "message": error.message,
            "validator": error.validator,
        })
    return result


def validate_event_schema(event):
    """Return schema diagnostics. Unknown types validate only the envelope."""
    diagnostics = _errors(_ENVELOPE_VALIDATOR, event, "event")
    if diagnostics or not isinstance(event, dict):
        return diagnostics
    validator = _payload_validator(event.get("type"))
    if validator is not None:
        diagnostics.extend(_errors(validator, event.get("payload"), "event.payload"))
    return diagnostics


def assert_event_schema(event):
    diagnostics = validate_event_schema(event)
    if diagnostics:
        first = diagnostics[0]
        raise ValueError("invalid event schema at {}: {}".format(first["path"], first["message"]))
    return event


def published_schemas():
    return copy.deepcopy(_ENVELOPE_SCHEMA), copy.deepcopy(_PAYLOADS_SCHEMA)
