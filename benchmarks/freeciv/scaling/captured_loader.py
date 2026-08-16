"""Streaming reconstruction of typed FDAS revisions from full telemetry."""

import hashlib
import json
from dataclasses import dataclass

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.state.atomspace.model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    term_kind,
)
from freeciv_agent.state.atomspace.predicates import (
    PredicateRegistry,
    PredicateSpec,
)
from freeciv_agent.state.atomspace.scopes import ScopeSpec


@dataclass(frozen=True)
class CapturedRevision:
    game_id: str
    turn: int
    revision_id: str
    snapshot_id: str
    records: tuple
    scopes: tuple
    predicate_registry: PredicateRegistry
    source_path: str
    source_sha256: str
    projection_summary: dict
    artifact_hash: str


def _validity(row):
    return ValidityInterval(
        snapshot_id=row.get("snapshot_id"),
        valid_from_turn=row.get("valid_from_turn"),
        valid_through_turn=row.get("valid_through_turn"),
        source_seq=row.get("source_seq"),
        ruleset_digest=row.get("ruleset_digest"),
    )


def _term(row):
    if row.get("term_type") == "entity":
        return EntityRef(str(row["kind"]), str(row["entity_id"]))
    if row.get("term_type") == "symbol":
        return SymbolRef(str(row["catalog"]), str(row["symbol"]))
    raise ValueError("captured atom contains an unknown typed term")


def _support(row):
    dependencies = tuple(DependencyRef(
        DependencyKey(
            str(item["key"]["kind"]),
            str(item["key"]["owner_id"]),
            str(item["key"]["path"])),
        str(item["fingerprint"]))
        for item in row["dependencies"])
    return SupportRecord(
        str(row["support_id"]),
        str(row["derivation_id"]),
        str(row["derivation_version"]),
        str(row["binding_hash"]),
        dependencies,
        str(row["witness_hash"]),
        tuple(str(value) for value in row.get("provenance_ids", ())),
        row.get("confidence_cap"),
    )


def _scope(row):
    return ScopeSpec(
        scope_id=str(row["scope_id"]),
        scope_kind=str(row["scope_kind"]),
        owner_player_id=int(row["owner_player_id"]),
        root_entities=tuple(_term(value) for value in row["root_entities"]),
        parent_scope_ids=tuple(row.get("parent_scope_ids", ())),
        imported_predicates=tuple(row.get("imported_predicates", ())),
        exported_predicates=tuple(row.get("exported_predicates", ())),
        namespaces=frozenset(AtomNamespace(value)
                             for value in row["namespaces"]),
        maximum_atoms=int(row["maximum_atoms"]),
        maximum_rule_fires=int(row["maximum_rule_fires"]),
        maximum_groundings=int(row["maximum_groundings"]),
        maximum_expansion_depth=int(row["maximum_expansion_depth"]),
        retention_policy=str(row["retention_policy"]),
        validity=_validity(row["validity"]),
    )


def _record(row, supports):
    key_row = row["key"]
    key = AtomKey(
        AtomNamespace(key_row["namespace"]),
        str(key_row["predicate"]),
        tuple(_term(value) for value in key_row["arguments"]),
        str(key_row["scope_id"]),
    )
    support_rows = tuple(supports[str(value)]
                         for value in row["support_ids"])
    return AtomRecord(
        atom_id=str(row["atom_id"]),
        key=key,
        authority=AuthorityClass(row["authority"]),
        truth=row["truth"],
        validity=_validity(row["validity"]),
        supports=support_rows,
        provenance_ids=tuple(str(value)
                             for value in row.get("provenance_ids", ())),
        lifecycle=str(row["lifecycle"]),
        materialization_key=str(row["materialization_key"]),
        tags=tuple(tuple(value) for value in row.get("tags", ())),
    )


def _registry(records, scopes):
    scope_kind = dict((row.scope_id, row.scope_kind) for row in scopes)
    groups = {}
    for record in records:
        key = record.key
        identity = (key.predicate, len(key.arguments))
        group = groups.setdefault(identity, {
            "argument_kinds": [set() for _ in key.arguments],
            "namespaces": set(),
            "scope_kinds": set(),
        })
        for index, term in enumerate(key.arguments):
            group["argument_kinds"][index].add(term_kind(term))
        group["namespaces"].add(key.namespace)
        group["scope_kinds"].add(scope_kind[key.scope_id])
    specs = []
    seen_predicates = set()
    for (predicate, arity), group in sorted(groups.items()):
        if predicate in seen_predicates:
            raise ValueError(
                "captured predicate has inconsistent arity: {}".format(
                    predicate))
        seen_predicates.add(predicate)
        specs.append(PredicateSpec(
            predicate=predicate,
            arity=arity,
            argument_kinds=tuple(tuple(sorted(value))
                                 for value in group["argument_kinds"]),
            namespaces=frozenset(group["namespaces"]),
            truth_kind="structural",
            allowed_scope_kinds=frozenset(group["scope_kinds"]),
            completeness_policy="open",
            export_policy="local",
            schema_version="captured-full-telemetry/1.0",
        ))
    return PredicateRegistry(tuple(specs))


