#!/usr/bin/env python3
"""Run the deterministic GDO-7B research decision-safety diagnostic."""

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from types import SimpleNamespace


REPO = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import ImpactCandidate  # noqa: E402
from freeciv_agent.planning.domain_models import (  # noqa: E402
    DomainEstimateRequest,
    EstimateAuthority,
    EstimateValidity,
    GroundedResearchTransitionModel,
)
from freeciv_agent.rulesets.ir import Requirement, Rule  # noqa: E402
from freeciv_agent.state import ResearchOptionState, ResearchState  # noqa: E402


def _requirement(name):
    return Requirement(
        "Tech", name, "Player", True,
        "symbolic", "has-tech",
        ("$player", name),
        {
            "file": "synthetic/techs.ruleset",
            "field": "reqs", "line": 1,
            "section": "advance_{}".format(name.lower()),
        })


def _rule(name, prerequisite=None):
    return Rule(
        "synthetic:tech:{}".format(name),
        "tech", name, name,
        "researchable", ("$player", name),
        (() if prerequisite is None
         else (_requirement(prerequisite),)),
        (), {"cost": {"value": 20}}, False,
        {
            "file": "synthetic/techs.ruleset",
            "field": "name", "line": 1,
            "section": "advance_{}".format(name.lower()),
        })


def _action(name):
    return {
        "action_type": "tech_research",
        "actor_id": 0,
        "target": {"tech_name": name},
    }


def _case(case_index):
    length = 3 + case_index % 4
    known_count = case_index % length
    names = tuple(
        "Case{:02d}Tech{}".format(case_index, index)
        for index in range(length))
    distractors = (
        "Case{:02d}DistractorA".format(case_index),
        "Case{:02d}DistractorB".format(case_index),
    )
    rules = []
    for index, name in enumerate(names):
        rules.append(_rule(
            name,
            None if index == 0 else names[index - 1]))
    rules.extend(_rule(name) for name in distractors)
    immediate = names[known_count]
    strategic = names[-1]
    advertised = (immediate,) + distractors
    actions = tuple(_action(name) for name in advertised)
    options = tuple(
        ResearchOptionState(
            tech_name=name,
            tech_id=index,
            tech_cost=20 + index * 3,
            action_json=canonical_json_bytes(
                action).decode("utf-8"))
        for index, (name, action) in enumerate(
            zip(advertised, actions)))
    option_by_name = {
        option.tech_name: option
        for option in options}
    switch = case_index % 2 == 1
    current = distractors[0] if switch else immediate
    rate = 0 if case_index % 10 == 0 else 5
    progress = case_index % 9
    snapshot_id = "research-case-{:02d}".format(case_index)
    legal_digest = hashlib.sha256(
        "\n".join(sorted(
            option.action_json
            for option in options)).encode("utf-8")
    ).hexdigest()
    snapshot = SimpleNamespace(
        player_id=0,
        turn=40 + case_index,
        snapshot_id=snapshot_id,
        legal_actions_digest=legal_digest,
        legal_action_json=tuple(sorted(
            option.action_json
            for option in options)),
        research=ResearchState(
            known_techs=names[:known_count],
            target_id=99,
            target_name=current,
            progress=progress,
            cost=30,
            beakers_per_turn=rate,
            available=True),
        research_option=lambda name: option_by_name.get(name))
    return {
        "actions": actions,
        "immediate": immediate,
        "ruleset": SimpleNamespace(rules=tuple(rules)),
        "snapshot": snapshot,
        "strategic": strategic,
        "switch": switch,
    }


def _estimate(case, action):
    snapshot = case["snapshot"]
    request = DomainEstimateRequest(
        request_id=hashlib.sha256(
            canonical_json_bytes({
                "action": action,
                "snapshot_id": snapshot.snapshot_id,
                "strategic": case["strategic"],
            })).hexdigest(),
        snapshot=snapshot,
        ruleset_ir=case["ruleset"],
        legal_action=action,
        candidate=ImpactCandidate(
            action=action,
            category="research_strategy",
            utility=1.0,
            rationale="GDO-7B diagnostic",
            projection={
                "strategic_target_tech":
                    case["strategic"],
            }),
        goal_losses=(("pf-impact:science", 3.0),),
        operation_context=None,
        validity=EstimateValidity(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            "synthetic-ruleset",
            snapshot.turn,
            snapshot.turn),
        horizon_turn=snapshot.turn + 50)
    return GroundedResearchTransitionModel().estimate(request)


