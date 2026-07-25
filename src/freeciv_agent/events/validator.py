"""Streaming schema, ordering, proof, provenance, and causal validation."""

import argparse
import copy
import json
import os
import sys
from dataclasses import dataclass, field

from .schema import KNOWN_EVENT_TYPES, structural_hash, validate_event_schema


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    line: int = 0
    event_id: str = None
    path: str = None

    def to_dict(self):
        return {
            key: value for key, value in {
                "code": self.code, "message": self.message, "line": self.line,
                "event_id": self.event_id, "path": self.path,
            }.items() if value is not None
        }


@dataclass
class ValidationReport:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    event_count: int = 0
    game_id: str = None
    schema_version: str = None
    bytes_by_turn: dict = field(default_factory=dict)

    @property
    def valid(self):
        return not self.errors

    def to_dict(self):
        return {
            "valid": self.valid,
            "event_count": self.event_count,
            "game_id": self.game_id,
            "schema_version": self.schema_version,
            "bytes_by_turn": dict(sorted(self.bytes_by_turn.items())),
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
        }


def _proof_hashes(proof):
    rows = {node["node_id"]: node for node in proof.get("nodes", [])}
    memo, visiting = {}, set()

    def visit(node_id):
        if node_id not in rows:
            raise ValueError("unknown premise node {}".format(node_id))
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            raise ValueError("serialized proof reference cycle at {}".format(node_id))
        visiting.add(node_id)
        node = rows[node_id]
        child_hashes = [visit(child) for child in node.get("premise_node_refs", [])]
        material = copy.deepcopy(node)
        material.pop("subtree_hash", None)
        material.pop("node_id", None)
        material.pop("premise_node_refs", None)
        material["premise_subtree_hashes"] = child_hashes
        memo[node_id] = structural_hash(material)
        visiting.remove(node_id)
        return memo[node_id]

    for node_id in rows:
        visit(node_id)
    return rows, memo


def _check_proof(event, report, line):
    proof = event["payload"].get("proof")
    if not isinstance(proof, dict):
        return
    eid = event["event_id"]
    node_ids = [node.get("node_id") for node in proof.get("nodes", []) if isinstance(node, dict)]
    if len(node_ids) != len(set(node_ids)):
        report.errors.append(Diagnostic("E_PROOF_DUPLICATE_NODE", "proof node IDs are not unique", line, eid))
        return
    try:
        rows, calculated = _proof_hashes(proof)
    except ValueError as exc:
        report.errors.append(Diagnostic("E_PROOF_REFERENCE", str(exc), line, eid))
        return
    root = proof.get("root_node_id")
    if root not in rows:
        report.errors.append(Diagnostic("E_PROOF_ROOT", "proof root does not exist", line, eid))
        return
    for node_id, node in rows.items():
        if node.get("subtree_hash") != calculated[node_id]:
            report.errors.append(Diagnostic(
                "E_PROOF_HASH", "subtree hash mismatch for {}".format(node_id), line, eid))
        if node.get("crisp") and node.get("tv", {}).get("strength") != 1.0:
            report.errors.append(Diagnostic(
                "E_CRISP_TV_DRIFT", "crisp proof node {} has strength {}".format(
                    node_id, node.get("tv", {}).get("strength")), line, eid))
        atom_tv = node.get("atom", {}).get("tv", {})
        if node.get("atom", {}).get("crisp") and atom_tv.get("strength") != 1.0:
            report.errors.append(Diagnostic(
                "E_CRISP_TV_DRIFT", "crisp atom in proof node {} has strength {}".format(
                    node_id, atom_tv.get("strength")), line, eid))
    if proof.get("structural_hash") != calculated[root]:
        report.errors.append(Diagnostic("E_PROOF_ROOT_HASH", "proof structural hash mismatch", line, eid))
    hashes = [calculated[node_id] for node_id in rows]
    if len(hashes) != len(set(hashes)):
        report.errors.append(Diagnostic(
            "E_PROOF_NOT_DEDUPLICATED", "proof contains repeated structurally identical subtrees",
            line, eid))


def _has_action_root(event_id, parents, types):
    pending = list(parents.get(event_id, ()))
    seen = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if types.get(current) in ("llm_proposal", "monitor_trigger"):
            return True
        pending.extend(parents.get(current, ()))
    return False


