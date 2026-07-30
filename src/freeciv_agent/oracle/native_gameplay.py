"""Black-box process boundary for optional native gameplay parity tools."""

import json
import subprocess

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)


class NativeGameplayOracleError(RuntimeError):
    pass


class NativeGameplayOracle:
    """Call a separately installed comparator using canonical JSON on stdin."""

    PROTOCOL_VERSION = "freeciv-native-gameplay-parity/1.0"

    def __init__(
            self, command, oracle_identity,
            timeout_seconds=5.0):
        command = tuple(command)
        if (not command
                or any(
                    not isinstance(value, str)
                    or not value
                    for value in command)):
            raise ValueError(
                "native gameplay command must contain non-empty strings")
        if (not isinstance(oracle_identity, str)
                or not oracle_identity):
            raise ValueError(
                "native gameplay oracle requires an identity")
        timeout_seconds = float(
            timeout_seconds)
        if timeout_seconds <= 0.0:
            raise ValueError(
                "native gameplay timeout must be positive")
        self.command = command
        self.oracle_identity = (
            oracle_identity)
        self.timeout_seconds = (
            timeout_seconds)

    def query(self, kind, payload):
        if kind not in (
                "movement", "combat"):
            raise ValueError(
                "unsupported native gameplay query kind")
        if not isinstance(payload, dict):
            raise TypeError(
                "native gameplay payload must be an object")
        request_id = structural_hash({
            "kind": kind,
            "oracle_identity":
                self.oracle_identity,
            "payload": payload,
            "protocol_version":
                self.PROTOCOL_VERSION,
        })
        request = {
            "kind": kind,
            "oracle_identity":
                self.oracle_identity,
            "payload": payload,
            "protocol_version":
                self.PROTOCOL_VERSION,
            "request_id": request_id,
        }
        try:
            completed = subprocess.run(
                self.command,
                input=canonical_json_bytes(
                    request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.timeout_seconds)
        except (OSError, subprocess.SubprocessError) as error:
            raise NativeGameplayOracleError(
                "native gameplay oracle invocation failed") from error
        if completed.returncode != 0:
            raise NativeGameplayOracleError(
                "native gameplay oracle returned status {}".format(
                    completed.returncode))
        try:
            response = json.loads(
                completed.stdout.decode(
                    "utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise NativeGameplayOracleError(
                "native gameplay oracle returned invalid JSON") from error
        if (not isinstance(response, dict)
                or response.get(
                    "protocol_version")
                != self.PROTOCOL_VERSION
                or response.get(
                    "oracle_identity")
                != self.oracle_identity
                or response.get(
                    "request_id")
                != request_id
                or not isinstance(
                    response.get("result"),
                    dict)):
            raise NativeGameplayOracleError(
                "native gameplay oracle response identity mismatch")
        return response["result"]


def compare_native_gameplay_cases(oracle, cases):
    """Compare clean-room results with a separately installed native oracle."""
    if not isinstance(
            oracle, NativeGameplayOracle):
        raise TypeError(
            "gameplay parity comparison requires NativeGameplayOracle")
    cases = tuple(cases)
    if not cases:
        raise ValueError(
            "gameplay parity comparison requires at least one case")
    case_ids = []
    normalized = []
    for row in cases:
        if not isinstance(row, dict):
            raise TypeError(
                "gameplay parity cases must be objects")
        case_id = row.get("case_id")
        kind = row.get("kind")
        payload = row.get("payload")
        derived_result = row.get(
            "derived_result")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(
                "gameplay parity case requires a case ID")
        if kind not in ("movement", "combat"):
            raise ValueError(
                "gameplay parity case has an unsupported kind")
        if not isinstance(payload, dict):
            raise TypeError(
                "gameplay parity case payload must be an object")
        if not isinstance(
                derived_result, dict):
            raise TypeError(
                "gameplay parity derived result must be an object")
        case_ids.append(case_id)
        normalized.append((
            case_id, kind, payload,
            derived_result))
    if len(case_ids) != len(
            set(case_ids)):
        raise ValueError(
            "gameplay parity case IDs must be unique")
    comparisons = []
    for case_id, kind, payload, derived in sorted(
            normalized,
            key=lambda value: value[0]):
        native = oracle.query(
            kind, payload)
        matches = (
            canonical_json_bytes(native)
            == canonical_json_bytes(
                derived))
        comparisons.append({
            "case_id": case_id,
            "derived_result": derived,
            "kind": kind,
            "matches": matches,
            "native_result": native,
        })
    report = {
        "case_count": len(comparisons),
        "comparisons": comparisons,
        "mismatch_count": sum(
            not row["matches"]
            for row in comparisons),
        "oracle_identity":
            oracle.oracle_identity,
        "passed": all(
            row["matches"]
            for row in comparisons),
        "protocol_version":
            oracle.PROTOCOL_VERSION,
        "schema_version": "1.0",
    }
    report["report_hash"] = structural_hash(
        report)
    return report
