"""Gauge-fixed source-sink projection for typed requested currents."""

import math
from dataclasses import dataclass

from ..events.schema import structural_hash
from .currents import RequestedCurrent
from .model import FlowView


def _dot(left, right):
    return sum(
        float(a) * float(b)
        for a, b in zip(left, right))


def _dense_solve(matrix, vector, tolerance):
    """Solve one small nonsingular system with deterministic pivoting."""
    size = len(vector)
    augmented = [
        [float(value) for value in matrix[row]]
        + [float(vector[row])]
        for row in range(size)]
    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: (
                abs(augmented[row][column]), -row))
        if abs(augmented[pivot][column]) <= tolerance:
            return None
        if pivot != column:
            augmented[column], augmented[pivot] = (
                augmented[pivot], augmented[column])
        scale = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= scale
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= (
                    factor * augmented[column][index])
    return tuple(augmented[row][-1] for row in range(size))


def _preconditioned_cg(
        matrix, vector, tolerance, maximum_iterations):
    """Deterministic diagonal-PCG fallback for an SPD reduced Laplacian."""
    size = len(vector)
    if size == 0:
        return (), 0, True
    diagonal = tuple(matrix[index][index] for index in range(size))
    if any(value <= 0.0 or not math.isfinite(value)
           for value in diagonal):
        return tuple(0.0 for _ in range(size)), 0, False

    # The reduced Laplacian is sparse even though the compatibility API
    # accepts dense rows. Compact it once so the dependency-free fallback
    # does not perform O(nodes^2) Python work on every CG iteration.
    sparse_rows = tuple(
        tuple(
            (index, float(value))
            for index, value in enumerate(row)
            if value != 0.0)
        for row in matrix)

    def multiply(values):
        return tuple(
            sum(
                coefficient * values[index]
                for index, coefficient in row)
            for row in sparse_rows)

    solution = [0.0] * size
    residual = [float(value) for value in vector]
    preconditioned = [
        residual[index] / diagonal[index]
        for index in range(size)]
    direction = list(preconditioned)
    residual_energy = _dot(residual, preconditioned)
    target = tolerance * max(
        1.0, math.sqrt(_dot(vector, vector)))
    if math.sqrt(_dot(residual, residual)) <= target:
        return tuple(solution), 0, True
    if residual_energy <= 0.0:
        return tuple(solution), 0, False
    for iteration in range(1, maximum_iterations + 1):
        product = multiply(direction)
        denominator = _dot(direction, product)
        if denominator <= 0.0 or not math.isfinite(denominator):
            return tuple(solution), iteration, False
        alpha = residual_energy / denominator
        solution = [
            value + alpha * step
            for value, step in zip(solution, direction)]
        residual = [
            value - alpha * step
            for value, step in zip(residual, product)]
        if math.sqrt(_dot(residual, residual)) <= target:
            return tuple(solution), iteration, True
        preconditioned = [
            residual[index] / diagonal[index]
            for index in range(size)]
        next_energy = _dot(residual, preconditioned)
        if next_energy <= 0.0 or not math.isfinite(next_energy):
            return tuple(solution), iteration, False
        beta = next_energy / residual_energy
        direction = [
            value + beta * prior
            for value, prior in zip(preconditioned, direction)]
        residual_energy = next_energy
    return tuple(solution), maximum_iterations, False


def _scipy_preconditioned_cg(
        matrix, vector, tolerance, maximum_iterations):
    """Use SciPy sparse CG when the optional numerical backend is present."""
    try:
        from scipy.sparse import csr_matrix, diags
        from scipy.sparse.linalg import cg
    except ImportError:
        return None
    sparse = csr_matrix(matrix, dtype=float)
    diagonal = sparse.diagonal()
    if any(value <= 0.0 or not math.isfinite(float(value))
           for value in diagonal):
        return tuple(0.0 for _ in vector), 0, False
    preconditioner = diags(
        [1.0 / float(value) for value in diagonal])
    iteration_count = [0]

    def counted(_):
        iteration_count[0] += 1

    try:
        solution, information = cg(
            sparse, vector, M=preconditioner,
            rtol=tolerance, atol=0.0,
            maxiter=maximum_iterations,
            callback=counted)
    except TypeError:
        # SciPy before 1.12 named the relative tolerance ``tol``.
        solution, information = cg(
            sparse, vector, M=preconditioner,
            tol=tolerance,
            maxiter=maximum_iterations,
            callback=counted)
    return (
        tuple(float(value) for value in solution),
        iteration_count[0],
        information == 0)