def validate_stream(lines, require_action_roots=True):
    report = ValidationReport()
    ids, parents, types = set(), {}, {}
    expected_seq = {}
    last_turn = None
    revisions = set()
    sent_actions = {}
    result_actions = []
    invalid_plans = set()
    belief_conflicts = {}
    quarantine_operations = set()

    for line_number, raw in enumerate(lines, 1):
        raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not text.strip():
            continue
        try:
            event = json.loads(text)
        except (TypeError, ValueError) as exc:
            report.errors.append(Diagnostic("E_JSON", "invalid JSON: {}".format(exc), line_number))
            continue
        report.event_count += 1
        schema_errors = validate_event_schema(event)
        eid = event.get("event_id") if isinstance(event, dict) else None
        for error in schema_errors:
            report.errors.append(Diagnostic(
                "E_SCHEMA", error["message"], line_number, eid, error["path"]))
        if schema_errors:
            continue

        turn = event["turn"]
        report.bytes_by_turn[turn] = report.bytes_by_turn.get(turn, 0) + len(raw_bytes)
        if report.game_id is None:
            report.game_id = event["game_id"]
            report.schema_version = event["schema_version"]
        elif event["game_id"] != report.game_id:
            report.errors.append(Diagnostic(
                "E_GAME_ID", "multiple game IDs in one stream", line_number, eid))
        if event["schema_version"] != report.schema_version:
            report.errors.append(Diagnostic(
                "E_SCHEMA_MIX", "multiple schema versions in one stream", line_number, eid))
        if last_turn is not None and turn < last_turn:
            report.errors.append(Diagnostic(
                "E_TURN_ORDER", "turn {} follows turn {}".format(turn, last_turn), line_number, eid))
        expected = expected_seq.get(turn, 0)
        if event["seq"] != expected:
            report.errors.append(Diagnostic(
                "E_SEQ_GAP", "turn {} expected seq {}, got {}".format(turn, expected, event["seq"]),
                line_number, eid))
            expected_seq[turn] = max(expected, event["seq"] + 1)
        else:
            expected_seq[turn] = expected + 1
        last_turn = turn

        if eid in ids:
            report.errors.append(Diagnostic("E_DUPLICATE_EVENT_ID", "duplicate event_id", line_number, eid))
        missing = [parent for parent in event["caused_by"] if parent not in ids]
        if missing:
            report.errors.append(Diagnostic(
                "E_CAUSAL_PARENT", "missing or forward causal parents: {}".format(missing), line_number, eid))
        ids.add(eid)
        parents[eid] = list(event["caused_by"])
        types[eid] = event["type"]

        if event["type"] not in KNOWN_EVENT_TYPES:
            report.warnings.append(Diagnostic(
                "W_UNKNOWN_TYPE", "unknown event type preserved as raw JSON", line_number, eid))
        if event["type"] == "pln_result":
            _check_proof(event, report, line_number)
        elif event["type"] == "revision" and event["payload"].get("operation") == "apply":
            key = (event["payload"]["target_atom"]["atom_id"], event["payload"]["provenance_id"])
            if key in revisions:
                report.errors.append(Diagnostic(
                    "E_DUPLICATE_PROVENANCE", "same provenance applied twice to atom", line_number, eid))
            revisions.add(key)
        elif event["type"] == "belief_conflict":
            payload = event["payload"]
            conflict_id = payload["conflict_id"]
            left = set(payload["left_provenance_ids"])
            right = set(payload["right_provenance_ids"])
            if left & right:
                report.errors.append(Diagnostic(
                    "E_CONFLICT_OVERLAP",
                    "conflict lineages are not provenance-distinct",
                    line_number, eid))
            if conflict_id in belief_conflicts:
                report.errors.append(Diagnostic(
                    "E_DUPLICATE_CONFLICT_ID",
                    "duplicate belief conflict ID", line_number, eid))
            belief_conflicts[conflict_id] = {
                "event_id": eid,
                "provenance_ids": left | right,
                "target_atom_id": payload["target_atom_id"],
            }
        elif event["type"] == "context_quarantine":
            payload = event["payload"]
            operation_id = payload["operation_id"]
            conflict = belief_conflicts.get(payload["conflict_id"])
            if operation_id in quarantine_operations:
                report.errors.append(Diagnostic(
                    "E_DUPLICATE_CONTEXT_QUARANTINE",
                    "duplicate context quarantine operation ID",
                    line_number, eid))
            quarantine_operations.add(operation_id)
            if conflict is None:
                report.errors.append(Diagnostic(
                    "E_CONTEXT_QUARANTINE_CONFLICT",
                    "context quarantine has no preceding belief conflict",
                    line_number, eid))
            else:
                excluded = set(payload["excluded_provenance_ids"])
                retained = set(payload["retained_provenance_ids"])
                if (excluded & retained
                        or excluded | retained != conflict["provenance_ids"]
                        or payload["target_atom_id"] != conflict["target_atom_id"]):
                    report.errors.append(Diagnostic(
                        "E_CONTEXT_QUARANTINE_PARTITION",
                        "context quarantine does not partition its conflict",
                        line_number, eid))
                if conflict["event_id"] not in event["caused_by"]:
                    report.errors.append(Diagnostic(
                        "E_CONTEXT_QUARANTINE_CAUSAL",
                        "context quarantine must directly cite its conflict event",
                        line_number, eid))
        elif event["type"] == "metric_sample":
            payload = event["payload"]
            if payload["name"] == "confabulation_write_through" and payload["value"] != 0:
                report.errors.append(Diagnostic(
                    "E_CONFABULATION_WRITE_THROUGH", "confabulation write-through is nonzero",
                    line_number, eid))
        elif event["type"] == "plan_invalidated":
            invalid_plans.add(event["payload"]["plan_id"])
        elif event["type"] == "action_sent":
            action_id = event["payload"]["action_id"]
            if action_id in sent_actions:
                report.errors.append(Diagnostic(
                    "E_DUPLICATE_ACTION_ID", "duplicate action_id", line_number, eid))
            plan_id = event["payload"].get("plan_id")
            if plan_id is not None and plan_id in invalid_plans:
                report.errors.append(Diagnostic(
                    "E_INVALID_PLAN_ACTION",
                    "action {} references already-invalid plan {}".format(
                        action_id, plan_id), line_number, eid))
            sent_actions[action_id] = eid
        elif event["type"] == "action_result":
            payload = event["payload"]
            response = payload.get("engine_response")
            # Fail-closed local preflight rejections intentionally have no
            # action_sent event because the transport was never invoked. They
            # are distinguishable from corrupt orphan engine results by their
            # rejection reason and direct verification parent.
            local_rejection = (
                payload.get("status") == "rejected"
                and isinstance(response, dict) and bool(response.get("reason"))
                and bool(event["caused_by"])
                and all(types.get(parent) == "verification"
                        for parent in event["caused_by"]))
            result_actions.append(
                (payload["action_id"], line_number, eid, local_rejection))

    if require_action_roots:
        for action_id, event_id in sent_actions.items():
            if not _has_action_root(event_id, parents, types):
                report.errors.append(Diagnostic(
                    "E_CAUSAL_ACTION_ROOT",
                    "action {} has no llm_proposal or monitor_trigger ancestor".format(action_id),
                    event_id=event_id))
    for action_id, line_number, event_id, local_rejection in result_actions:
        if action_id not in sent_actions and not local_rejection:
            report.errors.append(Diagnostic(
                "E_ACTION_RESULT_ORPHAN", "result has no matching action_sent", line_number, event_id))
    return report


def validate_file(path, require_action_roots=True):
    try:
        with open(path, "rb") as stream:
            return validate_stream(stream, require_action_roots=require_action_roots)
    except OSError as exc:
        report = ValidationReport()
        report.errors.append(Diagnostic("E_IO", str(exc)))
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="validate a PLN-FreeCiv JSONL event stream")
    parser.add_argument("path")
    parser.add_argument("--allow-rootless-actions", action="store_true")
    args = parser.parse_args(argv)
    report = validate_file(args.path, require_action_roots=not args.allow_rootless_actions)
    print(json.dumps(report.to_dict(), sort_keys=True, indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())