def run(case_count=60, repeat_count=10):
    cases = tuple(_case(index) for index in range(case_count))
    latencies = []
    rows = []
    for case in cases:
        for action in case["actions"]:
            started = time.perf_counter()
            estimate = _estimate(case, action)
            latencies.append(
                (time.perf_counter() - started) * 1000.0)
            artifact = estimate.to_dict().get(
                "model_artifact", {})
            selected = (
                estimate.authority
                != EstimateAuthority.ABSTAIN)
            correct = (
                action["target"]["tech_name"]
                == case["immediate"])
            rows.append({
                "admitted": selected,
                "correct_frontier_action": correct,
                "legacy_tech_want_applied": (
                    (artifact.get(
                        "dependency_profile") or {})
                    .get("legacy_tech_want_applied")),
                "research_switch_status": (
                    (artifact.get(
                        "research_switch_cost") or {})
                    .get("status")),
                "technology_known_now": (
                    artifact.get(
                        "availability", {})
                    .get("technology_known_now")),
            })
    admitted = tuple(row for row in rows if row["admitted"])
    correct = tuple(
        row for row in rows
        if row["correct_frontier_action"])
    semantic = {
        "case_count": case_count,
        "candidate_count": len(rows),
        "grounded": {
            "admitted_candidate_count": len(admitted),
            "false_admission_count": sum(
                not row["correct_frontier_action"]
                for row in admitted),
            "frontier_recall": (
                sum(row["admitted"] for row in correct)
                / float(len(correct))),
            "precision": (
                sum(row["correct_frontier_action"]
                    for row in admitted)
                / float(len(admitted))),
            "switch_history_unresolved_count": sum(
                row["research_switch_status"] == "unresolved"
                for row in admitted),
            "technology_known_now_claim_count": sum(
                row["technology_known_now"] is True
                for row in admitted),
            "legacy_tech_want_application_count": sum(
                row["legacy_tech_want_applied"] is True
                for row in admitted),
        },
        "immediate_simpler_baseline": {
            "description":
                "admit every server-advertised research action",
            "admitted_candidate_count": len(rows),
            "false_admission_count": sum(
                not row["correct_frontier_action"]
                for row in rows),
            "frontier_recall": 1.0,
            "precision": (
                sum(row["correct_frontier_action"]
                    for row in rows)
                / float(len(rows))),
        },
        "mechanism_gate": {
            "decision_safe_candidate_precision_improved": bool(
                len(admitted)
                and all(
                    row["correct_frontier_action"]
                    for row in admitted)
                and len(admitted) < len(rows)),
            "frontier_recall_preserved": bool(
                len(correct)
                and all(row["admitted"] for row in correct)),
            "no_immediate_completion_claims": bool(
                not any(
                    row["technology_known_now"] is True
                    for row in admitted)),
            "single_propagation_mode": bool(
                not any(
                    row["legacy_tech_want_applied"] is True
                    for row in admitted)),
        },
    }
    hashes = []
    for _ in range(repeat_count):
        repeat_rows = []
        for case in cases:
            for action in case["actions"]:
                value = _estimate(case, action).to_dict()
                repeat_rows.append(value)
        hashes.append(structural_hash(repeat_rows))
    ordered = sorted(latencies)
    p95_index = max(
        0, int(math.ceil(0.95 * len(ordered))) - 1)
    return {
        "diagnostic": "gdo7b-grounded-research",
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "p95": ordered[p95_index],
            "sample_count": len(latencies),
        },
        "repeatability": {
            "deterministic": len(set(hashes)) == 1,
            "repeat_count": repeat_count,
            "semantic_report_hash": structural_hash(semantic),
            "estimate_set_hash": hashes[0],
        },
        "schema_version": "1.0",
        "semantic_results": semantic,
        "scope": {
            "engine_backed": False,
            "policy_authority": False,
            "score_claim": False,
            "synthetic_graph_regime": True,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=os.path.join(
            REPO, "benchmarks", "gdo",
            "gdo7b_research_grounding_diagnostic.json"))
    parser.add_argument("--cases", type=int, default=60)
    parser.add_argument("--repeats", type=int, default=10)
    arguments = parser.parse_args()
    result = run(arguments.cases, arguments.repeats)
    os.makedirs(
        os.path.dirname(
            os.path.abspath(arguments.output)),
        exist_ok=True)
    with open(
            arguments.output, "w",
            encoding="utf-8") as stream:
        json.dump(
            result, stream, ensure_ascii=False,
            sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": os.path.abspath(arguments.output),
        "repeatable": result["repeatability"]["deterministic"],
        "semantic_report_hash":
            result["repeatability"]["semantic_report_hash"],
        "mechanism_gate":
            result["semantic_results"]["mechanism_gate"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