def _materialize_revision(
        path, source_sha256, game_id, turn, payload,
        record_rows, support_rows, scope_rows):
    records = tuple(sorted(
        (_record(row, support_rows) for row in record_rows.values()),
        key=lambda value: value.atom_id))
    scopes = tuple(sorted(scope_rows.values(), key=lambda value: value.scope_id))
    details = payload["details"]
    expected_atoms = int(details["atom_count"])
    expected_scopes = int(details["scope_count"])
    expected_supports = int(details["support_count"])
    actual_supports = len({
        support.support_id for record in records for support in record.supports})
    if len(records) != expected_atoms:
        raise ValueError(
            "captured revision atom count mismatch: {} != {}".format(
                len(records), expected_atoms))
    if len(scopes) != expected_scopes:
        raise ValueError(
            "captured revision scope count mismatch: {} != {}".format(
                len(scopes), expected_scopes))
    if actual_supports != expected_supports:
        raise ValueError(
            "captured revision support count mismatch: {} != {}".format(
                actual_supports, expected_supports))
    registry = _registry(records, scopes)
    material = {
        "game_id": game_id,
        "records": [row.to_dict() for row in records],
        "revision_id": payload["revision_id"],
        "scopes": [row.to_dict() for row in scopes],
        "snapshot_id": payload["snapshot_id"],
        "turn": turn,
    }
    return CapturedRevision(
        game_id=game_id,
        turn=turn,
        revision_id=str(payload["revision_id"]),
        snapshot_id=str(payload["snapshot_id"]),
        records=records,
        scopes=scopes,
        predicate_registry=registry,
        source_path=path,
        source_sha256=source_sha256,
        projection_summary=dict(details.get("projection_summary", {})),
        artifact_hash=structural_hash(material),
    )


def load_captured_revisions(path, target_turns, expected_sha256=None):
    """Stream a full-detail ledger and retain the last revision per target turn."""
    targets = frozenset(int(value) for value in target_turns)
    if not targets or any(value < 0 for value in targets):
        raise ValueError("captured target turns must be non-negative")
    digest = hashlib.sha256()
    record_rows = {}
    support_rows = {}
    current_scopes = {}
    pending = []
    game_id = None
    with open(path, "rb") as handle:
        for raw in handle:
            digest.update(raw)
            event = json.loads(raw.decode("utf-8"))
            game_id = game_id or str(event["game_id"])
            event_type = event.get("type")
            payload = event.get("payload", {})
            details = payload.get("details", {})
            if event_type == "atomspace_revision_started":
                current_scopes = {}
            elif event_type == "scope_materialized":
                scope = _scope(details["scope"])
                current_scopes[scope.scope_id] = scope
            elif event_type == "atom_support_added":
                support = _support(details["support"])
                support_rows[support.support_id] = support
            elif event_type == "atom_rederived":
                row = details["record"]
                record_rows[str(row["atom_id"])] = row
            elif event_type == "atom_invalidated":
                record_rows.pop(str(details["atom_id"]), None)
            elif (event_type == "atomspace_revision_committed"
                  and int(event["turn"]) in targets):
                pending.append((
                    int(event["turn"]), dict(payload), dict(record_rows),
                    dict(support_rows), dict(current_scopes)))
    actual_sha256 = digest.hexdigest()
    if expected_sha256 is not None and actual_sha256 != str(expected_sha256):
        raise ValueError("captured event ledger SHA-256 mismatch")
    # Multiple source snapshots may occur in one game turn; the last committed
    # revision is the unambiguous captured state for that requested turn.
    latest = {}
    for row in pending:
        latest[row[0]] = row
    missing = sorted(targets.difference(latest))
    if missing:
        raise ValueError(
            "captured turns are absent from the ledger: {}".format(missing))
    return tuple(_materialize_revision(
        path, actual_sha256, game_id, turn, payload,
        records, supports, scopes)
        for turn, payload, records, supports, scopes in (
            latest[value] for value in sorted(latest)))
