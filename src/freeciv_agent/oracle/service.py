"""Persistent, typed crisp dependency oracle over the canonical M0 IR."""

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field

from freeciv_agent.events import model
from freeciv_agent.events.schema import structural_hash


CRISP_TV = {"strength": 1.0, "confidence": 0.99}


class OracleError(RuntimeError):
    code = "ORACLE_ERROR"


class OracleTimeout(OracleError):
    code = "ORACLE_TIMEOUT"


class OracleClosed(OracleError):
    code = "ORACLE_CLOSED"


@dataclass(frozen=True)
class Goal:
    predicate: str
    arguments: tuple

    @classmethod
    def researchable(cls, player, tech):
        return cls("researchable", (str(player), str(tech)))


@dataclass(frozen=True)
class GroundedResult:
    satisfied: bool
    value: object = None
    inputs: dict = field(default_factory=dict)
    diagnostic: str = ""

    def to_dict(self):
        return {"diagnostic": self.diagnostic, "inputs": self.inputs,
                "satisfied": self.satisfied, "value": self.value}


class CrispStateView:
    """Immutable crisp facts and grounded checks for one snapshot."""

    def __init__(self, snapshot_id, facts=None, known_techs=None, player="player",
                 grounded=None):
        rows = set()
        for predicate, arguments in facts or ():
            rows.add((str(predicate), tuple(arguments)))
        for tech in known_techs or ():
            rows.add(("has-tech", (str(player), str(tech))))
        self.snapshot_id = str(snapshot_id)
        self.facts = frozenset(rows)
        self._grounded = dict(grounded or {})
        self.fingerprint = structural_hash({
            "facts": sorted((predicate, list(arguments)) for predicate, arguments in rows),
            "snapshot_id": self.snapshot_id,
        })

    def contains(self, predicate, arguments):
        return (predicate, tuple(arguments)) in self.facts

    def evaluate(self, predicate, arguments):
        function = self._grounded.get(predicate)
        if function is None:
            return GroundedResult(False, inputs={"arguments": list(arguments)},
                                  diagnostic="grounded predicate is unavailable")
        try:
            value = function(*arguments)
        except Exception as exc:
            return GroundedResult(False, inputs={"arguments": list(arguments)},
                                  diagnostic="{}: {}".format(type(exc).__name__, exc))
        if isinstance(value, GroundedResult):
            return value
        return GroundedResult(bool(value), value=value,
                              inputs={"arguments": list(arguments)})


@dataclass
class QueryResult:
    query_id: str
    goal: Goal
    status: str
    proof: dict
    frontier: list
    prerequisite_atoms: list
    latency_ms: float
    chain_depth: int
    cache_status: str
    error: object = None

    @property
    def executable(self):
        return self.status in ("PROVED", "BLOCKED") and self.error is None

    @property
    def prerequisite_names(self):
        return tuple(sorted({atom["args"][-1] for atom in self.prerequisite_atoms
                            if atom["predicate"] == "has-tech"}))

    def event_payload(self):
        return {
            "cache_status": self.cache_status,
            "chain_depth": self.chain_depth,
            "dampening_lambda": None,
            "error": copy.deepcopy(self.error),
            "latency_ms": self.latency_ms,
            "prerequisite_atoms": copy.deepcopy(self.prerequisite_atoms),
            "proof": copy.deepcopy(self.proof),
            "query_id": self.query_id,
            "status": self.status,
            "tree_size": len(self.proof["nodes"]),
            "unsatisfied_frontier": copy.deepcopy(self.frontier),
        }


def _atom(predicate, arguments):
    arguments = tuple(arguments)
    identity = structural_hash({"arguments": list(arguments), "predicate": predicate})[:20]
    return model.atom("atom-" + identity, predicate, list(arguments), tv=CRISP_TV, crisp=True)


def _frontier(node_id, blocker, atom_value, detail):
    return {"atom_id": atom_value["atom_id"], "blocker_type": blocker,
            "detail": detail, "node_id": node_id}


