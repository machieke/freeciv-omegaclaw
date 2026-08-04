import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_intention_live import (  # noqa: E402
    FIXED_SEEDS,
    expected_arm_order,
    paired_replacement_intention_analysis,
)


def _summary(seed, arm, both=True, opportunity=True, observed=True,
             completion=False):
    consequence = None
    if opportunity:
        consequence = {
            "assigned_actor_survival_count": 2,
            "both_cities_owned_and_present": both if observed else None,
            "city_retention_count": 2 if both else 1,
            "defended_city_count": 2 if both else 1,
            "exact_combat_attributed_actor_losses": 0,
            "outcome_status": "observed" if observed else "censored",
            "unexplained_actor_removals": 0 if observed else None,
        }
    return {
        "arm": arm,
        "assignment_turn": 40 if opportunity else None,
        "consequence": consequence,
        "execution_completion_turn": 44 if completion else None,
        "logical_pair": [8, 7, 3, 4] if opportunity else None,
        "opportunity": opportunity,
        "run_started_at": (
            "2026-08-04T00:00:{:02d}Z".format(
                10 if arm == "control" else 20)
            if expected_arm_order(seed)[0] == "control"
            else "2026-08-04T00:00:{:02d}Z".format(
                20 if arm == "control" else 10)),
        "seed": seed,
    }


def test_paired_replacement_intention_analysis_preserves_every_fixed_seed():
    control = {}
    treatment = {}
    outcomes = ((True, True), (False, True), (True, False), (True, True))
    for index, seed in enumerate(FIXED_SEEDS):
        if index < len(outcomes):
            control[seed] = _summary(seed, "control", outcomes[index][0])
            treatment[seed] = _summary(
                seed, "treatment", outcomes[index][1],
                completion=index < 2)
        else:
            control[seed] = _summary(
                seed, "control", opportunity=False)
            treatment[seed] = _summary(
                seed, "treatment", opportunity=False)

    result = paired_replacement_intention_analysis(control, treatment)

    assert len(result["rows"]) == 16
    assert result["classification_counts"] == {
        "matched-observed": 4,
        "matched-censored": 0,
        "no-opportunity": 12,
        "opportunity-mismatch": 0,
        "outcome-mismatch": 0,
        "incomplete-pair": 0,
    }
    assert result["primary"]["risk_difference"]["estimate"] == 0.0
    assert result["primary"]["discordance"]["baseline_only_win"] == 1
    assert result["primary"]["discordance"]["treatment_only_win"] == 1
    assert result["primary"]["discordance"]["exact_mcnemar_p"] == 1.0
    assert result["secondary"]["city_retention_count"]["estimate"] == 0.0
    assert result["progression"] == {
        "city_retention_point_estimate_nonnegative": True,
        "minimum_four_observed_pairs": True,
        "minimum_two_treatment_completions": True,
        "no_mechanical_failures": True,
        "no_treatment_excess_unexplained_removal": True,
    }


def test_paired_replacement_intention_analysis_fails_closed_on_mismatch():
    seed = FIXED_SEEDS[0]
    control = {seed: _summary(seed, "control")}
    treatment_row = _summary(seed, "treatment")
    treatment_row["assignment_turn"] = 41

    result = paired_replacement_intention_analysis(
        control, {seed: treatment_row})

    assert result["classification_counts"]["opportunity-mismatch"] == 1
    assert result["classification_counts"]["incomplete-pair"] == 15
    assert result["mechanical_failure_seeds"] == list(FIXED_SEEDS)
    assert result["primary"]["risk_difference"]["estimate"] is None
    assert result["progression"]["no_mechanical_failures"] is False
