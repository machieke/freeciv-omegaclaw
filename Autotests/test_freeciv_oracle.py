"""M1 crisp dependency service, proof, failure, and native-parity tests."""

import os
import sys
import tempfile
from types import SimpleNamespace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.events.writer import EventWriter  # noqa: E402
from freeciv_agent.oracle import (CrispStateView, DependencyOracle, Goal,  # noqa: E402
                                  NativeResearchOracle, compare_all)
from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.rulesets.ir import Requirement, Rule  # noqa: E402


def _external_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(REPO, "..", "..", "..", "Repos",
                                                   "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for oracle integration tests")


def _requirement(name):
    return Requirement("Tech", name, "Player", True, "symbolic", "has-tech",
                       ("$player", name),
                       {"file": "synthetic/techs.ruleset", "field": "reqs",
                        "line": 1, "section": "advance_" + name.lower()})


def _rule(name, requirements=(), suffix="one", disabled=False):
    return Rule(
        "synthetic:tech:{}:{}".format(name, suffix), "tech", name, name,
        "researchable", ("$player", name), tuple(_requirement(req) for req in requirements),
        tuple(), {}, disabled,
        {"file": "synthetic/techs.ruleset", "field": "name", "line": 1,
         "section": "advance_" + name.lower()},
    )


def _oracle(*rules):
    return DependencyOracle(SimpleNamespace(rules=rules))


def test_diamond_proof_reuses_shared_subproof_and_preserves_both_parent_paths():
    oracle = _oracle(_rule("A", ("B", "C")), _rule("B", ("D",)),
                     _rule("C", ("D",)), _rule("D"))
    result = oracle.deps(Goal.researchable("p", "A"), CrispStateView("s"))
    assert result.status == "BLOCKED"
    d_nodes = [node for node in result.proof["nodes"]
               if node["atom"]["predicate"] == "has-tech" and node["atom"]["args"][-1] == "D"]
    assert len(d_nodes) == 1
    d_id = d_nodes[0]["node_id"]
    assert sum(d_id in node["premise_node_refs"] for node in result.proof["nodes"]) == 2


def test_or_graph_preserves_all_alternatives_with_deterministic_order():
    oracle = _oracle(_rule("A", ("B",), "path-b"), _rule("A", ("C",), "path-c"),
                     _rule("B"), _rule("C"))
    first = oracle.deps(Goal.researchable("p", "A"), CrispStateView("s1"))
    second = oracle.deps(Goal.researchable("p", "A"), CrispStateView("s2"))
    assert any(node["kind"] == "or" and len(node["premise_node_refs"]) == 2
               for node in first.proof["nodes"])
    assert first.proof == second.proof


def test_active_path_cycle_and_disabled_goal_are_typed_unreachable():
    cyclic = _oracle(_rule("A", ("B",)), _rule("B", ("A",))).deps(
        Goal.researchable("p", "A"), CrispStateView("cycle"))
    assert cyclic.status == "UNREACHABLE"
    assert any(item["blocker_type"] == "cycle" for item in cyclic.frontier)
    disabled = _oracle(_rule("Never", disabled=True)).deps(
        Goal.researchable("p", "Never"), CrispStateView("disabled"))
    assert disabled.status == "UNREACHABLE"
    assert disabled.frontier[0]["blocker_type"] == "disabled-goal"


def test_known_facts_replace_missing_frontier_and_crisp_tv_never_drifts():
    oracle = _oracle(_rule("A", ("B",)), _rule("B"))
    blocked = oracle.deps(Goal.researchable("p", "A"), CrispStateView("s1"))
    proved = oracle.deps(Goal.researchable("p", "A"),
                         CrispStateView("s2", known_techs=("B",), player="p"))
    assert blocked.status == "BLOCKED" and proved.status == "PROVED"
    for result in (blocked, proved):
        assert all(node["tv"] == {"strength": 1.0, "confidence": 0.99}
                   and node["atom"]["tv"] == {"strength": 1.0, "confidence": 0.99}
                   for node in result.proof["nodes"])


def test_timeout_and_closed_service_return_structured_error_and_block_execution():
    timeout = _oracle(_rule("A")).deps(
        Goal.researchable("p", "A"), CrispStateView("timeout"), timeout_ms=0)
    assert timeout.status == "ERROR" and timeout.error["code"] == "ORACLE_TIMEOUT"
    assert not timeout.executable
    oracle = _oracle(_rule("A"))
    oracle.close()
    closed = oracle.deps(Goal.researchable("p", "A"), CrispStateView("closed"))
    assert closed.status == "ERROR" and closed.error["code"] == "ORACLE_CLOSED"
    assert not closed.executable


def test_real_query_emits_lossless_schema_valid_causal_events_and_cache_hit():
    ir = compile_ruleset(_external_root(), "civ2civ3")
    oracle = DependencyOracle(ir)
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "events.jsonl")
        writer = EventWriter(path, "oracle-test", durable=False)
        root = writer.emit("run_started", 0, {"condition_id": "test", "manifest_identity": "m"})
        result, query_event, result_event = oracle.emit_deps(
            Goal.researchable("p", "Environmentalism"), CrispStateView("snapshot"),
            writer, 0, caused_by=[root["event_id"]], invoking_layer="test")
        cached = oracle.deps(Goal.researchable("p", "Environmentalism"),
                             CrispStateView("snapshot"))
        oracle.close()
        failed, _, failed_event = oracle.emit_deps(
            Goal.researchable("p", "Alphabet"), CrispStateView("after-close"),
            writer, 0, caused_by=[result_event["event_id"]], invoking_layer="test")
        report = validate_file(path)
    assert report.valid, report.to_dict()
    assert result_event["caused_by"] == [query_event["event_id"]]
    assert result.chain_depth >= 10 and cached.cache_status == "hit"
    assert any(node.get("rule_source") for node in result.proof["nodes"])
    assert failed.status == "ERROR" and failed_event["payload"]["error"]["code"] == "ORACLE_CLOSED"
    assert not failed.executable


def test_native_adapter_calls_freeciv_functions_and_small_end_to_end_parity():
    source = open(os.path.join(REPO, "scripts", "freeciv", "native", "research_parity.c"),
                  encoding="utf-8").read()
    for function in ("research_goal_step", "research_goal_unknown_techs",
                     "research_goal_tech_req"):
        assert function + "(" in source
    native = NativeResearchOracle()
    try:
        native.image_identity()
    except Exception as exc:
        pytest.skip(str(exc))
    ir = compile_ruleset(_external_root(), "classic")
    report = compare_all(ir, DependencyOracle(ir), native, state_count=3)
    assert report["passed"], report["mismatches"][:1]
