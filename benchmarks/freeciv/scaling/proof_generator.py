"""Synthetic deep-proof workloads backed by the production rule engine."""

import time
from dataclasses import dataclass

from freeciv_agent.beliefs.rule_engine import (
    DeterministicRuleEngine,
    InferenceRequest,
)
from freeciv_agent.events.schema import structural_hash
from freeciv_agent.oracle.service import CrispStateView
from freeciv_agent.rulesets.ir import Requirement, Rule, RulesetIR
from freeciv_agent.state.atomspace.model import AtomNamespace

from .proof_reference import evaluate_reference


PROOF_SHAPES = frozenset((
    "and_tree", "binding_heavy", "chain", "cycle", "cycle_alternate",
    "cycle_only", "diamond_50", "diamond_90", "grounded_blocker",
    "or_one_success", "or_several_success", "or_unreachable",
    "shared_dag",
))


@dataclass(frozen=True)
class ProofCase:
    shape: str
    depth: int
    ruleset_ir: RulesetIR
    target: str
    expected_status: str
    expected_rule_count: int
    artifact_hash: str


@dataclass(frozen=True)
class ProofEvaluation:
    status: str
    proof_record_count: int
    prerequisite_count: int
    truncated: bool
    elapsed_ms: float
    artifact_hash: str
    matches_reference: bool
    work_counters: tuple

    def to_dict(self):
        return {
            "artifact_hash": self.artifact_hash,
            "elapsed_ms": self.elapsed_ms,
            "matches_reference": self.matches_reference,
            "prerequisite_count": self.prerequisite_count,
            "proof_record_count": self.proof_record_count,
            "status": self.status,
            "truncated": self.truncated,
            "work_counters": dict(self.work_counters),
        }


def _tech(index):
    return "scale-tech-{:05d}".format(index)


def _rule(index, dependency):
    antecedents = () if dependency is None else (Requirement(
        kind="Tech",
        name=dependency,
        range="Player",
        present=True,
        semantic="atom",
        predicate="has-tech",
        arguments=("$player", dependency),
        source={"kind": "scaling-generator"},
    ),)
    name = _tech(index)
    return Rule(
        rule_id="scale-rule-{:05d}".format(index),
        target_kind="tech",
        rule_name=name,
        display_name=name,
        target_predicate="researchable",
        target_arguments=("$player", name),
        antecedents=antecedents,
        obsolescence=(),
        quantitative={},
        disabled=False,
        source={"kind": "scaling-generator"},
    )


def _graph_rule(rule_id, target, dependencies=(), grounded=False):
    antecedents = [Requirement(
        kind="Tech",
        name=dependency,
        range="Player",
        present=True,
        semantic="atom",
        predicate="has-tech",
        arguments=("$player", dependency),
        source={"kind": "scaling-generator"},
    ) for dependency in dependencies]
    if grounded:
        antecedents.append(Requirement(
            kind="Resource",
            name="scale-grounded-blocker",
            range="Player",
            present=True,
            semantic="grounded",
            predicate="scale-grounded-ready",
            arguments=("$player",),
            source={"kind": "scaling-generator"},
        ))
    return Rule(
        rule_id=rule_id,
        target_kind="tech",
        rule_name=target,
        display_name=target,
        target_predicate="researchable",
        target_arguments=("$player", target),
        antecedents=tuple(antecedents),
        obsolescence=(),
        quantitative={},
        disabled=False,
        source={"kind": "scaling-generator"},
    )


def build_proof_case(depth, shape="chain"):
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("proof depth must be a positive integer")
    if shape not in PROOF_SHAPES:
        raise ValueError("unknown proof shape")
    rules = []
    for index in range(depth + 1):
        dependency = None if index == 0 else _tech(index - 1)
        if shape == "cycle" and index == 0:
            dependency = _tech(depth)
        rules.append(_rule(index, dependency))
    ir = RulesetIR(
        ruleset="scaling-proof-{}-{}".format(shape, depth),
        compiler_version="scaling-generator/1.0",
        source_hashes={"generator": "deterministic"},
        rules=tuple(rules),
        grounded_signatures=(),
        predicate_catalog=("has-tech", "researchable"),
    )
    reference = evaluate_reference(ir, _tech(depth))
    material = {
        "depth": depth,
        "rules": [rule.to_dict() for rule in rules],
        "shape": shape,
        "target": _tech(depth),
    }
    return ProofCase(
        shape=shape,
        depth=depth,
        ruleset_ir=ir,
        target=_tech(depth),
        expected_status=reference["status"],
        expected_rule_count=depth + 1,
        artifact_hash=structural_hash(material),
    )


