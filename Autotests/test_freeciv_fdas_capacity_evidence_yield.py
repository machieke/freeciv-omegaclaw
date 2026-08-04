import pytest

from freeciv.harness.fdas_retained_capacity_evidence_yield import (
    retained_capacity_evidence_yield_plan,
)
from freeciv.harness.fdas_retained_capacity_query_yield import (
    audit_fdas_retained_capacity_query_yield,
)
from freeciv.harness.fdas_retained_capacity_transition_discovery import (
    audit_fdas_retained_capacity_transition_discovery,
    retained_capacity_transition_discovery_adequacy,
)
from freeciv.harness.statistics import (
    binomial_at_least_probability,
    binomial_minimum_trials,
)


def test_exact_binomial_minimum_is_minimal_and_validates_inputs():
    design = binomial_minimum_trials(1.0 / 16.0, 10, 0.9)

    assert design["samples"] == 225
    assert design["achieved_probability"] >= 0.9
    assert binomial_at_least_probability(224, 1.0 / 16.0, 10) < 0.9
    with pytest.raises(ValueError, match="invalid binomial"):
        binomial_minimum_trials(0.0, 10, 0.9)
    with pytest.raises(ValueError, match="invalid binomial"):
        binomial_at_least_probability(-1, 0.5, 1)


def test_retained_capacity_yield_plan_reproduces_preregistered_sizes():
    first = retained_capacity_evidence_yield_plan()
    second = retained_capacity_evidence_yield_plan()

    assert first == second
    by_status = dict((value["status"], value) for value in first["statuses"])
    assert dict((status, value["plug_in_design"]["samples"])
                for status, value in by_status.items()) == {
        "effect-without-goal-relief": 225,
        "goal-relief-observed": 111,
        "no-effect-observed": 74,
    }
    assert dict((status, value[
        "wilson_lower_sensitivity_design"]["samples"])
                for status, value in by_status.items()) == {
        "effect-without-goal-relief": 1275,
        "goal-relief-observed": 404,
        "no-effect-observed": 213,
    }
    assert first["planning"] == {
        "conservative_wilson_lower_sensitivity_games": 1275,
        "provisional_games_per_discovery_or_confirmation_cohort": 225,
        "query_enabled_yield_pilot_games": 64,
        "required_status_bearing_games": 10,
        "target_probability": 0.9,
    }
    assert all(first[name] is False for name in (
        "learning_authority", "policy_authority", "readout_authority",
        "truth_mutated"))


def test_retained_capacity_yield_plan_rejects_changed_status_partition():
    with pytest.raises(ValueError, match="inputs differ"):
        retained_capacity_evidence_yield_plan({
            "effect-without-goal-relief": 1,
            "goal-relief-observed": 2,
        })


def test_retained_capacity_yield_plan_fails_closed_on_zero_observed_status():
    plan = retained_capacity_evidence_yield_plan({
        "effect-without-goal-relief": 0,
        "goal-relief-observed": 2,
        "no-effect-observed": 3,
    }, source_games=64)
    by_status = dict((value["status"], value) for value in plan["statuses"])

    missing = by_status["effect-without-goal-relief"]
    assert missing["plug_in_design"]["samples"] is None
    assert missing["wilson_lower_sensitivity_design"]["samples"] is None
    assert plan["planning"][
        "provisional_games_per_discovery_or_confirmation_cohort"] is None
    assert plan["planning"][
        "conservative_wilson_lower_sensitivity_games"] is None


def test_retained_capacity_query_yield_requires_exact_fixed_cohort():
    with pytest.raises(ValueError, match="requires 64 seeds"):
        audit_fdas_retained_capacity_query_yield(
            "unused", tuple(range(63)), "commit")


def _discovery_dataset(statuses_by_seed):
    rows = []
    games = []
    for seed, statuses in statuses_by_seed.items():
        games.append({
            "censored_rows": 0,
            "seed": seed,
            "terminal_rows": len(statuses),
        })
        rows.extend({
            "row": {
                "observation_status": "terminal-observed",
                "outcome_status": status,
            },
            "seed": seed,
        } for status in statuses)
    return {
        "games": games,
        "rows": rows,
        "summary": {"terminal_rows": len(rows)},
    }


def test_retained_capacity_transition_discovery_adequacy_is_game_scoped():
    statuses = (
        ["no-effect-observed"] * 10
        + ["effect-without-goal-relief"] * 10
        + ["goal-relief-observed"] * 10)
    inadequate = retained_capacity_transition_discovery_adequacy(
        _discovery_dataset({1: statuses}))

    assert inadequate["measures"]["terminal_rows"] == 30
    assert inadequate["measures"]["terminal_bearing_games"] == 1
    assert inadequate["measures"]["goal-relief-observed_games"] == 1
    assert inadequate["decision"] == "insufficient-evidence"

    adequate = retained_capacity_transition_discovery_adequacy(
        _discovery_dataset(dict((seed, (
            "no-effect-observed",
            "effect-without-goal-relief",
            "goal-relief-observed",
        )) for seed in range(10))))
    assert adequate["measures"]["terminal_bearing_games"] == 10
    assert adequate["decision"] == "insufficient-evidence"
    assert adequate["checks"]["terminal_bearing_games_minimum_met"] is False


def test_retained_capacity_transition_discovery_requires_exact_cohort():
    with pytest.raises(ValueError, match="requires 301 unique seeds"):
        audit_fdas_retained_capacity_transition_discovery(
            "unused", tuple(range(300)), "commit")
    with pytest.raises(ValueError, match="requires 301 unique seeds"):
        audit_fdas_retained_capacity_transition_discovery(
            "unused", tuple(range(300)) + (299,), "commit")
