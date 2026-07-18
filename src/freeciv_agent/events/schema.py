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
    "observation",
    "revision",
    "llm_proposal",
    "verification",
    "quarantine",
    "pln_query",
    "pln_result",
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


def _payload_validator(event_type):
    if event_type not in KNOWN_EVENT_TYPES:
        return None
    if event_type not in _PAYLOAD_VALIDATORS:
        schema = {
            "$schema": _PAYLOADS_SCHEMA["$schema"],
            "$ref": "#/$defs/{}".format(event_type),
            "$defs": copy.deepcopy(_PAYLOADS_SCHEMA["$defs"]),
        }
        _PAYLOAD_VALIDATORS[event_type] = jsonschema.Draft202012Validator(
            schema, format_checker=_FORMAT_CHECKER)
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

