"""M7 controller, reproducibility, statistics, fidelity, and capability gates."""

import asyncio
import io
import json
import os
import re
import sys
import tempfile
from unittest import mock

import jsonschema
import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(REPO, "src"), os.path.join(REPO, "benchmarks")):
    if path not in sys.path:
        sys.path.insert(0, path)

from freeciv.harness import (HarnessRunner, aggregate_impact_pairs,  # noqa: E402
                             aggregate_runs, write_impact_report, write_report)
from freeciv.harness.config import CapabilityContext, load  # noqa: E402
from freeciv.harness.statistics import (paired_binary_discordance,  # noqa: E402
                                        paired_binary_effect, paired_delta,
                                        paired_power, paired_score_randomization,
                                        paired_win_design_power,
                                        wilson)
from freeciv.harness.aggregate import _calibration_report  # noqa: E402
from freeciv.harness.impact_evaluation import _claim_evaluation  # noqa: E402
from freeciv.harness.runner import _impact_cohort_token  # noqa: E402
from freeciv.harness.engine_live import (  # noqa: E402
    _available_research_names, _needs_cognitive_stack, _opponent_memory_path,
    _claim_eligible_manifest, _ollama_readiness, _plain_prompt_state,
    _plain_state_summary, _refresh_accepted_impact_action,
    _decision_state_fingerprint, _decision_state_ready, _global_state_ready,
    _player_eliminated, _release_configuration_active, _state,
    _validate_compact_goal_proposal)
from freeciv.harness import engine_live  # noqa: E402
from freeciv_agent.events.schema import canonical_json_bytes, structural_hash  # noqa: E402
from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.state import ProxyStateDTO  # noqa: E402


