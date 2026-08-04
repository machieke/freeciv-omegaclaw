import os
import sys
from types import SimpleNamespace


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness.fdas_replacement_intention_live import (  # noqa: E402
    CORRECTED_FIXED_SEEDS,
    FIXED_SEEDS,
    ISOLATED_EXPERIMENT_ID,
    ISOLATED_FIXED_SEEDS,
    _assignment_readout_evidence,
    _removal,
    expected_arm_order,
    paired_replacement_intention_analysis,
)


def test_isolated_experiment_arm_order_is_deterministic_and_seed_fresh():
    assert len(ISOLATED_FIXED_SEEDS) == len(set(ISOLATED_FIXED_SEEDS)) == 16
    assert not set(ISOLATED_FIXED_SEEDS).intersection(FIXED_SEEDS)
    assert not set(ISOLATED_FIXED_SEEDS).intersection(CORRECTED_FIXED_SEEDS)
    first = tuple(expected_arm_order(
        seed, ISOLATED_EXPERIMENT_ID) for seed in ISOLATED_FIXED_SEEDS)
    second = tuple(expected_arm_order(
        seed, ISOLATED_EXPERIMENT_ID) for seed in ISOLATED_FIXED_SEEDS)

    assert first == second
    assert all(set(order) == {"control", "treatment"} for order in first)


def test_intention_removal_includes_assignment_turn_exact_evidence():
    event = {
        "caused_by": ["combat-result"],
        "event_id": "unit-removal",
        "payload": {
            "cause": "combat_attacker_lost",
            "detail": "actor died after the intention was assigned",
            "evidence_event_ids": ["combat-result"],
            "evidence_quality": "exact",
            "transition": "disappeared",
            "unit_id": 8,
        },
        "turn": 40,
        "type": "unit_lifecycle",
    }
    assignment = SimpleNamespace(
        assignment_turn=40,
        outcome=SimpleNamespace(observed_turn=72))

    removal = _removal((event,), 8, assignment, present=False)

    assert removal["exact"] is True
    assert removal["unexplained"] is False
    assert removal["cause"] == "combat_attacker_lost"
    assert removal["turn"] == 40


def test_assignment_readout_evidence_binds_logical_minimum():
    assignment = SimpleNamespace(logical_pair=(112, 108, 103, 116))
    readout = {
        "event_id": "readout",
        "payload": {
            "component_id": "fdas-coordinated-replacement-candidate-readout",
            "details": {"pairs": [
                {"replacement_actor_id": 122,
                 "reinforcement_actor_id": 108,
                 "source_city_id": 103, "target_city_id": 116},
                {"replacement_actor_id": 112,
                 "reinforcement_actor_id": 108,
                 "source_city_id": 103, "target_city_id": 116},
            ]},
        },
    }
    assigned = {"event_id": "assigned", "caused_by": ["readout"]}

    evidence = _assignment_readout_evidence(
        (readout, assigned), (assigned,), assignment)

    assert evidence["bound"] is True
    assert evidence["logical_pair_count"] == 2
    assert evidence["selected_is_lexicographic_minimum"] is True


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
        "assignment_candidate_logical_pair_hash": (
            "candidate-surface" if opportunity else None),
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


def test_paired_replacement_intention_excludes_failed_no_opportunity_arm():
    seed = FIXED_SEEDS[0]
    control_row = _summary(seed, "control", opportunity=False)
    treatment_row = _summary(seed, "treatment", opportunity=False)
    treatment_row["arm_audit_accepted"] = False
    treatment_row["infrastructure_failure"] = True
    treatment_row["infrastructure_error"] = "bounded pilot failed"

    result = paired_replacement_intention_analysis(
        {seed: control_row}, {seed: treatment_row})

    row = result["rows"][0]
    assert row["classification"] == "no-opportunity"
    assert row["arm_audits_valid"] is False
    assert seed in result["mechanical_failure_seeds"]
    assert result["progression"]["no_mechanical_failures"] is False
