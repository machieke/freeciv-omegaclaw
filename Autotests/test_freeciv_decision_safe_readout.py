"""Protected bridge/probe candidate-union contracts."""

import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.flow_control import (  # noqa: E402
    DecisionSafeCandidateSelector,
)


def test_protected_union_cannot_exclude_scalar_terminal_or_safety():
    selection = DecisionSafeCandidateSelector().select(
        scalar_ranked_operation_ids=("scalar", "second", "last"),
        all_operation_ids=(
            "scalar", "second", "last",
            "bridge", "terminal", "safety"),
        bridge_operation_ids=("bridge",),
        terminal_operation_ids=("terminal",),
        safety_operation_ids=("safety",),
        scalar_top_k=2)

    assert selection.operation_ids == (
        "scalar", "second", "bridge",
        "safety", "terminal")
    assert selection.members[0].reasons == (
        "scalar-top-k", "scalar-winner")
    assert selection.terminal_protected_operation_ids == (
        "terminal",)
    assert selection.safety_protected_operation_ids == (
        "safety",)
    assert selection.bridge_added_operation_ids == (
        "bridge",)


def test_bridge_order_or_duplicate_paths_cannot_change_final_union_order():
    selector = DecisionSafeCandidateSelector()
    arguments = {
        "scalar_ranked_operation_ids": ("a", "b", "c"),
        "all_operation_ids": ("a", "b", "c", "x", "y"),
        "scalar_top_k": 1,
        "readout_policy": "corrected-probe-union",
    }

    first = selector.select(
        bridge_operation_ids=("x", "y"),
        **arguments)
    duplicated = selector.select(
        bridge_operation_ids=("y", "x", "x", "y"),
        **arguments)

    assert first.operation_ids == duplicated.operation_ids
    assert first.operation_ids[0] == "a"
    uses = first.signal_ledger.to_dict()["uses"]
    assert not any(
        row["signal_name"] in (
            "bridge_height",
            "corrected_probe_weight",
            "raw_probe_count")
        and row["used_in_final_score"]
        for row in uses)