@dataclass(frozen=True)
class ProjectionResult:
    edge_ids: tuple
    node_ids: tuple
    feasible_current: tuple
    congestion_dual: tuple
    mobility: tuple
    balance_residual: float
    iterations: int
    gauge_policy: str
    health: str
    solver: str
    component_count: int
    blocked_edge_ids: tuple
    requested_current_hash: str
    candidate_authority: bool = False
    topology_generation: object = None
    topology_semantic_hash: object = None

    def __post_init__(self):
        if (len(self.edge_ids) != len(self.feasible_current)
                or len(self.edge_ids) != len(self.mobility)):
            raise ValueError(
                "projection edge arrays must align")
        if len(self.node_ids) != len(self.congestion_dual):
            raise ValueError(
                "projection node arrays must align")
        values = (
            self.feasible_current + self.congestion_dual
            + self.mobility + (self.balance_residual,))
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError(
                "projection result must be finite")
        if self.balance_residual < 0.0:
            raise ValueError(
                "projection residual must be non-negative")
        if self.iterations < 0 or self.component_count < 0:
            raise ValueError(
                "projection counts must be non-negative")
        if self.candidate_authority:
            raise ValueError(
                "projection current is never candidate authority")
        if (self.topology_generation is not None
                and (isinstance(self.topology_generation, bool)
                     or not isinstance(self.topology_generation, int)
                     or self.topology_generation < 0)):
            raise ValueError(
                "projection topology generation must be non-negative")
        if (self.topology_semantic_hash is not None
                and (not isinstance(self.topology_semantic_hash, str)
                     or not self.topology_semantic_hash)):
            raise ValueError(
                "projection topology semantic hash must be nonempty")

    @property
    def healthy(self):
        return self.health == "healthy"

    @property
    def result_hash(self):
        return structural_hash(self.to_dict())

    def to_dict(self):
        return {
            "balance_residual": float(self.balance_residual),
            "blocked_edge_ids": list(self.blocked_edge_ids),
            "candidate_authority": self.candidate_authority,
            "component_count": self.component_count,
            "congestion_dual": [
                float(value) for value in self.congestion_dual],
            "edge_ids": list(self.edge_ids),
            "feasible_current": [
                float(value) for value in self.feasible_current],
            "gauge_policy": self.gauge_policy,
            "health": self.health,
            "iterations": self.iterations,
            "mobility": [
                float(value) for value in self.mobility],
            "node_ids": list(self.node_ids),
            "requested_current_hash": (
                self.requested_current_hash),
            "solver": self.solver,
            "topology_generation": self.topology_generation,
            "topology_semantic_hash": self.topology_semantic_hash,
        }


