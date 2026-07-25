"""Deterministic branch-abandonment benchmark for PF-PLN Phase 4."""

from types import SimpleNamespace

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.pressure import ConductanceState, ImpactPressureRanker


class _Candidate(object):
    def __init__(self, category, utility, action_type):
        self.category = str(category)
        self.utility = float(utility)
        self.action = {"action_type": str(action_type)}
        self.rationale = str(action_type)
        self.projection = None

    @property
    def action_key(self):
        return self.action["action_type"]

    def to_dict(self):
        return {
            "action": dict(self.action),
            "category": self.category,
            "rationale": self.rationale,
            "utility": self.utility,
        }


def _selected(ranker, snapshot, candidates):
    ordered, artifact = ranker.rank(
        snapshot,
        candidates,
        expansion_city_target=3,
        horizon_turn=30,
    )
    return ordered[0].category, artifact


def _contains_truth_channel(value):
    if isinstance(value, dict):
        if set(value).intersection({
                "belief", "beliefs", "truth", "truth_value",
                "truth_values"}):
            return True
        return any(
            _contains_truth_channel(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_truth_channel(item) for item in value)
    return False


def run_conductance_benchmark(maximum_attempts=12):
    """Compare learned conductance with the fixed Phase-1 route prior."""
    maximum_attempts = int(maximum_attempts)
    if maximum_attempts < 1:
        raise ValueError("maximum attempts must be positive")
    snapshot = SimpleNamespace(cities=(), turn=5)
    candidates = (
        _Candidate("production_economy", 1000.0, "economy"),
        _Candidate("production_military_score", 500.0, "military"),
    )

    fixed_state = ConductanceState(identity="phase-4-fixed")
    fixed_ranker = ImpactPressureRanker(conductance_state=fixed_state)
    fixed_choices = [
        _selected(fixed_ranker, snapshot, candidates)[0]
        for _ in range(maximum_attempts + 1)
    ]

    learned_state = ConductanceState(identity="phase-4-learned")
    learned_ranker = ImpactPressureRanker(
        conductance_state=learned_state)
    learned_choices = []
    abandonment_attempt = None
    final_artifact = None
    for attempt in range(maximum_attempts + 1):
        selected, final_artifact = _selected(
            learned_ranker, snapshot, candidates)
        learned_choices.append(selected)
        if selected != "production_economy":
            abandonment_attempt = attempt
            break
        if attempt < maximum_attempts:
            learned_state.feedback(
                "production_economy",
                False,
                "phase-4-no-progress-{:02d}".format(attempt),
                realized_relief=0.0,
                relief_source="authoritative:no-state-or-goal-change",
            )

    fixed_abandonment_attempt = next(
        (
            index for index, category in enumerate(fixed_choices)
            if category != "production_economy"
        ),
        None,
    )
    report = {
        "acceptance": {
            "branch_abandoned_within_bound": (
                abandonment_attempt is not None
                and abandonment_attempt <= maximum_attempts),
            "fixed_phase_1_route_does_not_abandon": (
                fixed_abandonment_attempt is None),
            "learned_abandonment_is_faster": (
                abandonment_attempt is not None
                and fixed_abandonment_attempt is None),
            "pressure_state_is_truth_free": not _contains_truth_channel(
                learned_state.snapshot()),
        },
        "benchmark": "pf-pln-phase-4-conductance-learning",
        "branch_abandonment": {
            "fixed_abandonment_attempt": fixed_abandonment_attempt,
            "fixed_choices": fixed_choices,
            "learned_abandonment_attempt": abandonment_attempt,
            "learned_choices": learned_choices,
            "maximum_attempts": maximum_attempts,
        },
        "configuration": learned_state.snapshot()["configuration"],
        "final_conductance_state": final_artifact["conductance_state"],
        "schema_version": "1.0",
    }
    report["artifact_hash"] = structural_hash(report)
    return report