def test_config_predeclares_identical_30_seed_matrix_and_20_game_induction():
    config = load()
    assert len(config["seeds"]) == 30 == len(set(config["seeds"]))
    assert config["induction"]["games"] >= 20
    assert config["conditions"] == [
        "a_stock_llm", "b_state_oracle", "c_dependency_scheduler",
        "d_uncertain_monitor", "e_full_loop"]
    assert config["model"]["name"] == "qwen3-coder-next:latest"
    assert config["model"]["think"] is False
    assert config["impact_policy"]["no_effect_retry_limit"] == 1
    assert config["impact_policy"]["max_no_effect_failovers_per_scope"] == 4
    assert config["impact_policy"]["horizon_turn"] == 30
    assert config["impact_policy"]["production_minimum_remaining_turns"] == 8
    assert config["impact_policy"]["unit_build_score_divisor"] == 10
    assert config["impact_policy"]["refresh_timeout_seconds"] == 2.0
    assert config["impact_policy"]["production_strategy"] == "horizon_score"
    assert config["impact_policy"]["pressure_learning_enabled"] is True
    assert config["impact_policy"]["pressure_max_routes_per_conclusion"] == 32
    assert config["impact_policy"]["pressure_survival_threat_radius"] == 3
    assert config["impact_policy"]["pressure_learning_rate"] == 0.10
    assert config["impact_policy"]["pressure_no_progress_rate"] == 0.10
    assert config["impact_policy"]["pressure_initial_conductance"] == 1.00
    paired = config["paired_impact"]
    assert paired["default_cohort"] == "development"
    assert {name: len(row["seeds"]) for name, row in paired["cohorts"].items()} == {
        "development": 100, "diagnostic_unitless_city_v1": 1, "pilot": 40,
        "pilot_horizon_60": 40,
        "pilot_horizon_60_v2": 40,
        "pilot_horizon_60_v3": 40,
        "pilot_horizon_60_v4": 40,
        "confirmatory_score": 100,
        "confirmatory_score_horizon_60_v1": 200,
        "timing_parity_v1": 3,
        "diagnostic_terminal_elimination_v1": 2,
        "confirmatory_joint": 450,
        "pressure_ablation_pilot_v1": 40,
        "pressure_ablation_pilot_v2": 40,
        "pressure_goal_relief_pilot_v1": 40,
        "pressure_threat_relevance_pilot_v1": 40,
        "pressure_defense_relevance_pilot_v1": 40,
        "pressure_category_invariance_pilot_v1": 40,
    }
    seed_sets = [set(row["seeds"]) for row in paired["cohorts"].values()]
    assert all(not left & right for index, left in enumerate(seed_sets)
               for right in seed_sets[index + 1:])
    assert paired["outcomes"]["win_metric"] == "score_lead_turn_n"
    assert paired["outcomes"]["win_definition"] == "fixed_horizon_score_lead"
    assert paired["outcomes"]["early_terminal_score"] == (
        "terminal_absorbing_score_carried_to_horizon")
    assert paired["power"]["minimum_variance_pairs"] == 30
    assert paired["claims"]["multiplicity"] == "hierarchical_score_then_win"
    assert paired["claims"]["score_test"] == {
        "alternative": "two_sided", "maximum_states": 1000000,
        "method": "exact_paired_sign_flip"}
    assert paired["claims"]["meaningful_score_test"] == {
        "alternative": "greater", "maximum_states": 1000000,
        "method": "exact_paired_sign_flip"}
    assert config["paired_impact"]["arms"] == {
        "baseline": {
            "max_no_effect_failovers_per_scope": 0,
            "production_strategy": "static_priority"},
        "treatment": {
            "max_no_effect_failovers_per_scope": 4,
            "production_strategy": "horizon_score"},
    }
    score_derivation = paired["cohorts"]["confirmatory_score"]["seed_derivation"]
    assert score_derivation == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pln-freeciv-impact-confirmatory-score-v4",
        "count": 100, "minimum": 1100000, "maximum": 1199999,
    }
    assert paired["cohorts"]["confirmatory_score"]["claim_eligible"] is False
    fresh_score = paired["cohorts"]["confirmatory_score_horizon_60_v1"]
    assert fresh_score["score_design"] == {
        "minimum_detectable_delta": 0.2,
        "maximum_planning_sd": 1.0,
    }
    assert fresh_score["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pln-freeciv-impact-confirmatory-score-horizon60-v1",
        "count": 200, "minimum": 1400000, "maximum": 1699999,
    }
    retired_score = paired["retired_cohorts"]["confirmatory_score_horizon_60_v2"]
    assert retired_score["retired_reason"] == (
        "unitless_city_state_rejected_at_seed_1905459_turn_25")
    assert retired_score["completed_arms"] == 899
    assert retired_score["score_design"] == {
        "minimum_detectable_delta": 0.2,
        "maximum_planning_sd": 1.5,
    }
    assert retired_score["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": (
            "pln-freeciv-impact-confirmatory-score-horizon60-v2-current-policy"),
        "count": 450, "minimum": 1900000, "maximum": 1999999,
    }
    retired_latency = paired["retired_cohorts"]["confirmatory_score_horizon_60_v3"]
    assert retired_latency["retired_reason"] == (
        "operational_latency_retirement_before_outcome_inspection")
    assert retired_latency["completed_arms"] == 38
    assert retired_latency["outcome_values_inspected"] is False
    retired_terminal = paired["retired_cohorts"]["confirmatory_score_horizon_60_v4"]
    assert retired_terminal["retired_reason"] == (
        "terminal_player_elimination_misclassified_as_infrastructure_timeout")
    assert retired_terminal["completed_arms"] == 897
    assert retired_terminal["active_infrastructure_failures"] == 3
    assert retired_terminal["score_design"] == {
        "minimum_detectable_delta": 0.2,
        "maximum_planning_sd": 1.5,
    }
    assert retired_terminal["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": (
            "pln-freeciv-impact-confirmatory-score-horizon60-v4-pair-parallel"),
        "count": 450, "minimum": 2100000, "maximum": 2199999,
    }
    assert retired_terminal["controller_workers"] == 3
    terminal_diagnostic = paired["cohorts"]["diagnostic_terminal_elimination_v1"]
    assert terminal_diagnostic == {
        "purpose": "diagnostic", "claim_eligible": False,
        "require_clean_source": True,
        "endpoints": ["score_turn_n", "score_lead_turn_n"],
        "horizon_turn": 60, "planned_pairs": 2, "controller_workers": 2,
        "seeds": [2119913, 2146151],
    }
    assert paired["cohorts"]["pilot_horizon_60"] == {
        "purpose": "pilot", "claim_eligible": False,
        "require_clean_source": True,
        "endpoints": ["score_turn_n", "score_lead_turn_n"],
        "horizon_turn": 60, "planned_pairs": 40,
        "seed_derivation": {
            "algorithm": "sha256-counter-v1",
            "namespace": "pln-freeciv-impact-pilot-horizon60-v1",
            "count": 40, "minimum": 1200000, "maximum": 1299999,
        },
        "seeds": paired["cohorts"]["pilot_horizon_60"]["seeds"],
    }
    assert paired["cohorts"]["pilot_horizon_60_v2"]["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pln-freeciv-impact-pilot-horizon60-v2",
        "count": 40, "minimum": 1300000, "maximum": 1399999,
    }
    assert paired["cohorts"]["pilot_horizon_60_v3"]["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pln-freeciv-impact-pilot-horizon60-v3",
        "count": 40, "minimum": 1700000, "maximum": 1799999,
    }
    assert paired["cohorts"]["pilot_horizon_60_v4"]["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pln-freeciv-impact-pilot-horizon60-v4",
        "count": 40, "minimum": 1800000, "maximum": 1899999,
    }
    pressure_pilot = paired["cohorts"]["pressure_ablation_pilot_v1"]
    assert pressure_pilot["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-ablation-pilot-v1",
        "count": 40, "minimum": 2300000, "maximum": 2399999,
    }
    assert pressure_pilot["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    pressure_pilot_v2 = paired["cohorts"]["pressure_ablation_pilot_v2"]
    assert pressure_pilot_v2["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-ablation-pilot-v2",
        "count": 40, "minimum": 2400000, "maximum": 2499999,
    }
    assert pressure_pilot_v2["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    goal_relief_pilot = paired["cohorts"]["pressure_goal_relief_pilot_v1"]
    assert goal_relief_pilot["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-goal-relief-pilot-v1",
        "count": 40, "minimum": 2500000, "maximum": 2599999,
    }
    assert goal_relief_pilot["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    threat_pilot = paired["cohorts"]["pressure_threat_relevance_pilot_v1"]
    assert threat_pilot["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-threat-relevance-pilot-v1",
        "count": 40, "minimum": 2600000, "maximum": 2699999,
    }
    assert threat_pilot["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    defense_pilot = paired["cohorts"]["pressure_defense_relevance_pilot_v1"]
    assert defense_pilot["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-defense-relevance-pilot-v1",
        "count": 40, "minimum": 2700000, "maximum": 2799999,
    }
    assert defense_pilot["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    category_pilot = paired["cohorts"]["pressure_category_invariance_pilot_v1"]
    assert category_pilot["seed_derivation"] == {
        "algorithm": "sha256-counter-v1",
        "namespace": "pf-pln-pressure-category-invariance-pilot-v1",
        "count": 40, "minimum": 2800000, "maximum": 2899999,
    }
    assert category_pilot["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    assert config["rulebase"] == {
        "compiler_version": "freeciv-ruleset-compiler/1.2",
        "source_sha256": "3aed61bdc092b4bde2515c9d925a43be38c650fca88ff3bef32ad316b0dccd8e",
        "ir_sha256": "be57b9141bc0c9a439abcc6ab4052601c2cec82c6c6e148f5ebd587fde120687",
        "atomese_sha256": "cecd6aa53684e276c6d2426f93151d19998635d60bbcf02383a4387557f19edb",
    }


def test_config_rejects_an_underpowered_predeclared_win_design():
    source = open(os.path.join(
        REPO, "profile", "freeciv_harness.yaml"), encoding="utf-8").read()
    source = source.replace(
        "      planned_pairs: 450\n  claims:",
        "      planned_pairs: 100\n  claims:")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "underpowered.yaml")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(source)
        with pytest.raises(ValueError, match="win planned_pairs does not meet"):
            load(path)


def test_config_rejects_an_underpowered_cohort_specific_score_design():
    source = open(os.path.join(
        REPO, "profile", "freeciv_harness.yaml"), encoding="utf-8").read()
    source = source.replace(
        "      planned_pairs: 200\n      score_design:\n",
        "      planned_pairs: 100\n      score_design:\n", 1).replace(
            "        namespace: pln-freeciv-impact-confirmatory-score-horizon60-v1\n"
            "        count: 200\n",
            "        namespace: pln-freeciv-impact-confirmatory-score-horizon60-v1\n"
            "        count: 100\n", 1)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "underpowered-score.yaml")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(source)
        with pytest.raises(ValueError, match="underpowered for the declared score design"):
            load(path)


def test_config_rejects_pressure_cohort_with_an_undeclared_arm_difference():
    source = open(os.path.join(
        REPO, "profile", "freeciv_harness.yaml"), encoding="utf-8").read()
    source = source.replace(
        "      isolated_policy_keys:\n"
        "        - pressure_enabled\n"
        "        - pressure_learning_enabled\n",
        "      isolated_policy_keys:\n"
        "        - pressure_enabled\n",
        1)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "invalid-pressure-isolation.yaml")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(source)
        with pytest.raises(
                ValueError, match="exactly match isolated_policy_keys"):
            load(path)


def test_wilson_and_paired_bootstrap_are_bounded_and_deterministic():
    interval = wilson(20, 30)
    assert 0 <= interval["lower"] <= interval["estimate"] <= interval["upper"] <= 1
    first = paired_delta({1: 1, 2: 3}, {1: 2, 2: 7}, samples=1000, seed=9)
    second = paired_delta({2: 3, 1: 1}, {2: 7, 1: 2}, samples=1000, seed=9)
    assert first == second and first["paired_seeds"] == [1, 2]


def test_paired_binary_discordance_and_power_keep_games_as_experimental_units():
    binary = paired_binary_discordance(
        {1: 1, 2: 0, 3: 1, 4: 0}, {1: 1, 2: 1, 3: 0, 4: 0})
    assert binary["both_win"] == binary["both_lose"] == 1
    assert binary["baseline_only_win"] == binary["treatment_only_win"] == 1
    assert binary["discordant_pairs"] == 2
    assert binary["exact_mcnemar_p"] == 1.0
    effect = paired_binary_effect(
        {1: 1, 2: 0, 3: 1, 4: 0}, {1: 1, 2: 1, 3: 0, 4: 0},
        samples=1000, seed=9)
    assert effect["estimate"] == 0 and effect["n"] == 4
    assert effect["lower"] <= 0 <= effect["upper"]
    suppressed = paired_power([-2, 0, 2, 4, 6], minimum_detectable_delta=2)
    assert suppressed["achieved_pairs"] == 5
    assert suppressed["ready"] is False
    assert suppressed["observed_paired_sd"] is None
    power = paired_power(([-2, 0, 2, 4, 6] * 6), minimum_detectable_delta=2)
    assert power["achieved_pairs"] == 30 and power["ready"] is True
    assert power["observed_paired_sd"] > 0
    assert power["required_pairs"] >= 30
    assert power["detectable_delta_at_achieved_n"] > 0
    win_power = paired_win_design_power(450, 0.10, 0.50)
    assert win_power["planned_power"] >= 0.8
    assert win_power["target_met"] is True


def test_exact_paired_score_randomization_is_deterministic_and_fails_closed():
    strong = paired_score_randomization([2] * 10)
    assert strong["ready"] is True
    assert strong["exact"] is True
    assert strong["p_value"] == pytest.approx(2.0 / (2 ** 10))
    assert strong["states_evaluated"] == 11
    assert strong["nonzero_pairs"] == 10

    null = paired_score_randomization([-2, -1, 0, 1, 2])
    assert null["ready"] is True and null["p_value"] == 1.0
    bounded = paired_score_randomization([1, 2, 4, 8], maximum_states=4)
    assert bounded["ready"] is False
    assert "state bound" in bounded["reason"]
    fractional = paired_score_randomization([1.5, 2.5])
    assert fractional["ready"] is False
    assert "integer score differences" in fractional["reason"]

    meaningful = paired_score_randomization(
        [3] * 10, margin=2, alternative="greater")
    assert meaningful["alternative"] == "greater"
    assert meaningful["observed_mean_difference"] == 1.0
    assert meaningful["p_value"] == pytest.approx(1.0 / (2 ** 10))
    wrong_direction = paired_score_randomization(
        [0] * 10, margin=2, alternative="greater")
    assert wrong_direction["observed_mean_difference"] == -2.0
    assert wrong_direction["p_value"] == 1.0
    with pytest.raises(ValueError, match="alternative"):
        paired_score_randomization([1], alternative="less")


def test_condition_capability_access_fails_closed():
    context = CapabilityContext("b_state_oracle", load()["capabilities"]["b_state_oracle"])
    assert context.use("authoritative_state")
    with pytest.raises(PermissionError, match="cannot import/use scheduler"):
        context.use("scheduler")


def test_live_candidates_exclude_server_rejected_research_actions():
    raw = {"legal_actions": [
        {"type": "tech_research", "tech_name": "Alphabet", "is_valid": True},
        {"type": "tech_research", "tech_name": "Engineering", "is_valid": False},
        {"type": "tech_research", "tech_name": "Alphabet", "is_valid": True},
        {"type": "unit_move", "tech_name": "Writing", "is_valid": True},
    ]}
    assert _available_research_names(raw) == ["Alphabet"]


def test_release_configuration_accepts_exact_reuse_and_rejects_drift():
    expected = {"ruleset": "civ2civ3", "mapseed": 104729}
    assert _release_configuration_active({
        "game_config_applied": True, "game_config": expected}, expected)
    assert _release_configuration_active({
        "game_config_applied": False, "game_config": expected}, expected)
    assert not _release_configuration_active({
        "game_config_applied": True, "game_config": None}, expected)
    assert not _release_configuration_active({
        "game_config_applied": False,
        "game_config": {"ruleset": "classic", "mapseed": 104729}}, expected)


def test_stock_condition_uses_only_legacy_action_summary_and_no_crisp_stack():
    raw = {"turn": 8, "gold": 99, "legal_actions": [
        {"type": "tech_research", "is_valid": True, "tech_name": "Alphabet"},
        {"type": "unit_move", "is_valid": False},
    ]}
    summary = _plain_state_summary(raw)
    assert summary == {"legal_action_kinds": ["tech_research"]}
    assert "turn" not in summary and "gold" not in summary
    assert _plain_prompt_state(summary) == "disabled"
    assert _plain_prompt_state({
        "cities": [{"id": 1}], "known_techs": ["Alphabet"],
        "legal_action_kinds": ["tech_research"],
        "research": {"beakers_per_turn": 4, "progress": 9, "target": "Writing"},
        "units": [{"id": 1, "type": "Settlers", "x": 5}],
        "visible_enemy_units": [{"id": 9, "type": "Warriors", "x": 8}],
    }) == {
        "city_count": 1, "known_techs": ["Alphabet"],
        "research": {"beakers_per_turn": 4, "target": "Writing"},
        "unit_types": ["Settlers"], "visible_enemy_types": ["Warriors"],
    }
    stock = CapabilityContext("a_stock_llm", load()["capabilities"]["a_stock_llm"])
    state = CapabilityContext("b_state_oracle", load()["capabilities"]["b_state_oracle"])
    crisp = CapabilityContext(
        "c_dependency_scheduler", load()["capabilities"]["c_dependency_scheduler"])
    assert not _needs_cognitive_stack(stock)
    assert not _needs_cognitive_stack(state)
    assert _needs_cognitive_stack(crisp)


def test_compact_live_goal_references_are_bounded_and_claim_free():
    valid = {"goal_indices": [0, 1], "selection": 1, "claims": []}
    assert _validate_compact_goal_proposal(valid, 2) is None
    for invalid in (
        {"goal_indices": [0, 0], "selection": 0, "claims": []},
        {"goal_indices": [2], "selection": 2, "claims": []},
        {"goal_indices": [0], "selection": 1, "claims": []},
        {"goal_indices": [0], "selection": 0, "claims": [{"text": "guess"}]},
    ):
        with pytest.raises(ValueError):
            _validate_compact_goal_proposal(invalid, 2)


def test_live_model_transport_reuses_identical_verified_decision_context(monkeypatch):
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout, json.loads(request.data)))
        return Response(json.dumps({
            "message": {"content": '{"selection":"end_turn"}'},
        }).encode("utf-8"))

    monkeypatch.setattr(engine_live.urllib.request, "urlopen", urlopen)
    engine_live._MODEL_JSON_CACHE.clear()
    manifest = {"model": "qwen3-coder-next:latest", "model_config": {
        "turn_timeout_seconds": 30, "max_tokens": 40,
        "temperature": 0, "think": False}}
    first = engine_live._ollama_json(manifest, "cache-test", ("selection",))
    second = engine_live._ollama_json(manifest, "cache-test", ("selection",))
    assert first[0] == second[0] == {"selection": "end_turn"}
    assert first[2] >= 0 and second[2] == 0
    assert len(calls) == 1 and calls[0][0].endswith("/api/chat")
    assert calls[0][2]["model"] == "qwen3-coder-next:latest"
    assert calls[0][2]["think"] is False
    engine_live._MODEL_JSON_CACHE.clear()


