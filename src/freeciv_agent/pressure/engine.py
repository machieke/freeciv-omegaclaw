"""Bounded reverse pressure transport over a typed dependency hypergraph."""

import math
from collections import defaultdict
from dataclasses import dataclass, field, replace

from ..events.schema import structural_hash
from .model import (
    ACTION_CAUSAL_KINDS,
    AtomState,
    GoalState,
    PressureConfig,
    PressureRule,
    PressureVector,
    Resolvability,
)


_ZERO_PRESSURE = PressureVector()


def _softmax(values, temperature):
    if not values:
        return ()
    maximum = max(values)
    exponentials = [math.exp((float(value) - maximum) / float(temperature))
                    for value in values]
    denominator = sum(exponentials)
    return tuple(value / denominator for value in exponentials)


def _exploratory_shares(values, temperature, exploration_floor):
    raw = _softmax(values, temperature)
    if not raw:
        return ()
    uniform = float(exploration_floor) / len(raw)
    return tuple((1.0 - float(exploration_floor)) * value + uniform
                 for value in raw)


@dataclass(frozen=True)
class PressureTrace:
    goal_id: str
    rule_id: str
    conclusion_id: str
    premise_id: str
    hop: int
    incoming_pressure: float
    rule_share: float
    premise_share: float
    transported_pressure: float
    action_pressure: float
    causal_kind: str

    def to_dict(self):
        return {
            "action_pressure": float(self.action_pressure),
            "causal_kind": self.causal_kind,
            "conclusion_id": self.conclusion_id,
            "goal_id": self.goal_id,
            "hop": int(self.hop),
            "incoming_pressure": float(self.incoming_pressure),
            "premise_id": self.premise_id,
            "premise_share": float(self.premise_share),
            "rule_id": self.rule_id,
            "rule_share": float(self.rule_share),
            "transported_pressure": float(self.transported_pressure),
        }


class PressureGraph(object):
    """Shared atom/rule topology with pressure state stored outside the graph."""

    def __init__(self):
        self._atoms = {}
        self._rules = {}
        self._resolvability = {}
        self._by_conclusion = defaultdict(list)

    def add_atom(self, atom, resolvability=None):
        if not isinstance(atom, AtomState):
            raise TypeError("pressure graph accepts AtomState")
        existing = self._atoms.get(atom.atom_id)
        if existing is not None and existing != atom:
            raise ValueError("atom {} already exists with different state".format(
                atom.atom_id))
        self._atoms[atom.atom_id] = atom
        if resolvability is not None:
            self.set_resolvability(atom.atom_id, resolvability)
        return atom

    def set_resolvability(self, atom_id, resolvability):
        if atom_id not in self._atoms:
            raise KeyError("unknown atom {}".format(atom_id))
        if not isinstance(resolvability, Resolvability):
            raise TypeError("resolvability must be Resolvability")
        self._resolvability[atom_id] = resolvability

    def add_rule(self, rule):
        if not isinstance(rule, PressureRule):
            raise TypeError("pressure graph accepts PressureRule")
        if rule.conclusion_id not in self._atoms:
            raise KeyError("unknown rule conclusion {}".format(rule.conclusion_id))
        missing = [value for value in rule.premise_ids if value not in self._atoms]
        if missing:
            raise KeyError("unknown rule premises {}".format(missing))
        existing = self._rules.get(rule.rule_id)
        if existing is not None and existing != rule:
            raise ValueError("rule {} already exists with different state".format(
                rule.rule_id))
        if existing is None:
            self._rules[rule.rule_id] = rule
            self._by_conclusion[rule.conclusion_id].append(rule.rule_id)
            self._by_conclusion[rule.conclusion_id].sort()
        return rule

    def atom(self, atom_id):
        return self._atoms[str(atom_id)]

    def rules_for(self, conclusion_id):
        return tuple(self._rules[value]
                     for value in self._by_conclusion.get(str(conclusion_id), ()))

    def resolvability(self, atom_id):
        return self._resolvability.get(str(atom_id), Resolvability())

    @property
    def atoms(self):
        return tuple(self._atoms[key] for key in sorted(self._atoms))

    @property
    def rules(self):
        return tuple(self._rules[key] for key in sorted(self._rules))

    @property
    def artifact_hash(self):
        return structural_hash({
            "atoms": [row.to_dict() for row in self.atoms],
            "resolvability": dict(
                (key, self._resolvability[key].to_dict())
                for key in sorted(self._resolvability)),
            "rules": [row.to_dict() for row in self.rules],
        })