def build_proof_dag_case(
        depth, relevant_nodes, shape="and_tree", distractor_count=0):
    """Build an exact-size relevant graph with depth controlled independently."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("proof depth must be a positive integer")
    if (isinstance(relevant_nodes, bool)
            or not isinstance(relevant_nodes, int)
            or relevant_nodes < depth + 1):
        raise ValueError("relevant nodes must cover the requested depth")
    if (isinstance(distractor_count, bool)
            or not isinstance(distractor_count, int)
            or distractor_count < 0):
        raise ValueError("distractor count must be nonnegative")
    if shape not in (
            "and_tree", "binding_heavy", "chain", "shared_dag",
            "diamond_50", "diamond_90", "or_one_success",
            "or_several_success", "or_unreachable", "cycle_alternate",
            "cycle_only", "grounded_blocker"):
        raise ValueError("unsupported proof DAG shape")
    names = tuple("scale-dag-tech-{:07d}".format(i)
                  for i in range(relevant_nodes))
    dependencies = dict((index, []) for index in range(relevant_nodes))
    for index in range(depth):
        dependencies[index].append(names[index + 1])
    if shape == "cycle_only":
        dependencies[depth].append(names[0])
    extras = range(depth + 1, relevant_nodes)
    for offset, index in enumerate(extras):
        parent = offset % max(1, depth)
        dependencies[parent].append(names[index])
        sharing_fraction = {
            "shared_dag": 1.0,
            "diamond_50": 0.50,
            "diamond_90": 0.90,
        }.get(shape, 0.0)
        should_share = (
            depth > 1 and sharing_fraction > 0.0
            and offset < int(round(
                max(0, relevant_nodes - depth - 1) * sharing_fraction)))
        if should_share:
            second = (parent + 1) % depth
            dependencies[second].append(names[index])
    if shape == "or_unreachable":
        dependencies[0] = [names[0]]
    rules = [
        _graph_rule(
            "scale-dag-rule-{:07d}".format(index),
            names[index], dependencies[index],
            grounded=(shape == "grounded_blocker" and index == 0))
        for index in range(relevant_nodes)
    ]
    if shape == "cycle_alternate":
        rules.append(_graph_rule(
            "scale-dag-cycle-alternative",
            names[0], (names[0],)))
    elif shape == "or_one_success":
        rules.append(_graph_rule(
            "scale-dag-or-grounded-blocker",
            names[0], (), grounded=True))
    elif shape == "or_several_success":
        rules.extend((
            _graph_rule(
                "scale-dag-or-success-a", names[0], (names[-1],)),
            _graph_rule(
                "scale-dag-or-success-b", names[0],
                (names[-2 if len(names) > 1 else -1],)),
        ))
    elif shape == "or_unreachable":
        rules.append(_graph_rule(
            "scale-dag-or-unreachable-grounded",
            names[0], (), grounded=True))
    elif shape == "binding_heavy":
        branch_count = min(64, max(1, relevant_nodes - depth - 1))
        for branch in range(branch_count):
            rules.append(_graph_rule(
                "scale-dag-binding-heavy-{:04d}".format(branch),
                names[0], (names[-1 - branch],)))
    for index in range(distractor_count):
        target = "scale-distractor-tech-{:07d}".format(index)
        rules.append(_graph_rule(
            "scale-distractor-rule-{:07d}".format(index), target))
    ir = RulesetIR(
        ruleset="scaling-proof-dag-{}-{}-{}".format(
            shape, relevant_nodes, distractor_count),
        compiler_version="scaling-generator/1.0",
        source_hashes={"generator": "deterministic"},
        rules=tuple(rules),
        grounded_signatures=("scale-grounded-ready",),
        predicate_catalog=(
            "has-tech", "researchable", "scale-grounded-ready"),
    )
    reference = evaluate_reference(ir, names[0])
    material = {
        "depth": depth,
        "distractor_count": distractor_count,
        "relevant_nodes": relevant_nodes,
        "rules": [rule.to_dict() for rule in rules],
        "shape": shape,
        "target": names[0],
    }
    return ProofCase(
        shape=shape,
        depth=depth,
        ruleset_ir=ir,
        target=names[0],
        expected_status=reference["status"],
        expected_rule_count=len(reference["visited_rule_ids"]),
        artifact_hash=structural_hash(material),
    )


def evaluate_proof_case(
        case, maximum_depth=None, maximum_bindings=None,
        maximum_rule_fires=None):
    if not isinstance(case, ProofCase):
        raise TypeError("proof evaluation requires ProofCase")
    request = InferenceRequest(
        mode="prove",
        target_pattern={
            "arguments": ["player", case.target],
            "predicate": "researchable",
        },
        scope_id="scope:scaling-proof",
        namespaces=frozenset((
            AtomNamespace.AUTHORITATIVE,
            AtomNamespace.RULESET,
            AtomNamespace.DERIVED,
        )),
        maximum_depth=(
            case.depth + 1 if maximum_depth is None else maximum_depth),
        maximum_bindings=(
            max(case.expected_rule_count * 4, case.depth + 2)
            if maximum_bindings is None else maximum_bindings),
        maximum_rule_fires=(
            max(case.expected_rule_count * 4, case.depth + 2)
            if maximum_rule_fires is None else maximum_rule_fires),
    )
    started = time.perf_counter()
    outcome = DeterministicRuleEngine(case.ruleset_ir).prove(
        "researchable",
        ("player", case.target),
        CrispStateView("scaling-proof-state", known_techs=(), player="player"),
        request=request,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    matches = (
        outcome.status == case.expected_status
        and len(outcome.proof_records) == case.expected_rule_count)
    return ProofEvaluation(
        status=outcome.status,
        proof_record_count=len(outcome.proof_records),
        prerequisite_count=len(outcome.prerequisite_names),
        truncated=outcome.truncated,
        elapsed_ms=elapsed_ms,
        artifact_hash=outcome.artifact_hash,
        matches_reference=matches,
        work_counters=tuple(sorted(outcome.counters.to_dict().items())),
    )