def test_live_model_readiness_uses_native_chat_and_validates_json(monkeypatch):
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout, json.loads(request.data)))
        return Response(json.dumps({
            "model": "qwen3-coder-next:latest", "done": True,
            "message": {"content": "{\"ready\": true}"},
        }).encode("utf-8"))

    monkeypatch.setenv("OLLAMA_OPENAI_BASE_URL", "http://ollama.test:11434/v1/")
    monkeypatch.setattr(engine_live.urllib.request, "urlopen", urlopen)
    manifest = {"model": "qwen3-coder-next:latest", "model_config": {
        "readiness_timeout_seconds": 91, "keep_alive": "30m", "think": False}}
    result = _ollama_readiness(manifest)
    assert result["done"] is True
    assert calls == [("http://ollama.test:11434/api/chat", 91.0, {
        "model": "qwen3-coder-next:latest", "stream": False, "format": "json",
        "think": False, "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 16},
        "messages": [
            {"role": "system", "content": "Return one JSON object only; no markdown."},
            {"role": "user", "content": "Return exactly {\"ready\":true}."},
        ],
    })]


def test_live_model_readiness_rejects_invalid_json(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(engine_live.urllib.request, "urlopen", lambda *_args, **_kwargs:
                        Response(json.dumps({
                            "done": True, "message": {"content": "not-json"},
                        }).encode("utf-8")))
    with pytest.raises(RuntimeError, match="readiness returned invalid JSON"):
        _ollama_readiness({"model": "qwen3-coder-next:latest", "model_config": {
            "readiness_timeout_seconds": 91,
        }})


def _ready_raw(source_seq=1, moves_left=3, buildability=True,
               include_units=True, include_cities=True, turn=1, player_alive=True):
    raw = {
        "format": "pln_authoritative", "turn": turn, "phase": "movement",
        "player_id": 0,
        "authoritative": {
            "source_seq": source_seq,
            "player": {"is_alive": player_alive,
                       "gold": 10, "gold_per_turn": 1, "tax": 40,
                       "science": 60, "luxury": 0},
            "research": {"researching": 1, "researching_name": "Alphabet",
                         "researching_cost": 10, "bulbs_researched": 0,
                         "beakers_per_turn": 1},
            "ruleset": {"ready": True},
        },
        "techs": {"player0": []},
        "units": {"1": {"id": 1, "owner": 0, "type": "Settlers",
                            "type_id": 0, "tile": 0, "x": 0, "y": 0,
                            "moves_left": moves_left, "hp": 20,
                            "activity": "idle", "upkeep": []}},
        "cities": {"10": {
            "id": 10, "owner": 0, "name": "Rome", "tile": 0,
            "x": 0, "y": 0, "size": 1, "production_kind": 6,
            "production_value": 0, "food_stock": 0, "shield_stock": 0,
            "surplus": [0], "prod": [1],
            "buildability": {"available": buildability, "options": []},
        }},
        "map": {"width": 10, "height": 10, "tiles": []},
        "visible_tiles": [],
        "legal_actions": [{"action_type": "end_turn", "is_valid": True}],
    }
    if not include_units:
        raw["units"] = {}
    if not include_cities:
        raw["cities"] = {}
    return raw


def _ready_snapshot(source_seq=1, moves_left=3, buildability=True,
                    include_units=True, include_cities=True, turn=1,
                    player_alive=True):
    raw = _ready_raw(
        source_seq=source_seq, moves_left=moves_left,
        buildability=buildability, include_units=include_units,
        include_cities=include_cities, turn=turn, player_alive=player_alive)
    return ProxyStateDTO.parse(
        "readiness-test", source_seq, raw).to_snapshot()


def test_decision_readiness_waits_for_complete_active_state_and_ignores_cadence():
    first = _ready_snapshot(source_seq=1)
    second = _ready_snapshot(source_seq=2)
    assert _decision_state_ready(first, require_own_units=True)
    assert _decision_state_fingerprint(first) == _decision_state_fingerprint(second)
    assert not _decision_state_ready(_ready_snapshot(moves_left=0))
    assert not _decision_state_ready(_ready_snapshot(buildability=False))


def test_unitless_city_state_is_decision_ready_and_not_eliminated(monkeypatch):
    raw = _ready_raw(
        source_seq=25, include_units=False, include_cities=True, turn=25)

    async def city_only_state(_ws, _format):
        return raw

    monkeypatch.setattr(engine_live.turncycle, "get_state", city_only_state)
    returned, snapshot = asyncio.run(_state(
        object(), "unitless-city", minimum_turn=25,
        require_decision_ready=True, stable_samples=1, timeout=0.2))
    assert returned is raw
    assert snapshot.turn == 25
    assert not snapshot.units and snapshot.cities
    assert _decision_state_ready(snapshot)
    assert not _player_eliminated(snapshot)
    assert not _player_eliminated(_ready_snapshot(
        include_units=False, include_cities=False, player_alive=True))


def test_packet_backed_elimination_overrides_stale_city_and_current_turn(monkeypatch):
    raw = _ready_raw(
        source_seq=54, include_units=False, include_cities=True, turn=54,
        player_alive=False)

    async def eliminated_state(_ws, _format):
        return raw

    monkeypatch.setattr(engine_live.turncycle, "get_state", eliminated_state)
    returned, snapshot = asyncio.run(_state(
        object(), "eliminated-player", minimum_turn=55,
        require_decision_ready=True, stable_samples=2, timeout=0.2))

    assert returned is raw
    assert snapshot.turn == 54
    assert snapshot.player_alive is False
    assert snapshot.cities and not snapshot.units
    assert _player_eliminated(snapshot)
    assert not _decision_state_ready(snapshot)


def test_missing_player_status_fails_closed_for_decisions():
    raw = _ready_raw()
    raw["authoritative"]["player"].pop("is_alive")
    snapshot = ProxyStateDTO.parse(
        "missing-player-status", 1, raw).to_snapshot()

    assert snapshot.player_alive is None
    assert not _player_eliminated(snapshot)
    assert not _decision_state_ready(snapshot)


def test_global_state_readiness_requires_both_authoritative_scores():
    state = {
        "units": {"1": {"id": 1}}, "techs": {"player0": []},
        "players": {
            "0": {"id": 0, "score": 4},
            "1": {"id": 1, "score": 3},
        },
    }
    assert _global_state_ready(state, player_id=0)
    state["players"]["1"].pop("score")
    assert not _global_state_ready(state, player_id=0)


def test_state_poll_enforces_the_callers_deadline(monkeypatch):
    async def blocked_state(_ws, _format):
        await asyncio.sleep(1.0)
        return None

    monkeypatch.setattr(engine_live.turncycle, "get_state", blocked_state)
    started = engine_live.time.monotonic()
    with pytest.raises(TimeoutError, match="did not reach turn"):
        asyncio.run(_state(object(), "deadline-test", timeout=0.05))
    assert engine_live.time.monotonic() - started < 0.5


def test_claim_eligible_arms_fail_closed_on_model_fallback():
    assert _claim_eligible_manifest({"impact_pair": {"claim_eligible": True}})
    assert _claim_eligible_manifest({"claim_eligible": True})
    assert not _claim_eligible_manifest({"impact_pair": {"claim_eligible": False}})


def test_live_model_lock_wait_is_inside_whole_turn_budget(monkeypatch):
    calls = []

    class ExhaustedLock:
        def acquire(self, timeout):
            calls.append(timeout)
            return False

        def release(self):
            raise AssertionError("an unacquired lock must not be released")

    monkeypatch.setattr(engine_live, "_MODEL_CACHE_LOCK", ExhaustedLock())
    manifest = {"model": "qwen3-coder-next:latest", "model_config": {
        "turn_timeout_seconds": 5, "temperature": 0}}
    with pytest.raises(RuntimeError, match="budget exhausted"):
        engine_live._ollama_json(manifest, "queued", ("selection",))
    assert calls == [3.0]


def test_engine_live_workers_are_bounded_to_dedicated_server_ports():
    runner = HarnessRunner("unused", backend="engine-live", workers=3)
    assert [runner._manifest(job, worker)["port"] for worker, job in enumerate([
        {"condition": "a_stock_llm", "seed": 1, "track": "main", "sequence": 0},
        {"condition": "a_stock_llm", "seed": 2, "track": "main", "sequence": 0},
        {"condition": "a_stock_llm", "seed": 3, "track": "main", "sequence": 0},
    ])] == [6001, 6002, 6003]
    with pytest.raises(ValueError, match="dedicated ports"):
        HarnessRunner("unused", backend="engine-live", workers=10)


def test_engine_live_workers_accept_explicit_noncontiguous_server_ports():
    runner = HarnessRunner(
        "unused", backend="engine-live", workers=3,
        server_ports=(6001, 6003, 6004))
    job = {"condition": "a_stock_llm", "seed": 1,
           "track": "main", "sequence": 0}
    assert [runner._manifest(job, worker)["port"] for worker in range(3)] == [
        6001, 6003, 6004]
    with pytest.raises(ValueError, match="dedicated ports"):
        HarnessRunner(
            "unused", backend="engine-live", workers=3,
            server_ports=(6001, 6001, 6003))
    with pytest.raises(ValueError, match="dedicated ports"):
        HarnessRunner(
            "unused", backend="engine-live", workers=3,
            server_ports=(6001, 6003))


def test_engine_live_clears_stale_proxy_game_before_server_recycle(monkeypatch):
    calls = []

    def terminate(game_id, token, required=False):
        calls.append(("terminate", game_id, token, required))

    def recycle(port):
        calls.append(("recycle", port))

    async def play(run_dir, manifest, context):
        calls.append(("play", run_dir, manifest["game_id"], context))
        return {"completed": True}

    monkeypatch.setattr(engine_live, "_terminate_proxy", terminate)
    monkeypatch.setattr(engine_live, "_recycle_server", recycle)
    monkeypatch.setattr(engine_live, "_ollama_readiness", lambda _manifest: None)
    monkeypatch.setattr(engine_live, "_play", play)
    context = object()
    result = engine_live.run_game(
        "/tmp/run", {"game_id": "release-retry", "port": 6001}, context)

    assert result == {"completed": True}
    assert calls == [
        ("terminate", "release-retry", "test-token-fc3d-001", True),
        ("recycle", 6001),
        ("play", "/tmp/run", "release-retry", context),
        ("terminate", "release-retry", "test-token-fc3d-001", False),
    ]


def test_accepted_unit_no_update_reaches_no_effect_accounting():
    raw = {"turn": 1}
    snapshot = object()
    parent = "accepted-result"

    class Candidate:
        unit_scope_consumed_on_accept = True

    async def no_update(current, cause):
        assert current is snapshot and cause == parent
        raise TimeoutError("authoritative state did not reach turn 1")

    result = asyncio.run(_refresh_accepted_impact_action(
        no_update, raw, snapshot, parent, Candidate()))

    assert result == (raw, snapshot, parent, False)


def test_accepted_non_unit_no_update_closes_as_bounded_no_effect():
    class Candidate:
        unit_scope_consumed_on_accept = False

    async def no_update(_current, _cause, timeout):
        assert timeout == 2.0
        raise TimeoutError("authoritative state did not reach turn 1")

    snapshot = object()
    assert asyncio.run(_refresh_accepted_impact_action(
        no_update, {}, snapshot, "accepted-result", Candidate(),
        refresh_timeout=2.0)) == (
            {}, snapshot, "accepted-result", False)


def test_accepted_impact_refresh_waits_for_candidate_specific_effect():
    snapshot = object()
    applied = object()
    seen = []

    async def refresh(current, cause, predicate, timeout):
        assert current is snapshot and cause == "accepted-result"
        assert timeout == 2.0
        seen.append(predicate(applied))
        return {"turn": 1}, applied, "effect-state"

    result = asyncio.run(_refresh_accepted_impact_action(
        refresh, {}, snapshot, "accepted-result", object(),
        refresh_timeout=2.0, effect_predicate=lambda value: value is applied))
    assert seen == [True]
    assert result == ({"turn": 1}, applied, "effect-state", True)


def test_state_poll_interval_is_bounded_before_transport():
    with pytest.raises(ValueError, match="poll_interval"):
        asyncio.run(_state(None, "game", poll_interval=0.01))
    with pytest.raises(ValueError, match="poll_interval"):
        asyncio.run(_state(None, "game", poll_interval=1.01))


def test_worker_assignment_does_not_change_behavioral_manifest_identity():
    runner = HarnessRunner("unused", backend="engine-live", workers=3)
    job = {"condition": "a_stock_llm", "seed": 104729,
           "track": "main", "sequence": 0}
    left = runner._manifest(job, 0)
    right = runner._manifest(job, 2)
    assert left["port"] != right["port"]
    assert left["manifest_identity"] == right["manifest_identity"]
    assert left["source"]["commit"]
    assert len(left["source"]["implementation_sha256"]) == 64
    assert left["source"]["source_files"] > 20


def test_total_controller_concurrency_changes_behavioral_manifest_identity():
    job = {"condition": "a_stock_llm", "seed": 104729,
           "track": "main", "sequence": 0}
    three = HarnessRunner("unused", backend="engine-live", workers=3)._manifest(job, 0)
    nine = HarnessRunner("unused", backend="engine-live", workers=9)._manifest(job, 0)
    assert three["controller_workers"] == 3
    assert nine["controller_workers"] == 9
    assert three["manifest_identity"] != nine["manifest_identity"]


def test_smoke_filters_use_a_seed_prefix_and_selected_condition_only():
    runner = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",))
    jobs = runner._jobs(include_induction=False, include_grading=False)
    assert jobs == [{
        "condition": "e_full_loop", "seed": runner.config["seeds"][0],
        "track": "main", "sequence": 0}]


def test_paired_impact_jobs_alternate_order_and_override_only_declared_policy():
    runner = HarnessRunner(
        "unused", seed_limit=3, conditions=("e_full_loop",))
    jobs = runner._impact_jobs()
    seeds = runner.config["paired_impact"]["cohorts"]["development"]["seeds"]
    assert [(row["seed"], row["policy_arm"]) for row in jobs] == [
        (seeds[0], "baseline"), (seeds[0], "treatment"),
        (seeds[1], "treatment"), (seeds[1], "baseline"),
        (seeds[2], "baseline"), (seeds[2], "treatment"),
    ]
    baseline = runner._manifest(jobs[0], 0)
    treatment = runner._manifest(jobs[1], 0)
    assert baseline["impact_pair"]["within_pair_order"] == 0
    assert baseline["impact_pair"]["cohort"] == "development"
    assert len(baseline["game_id"]) <= 50
    assert re.fullmatch(r"[A-Za-z0-9_-]+", baseline["game_id"])
    assert baseline["game_id"] != treatment["game_id"]
    assert treatment["impact_pair"]["within_pair_order"] == 1
    assert treatment["impact_outcomes"]["win_metric"] == "score_lead_turn_n"
    assert baseline["impact_policy"]["max_no_effect_failovers_per_scope"] == 0
    assert treatment["impact_policy"]["max_no_effect_failovers_per_scope"] == 4
    assert baseline["impact_policy"]["production_strategy"] == "static_priority"
    assert treatment["impact_policy"]["production_strategy"] == "horizon_score"
    assert baseline["manifest_identity"] != treatment["manifest_identity"]
    pilot = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="pilot")
    pilot_manifest = pilot._manifest(pilot._impact_jobs()[0], 0)
    assert pilot_manifest["impact_pair"]["seed_derivation"]["namespace"] == (
        "pln-freeciv-impact-pilot-v1")
    assert pilot_manifest["impact_pair"]["require_clean_source"] is True
    long_pilot = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="pilot_horizon_60_v3")
    long_manifest = long_pilot._manifest(long_pilot._impact_jobs()[0], 0)
    assert long_manifest["turn_limit"] == long_manifest["engine_max_turns"] == 60
    assert long_manifest["impact_policy"]["horizon_turn"] == 60
    assert long_manifest["impact_outcomes"]["horizon_turn"] == 60
    assert long_manifest["impact_pair"]["horizon_turn"] == 60
    current_pilot = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="pilot_horizon_60_v4")
    assert current_pilot._impact_jobs()[0]["seed"] == (
        current_pilot.config["paired_impact"]["cohorts"]
        ["pilot_horizon_60_v4"]["seeds"][0])
    confirmatory = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="confirmatory_score_horizon_60_v1")
    confirmatory_manifest = confirmatory._manifest(
        confirmatory._impact_jobs()[0], 0)
    assert confirmatory_manifest["turn_limit"] == 60
    assert confirmatory_manifest["impact_pair"]["score_design"] == {
        "minimum_detectable_delta": 0.2,
        "maximum_planning_sd": 1.0,
    }
    unitless_diagnostic = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="diagnostic_unitless_city_v1")
    diagnostic_manifest = unitless_diagnostic._manifest(
        unitless_diagnostic._impact_jobs()[0], 0)
    assert diagnostic_manifest["turn_limit"] == 30
    assert diagnostic_manifest["seed"] == 1905459
    assert diagnostic_manifest["impact_pair"]["claim_eligible"] is False
    terminal_diagnostic = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="diagnostic_terminal_elimination_v1", workers=2)
    terminal_manifest = terminal_diagnostic._manifest(
        terminal_diagnostic._impact_jobs()[0], 0)
    assert terminal_manifest["turn_limit"] == 60
    assert terminal_manifest["seed"] == 2119913
    assert terminal_manifest["impact_pair"]["cohort_purpose"] == "diagnostic"
    assert terminal_manifest["impact_pair"]["claim_eligible"] is False
    assert terminal_manifest["impact_outcomes"]["early_terminal_score"] == (
        "terminal_absorbing_score_carried_to_horizon")

    pressure_runner = HarnessRunner(
        "unused", seed_limit=1, conditions=("e_full_loop",),
        impact_cohort="pressure_ablation_pilot_v1")
    pressure_jobs = pressure_runner._impact_jobs()
    pressure_baseline = pressure_runner._manifest(pressure_jobs[0], 0)
    pressure_treatment = pressure_runner._manifest(pressure_jobs[1], 0)
    differing = sorted(
        key for key in pressure_baseline["impact_policy"]
        if pressure_baseline["impact_policy"][key]
        != pressure_treatment["impact_policy"][key])
    assert differing == [
        "pressure_enabled", "pressure_learning_enabled"]
    assert pressure_baseline["impact_policy"]["pressure_enabled"] is False
    assert pressure_baseline[
        "impact_policy"]["pressure_learning_enabled"] is False
    assert pressure_treatment["impact_policy"]["pressure_enabled"] is True
    assert pressure_treatment[
        "impact_policy"]["pressure_learning_enabled"] is True
    assert pressure_baseline["impact_pair"]["isolated_policy_keys"] == differing
    assert pressure_treatment["impact_pair"]["isolated_policy_keys"] == differing
    assert pressure_baseline["turn_limit"] == pressure_treatment[
        "turn_limit"] == 60


