"""Revision-bound typed FDAS queries with decision-staleness guards."""

from dataclasses import dataclass

from ...events.schema import structural_hash
from .model import AtomNamespace, EntityRef, SymbolRef


class StaleAtomSpaceRevision(RuntimeError):
    pass


@dataclass(frozen=True)
class AtomQuery:
    predicate: object = None
    namespace: object = None
    arguments: object = None
    scope_id: object = None

    def __post_init__(self):
        if self.predicate is not None and (
                not isinstance(self.predicate, str) or not self.predicate):
            raise ValueError("query predicate must be non-empty or absent")
        if self.namespace is not None:
            object.__setattr__(
                self, "namespace", AtomNamespace(self.namespace))
        if self.arguments is not None:
            arguments = tuple(self.arguments)
            if any(not isinstance(value, (EntityRef, SymbolRef))
                   for value in arguments):
                raise TypeError("query arguments must be typed terms")
            object.__setattr__(self, "arguments", arguments)
        if self.scope_id is not None and (
                not isinstance(self.scope_id, str) or not self.scope_id):
            raise ValueError("query scope ID must be non-empty or absent")


class RevisionQueryContext(object):
    def __init__(self, revision, expected_snapshot_id=None,
                 decision_safe=False):
        self.revision = revision
        self.expected_snapshot_id = expected_snapshot_id
        self.decision_safe = bool(decision_safe)
        if self.decision_safe:
            if not isinstance(expected_snapshot_id, str) or not expected_snapshot_id:
                raise ValueError(
                    "decision-safe query requires expected snapshot ID")
            if revision.snapshot_id != expected_snapshot_id:
                raise StaleAtomSpaceRevision(
                    "FDAS revision {} is stale for snapshot {}".format(
                        revision.snapshot_id, expected_snapshot_id))

    def records(self, query=None):
        query = query or AtomQuery()
        if not isinstance(query, AtomQuery):
            raise TypeError("FDAS records require AtomQuery")
        result = []
        for record in self.revision.records:
            if (query.predicate is not None
                    and record.key.predicate != query.predicate):
                continue
            if (query.namespace is not None
                    and record.key.namespace != query.namespace):
                continue
            if (query.arguments is not None
                    and record.key.arguments != query.arguments):
                continue
            if (query.scope_id is not None
                    and record.key.scope_id != query.scope_id):
                continue
            result.append(record)
        return tuple(result)

    def require_record(self, atom_id):
        record = self.revision.record(str(atom_id))
        if record is None:
            raise KeyError("unknown atom in revision: {}".format(atom_id))
        return record

    def explain(self, atom_id, support_limit=None):
        """Return a deterministic dependency/provenance explanation."""
        record = self.require_record(atom_id)
        if support_limit is not None and (
                isinstance(support_limit, bool)
                or not isinstance(support_limit, int)
                or support_limit < 1):
            raise ValueError("support limit must be positive or absent")
        supports = record.supports[
            :support_limit if support_limit is not None else None]
        rows = []
        for support in supports:
            premise_atom_ids = sorted(set(
                dependency.key.owner_id
                for dependency in support.dependencies
                if dependency.key.kind.startswith("atom")))
            grounding_dependencies = [
                dependency.to_dict()
                for dependency in support.dependencies
                if dependency.key.kind in (
                    "grounding-result", "ruleset-digest")]
            rows.append({
                "binding_hash": support.binding_hash,
                "confidence_cap": support.confidence_cap,
                "dependencies": [
                    dependency.to_dict()
                    for dependency in support.dependencies],
                "derivation_id": support.derivation_id,
                "derivation_version": support.derivation_version,
                "groundings": grounding_dependencies,
                "premise_atom_ids": premise_atom_ids,
                "provenance_ids": list(support.provenance_ids),
                "support_id": support.support_id,
                "witness_hash": support.witness_hash,
            })
        semantic = {
            "atom": record.key.to_dict(),
            "atom_id": record.atom_id,
            "authority": record.authority.value,
            "lifecycle": record.lifecycle,
            "revision_id": self.revision.revision_id,
            "snapshot_id": self.revision.snapshot_id,
            "supports": rows,
            "truth": record.truth,
            "validity": record.validity.to_dict(),
        }
        semantic["structural_hash"] = structural_hash(semantic)
        return semantic

    def why_not(self, query):
        """Explain a missing binary domain condition without inventing false."""
        if not isinstance(query, AtomQuery):
            raise TypeError("why-not requires AtomQuery")
        matches = self.records(query)
        if matches:
            semantic = {
                "blockers": [],
                "query": {
                    "arguments": [value.to_dict() for value in (
                        query.arguments or ())],
                    "namespace": (
                        query.namespace.value if query.namespace else None),
                    "predicate": query.predicate,
                    "scope_id": query.scope_id,
                },
                "status": "PROVED",
                "supporting_atom_ids": [value.atom_id for value in matches],
                "unknown": False,
            }
            semantic["structural_hash"] = structural_hash(semantic)
            return semantic
        complements = {
            "city-food-secure": "city-food-deficit",
            "city-food-deficit": "city-food-secure",
            "city-order-stable": "city-order-deficit",
            "city-order-deficit": "city-order-stable",
            "city-production-active": "city-production-stalled",
            "city-production-stalled": "city-production-active",
            "treasury-below-reserve": "treasury-structurally-safe",
            "treasury-structurally-safe": "treasury-below-reserve",
            "research-throughput-active": "research-throughput-stalled",
            "research-throughput-stalled": "research-throughput-active",
        }
        complement = complements.get(query.predicate)
        blocker_records = self.records(AtomQuery(
            predicate=complement,
            namespace=query.namespace,
            arguments=query.arguments,
            scope_id=query.scope_id,
        )) if complement is not None else ()
        status = "BLOCKED" if blocker_records else "UNKNOWN"
        semantic = {
            "blockers": [
                self.explain(value.atom_id) for value in blocker_records],
            "query": {
                "arguments": [value.to_dict() for value in (
                    query.arguments or ())],
                "namespace": (
                    query.namespace.value if query.namespace else None),
                "predicate": query.predicate,
                "scope_id": query.scope_id,
            },
            "status": status,
            "supporting_atom_ids": [],
            "unknown": status == "UNKNOWN",
        }
        semantic["structural_hash"] = structural_hash(semantic)
        return semantic