@dataclass(frozen=True)
class PressureResult:
    goals: tuple
    dependency_rows: tuple
    action_rows: tuple
    pressure_rows: tuple
    traces: tuple
    graph_hash: str
    config: PressureConfig
    _dependency_index: dict = field(
        init=False, repr=False, compare=False)
    _action_index: dict = field(
        init=False, repr=False, compare=False)
    _pressure_index: dict = field(
        init=False, repr=False, compare=False)

    @staticmethod
    def _index(rows):
        return dict((goal_id, dict(values)) for goal_id, values in rows)

    def __post_init__(self):
        object.__setattr__(
            self, "_dependency_index", self._index(self.dependency_rows))
        object.__setattr__(
            self, "_action_index", self._index(self.action_rows))
        object.__setattr__(
            self, "_pressure_index", self._index(self.pressure_rows))

    def dependency(self, goal_id, atom_id):
        return float(self._dependency_index.get(
            str(goal_id), {}).get(str(atom_id), 0.0))

    def action_dependency(self, goal_id, atom_id):
        return float(self._action_index.get(
            str(goal_id), {}).get(str(atom_id), 0.0))

    def pressure(self, goal_id, atom_id):
        return self._pressure_index.get(
            str(goal_id), {}).get(str(atom_id), _ZERO_PRESSURE)

    @property
    def artifact_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "action_dependency": dict(
                (goal_id, dict(values)) for goal_id, values in self.action_rows),
            "config": self.config.to_dict(),
            "dependency": dict(
                (goal_id, dict(values)) for goal_id, values in self.dependency_rows),
            "goals": [goal.to_dict() for goal in self.goals],
            "graph_hash": self.graph_hash,
            "pressure": dict(
                (goal_id, dict((atom_id, pressure.to_dict())
                               for atom_id, pressure in values))
                for goal_id, values in self.pressure_rows),
            "traces": [trace.to_dict() for trace in self.traces],
        }


class PressureEngine(object):
    """Deterministic, finite-horizon approximation of reverse PF transport."""

    SOLVER_IDENTITY = "pf-pln-pressure-engine/1.0"

    def __init__(self, config=None):
        self.config = config or PressureConfig()
        if not isinstance(self.config, PressureConfig):
            raise TypeError("pressure engine config must be PressureConfig")

    def _rule_shares(self, rules):
        if len(rules) == 1:
            return (1.0,)
        values = [self._route_value(rule) for rule in rules]
        return _exploratory_shares(
            values, self.config.softmax_temperature,
            self.config.exploration_floor)

    def _route_value(self, rule):
        return (
            rule.success_probability * rule.deadline_fit
            * rule.conductance * rule.compatibility
            / (rule.route_cost + self.config.cost_epsilon))

    def _active_rules(self, rules):
        return tuple(sorted(
            rules, key=lambda rule: (
                -self._route_value(rule) * rule.residual, rule.rule_id)
        )[:self.config.max_routes_per_conclusion])

    def _premise_shares(self, graph, rule):
        if rule.premise_weights:
            total = sum(float(value) for value in rule.premise_weights)
            if total:
                normalized = [
                    float(value) / total for value in rule.premise_weights]
                uniform = self.config.exploration_floor / len(normalized)
                return tuple(
                    (1.0 - self.config.exploration_floor) * value + uniform
                    for value in normalized)
        rows = []
        for premise_id in rule.premise_ids:
            atom = graph.atom(premise_id)
            resolvability = graph.resolvability(premise_id)
            unmet = max(0.0, 1.0 - atom.truth.supported_strength)
            feasible = resolvability.maximum
            if rule.kind == "or":
                route_readiness = min(
                    1.0, atom.truth.supported_strength + feasible * unmet)
                rows.append(
                    route_readiness * unmet * rule.success_probability
                    * rule.deadline_fit / (rule.route_cost + self.config.cost_epsilon))
            else:
                # AND and ordinary dependencies focus on achievable blockers.
                rows.append(unmet * feasible * rule.deadline_fit)
        if not any(rows):
            rows = [1.0] * len(rule.premise_ids)
        if rule.kind == "or":
            return _exploratory_shares(
                rows, self.config.softmax_temperature,
                self.config.exploration_floor)
        # The AND exploration floor prevents starving a coordinated prerequisite.
        total = sum(rows)
        normalized = [value / total for value in rows]
        uniform = self.config.exploration_floor / len(rows)
        return tuple(
            (1.0 - self.config.exploration_floor) * value + uniform
            for value in normalized)

    def propagate(self, graph, goals):
        if not isinstance(graph, PressureGraph):
            raise TypeError("propagate graph must be PressureGraph")
        goals = tuple(sorted(goals, key=lambda value: value.goal_id))
        if not goals or any(not isinstance(goal, GoalState) for goal in goals):
            raise ValueError("propagate requires GoalState values")
        if len(set(goal.goal_id for goal in goals)) != len(goals):
            raise ValueError("goal IDs must be unique")

        dependencies = {}
        action_dependencies = {}
        traces = []
        directions = {}

        for goal in goals:
            target = graph.atom(goal.target_atom_id)
            source = goal.demand(target.truth)
            direction = goal.direction(target.truth)
            directions[goal.goal_id] = direction
            dependency = defaultdict(float)
            action_dependency = defaultdict(float)
            dependency[target.atom_id] += source
            action_dependency[target.atom_id] += source
            frontier = {(target.atom_id): (source, source)}

            for hop in range(self.config.max_hops):
                if not frontier:
                    break
                following = defaultdict(lambda: [0.0, 0.0])
                for conclusion_id in sorted(frontier):
                    incoming, incoming_action = frontier[conclusion_id]
                    rules = self._active_rules(
                        graph.rules_for(conclusion_id))
                    for rule, rule_share in zip(rules, self._rule_shares(rules)):
                        gated = (
                            incoming * self.config.damping * rule.transport_gate
                            * rule_share)
                        action_gate_open = (
                            rule.causal_kind in ACTION_CAUSAL_KINDS
                            and rule.compatibility
                            >= self.config.action_compatibility_threshold)
                        gated_action = (
                            incoming_action * self.config.damping
                            * rule.transport_gate * rule_share
                            if action_gate_open else 0.0)
                        for premise_id, premise_share in zip(
                                rule.premise_ids,
                                self._premise_shares(graph, rule)):
                            transported = gated * premise_share
                            transported_action = gated_action * premise_share
                            if transported < self.config.residual_floor:
                                continue
                            dependency[premise_id] += transported
                            action_dependency[premise_id] += transported_action
                            following[premise_id][0] += transported
                            following[premise_id][1] += transported_action
                            traces.append(PressureTrace(
                                goal.goal_id, rule.rule_id, conclusion_id,
                                premise_id, hop + 1, incoming, rule_share,
                                premise_share, transported, transported_action,
                                rule.causal_kind))
                frontier = dict(
                    (atom_id, tuple(values)) for atom_id, values in following.items()
                    if values[0] >= self.config.residual_floor)

            dependencies[goal.goal_id] = dict(dependency)
            action_dependencies[goal.goal_id] = dict(action_dependency)

        pressure = {}
        for goal in goals:
            rows = {}
            direction = directions[goal.goal_id]
            for atom_id, amount in sorted(dependencies[goal.goal_id].items()):
                if amount < self.config.materialization_floor:
                    continue
                resolvability = graph.resolvability(atom_id)
                vector = resolvability.operational_pressure(amount, direction)
                # Action pressure requires a causal/procedural route from the goal.
                vector = replace(
                    vector,
                    act=(action_dependencies[goal.goal_id].get(atom_id, 0.0)
                         * resolvability.act))
                if vector.total >= self.config.materialization_floor:
                    rows[atom_id] = vector
            pressure[goal.goal_id] = rows

        return PressureResult(
            goals,
            tuple((goal_id, tuple(sorted(values.items())))
                  for goal_id, values in sorted(dependencies.items())),
            tuple((goal_id, tuple(sorted(values.items())))
                  for goal_id, values in sorted(action_dependencies.items())),
            tuple((goal_id, tuple(sorted(values.items())))
                  for goal_id, values in sorted(pressure.items())),
            tuple(traces), graph.artifact_hash, self.config)