def test_parallel_impact_execution_keeps_each_pair_serial_on_one_worker(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, workers=3, seed_limit=6,
            conditions=("e_full_loop",))
        calls = []
        lock = runner._lock

        def run_one(indexed_job, resume, worker=None):
            _, job = indexed_job
            with lock:
                calls.append((len(calls), job["pair_index"],
                              job["within_pair_order"], job["policy_arm"], worker))
            return {"manifest": {}, "status": {"status": "completed"},
                    "resumed": False}

        monkeypatch.setattr(runner, "_run_one", run_one)
        summary = runner.run_impact_pairs(resume=False)

    assert summary["completed"] == summary["jobs"] == 12
    assert summary["controller_workers"] == 3
    for pair_index in range(6):
        rows = sorted((row for row in calls if row[1] == pair_index),
                      key=lambda row: row[0])
        assert [row[2] for row in rows] == [0, 1]
        assert {row[4] for row in rows} == {pair_index % 3}


def test_parallel_cohort_requires_predeclared_worker_count():
    runner = HarnessRunner(
        "unused", workers=1, conditions=("e_full_loop",),
        impact_cohort="diagnostic_terminal_elimination_v1")
    with pytest.raises(ValueError, match="requires controller_workers=2"):
        runner.run_impact_pairs(resume=False)