class ProjectionSolver:
    """Project a raw current onto balanced legal source-sink flow."""

    SOLVER_IDENTITY = "pf-source-sink-projection/1.0"
    GAUGE_POLICIES = frozenset((
        "first_node_zero", "last_node_zero"))

    def __init__(
            self, gauge_policy="first_node_zero",
            dense_fixture_limit=8,
            maximum_iterations=None):
        if gauge_policy not in self.GAUGE_POLICIES:
            raise ValueError("unknown projection gauge policy")
        if (isinstance(dense_fixture_limit, bool)
                or not isinstance(dense_fixture_limit, int)
                or dense_fixture_limit < 1):
            raise ValueError(
                "dense fixture limit must be positive")
        if (maximum_iterations is not None
                and (isinstance(maximum_iterations, bool)
                     or not isinstance(maximum_iterations, int)
                     or maximum_iterations < 1)):
            raise ValueError(
                "maximum iterations must be positive")
        self.gauge_policy = gauge_policy
        self.dense_fixture_limit = dense_fixture_limit
        self.maximum_iterations = maximum_iterations

    @staticmethod
    def _aligned_mobility(view, requested, mobility):
        edge_ids = tuple(row.stable_id for row in view.edges)
        if requested.edge_ids != edge_ids:
            raise ValueError(
                "requested current is not aligned with flow view")
        if mobility is None:
            values = tuple(
                float(row.control_weight)
                for row in view.edges)
        elif isinstance(mobility, dict):
            unknown = set(mobility) - set(edge_ids)
            if unknown:
                raise ValueError(
                    "mobility references unknown flow edge")
            values = tuple(
                float(mobility.get(edge_id, 0.0))
                for edge_id in edge_ids)
        else:
            values = tuple(float(value) for value in mobility)
            if len(values) != len(edge_ids):
                raise ValueError(
                    "mobility must align with flow edges")
        if any(not math.isfinite(value) or value < 0.0
               for value in values):
            raise ValueError(
                "mobility must be finite and non-negative")
        return tuple(
            value if legal else 0.0
            for value, legal in zip(
                values, requested.legality_mask))

    @staticmethod
    def _boundary(view, requested, boundary):
        if boundary is None:
            boundary = requested.boundary_vector
        if isinstance(boundary, dict):
            rows = tuple(boundary.items())
        else:
            rows = tuple(boundary)
        node_ids = tuple(
            row.stable_id
            for row in sorted(
                view.nodes, key=lambda row: row.local_id))
        unknown = set(str(node_id) for node_id, _ in rows) - set(node_ids)
        if unknown:
            raise ValueError(
                "projection boundary references unknown node")
        values = dict((node_id, 0.0) for node_id in node_ids)
        for node_id, value in rows:
            node_id = str(node_id)
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(
                    "projection boundary must be finite")
            values[node_id] += value
        return node_ids, tuple(values[node_id] for node_id in node_ids)

    @staticmethod
    def _components(view, mobility, node_index):
        adjacency = [set() for _ in node_index]
        for edge, value in zip(view.edges, mobility):
            if value <= 0.0:
                continue
            source = node_index[edge.source_node_id]
            target = node_index[edge.target_node_id]
            adjacency[source].add(target)
            adjacency[target].add(source)
        unseen = set(range(len(node_index)))
        components = []
        while unseen:
            root = min(unseen)
            pending = [root]
            unseen.remove(root)
            component = []
            while pending:
                node = pending.pop()
                component.append(node)
                neighbors = sorted(
                    adjacency[node] & unseen, reverse=True)
                for neighbor in neighbors:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
            components.append(tuple(sorted(component)))
        return tuple(components)

    @staticmethod
    def _divergence(view, current, node_index):
        divergence = [0.0] * len(node_index)
        for edge, value in zip(view.edges, current):
            divergence[node_index[edge.source_node_id]] += value
            divergence[node_index[edge.target_node_id]] -= value
        return tuple(divergence)

    def _failure(
            self, view, requested, node_ids, mobility,
            boundary, components, health, iterations=0):
        current = tuple(0.0 for _ in view.edges)
        divergence = self._divergence(
            view, current,
            dict((value, index)
                 for index, value in enumerate(node_ids)))
        residual = max((
            abs(value - target)
            for value, target in zip(divergence, boundary)),
            default=0.0)
        return ProjectionResult(
            edge_ids=tuple(
                row.stable_id for row in view.edges),
            node_ids=node_ids,
            feasible_current=current,
            congestion_dual=tuple(
                0.0 for _ in node_ids),
            mobility=mobility,
            balance_residual=residual,
            iterations=iterations,
            gauge_policy=self.gauge_policy,
            health=health,
            solver="none",
            component_count=len(components),
            blocked_edge_ids=tuple(
                edge.stable_id
                for edge, value in zip(
                    view.edges, mobility)
                if value <= 0.0),
            requested_current_hash=requested.current_hash,
            topology_generation=view.topology_generation,
            topology_semantic_hash=view.probe_semantic_hash)

    def solve(
            self, view, requested, boundary=None,
            tolerance=1e-9, mobility=None):
        if not isinstance(view, FlowView):
            raise TypeError(
                "projection requires FlowView")
        if not isinstance(requested, RequestedCurrent):
            raise TypeError(
                "projection requires RequestedCurrent")
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError(
                "projection tolerance must be positive")
        mobility = self._aligned_mobility(
            view, requested, mobility)
        node_ids, boundary = self._boundary(
            view, requested, boundary)
        node_index = dict(
            (value, index)
            for index, value in enumerate(node_ids))
        components = self._components(
            view, mobility, node_index)
        if abs(sum(boundary)) > tolerance:
            return self._failure(
                view, requested, node_ids, mobility,
                boundary, components,
                "unhealthy:globally-unbalanced-boundary")
        for component in components:
            if abs(sum(boundary[index]
                       for index in component)) > tolerance:
                return self._failure(
                    view, requested, node_ids, mobility,
                    boundary, components,
                    "unhealthy:disconnected-boundary")

        raw_current = tuple(
            float(value) if edge_mobility > 0.0 else 0.0
            for value, edge_mobility in zip(
                requested.velocity, mobility))
        raw_divergence = self._divergence(
            view, raw_current, node_index)
        residual_rhs = tuple(
            value - target
            for value, target in zip(
                raw_divergence, boundary))
        size = len(node_ids)
        laplacian = [
            [0.0] * size for _ in range(size)]
        for edge, value in zip(view.edges, mobility):
            if value <= 0.0:
                continue
            source = node_index[edge.source_node_id]
            target = node_index[edge.target_node_id]
            laplacian[source][source] += value
            laplacian[target][target] += value
            laplacian[source][target] -= value
            laplacian[target][source] -= value

        dual = [0.0] * size
        total_iterations = 0
        used_solvers = set()
        for component in components:
            if len(component) == 1:
                if abs(residual_rhs[component[0]]) > tolerance:
                    return self._failure(
                        view, requested, node_ids, mobility,
                        boundary, components,
                        "unhealthy:isolated-residual")
                continue
            gauge = (
                component[0]
                if self.gauge_policy == "first_node_zero"
                else component[-1])
            variables = tuple(
                index for index in component
                if index != gauge)
            matrix = tuple(
                tuple(laplacian[row][column]
                      for column in variables)
                for row in variables)
            vector = tuple(
                residual_rhs[index] for index in variables)
            if len(variables) <= self.dense_fixture_limit:
                solution = _dense_solve(
                    matrix, vector, tolerance * 1e-3)
                iterations = 1
                converged = solution is not None
                used_solvers.add("dense-exact")
            else:
                maximum = (
                    self.maximum_iterations
                    if self.maximum_iterations is not None
                    else max(64, 4 * len(variables)))
                scipy_result = _scipy_preconditioned_cg(
                    matrix, vector, tolerance, maximum)
                if scipy_result is None:
                    solution, iterations, converged = (
                        _preconditioned_cg(
                            matrix, vector, tolerance, maximum))
                    used_solvers.add("diagonal-pcg")
                else:
                    solution, iterations, converged = scipy_result
                    used_solvers.add("scipy-diagonal-pcg")
            total_iterations += iterations
            if not converged:
                return self._failure(
                    view, requested, node_ids, mobility,
                    boundary, components,
                    "unhealthy:nonconverged",
                    total_iterations)
            for index, value in zip(variables, solution):
                dual[index] = value

        current = []
        for edge, value, edge_mobility in zip(
                view.edges, raw_current, mobility):
            gradient = (
                dual[node_index[edge.source_node_id]]
                - dual[node_index[edge.target_node_id]])
            current.append(
                value - edge_mobility * gradient)
        current = tuple(
            0.0 if abs(value) <= tolerance * 1e-3 else value
            for value in current)
        divergence = self._divergence(
            view, current, node_index)
        residual = max((
            abs(value - target)
            for value, target in zip(
                divergence, boundary)),
            default=0.0)
        if residual > tolerance:
            return self._failure(
                view, requested, node_ids, mobility,
                boundary, components,
                "unhealthy:balance-residual",
                total_iterations)
        solver = "+".join(sorted(used_solvers)) or "trivial"
        return ProjectionResult(
            edge_ids=tuple(
                row.stable_id for row in view.edges),
            node_ids=node_ids,
            feasible_current=current,
            congestion_dual=tuple(dual),
            mobility=mobility,
            balance_residual=residual,
            iterations=total_iterations,
            gauge_policy=self.gauge_policy,
            health="healthy",
            solver=solver,
            component_count=len(components),
            blocked_edge_ids=tuple(
                edge.stable_id
                for edge, value in zip(
                    view.edges, mobility)
                if value <= 0.0),
            requested_current_hash=requested.current_hash,
            topology_generation=view.topology_generation,
            topology_semantic_hash=view.probe_semantic_hash)
