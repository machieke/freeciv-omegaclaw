"""Deterministic benchmark-only AtomSpace construction and invalidation cases."""

import random
import time
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
    ValidityInterval,
)
from freeciv_agent.state.atomspace.predicates import (
    PredicateRegistry,
    PredicateSpec,
)
from freeciv_agent.state.atomspace.scopes import ScopeSpec
from freeciv_agent.state.atomspace.transaction import AtomSpaceTransaction


TOPOLOGIES = frozenset((
    "local", "chain", "hub", "balanced_tree", "shared_dag",
    "distractor_shards", "mixed"))
INSERTION_ORDERS = frozenset(("canonical", "reverse", "shuffled"))


@dataclass(frozen=True)
class AtomSpaceCase:
    snapshot_id: str
    records: tuple
    scopes: tuple
    revision_id: str
    dependency_index: object
    source_dependency_keys: tuple
    topology: str
    insertion_order: str

    @property
    def atom_count(self):
        return len(self.records)

    @property
    def support_count(self):
        return sum(len(row.supports) for row in self.records)

    @property
    def scope_count(self):
        return len(self.scopes)

    @property
    def artifact_hash(self):
        return structural_hash({
            "records": [row.to_dict() for row in self.records],
            "revision_id": self.revision_id,
            "scopes": [row.to_dict() for row in self.scopes],
        })


@dataclass(frozen=True)
class AtomSpaceChurnResult:
    cold_revision_id: str
    incremental_revision_id: str
    cold_hash: str
    incremental_hash: str
    equivalent: bool
    changed_dependency_count: int
    affected_atom_count: int
    unsupported_atom_count: int
    invalidated_support_count: int
    cold_ms: float
    incremental_ms: float


def benchmark_registry():
    return PredicateRegistry((PredicateSpec(
        predicate="scale-fact",
        arity=1,
        argument_kinds=(("scale-entity",),),
        namespaces=frozenset((AtomNamespace.DIAGNOSTIC,)),
        truth_kind="crisp",
        allowed_scope_kinds=frozenset(("scale",)),
        completeness_policy="open",
        export_policy="local",
        schema_version="1.0",
    ),))


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("{} must be a positive integer".format(name))
    return value


def _atom_key(index, scope_id):
    return AtomKey(
        AtomNamespace.DIAGNOSTIC,
        "scale-fact",
        (EntityRef("scale-entity", "entity-{:09d}".format(index)),),
        scope_id,
    )