def test_arbitrary_declared_impact_cohorts_have_stable_safe_manifest_tokens():
    assert _impact_cohort_token("development") == "dev"
    token = _impact_cohort_token("population route/replay")
    assert token == _impact_cohort_token("population route/replay")
    assert token != _impact_cohort_token("population route replay")
    assert re.fullmatch(r"x[0-9a-f]{10}", token)


def test_pressure_ablation_pilot_runs_and_aggregates_as_an_isolated_pair(
        monkeypatch):
    clean_source = {
        "commit": "pressure-test-commit", "dirty": False,
        "implementation_sha256": "a" * 64, "source_files": 1,
    }
    monkeypatch.setattr(
        "freeciv.harness.runner._source_identity",
        lambda: dict(clean_source))
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",),
            impact_cohort="pressure_ablation_pilot_v1")
        summary = runner.run_impact_pairs(resume=False)
        aggregate = aggregate_impact_pairs(
            directory, cohort="pressure_ablation_pilot_v1")
        resumed = runner.run_impact_pairs(resume=True)
        replayed_aggregate = aggregate_impact_pairs(
            directory, cohort="pressure_ablation_pilot_v1")
    assert summary["completed"] == 2
    assert aggregate["complete_pairs"] == 1
    assert aggregate["design"]["claim_eligible"] is False
    assert aggregate["design"]["isolated_policy_keys"] == [
        "pressure_enabled", "pressure_learning_enabled"]
    assert aggregate["design"]["arms"] == {
        "baseline": {
            "pressure_enabled": False,
            "pressure_learning_enabled": False,
        },
        "treatment": {
            "pressure_enabled": True,
            "pressure_learning_enabled": True,
        },
    }
    assert aggregate["claim_evaluation"]["status"] == "ineligible"
    assert aggregate["source_freeze"]["passed"]
    assert resumed["resumed"] == 2
    assert canonical_json_bytes(replayed_aggregate) == canonical_json_bytes(
        aggregate)


