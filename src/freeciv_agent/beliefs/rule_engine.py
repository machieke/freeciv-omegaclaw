"""Bounded typed deterministic proof engine for FDAS shadow parity."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from ..state.atomspace.model import AtomNamespace, EntityRef, SymbolRef


@dataclass(frozen=True)
class RuleBinding:
    rule_id: str
    scope_id: str
    variables: tuple
    premise_atom_ids: tuple
    grounding_result_ids: tuple
    completeness_witness_ids: tuple
    binding_hash: str

    @classmethod
    def create(cls, rule_id, scope_id, variables, premises=(),
               groundings=(), completeness=()):
        variables = tuple(sorted(variables, key=lambda value: value[0]))
        material = {
            "completeness": list(completeness),
            "groundings": list(groundings),
            "premises": list(premises),
            "rule_id": rule_id,
            "scope_id": scope_id,
            "variables": [
                [name, value.to_dict()] for name, value in variables],
        }
        return cls(
            str(rule_id),
            str(scope_id),
            variables,
            tuple(premises),
            tuple(groundings),
            tuple(completeness),
            structural_hash(material),
        )


@dataclass(frozen=True)
class InferenceRequest:
    mode: str
    target_pattern: object
    scope_id: str
    namespaces: frozenset
    maximum_depth: int
    maximum_bindings: int
    maximum_rule_fires: int
    pressure_budget_id: object = None

    def __post_init__(self):
        if self.mode not in ("materialize", "prove", "regress", "assess"):
            raise ValueError("unknown inference mode")
        object.__setattr__(self, "namespaces", frozenset(
            AtomNamespace(value) for value in self.namespaces))
        for value, name in (
                (self.maximum_depth, "maximum depth"),
                (self.maximum_bindings, "maximum bindings"),
                (self.maximum_rule_fires, "maximum rule fires")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("{} must be positive".format(name))


@dataclass(frozen=True)
class ProofRecord:
    conclusion_atom_id: str
    rule_id: str
    binding_hash: str
    premises: tuple
    grounded_witnesses: tuple
    support_id: str
    proof_hash: str

    @classmethod
    def create(cls, conclusion_atom_id, rule_id, binding, premises=(),
               grounded_witnesses=()):
        premises = tuple(sorted(premises))
        grounded_witnesses = tuple(sorted(grounded_witnesses))
        material = {
            "binding_hash": binding.binding_hash,
            "conclusion_atom_id": conclusion_atom_id,
            "grounded_witnesses": list(grounded_witnesses),
            "premises": list(premises),
            "rule_id": rule_id,
        }
        proof_hash = structural_hash(material)
        return cls(
            conclusion_atom_id,
            rule_id,
            binding.binding_hash,
            premises,
            grounded_witnesses,
            "proof-support-" + proof_hash[:24],
            proof_hash,
        )


@dataclass(frozen=True)
class InferenceOutcome:
    status: str
    predicate: str
    arguments: tuple
    proof_records: tuple
    blockers: tuple
    prerequisite_names: tuple
    truncated: bool
    artifact_hash: str

    @property
    def proved(self):
        return self.status == "PROVED"

    def to_dict(self):
        return {
            "arguments": list(self.arguments),
            "artifact_hash": self.artifact_hash,
            "blockers": list(self.blockers),
            "predicate": self.predicate,
            "prerequisite_names": list(self.prerequisite_names),
            "proof_records": [
                {
                    "binding_hash": value.binding_hash,
                    "conclusion_atom_id": value.conclusion_atom_id,
                    "grounded_witnesses": list(value.grounded_witnesses),
                    "premises": list(value.premises),
                    "proof_hash": value.proof_hash,
                    "rule_id": value.rule_id,
                    "support_id": value.support_id,
                }
                for value in self.proof_records],
            "status": self.status,
            "truncated": self.truncated,
        }


def _atom_id(predicate, arguments):
    return "rule-atom-" + structural_hash({
        "arguments": list(arguments),
        "predicate": predicate,
    })[:24]


class TypedRuleIndex(object):
    def __init__(self, rules):
        index = {}
        for rule in rules:
            index.setdefault(
                (rule.target_predicate, str(rule.rule_name)), []).append(rule)
        self._index = dict(
            (key, tuple(sorted(value, key=lambda row: row.rule_id)))
            for key, value in index.items())

    def conclusions(self, predicate, target_name):
        return self._index.get((str(predicate), str(target_name)), ())


class _BudgetExhausted(RuntimeError):
    pass


class DeterministicRuleEngine(object):
    """Typed indexed proof without global unification or action authority."""

    def __init__(self, ruleset_ir):
        self.ir = ruleset_ir
        self.index = TypedRuleIndex(ruleset_ir.rules)

    @staticmethod
    def _context(rule, arguments):
        result = {}
        for template, value in zip(rule.target_arguments, arguments):
            if isinstance(template, str) and template.startswith("$"):
                result[template] = value
        return result

    @staticmethod
    def _arguments(requirement, context):
        return tuple(
            context.get(value, value) if isinstance(value, str) else value
            for value in requirement.arguments)

    def _static_tech_closure(self, kind, name, active=None):
        active = set() if active is None else active
        key = (kind, name)
        if key in active:
            return set()
        active.add(key)
        result = set()
        predicate = "researchable" if kind == "tech" else "buildable"
        for rule in self.index.conclusions(predicate, name):
            if rule.disabled:
                continue
            for requirement in rule.antecedents:
                if requirement.kind == "Tech" and requirement.present:
                    tech = str(requirement.name)
                    result.add(tech)
                    result.update(self._static_tech_closure(
                        "tech", tech, active))
        active.remove(key)
        return result

    def prove(self, predicate, arguments, state, request=None):
        arguments = tuple(str(value) for value in arguments)
        request = request or InferenceRequest(
            "prove",
            {"arguments": list(arguments), "predicate": predicate},
            "scope:generic-proof",
            frozenset((AtomNamespace.AUTHORITATIVE,
                       AtomNamespace.RULESET,
                       AtomNamespace.DERIVED)),
            32,
            4096,
            4096,
        )
        fires = [0]
        bindings = [0]
        records = {}
        blockers = set()
        memo = {}
        active = set()
        truncated = False

        def consume(depth):
            if depth > request.maximum_depth:
                raise _BudgetExhausted("depth")
            fires[0] += 1
            if fires[0] > request.maximum_rule_fires:
                raise _BudgetExhausted("rule-fires")

        def prove_goal(goal_predicate, goal_arguments, depth):
            consume(depth)
            target_name = str(goal_arguments[-1])
            memo_key = (goal_predicate, tuple(goal_arguments))
            if memo_key in memo:
                return memo[memo_key]
            if memo_key in active:
                blockers.add(("cycle", target_name))
                return False, False, ()
            if (goal_predicate == "researchable"
                    and state.contains("has-tech", goal_arguments)):
                return True, True, ()
            rules = tuple(
                value for value in self.index.conclusions(
                    goal_predicate, target_name)
                if not value.disabled)
            if not rules:
                blockers.add(("unreachable", target_name))
                return False, False, ()
            active.add(memo_key)
            alternatives = []
            for rule in rules:
                bindings[0] += 1
                if bindings[0] > request.maximum_bindings:
                    raise _BudgetExhausted("bindings")
                context = self._context(rule, goal_arguments)
                variables = []
                for name, value in sorted(context.items()):
                    kind = "player" if name == "$player" else (
                        "city" if name == "$city" else "entity")
                    variables.append((name, EntityRef(kind, str(value))))
                binding = RuleBinding.create(
                    rule.rule_id, request.scope_id, variables)
                ready = True
                reachable = True
                premises = []
                grounded = []
                for requirement in rule.antecedents:
                    req_args = self._arguments(requirement, context)
                    premise_id = _atom_id(requirement.predicate, req_args)
                    premises.append(premise_id)
                    if requirement.semantic == "grounded":
                        result = state.evaluate(
                            requirement.predicate, req_args)
                        grounded.append(structural_hash(result.to_dict()))
                        satisfied = result.satisfied == requirement.present
                        ready = ready and satisfied
                        reachable = reachable and satisfied
                        if not satisfied:
                            blockers.add(("grounded", requirement.predicate))
                        continue
                    present = state.contains(requirement.predicate, req_args)
                    if present == requirement.present:
                        continue
                    ready = False
                    if requirement.present and requirement.kind == "Tech":
                        _child_ready, child_reachable, _child = prove_goal(
                            "researchable",
                            (req_args[0], str(requirement.name)),
                            depth + 1,
                        )
                        reachable = reachable and child_reachable
                        blockers.add(("missing-tech", str(requirement.name)))
                    else:
                        reachable = False
                        blockers.add((
                            "missing-{}".format(requirement.kind.lower()),
                            str(requirement.name)))
                conclusion_id = _atom_id(goal_predicate, goal_arguments)
                proof = ProofRecord.create(
                    conclusion_id,
                    rule.rule_id,
                    binding,
                    premises,
                    grounded,
                )
                records[proof.proof_hash] = proof
                alternatives.append((ready, reachable, proof.proof_hash))
            active.remove(memo_key)
            ready = any(value[0] and value[1] for value in alternatives)
            reachable = any(value[1] for value in alternatives)
            result = ready, reachable, tuple(
                value[2] for value in alternatives)
            memo[memo_key] = result
            return result

        try:
            ready, reachable, _proofs = prove_goal(predicate, arguments, 0)
            status = "PROVED" if ready else (
                "BLOCKED" if reachable else "UNREACHABLE")
        except _BudgetExhausted as error:
            status = "UNKNOWN"
            blockers.add(("budget-exhausted", str(error)))
            truncated = True
        kind = "tech" if predicate == "researchable" else str(arguments[-2])
        closure = self._static_tech_closure(kind, str(arguments[-1]))
        prerequisites = tuple(sorted(
            tech for tech in closure
            if not state.contains("has-tech", (arguments[0], tech))))
        semantic = {
            "arguments": list(arguments),
            "blockers": [list(value) for value in sorted(blockers)],
            "predicate": predicate,
            "prerequisite_names": list(prerequisites),
            "proof_hashes": sorted(records),
            "status": status,
            "truncated": truncated,
        }
        return InferenceOutcome(
            status,
            str(predicate),
            arguments,
            tuple(records[key] for key in sorted(records)),
            tuple(sorted(blockers)),
            prerequisites,
            truncated,
            structural_hash(semantic),
        )


def compare_technology_proof(ruleset_ir, state, player, technology,
                             compatibility_oracle):
    from ..oracle.service import Goal
    generic = DeterministicRuleEngine(ruleset_ir).prove(
        "researchable", (str(player), str(technology)), state)
    legacy = compatibility_oracle.deps(
        Goal.researchable(player, technology), state,
        query_id="generic-proof-parity:{}:{}".format(player, technology))
    return {
        "generic_artifact_hash": generic.artifact_hash,
        "generic_prerequisites": list(generic.prerequisite_names),
        "generic_status": generic.status,
        "legacy_prerequisites": list(legacy.prerequisite_names),
        "legacy_proof_hash": legacy.proof["structural_hash"],
        "legacy_status": legacy.status,
        "prerequisite_parity": (
            generic.prerequisite_names == legacy.prerequisite_names),
        "status_parity": generic.status == legacy.status,
    }