class _ProofBuilder:
    def __init__(self, rules, state, deadline):
        self.rules = rules
        self.state = state
        self.deadline = deadline
        self.nodes = {}
        self.memo = {}
        self.active = set()

    def _check_deadline(self):
        if time.perf_counter() > self.deadline:
            raise OracleTimeout("dependency query exceeded its deadline")

    def _add_node(self, kind, atom_value, satisfied, rule=None, refs=(),
                  grounded=None, formula=None, source=None, scope=None):
        material = {"atom": atom_value, "kind": kind, "refs": list(refs),
                    "rule": rule, "satisfied": satisfied, "source": source}
        node_id = "node-" + structural_hash(material)[:20]
        node = model.proof_node(
            node_id, kind, atom_value, satisfied, rule_applied=rule,
            premise_node_refs=list(refs), grounded_result=grounded,
            formula=formula, rule_source=source, scope=scope,
        )
        existing = self.nodes.get(node_id)
        if existing is not None and existing != node:
            raise OracleError("stable proof-node ID collision")
        self.nodes[node_id] = node
        return node_id

    @staticmethod
    def _context(goal):
        if goal.predicate == "researchable":
            return {"$player": goal.arguments[0], "$tech": goal.arguments[-1]}
        if goal.predicate == "buildable":
            return {"$city": goal.arguments[0], "$target": goal.arguments[-1]}
        return {}

    @staticmethod
    def _arguments(requirement, context):
        return tuple(context.get(value, value) if isinstance(value, str) else value
                     for value in requirement.arguments)

    def _requirement(self, requirement, context, depth):
        self._check_deadline()
        arguments = self._arguments(requirement, context)
        atom_value = _atom(requirement.predicate, arguments)
        if requirement.semantic == "grounded":
            result = self.state.evaluate(requirement.predicate, arguments)
            satisfied = result.satisfied == requirement.present
            node_id = self._add_node(
                "grounded", atom_value, satisfied, grounded=result.to_dict(),
                formula={"name": "grounded-crisp", "inputs": {"present": requirement.present}},
                source=requirement.source, scope=requirement.range,
            )
            frontier = [] if satisfied else [_frontier(
                node_id, "grounded-predicate", atom_value,
                result.diagnostic or "grounded predicate is not satisfied")]
            return node_id, satisfied, True, depth, set(), frontier

        present_in_state = self.state.contains(requirement.predicate, arguments)
        satisfied = present_in_state == requirement.present
        if satisfied:
            node_id = self._add_node("premise", atom_value, True, source=requirement.source,
                                     scope=requirement.range)
            return node_id, True, True, depth, set(), []
        if not requirement.present:
            node_id = self._add_node("premise", atom_value, False, source=requirement.source,
                                     scope=requirement.range)
            return node_id, False, True, depth, set(), [_frontier(
                node_id, "unreachable", atom_value, "negated requirement is currently present")]
        if requirement.kind == "Tech":
            return self._missing_tech(arguments[0], str(requirement.name), depth)

        blocker = "missing-building" if requirement.kind == "Building" else "unreachable"
        node_id = self._add_node("premise", atom_value, False, source=requirement.source,
                                 scope=requirement.range)
        return node_id, False, True, depth, set(), [_frontier(
            node_id, blocker, atom_value,
            "missing {} requirement {}".format(requirement.kind, requirement.name))]

    def _missing_tech(self, player, tech, depth):
        key = ("tech", player, tech)
        if key in self.memo:
            return self.memo[key]
        atom_value = _atom("has-tech", (player, tech))
        if key in self.active:
            node_id = self._add_node("cycle", atom_value, False,
                                     formula={"name": "active-path-cycle", "inputs": {}})
            return node_id, False, False, depth, {tech}, [_frontier(
                node_id, "cycle", atom_value, "active dependency path contains a cycle")]
        candidates = self.rules.get(("tech", tech), ())
        if not candidates or all(rule.disabled for rule in candidates):
            node_id = self._add_node("unreachable", atom_value, False)
            blocker = "disabled-goal" if candidates else "unreachable"
            return node_id, False, False, depth, {tech}, [_frontier(
                node_id, blocker, atom_value, "technology has no enabled compiled rule")]

        self.active.add(key)
        branches = []
        all_missing = {tech}
        all_frontier = []
        maximum = depth
        for rule in candidates:
            if rule.disabled:
                continue
            context = {"$player": player, "$tech": tech}
            children = [self._requirement(req, context, depth + 1)
                        for req in rule.antecedents]
            refs = tuple(child[0] for child in children)
            ready = all(child[1] for child in children)
            reachable = all(child[2] for child in children)
            maximum = max([maximum] + [child[3] for child in children])
            for child in children:
                all_missing.update(child[4])
                all_frontier.extend(child[5])
            and_atom = _atom("requirements-satisfied", (player, "tech", tech, rule.rule_id))
            and_id = self._add_node(
                "and", and_atom, ready and reachable, rule=rule.rule_id, refs=refs,
                formula={"name": "crisp-conjunction", "inputs": {"premises": len(refs)}},
                source=rule.source, scope="Player",
            )
            branches.append((and_id, ready, reachable))
        self.active.remove(key)

        ready = any(branch[1] and branch[2] for branch in branches)
        reachable = any(branch[2] for branch in branches)
        if len(branches) == 1:
            refs = (branches[0][0],)
        else:
            or_atom = _atom("alternative-dependency-path", (player, "tech", tech))
            refs = (self._add_node(
                "or", or_atom, ready, refs=tuple(branch[0] for branch in branches),
                formula={"name": "crisp-disjunction", "inputs": {"paths": len(branches)}},
                scope="Player",
            ),)
        node_id = self._add_node("goal", atom_value, False, refs=refs,
                                 formula={"name": "dependency-expansion", "inputs": {}})
        if ready and reachable:
            all_frontier.append(_frontier(
                node_id, "missing-tech", atom_value,
                "technology is a currently researchable dependency"))
        result = (node_id, False, reachable, maximum, all_missing, all_frontier)
        self.memo[key] = result
        return result

    def _static_tech_closure(self, kind, name, active=None):
        """Return the engine-style transitive tech closure, independent of holes."""
        active = set() if active is None else active
        key = (kind, name)
        if key in active:
            return set()
        active.add(key)
        closure = set()
        for rule in self.rules.get(key, ()):
            if rule.disabled:
                continue
            for requirement in rule.antecedents:
                if requirement.kind == "Tech" and requirement.present:
                    tech = str(requirement.name)
                    closure.add(tech)
                    closure.update(self._static_tech_closure("tech", tech, active))
        active.remove(key)
        return closure

    def build(self, goal):
        self._check_deadline()
        if goal.predicate not in ("researchable", "buildable"):
            raise OracleError("unsupported crisp goal predicate: {}".format(goal.predicate))
        kind = "tech" if goal.predicate == "researchable" else str(goal.arguments[-2])
        name = str(goal.arguments[-1])
        candidates = self.rules.get((kind, name), ())
        goal_atom = _atom(goal.predicate, goal.arguments)
        if (kind == "tech"
                and self.state.contains("has-tech", (goal.arguments[0], name))):
            root = self._add_node("goal", goal_atom, True,
                                  formula={"name": "already-achieved", "inputs": {}})
            return "PROVED", model.proof_tree(root, list(self.nodes.values())), [], [], 0
        if not candidates or all(rule.disabled for rule in candidates):
            node_id = self._add_node("unreachable", goal_atom, False)
            blocker = "disabled-goal" if candidates else "unreachable"
            frontier = [_frontier(node_id, blocker, goal_atom,
                                  "goal has no enabled compiled target rule")]
            proof = model.proof_tree(node_id, list(self.nodes.values()))
            return "UNREACHABLE", proof, frontier, [], 0

        context = self._context(goal)
        branches = []
        missing = set()
        frontier = []
        maximum = 0
        for rule in candidates:
            if rule.disabled:
                continue
            children = [self._requirement(req, context, 1) for req in rule.antecedents]
            refs = tuple(child[0] for child in children)
            ready = all(child[1] for child in children)
            reachable = all(child[2] for child in children)
            maximum = max([maximum] + [child[3] for child in children])
            for child in children:
                missing.update(child[4])
                frontier.extend(child[5])
            and_atom = _atom("requirements-satisfied", goal.arguments + (rule.rule_id,))
            and_id = self._add_node(
                "and", and_atom, ready and reachable, rule=rule.rule_id, refs=refs,
                formula={"name": "crisp-conjunction", "inputs": {"premises": len(refs)}},
                source=rule.source,
            )
            branches.append((and_id, ready, reachable))
        ready = any(branch[1] and branch[2] for branch in branches)
        reachable = any(branch[2] for branch in branches)
        if len(branches) == 1:
            refs = (branches[0][0],)
        else:
            or_atom = _atom("alternative-dependency-path", goal.arguments)
            refs = (self._add_node(
                "or", or_atom, ready, refs=tuple(branch[0] for branch in branches),
                formula={"name": "crisp-disjunction", "inputs": {"paths": len(branches)}},
            ),)
        root = self._add_node("goal", goal_atom, ready, refs=refs,
                              formula={"name": "crisp-goal", "inputs": {}})
        proof = model.deduplicate_proof_tree(
            model.proof_tree(root, list(self.nodes.values())))
        unique_frontier = {item["node_id"]: item for item in frontier}
        # FreeCiv's research_goal_tech_req iterates the target's precomputed full
        # closure, then removes each known technology individually. It intentionally
        # does not stop at a known intermediate when adversarial states contain holes.
        engine_closure = self._static_tech_closure(kind, name)
        missing = {tech for tech in engine_closure
                   if not self.state.contains("has-tech", (goal.arguments[0], tech))}
        prereqs = [_atom("has-tech", (goal.arguments[0], tech)) for tech in sorted(missing)]
        status = "PROVED" if ready else ("BLOCKED" if reachable else "UNREACHABLE")
        return status, proof, [unique_frontier[key] for key in sorted(unique_frontier)], prereqs, maximum