def test_paired_impact_smoke_is_reproducible_and_reports_power_and_order():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=5, conditions=("e_full_loop",))
        summary = runner.run_impact_pairs(resume=False)
        assert summary["jobs"] == summary["completed"] == 10
        assert summary["pairs"] == 5 and summary["infrastructure_failures"] == 0
        aggregate = aggregate_impact_pairs(directory)
        assert aggregate["complete_pairs"] == aggregate["attempted_pairs"] == 5
        assert aggregate["primary_outcome"]["estimate"] == pytest.approx(2.0)
        assert aggregate["primary_outcome"]["n"] == 5
        assert aggregate["paired_deltas"]["decision_effect_observed_rate"][
            "estimate"] > 0
        assert aggregate["design"]["order_counts"] == {
            "baseline_first": 3, "treatment_first": 2}
        assert aggregate["design"]["order_violations"] == []
        assert aggregate["win_discordance"]["pairs"] == 5
        assert aggregate["win_rate_difference"]["n"] == 5
        assert aggregate["power_analysis"]["ready"] is False
        assert aggregate["power_analysis"]["required_pairs"] is None
        assert aggregate["win_power_analysis"]["target_met"] is True
        assert aggregate["claim_evaluation"]["status"] == "ineligible"
        assert aggregate["source_freeze"]["required"] is False
        assert aggregate["safety_gates"]["engine_rejected_action_rate"]["passed"]
        assert aggregate["safety_gates"]["model_safe_fallback_rate"]["passed"]
        assert aggregate["safety_gates"]["full_loop_under_30s_rate"]["passed"] is None
        assert aggregate["safety_gates"]["paired_initial_state_fidelity"] == {
            "evaluated": True, "mismatch_count": 0, "mismatch_seeds": [],
            "passed": True, "unavailable_seeds": [],
        }
        assert aggregate["safety_gates"]["overall_passed"]
        first = canonical_json_bytes(aggregate)
        assert first == canonical_json_bytes(aggregate_impact_pairs(directory))
        path = write_impact_report(directory, aggregate)
        assert open(path, "rb").read() == first + b"\n"
        report = open(os.path.join(
            directory, "impact-report.md"), encoding="utf-8").read()
        assert "Treatment minus baseline score" in report
        assert "score_margin_turn_n" in report
        assert "It is not labeled as an engine-reported terminal victory" in report
        assert "Overall status: `ineligible`" in report
        assert "must not be used to stop early" in report
        event_report = validate_file(os.path.join(
            directory, "impact-aggregate-events.jsonl"))
        assert event_report.valid, event_report.to_dict()