class ConductanceLearner(object):
    """Teleological credit changes transport, never a rule's truth value."""

    def __init__(self, learning_rate=0.10, no_progress_rate=0.10):
        if not 0 < float(learning_rate) <= 1:
            raise ValueError("learning rate must be in (0,1]")
        if not 0 <= float(no_progress_rate) <= 1:
            raise ValueError("no-progress rate must be in [0,1]")
        self.learning_rate = float(learning_rate)
        self.no_progress_rate = float(no_progress_rate)

    @staticmethod
    def _sigmoid(value):
        return 1.0 / (1.0 + math.exp(-float(value)))

    def update(self, rule, calibration, realized_relief, information_gain,
               failure_rate, dependency_risk):
        if not isinstance(rule, PressureRule):
            raise TypeError("conductance learner accepts PressureRule")
        target = self._sigmoid(
            float(calibration) + float(realized_relief)
            + float(information_gain) - float(failure_rate)
            - float(dependency_risk))
        conductance = (
            (1.0 - self.learning_rate) * rule.conductance
            + self.learning_rate * target)
        return replace(rule, conductance=min(1.0, max(0.0, conductance)))

    def credit(self, rule, realized_relief):
        """Apply bounded positive credit without lowering an optimistic prior."""
        if not isinstance(rule, PressureRule):
            raise TypeError("conductance learner accepts PressureRule")
        if isinstance(realized_relief, bool):
            raise ValueError("realized relief must be numeric")
        relief = float(realized_relief)
        if not 0.0 <= relief <= 1.0:
            raise ValueError("realized relief must be in [0,1]")
        conductance = (
            rule.conductance
            + self.learning_rate * relief * (1.0 - rule.conductance))
        return replace(rule, conductance=min(1.0, max(0.0, conductance)))

    def no_progress(self, rule, amount=1.0):
        if not isinstance(rule, PressureRule):
            raise TypeError("conductance learner accepts PressureRule")
        conductance = rule.conductance * math.exp(
            -self.no_progress_rate * max(0.0, float(amount)))
        return replace(rule, conductance=max(0.0, conductance))
