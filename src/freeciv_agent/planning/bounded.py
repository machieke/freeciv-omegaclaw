"""Deterministic bounded production scheduler for interleaved city work."""

import itertools
import math
import time
from dataclasses import dataclass

from ..events.schema import structural_hash
from .model import NonPlan, PlanStep, ResourceLedger, ResourceLedgerEntry


@dataclass(frozen=True)
class ProductionGoal:
    goal_id: str
    target: str
    count: int = 1


class ProductionScheduler(object):
    SOLVER = "bounded-production-enumerator/1.0"

    def __init__(self, horizon=30, timeout_ms=500.0):
        if horizon < 1 or horizon > 30:
            raise ValueError("production horizon must be in 1..30")
        self.horizon = int(horizon)
        self.timeout_ms = float(timeout_ms)

    def schedule(self, goals, snapshot, proof_hash="0" * 64):
        started = time.perf_counter()
        tasks = []
        for goal in goals:
            cost = snapshot.build_cost(goal.target)
            if cost is None:
                return NonPlan("NO_PLAN", "MISSING_BUILD_COST", snapshot.snapshot_id,
                               proof_hash, self.SOLVER, goal.target)
            tasks.extend((goal, int(cost), copy_index) for copy_index in range(goal.count))
        cities = tuple(sorted(str(key) for key, _ in snapshot.city_shields_per_turn))
        if tasks and not cities:
            return NonPlan("NO_PLAN", "NO_PRODUCTION_CITY", snapshot.snapshot_id,
                           proof_hash, self.SOLVER)
        best = None
        for assignment in itertools.product(cities, repeat=len(tasks)):
            if (time.perf_counter() - started) * 1000.0 > self.timeout_ms:
                return NonPlan("NO_PLAN", "SCHEDULER_TIMEOUT", snapshot.snapshot_id,
                               proof_hash, self.SOLVER)
            city_ready = {city: snapshot.turn for city in cities}
            city_stock = {city: int(snapshot.city_stockpile(city) or 0) for city in cities}
            rows = []
            ledger = []
            feasible = True
            for position, ((goal, cost, copy_index), city) in enumerate(zip(tasks, assignment)):
                rate = snapshot.city_rate(city)
                if rate is None or rate <= 0:
                    feasible = False
                    break
                stock = city_stock[city]
                remaining = max(0, cost - stock)
                duration = int(math.ceil(float(remaining) / rate))
                finish = city_ready[city] + duration
                if finish - snapshot.turn > self.horizon:
                    feasible = False
                    break
                step_id = "prod-{:02d}-{}".format(position, structural_hash(
                    [goal.goal_id, copy_index, city])[:10])
                available = stock + duration * rate
                ledger.append(ResourceLedgerEntry(
                    "city-shields:{}:{}".format(city, step_id), available,
                    float(cost), float(available - cost), step_id))
                city_stock[city] = available - cost
                city_ready[city] = finish
                rows.append(PlanStep(step_id, "produce", {
                    "city": city, "target": goal.target, "copy": copy_index,
                }, finish, duration, float(cost), snapshot_id=snapshot.snapshot_id))
            if not feasible:
                continue
            makespan = max([snapshot.turn] + [step.predicted_turn for step in rows])
            candidate = (makespan, tuple(step.step_id for step in rows),
                         tuple(rows), ResourceLedger(tuple(ledger)))
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is None:
            return NonPlan("NO_PLAN_WITHIN_HORIZON", "NO_PLAN_WITHIN_HORIZON",
                           snapshot.snapshot_id, proof_hash, self.SOLVER,
                           {"horizon": self.horizon})
        best[3].validate()
        return {"predicted_turns": best[0] - snapshot.turn,
                "steps": best[2], "ledger": best[3], "solver_identity": self.SOLVER}