class DependencyOracle:
    """Long-lived dependency service; rule import and indexing happen once."""

    def __init__(self, ir, default_timeout_ms=500.0):
        index = {}
        for rule in ir.rules:
            index.setdefault((rule.target_kind, rule.rule_name), []).append(rule)
        self._rules = {key: tuple(sorted(value, key=lambda rule: rule.rule_id))
                       for key, value in index.items()}
        self._default_timeout_ms = float(default_timeout_ms)
        self._cache = {}
        self._lock = threading.RLock()
        self._closed = False

    def close(self):
        with self._lock:
            self._closed = True
            self._cache.clear()

    def deps(self, goal, state_view, timeout_ms=None, query_id=None):
        if not isinstance(goal, Goal):
            raise TypeError("goal must be Goal")
        if not isinstance(state_view, CrispStateView):
            raise TypeError("state_view must be CrispStateView")
        started = time.perf_counter()
        query_id = query_id or "query-{}".format(uuid.uuid4().hex)
        key = (goal.predicate, goal.arguments, state_view.fingerprint)
        with self._lock:
            if self._closed:
                return self._error_result(query_id, goal, OracleClosed("oracle is closed"), started)
            cached = self._cache.get(key)
            if cached is not None:
                result = copy.deepcopy(cached)
                result.query_id = query_id
                result.cache_status = "hit"
                result.latency_ms = (time.perf_counter() - started) * 1000.0
                return result
        timeout = self._default_timeout_ms if timeout_ms is None else float(timeout_ms)
        deadline = started + max(0.0, timeout) / 1000.0
        try:
            builder = _ProofBuilder(self._rules, state_view, deadline)
            status, proof, frontier, prereqs, depth = builder.build(goal)
            result = QueryResult(
                query_id, goal, status, proof, frontier, prereqs,
                (time.perf_counter() - started) * 1000.0, depth, "miss",
            )
        except OracleError as exc:
            return self._error_result(query_id, goal, exc, started)
        with self._lock:
            if not self._closed:
                self._cache[key] = copy.deepcopy(result)
        return result

    @staticmethod
    def _error_result(query_id, goal, error, started):
        atom_value = _atom(goal.predicate, goal.arguments)
        node = model.proof_node("node-error", "unreachable", atom_value, False,
                                formula={"name": "structured-error", "inputs": {}})
        proof = model.proof_tree("node-error", [node])
        return QueryResult(
            query_id, goal, "ERROR", proof, [], [],
            (time.perf_counter() - started) * 1000.0, 0, "error",
            error={"code": error.code, "message": str(error)},
        )

    def emit_deps(self, goal, state_view, writer, turn, caused_by=None,
                  invoking_layer="planner", timeout_ms=None):
        query_id = "query-{}".format(uuid.uuid4().hex)
        query_event = writer.emit("pln_query", turn, {
            "invoking_layer": invoking_layer, "query_atom": _atom(goal.predicate, goal.arguments),
            "query_id": query_id, "query_type": "deps",
        }, caused_by=list(caused_by or []))
        result = self.deps(goal, state_view, timeout_ms=timeout_ms, query_id=query_id)
        result_event = writer.emit("pln_result", turn, result.event_payload(),
                                   caused_by=[query_event["event_id"]])
        return result, query_event, result_event