def test_pilot_and_confirmatory_cohorts_fail_closed_on_source_or_partial_run():
    with tempfile.TemporaryDirectory() as directory:
        pilot = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",),
            impact_cohort="pilot")
        dirty = dict(pilot.source_identity, commit="a" * 40, dirty=True)
        with mock.patch("freeciv.harness.runner._source_identity", return_value=dirty):
            with pytest.raises(RuntimeError, match="requires a clean source tree"):
                pilot.run_impact_pairs(resume=False)

        clean = dict(pilot.source_identity, commit="a" * 40, dirty=False)
        changed = dict(clean, implementation_sha256="b" * 64)
        with mock.patch(
                "freeciv.harness.runner._source_identity",
                side_effect=(clean, changed)):
            with pytest.raises(RuntimeError, match="source changed during execution"):
                pilot.run_impact_pairs(resume=False)
        assert json.load(open(os.path.join(
            directory, "impact-run-summary.json"), encoding="utf-8"))[
                "source_stable"] is False

        confirmatory = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",),
            impact_cohort="confirmatory_score_horizon_60_v1")
        with pytest.raises(ValueError, match="cannot use a pair limit"):
            confirmatory.run_impact_pairs(resume=False)


def test_complete_clean_score_cohort_is_the_only_claim_eligible_score_path():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, conditions=("e_full_loop",),
            impact_cohort="confirmatory_score_horizon_60_v1")
        clean = dict(runner.source_identity, commit="a" * 40, dirty=False)
        with mock.patch("freeciv.harness.runner._source_identity", return_value=clean):
            summary = runner.run_impact_pairs(resume=False)
        assert summary["completed"] == 400 and summary["claim_eligible"] is True
        aggregate = aggregate_impact_pairs(
            directory, cohort="confirmatory_score_horizon_60_v1")
        assert aggregate["complete_pairs"] == 200
        assert aggregate["source_freeze"]["passed"] is True
        assert aggregate["power_analysis"]["ready"] is True
        assert aggregate["power_analysis"]["minimum_detectable_delta"] == 0.2
        assert aggregate["claim_evaluation"]["score"]["status"] == "passed"
        assert aggregate["claim_evaluation"]["win_rate"]["status"] == "not_declared"
        assert aggregate["claim_evaluation"]["claimable"] == ["score_improvement"]


def test_joint_claims_are_hierarchical_and_require_score_gate_first():
    design = load()["paired_impact"]
    cohort = design["cohorts"]["confirmatory_joint"]
    safety = {"overall_passed": True}
    source = {"passed": True}
    power = {"ready": True}
    win = {"estimate": 0.12, "lower": 0.04, "upper": 0.20}
    discordance = {"exact_mcnemar_p": 0.03}
    score = {"estimate": 2.0, "lower": 0.5, "upper": 3.5}
    score_test = {"ready": True, "p_value": 0.01}
    meaningful_score_test = {
        "ready": True, "p_value": 0.50, "observed_mean_difference": 0.0}
    passed = _claim_evaluation(
        design, cohort, 450, [], [], [], safety, source,
        score, score_test, meaningful_score_test, win, discordance, power)
    assert passed["status"] == "claim_supported"
    assert passed["claimable"] == [
        "score_improvement", "fixed_horizon_score_lead_rate_improvement"]
    assert passed["score"]["interval_passed"] is True
    assert passed["score"]["randomization_passed"] is True

    score["lower"] = -0.1
    gated = _claim_evaluation(
        design, cohort, 450, [], [], [], safety, source,
        score, score_test, meaningful_score_test, win, discordance, power)
    assert gated["score"]["status"] == "failed"
    assert gated["win_rate"]["status"] == "gated"
    assert gated["claimable"] == [] and gated["status"] == "no_claim"

    score["lower"] = 0.5
    score_test["p_value"] = 0.08
    randomization_failed = _claim_evaluation(
        design, cohort, 450, [], [], [], safety, source,
        score, score_test, meaningful_score_test, win, discordance, power)
    assert randomization_failed["score"]["interval_passed"] is True
    assert randomization_failed["score"]["randomization_passed"] is False
    assert randomization_failed["score"]["status"] == "failed"
    assert randomization_failed["win_rate"]["status"] == "gated"

    score.update({"estimate": 3.0, "lower": 2.25, "upper": 3.75})
    score_test["p_value"] = 0.001
    meaningful_score_test["p_value"] = 0.02
    meaningful_score_test["observed_mean_difference"] = 1.0
    meaningful = _claim_evaluation(
        design, cohort, 450, [], [], [], safety, source,
        score, score_test, meaningful_score_test, win, discordance, power)
    assert meaningful["score"]["meaningful_passed"] is True
    assert meaningful["claimable"] == [
        "score_improvement", "meaningful_score_improvement",
        "fixed_horizon_score_lead_rate_improvement"]


def test_paired_impact_excludes_both_sides_of_incomplete_pair_and_retains_failure():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=2, conditions=("e_full_loop",))
        runner.run_impact_pairs(resume=False)
        seed = runner.config["paired_impact"]["cohorts"]["development"]["seeds"][0]
        status_path = os.path.join(
            directory, "games", "impact_pair", "development", "treatment", "e_full_loop",
            "{}-00".format(seed), "status.json")
        with open(status_path, "w", encoding="utf-8") as stream:
            json.dump({
                "completed": False, "error": "synthetic retained failure",
                "infrastructure_failure": True, "status": "infrastructure_failure",
            }, stream)
        aggregate = aggregate_impact_pairs(directory)
        assert aggregate["complete_pairs"] == 1
        assert aggregate["incomplete_pairs"] == [{
            "completed_arms": ["baseline"], "seed": seed}]
        assert aggregate["failures"][0]["error"] == "synthetic retained failure"
        assert aggregate["failures"][0]["historical"] is False
        assert aggregate["primary_outcome"]["n"] == 1


def test_paired_aggregate_fails_closed_on_initial_state_mismatch():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        runner.run_impact_pairs(resume=False)
        seed = runner.config["paired_impact"]["cohorts"]["development"]["seeds"][0]
        status_path = os.path.join(
            directory, "games", "impact_pair", "development", "treatment",
            "e_full_loop", "{}-00".format(seed), "status.json")
        status = json.load(open(status_path, encoding="utf-8"))
        status["initial_state_fingerprint"] = "f" * 64
        with open(status_path, "w", encoding="utf-8") as stream:
            json.dump(status, stream)

        aggregate = aggregate_impact_pairs(directory)
        fidelity = aggregate["safety_gates"]["paired_initial_state_fidelity"]
        assert fidelity["passed"] is False
        assert fidelity["mismatch_seeds"] == [seed]
        assert aggregate["safety_gates"]["overall_passed"] is False


