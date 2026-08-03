import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from audit_fdas_scalar_baseline_grounding_diagnostic import (  # noqa: E402
    _reason_summary,
)


def _event(reason, component="fdas-scalar-baseline-candidate-readout"):
    return {
        "payload": {
            "component_id": component,
            "details": {"reason": reason},
        },
        "type": "atomspace_shadow_decision",
    }


def test_grounding_diagnostic_counts_only_scalar_baseline_reasons(tmp_path):
    game = os.path.join(
        str(tmp_path), "games", "main", "e_full_loop", "109021-00")
    os.makedirs(game)
    with open(os.path.join(game, "events.jsonl"), "w",
              encoding="utf-8") as stream:
        for event in (
                _event("control-bounded-validator-route-unavailable"),
                _event("no-protected-alternative"),
                _event(
                    "ignored",
                    component="fdas-decision-safe-candidate-readout")):
            stream.write(json.dumps(event) + "\n")

    assert _reason_summary(str(tmp_path)) == {
        "control-bounded-validator-route-unavailable": 1,
        "no-protected-alternative": 1,
    }