def build_atomspace_case(
        atom_count, scope_count=1, support_multiplicity=1,
        topology="mixed", seed=1729, insertion_order="canonical"):
    """Build and commit exactly the requested number of real typed records."""
    atom_count = _positive_integer(atom_count, "atom count")
    scope_count = _positive_integer(scope_count, "scope count")
    support_multiplicity = _positive_integer(
        support_multiplicity, "support multiplicity")
    if topology not in TOPOLOGIES:
        raise ValueError("unknown dependency topology")
    if insertion_order not in INSERTION_ORDERS:
        raise ValueError("unknown insertion order")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")

    snapshot_id = "scaling-atomspace-{}-{}-{}".format(
        atom_count, topology, seed)
    validity = ValidityInterval(
        snapshot_id=snapshot_id,
        valid_from_turn=0,
        valid_through_turn=0,
        source_seq=0,
    )
    per_scope = [0] * scope_count
    for index in range(atom_count):
        per_scope[index % scope_count] += 1
    scopes = tuple(ScopeSpec(
        scope_id="scale-scope-{:05d}".format(index),
        scope_kind="scale",
        owner_player_id=0,
        root_entities=(EntityRef("scale-root", "root-{:05d}".format(index)),),
        parent_scope_ids=(),
        imported_predicates=(),
        exported_predicates=(),
        namespaces=frozenset((AtomNamespace.DIAGNOSTIC,)),
        maximum_atoms=max(1, per_scope[index]),
        maximum_rule_fires=0,
        maximum_groundings=0,
        maximum_expansion_depth=0,
        retention_policy="benchmark-revision",
        validity=validity,
    ) for index in range(scope_count))
    keys = tuple(
        _atom_key(index, scopes[index % scope_count].scope_id)
        for index in range(atom_count))
    # One source per atom makes the local-churn fraction exact. Hub/chain
    # amplification remains a separate measured fan-out dimension.
    source_keys = tuple(DependencyKey(
        "benchmark-source",
        "source-{:06d}".format(index),
        "value",
    ) for index in range(atom_count))

    records = []
    for index, key in enumerate(keys):
        supports = []
        for support_index in range(support_multiplicity):
            dependencies = [DependencyRef(
                source_keys[(index + support_index) % len(source_keys)],
                "source-fingerprint-{:06d}".format(
                    (index + support_index) % len(source_keys)),
            )]
            parents = []
            use_chain = topology == "chain" or (
                topology == "mixed" and index % 3 == 1)
            use_hub = topology == "hub" or (
                topology == "mixed" and index % 3 == 2)
            if use_chain and index:
                parents.append(index - 1)
            elif use_hub and index:
                parents.append(0)
            elif topology == "balanced_tree" and index:
                parents.append((index - 1) // 2)
            elif topology == "shared_dag" and index:
                first = (index - 1) // 2
                parents.append(first)
                if first > 0:
                    parents.append(first - 1)
            elif topology == "distractor_shards":
                shard_size = max(1, atom_count // max(1, scope_count))
                shard_start = (index // shard_size) * shard_size
                if index > shard_start:
                    parents.append(index - 1)
            for parent in parents:
                dependencies.append(DependencyRef(
                    DependencyKey("atom-output", keys[parent].atom_id, "value"),
                    "atom-fingerprint-{:09d}".format(parent),
                ))
            supports.append(SupportRecord.create(
                derivation_id="scaling-generator",
                derivation_version="1.0",
                binding={"atom_index": index, "support_index": support_index},
                dependencies=tuple(dependencies),
                witness={"seed": seed, "topology": topology},
                provenance_ids=("scaling-generator",),
            ))
        records.append(AtomRecord.create(
            key=key,
            authority=AuthorityClass.CONTROL_MODEL,
            truth={"confidence": 1.0, "strength": 1.0},
            validity=validity,
            supports=tuple(supports),
            provenance_ids=("scaling-generator",),
            tags=(("benchmark", "atomspace-scaling"),),
        ))

    if insertion_order == "reverse":
        records.reverse()
    elif insertion_order == "shuffled":
        random.Random(seed).shuffle(records)
    transaction = AtomSpaceTransaction(
        snapshot_id,
        benchmark_registry(),
        scopes,
        maximum_atoms=atom_count,
    )
    for record in records:
        transaction.apply(record)
    revision_id = transaction.commit()
    return AtomSpaceCase(
        snapshot_id=snapshot_id,
        records=transaction.records,
        scopes=transaction.scopes,
        revision_id=revision_id,
        dependency_index=transaction.dependency_index,
        source_dependency_keys=source_keys,
        topology=topology,
        insertion_order=insertion_order,
    )


def apply_atomspace_churn(case, churn_fraction=0.01):
    """Compare a support-aware incremental update with its cold rebuild."""
    if not isinstance(case, AtomSpaceCase):
        raise TypeError("churn requires AtomSpaceCase")
    churn_fraction = float(churn_fraction)
    if not 0.0 < churn_fraction <= 1.0:
        raise ValueError("churn fraction must be in (0,1]")
    changed_count = max(1, int(round(case.atom_count * churn_fraction)))
    changed_keys = tuple(case.source_dependency_keys[:changed_count])
    changed_set = frozenset(changed_keys)
    desired = []
    for record in case.records:
        supports = []
        for support in record.supports:
            dependencies = tuple(DependencyRef(
                dependency.key,
                dependency.fingerprint + ":churn"
                if dependency.key in changed_set else dependency.fingerprint,
            ) for dependency in support.dependencies)
            supports.append(SupportRecord.from_hashes(
                support.derivation_id,
                support.derivation_version,
                support.binding_hash,
                dependencies,
                support.witness_hash,
                support.provenance_ids,
                support.confidence_cap,
            ))
        desired.append(AtomRecord.create(
            record.key,
            record.authority,
            record.truth,
            record.validity,
            tuple(supports),
            record.provenance_ids,
            record.lifecycle,
            record.tags,
        ))
    desired_by_id = dict((row.atom_id, row) for row in desired)

    started = time.perf_counter()
    cold = AtomSpaceTransaction(
        case.snapshot_id, benchmark_registry(), case.scopes,
        maximum_atoms=case.atom_count)
    for record in desired:
        cold.apply(record)
    cold_revision_id = cold.commit()
    cold_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    incremental = AtomSpaceTransaction(
        case.snapshot_id, benchmark_registry(), case.scopes,
        records=case.records, maximum_atoms=case.atom_count)
    invalidation = incremental.invalidate(changed_keys)
    for atom_id in invalidation.affected_atom_ids:
        incremental.apply(desired_by_id[atom_id])
    incremental_revision_id = incremental.commit()
    incremental_ms = (time.perf_counter() - started) * 1000.0
    cold_hash = structural_hash([row.to_dict() for row in cold.records])
    incremental_hash = structural_hash(
        [row.to_dict() for row in incremental.records])
    return AtomSpaceChurnResult(
        cold_revision_id=cold_revision_id,
        incremental_revision_id=incremental_revision_id,
        cold_hash=cold_hash,
        incremental_hash=incremental_hash,
        equivalent=(
            cold_revision_id == incremental_revision_id
            and cold_hash == incremental_hash),
        changed_dependency_count=len(changed_keys),
        affected_atom_count=len(invalidation.affected_atom_ids),
        unsupported_atom_count=len(invalidation.unsupported_atom_ids),
        invalidated_support_count=len(invalidation.invalid_support_ids),
        cold_ms=cold_ms,
        incremental_ms=incremental_ms,
    )
