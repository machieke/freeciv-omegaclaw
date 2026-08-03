import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_scalar_baseline_pair_scope_diagnostic import (  # noqa: E402
    _pair_scope_summary,
)


def _event(rejected):
    return {
        "type": "atomspace_shadow_decision",
        "payload": {
            "component_id": "fdas-scalar-baseline-candidate-readout",
            "details": {"rejected": rejected},
        },
    }


def _run(tmp_path, events):
    event_path = (tmp_path / "games" / "main" / "e_full_loop"
                  / "1-00" / "events.jsonl")
    event_path.parent.mkdir(parents=True)
    event_path.write_text(
        "".join(json.dumps(value) + "\n" for value in events),
        encoding="utf-8")
    return str(tmp_path)


def test_pair_scope_summary_exposes_exact_resource_overlap(tmp_path):
    run_root = _run(tmp_path, (_event([
        "operation-a:pair-scope:identical-resource-set",
        "operation-a:pair-scope:resource-overlap:unit-action:7",
    ]),))

    summary = _pair_scope_summary(run_root)

    assert summary == {
        "affected_readouts": 1,
        "exact_reason_counts": {
            "identical-resource-set": 1,
            "resource-overlap:unit-action:7": 1,
        },
        "exact_rejections": 2,
        "generic_rejections": 0,
        "malformed_exact_rejections": 0,
        "resource_overlap_rejections": 1,
    }


def test_pair_scope_summary_preserves_generic_and_malformed_counts(tmp_path):
    run_root = _run(tmp_path, (
        _event(["operation-a:pair-scope-mismatch"]),
        _event(["operation-b:pair-scope:unknown-scope"]),
    ))

    summary = _pair_scope_summary(run_root)

    assert summary["affected_readouts"] == 2
    assert summary["generic_rejections"] == 1
    assert summary["exact_rejections"] == 1
    assert summary["malformed_exact_rejections"] == 1