def test_paired_aggregate_rejects_manifest_from_another_configuration():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        runner.run_impact_pairs(resume=False)
        seed = runner.config["paired_impact"]["cohorts"]["development"]["seeds"][0]
        manifest_path = os.path.join(
            directory, "games", "impact_pair", "development", "baseline",
            "e_full_loop", "{}-00".format(seed), "manifest.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        manifest["configuration_hash"] = "0" * 64
        with open(manifest_path, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream)
        with pytest.raises(ValueError, match="belongs to another configuration"):
            aggregate_impact_pairs(directory)


def test_paired_impact_resume_archives_failed_attempt_after_successful_retry():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        runner.run_impact_pairs(resume=True)
        seed = runner.config["paired_impact"]["cohorts"]["development"]["seeds"][0]
        run_dir = os.path.join(
            directory, "games", "impact_pair", "development", "treatment", "e_full_loop",
            "{}-00".format(seed))
        status_path = os.path.join(run_dir, "status.json")
        with open(status_path, "w", encoding="utf-8") as stream:
            json.dump({
                "completed": False, "error": "first attempt failed",
                "infrastructure_failure": True, "status": "infrastructure_failure",
            }, stream)
        with open(os.path.join(
                run_dir, "pressure-conductance.json"),
                "w", encoding="utf-8") as stream:
            json.dump({"attempt": "first"}, stream)

        summary = runner.run_impact_pairs(resume=True)
        assert summary["completed"] == 2 and summary["resumed"] == 1
        aggregate = aggregate_impact_pairs(directory)
        assert aggregate["complete_pairs"] == 1
        assert aggregate["incomplete_pairs"] == []
        assert len(aggregate["failures"]) == 1
        failure = aggregate["failures"][0]
        assert failure["historical"] is True
        assert failure["error"] == "first attempt failed"
        assert failure["attempt_id"]
        history = os.path.join(directory, "attempt-history")
        assert any("events.jsonl" in files for _, _, files in os.walk(history))
        assert any(
            "pressure-conductance.json" in files
            for _, _, files in os.walk(history))
        assert not os.path.exists(os.path.join(
            run_dir, "pressure-conductance.json"))


def test_induction_memory_is_condition_isolated():
    run_dir = os.path.join(
        "out", "games", "induction", "d_uncertain_monitor", "104729-01")
    left = _opponent_memory_path(run_dir, "d_uncertain_monitor")
    right = _opponent_memory_path(run_dir, "e_full_loop")
    assert left != right
    assert left.endswith(os.path.join("opponent-memory", "d_uncertain_monitor.json"))
    assert right.endswith(os.path.join("opponent-memory", "e_full_loop.json"))


def test_partial_smoke_aggregate_report_marks_unrun_conditions_na():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        summary = runner.run(
            resume=False, include_induction=False, include_grading=False)
        assert summary["jobs"] == summary["completed"] == 1
        aggregate = aggregate_runs(directory)
        write_report(directory, aggregate)
        report = open(os.path.join(directory, "report.md"), encoding="utf-8").read()
        assert "| a_stock_llm | 0 | 0 | n/a (n=0) | n/a (n=0) |" in report
        assert "| e_full_loop | 1 |" in report


def test_calibration_is_pooled_bucketed_and_reports_insufficient_samples():
    rows = [{
        "manifest": {"condition_id": "d_uncertain_monitor"},
        "calibration": ([{"atom_id": "a{}".format(index), "opponent": "fixed",
                          "strength": 0.95, "truth": 1} for index in range(10)]
                        + [{"atom_id": "b{}".format(index), "opponent": "fixed",
                            "strength": 0.15, "truth": 0} for index in range(3)]),
    }]
    report = _calibration_report(rows)
    assert report["pooled"]["samples"] == 13
    low, high = report["pooled"]["buckets"]
    assert low["bucket"] == "0.1" and low["within_tolerance"] is None
    assert high["bucket"] == "0.9" and high["samples"] == 10
    assert high["absolute_error"] == pytest.approx(0.05)
    assert high["within_tolerance"] is True
    assert report["per_opponent"]["fixed"] == report["pooled"]


def test_full_250_run_matrix_aggregates_byte_identically_and_preserves_fidelity():
    with tempfile.TemporaryDirectory() as directory:
        summary = HarnessRunner(directory, workers=4).run(resume=False)
        assert summary["jobs"] == summary["completed"] == 250
        assert summary["infrastructure_failures"] == 0
        aggregate = aggregate_runs(directory)
        assert all(row["completed_games"] == 30 for row in aggregate["conditions"].values())
        assert aggregate["grading_ab"]["games_per_arm"] == 30
        assert aggregate["induction"]["d_uncertain_monitor"]["games"] == 20
        assert aggregate["induction"]["e_full_loop"]["games"] == 20
        assert aggregate["induction"]["oracle_vs_induction"]["prediction_assumed"] is False
        assert aggregate["calibration"]["pooled"]["samples"] == 60
        assert aggregate["calibration"]["per_opponent"][
            "builtin-ai-experimental"]["samples"] == 60
        assert any(result["estimate"] is not None and result["estimate"] < 0
                   for metrics in aggregate["marginal_deltas"].values()
                   for result in metrics.values())
        first = canonical_json_bytes(aggregate)
        second = canonical_json_bytes(aggregate_runs(directory))
        assert first == second
        path = write_report(directory, aggregate)
        assert open(path, "rb").read() == first + b"\n"
        event_report = validate_file(os.path.join(directory, "aggregate-events.jsonl"))
        assert event_report.valid, event_report.to_dict()
        schema = json.load(open(os.path.join(
            REPO, "schemas", "freeciv-harness", "v1", "aggregate.schema.json"), encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(aggregate)


def test_resume_skips_valid_completed_games_without_double_applying_events():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory, workers=4)
        first = runner.run(resume=True, include_induction=False, include_grading=False)
        second = runner.run(resume=True, include_induction=False, include_grading=False)
        assert first["completed"] == second["completed"] == 150
        assert second["resumed"] == 150


def test_resume_never_reuses_a_completed_game_from_another_configuration():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory)
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        first = runner._run_one((0, job), resume=True)
        first_identity = first["manifest"]["manifest_identity"]
        runner.config["turn_limit"] += 1
        runner.config["configuration_hash"] = structural_hash(runner.config)
        second = runner._run_one((0, job), resume=True)
        assert not first["resumed"] and not second["resumed"]
        assert second["manifest"]["manifest_identity"] != first_identity


def test_game_manifest_records_source_rulebase_schema_and_wall_clock():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        result = runner._run_one((0, job), resume=False)
        manifest = json.load(open(os.path.join(
            result["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        assert manifest["events_schema_version"] == "1.0"
        assert manifest["source"]["commit"]
        assert len(manifest["source"]["implementation_sha256"]) == 64
        assert manifest["rulebase"] == runner.config["rulebase"]
        assert manifest["runtime"]["started_at"].endswith("Z")
        assert manifest["runtime"]["ended_at"].endswith("Z")
        assert len(manifest["attempt_id"]) == 16


def test_retry_keeps_behavior_identity_but_rotates_proxy_attempt_identity():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(directory)
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        first = runner._run_one((0, job), resume=False)
        first_manifest = json.load(open(os.path.join(
            first["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        second = runner._run_one((0, job), resume=False)
        second_manifest = json.load(open(os.path.join(
            second["manifest"]["_run_dir"], "manifest.json"), encoding="utf-8"))
        assert first_manifest["manifest_identity"] == second_manifest["manifest_identity"]
        assert first_manifest["attempt_id"] != second_manifest["attempt_id"]


def test_rerun_replaces_stale_completed_status_before_backend_execution():
    with tempfile.TemporaryDirectory() as directory:
        runner = HarnessRunner(
            directory, seed_limit=1, conditions=("e_full_loop",))
        job = runner._jobs(include_induction=False, include_grading=False)[0]
        manifest = runner._manifest(job, 0)
        run_dir = manifest["_run_dir"]
        os.makedirs(run_dir, exist_ok=True)
        status_path = os.path.join(run_dir, "status.json")
        with open(status_path, "w", encoding="utf-8") as stream:
            json.dump({"status": "completed", "completed": True}, stream)

        observed = {}

        def backend(_run_dir, _manifest, _context):
            observed.update(json.load(open(status_path, encoding="utf-8")))
            EventWriter(
                os.path.join(_run_dir, "events.jsonl"),
                _manifest["game_id"], durable=False,
            ).emit("run_started", 0, {
                "condition_id": _manifest["condition_id"],
                "manifest_identity": _manifest["manifest_identity"],
            })
            return {"completed": True, "infrastructure_failure": False}

        with mock.patch("freeciv.harness.runner.representative_game", backend):
            result = runner._run_one((0, job), resume=False)
        assert result["status"]["status"] == "completed"
        assert observed == {
            "status": "running", "completed": False,
            "infrastructure_failure": False,
            "manifest_identity": manifest["manifest_identity"],
        }
