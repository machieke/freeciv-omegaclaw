import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRIPTS = os.path.join(REPO, "scripts", "freeciv")
for path in (SRC, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from evaluate_fdas_path_persistence_relevance import (  # noqa: E402
    _paired_summary,
    _route_outcome,
    _select_control,
)


MOVE = "fdas-shadow:city-garrison-deficit:unit_move"
FORTIFY = "fdas-shadow:unit-fortification-opportunity:unit_fortify"


def _readout(route, rank, reachability, operation_type=MOVE,
             probe_member=False):
    return {
        "baseline_rank": rank,
        "instantaneous_reachability": reachability,
        "operation_id": "operation-{}".format(route),
        "operation_type": operation_type,
        "probe_member": probe_member,
        "route_id": "fdas-path-corridor:{}".format(route),
    }


def test_relevance_control_prefers_action_matched_nearest_route():
    rows = [
        _readout("scalar", 1, 1.0, probe_member=True),
        _readout("treatment", 3, 0.51),
        _readout("different-action", 4, 0.51, FORTIFY),
        _readout("matched", 5, 0.49),
    ]

    control = _select_control(rows, "fdas-path-corridor:treatment")

    assert control["route_id"] == "fdas-path-corridor:matched"


def test_relevance_outcome_tracks_probe_scalar_expiry_and_censoring():
    route = "fdas-path-corridor:treatment"
    rows = [{"readouts": [_readout("treatment", 2, 0.5)]}, {
        "readouts": [_readout(
            "treatment", 2, 0.6, probe_member=True)],
    }, {
        "readouts": [_readout(
            "treatment", 1, 0.8, probe_member=True)],
    }, {"readouts": []}]

    outcome = _route_outcome(rows, 0, route, 8)

    assert outcome == {
        "expiry_delay_decisions": None,
        "horizon_censored": False,
        "probe_delay_decisions": 1,
        "probe_reentry_observed": True,
        "probe_reentry": True,
        "scalar_delay_decisions": 2,
        "scalar_winner_observed": True,
        "scalar_winner": True,
    }
    expired = _route_outcome(rows, 2, route, 8)
    assert expired["expiry_delay_decisions"] == 1
    assert expired["probe_reentry_observed"] is True
    assert expired["probe_reentry"] is False


def test_relevance_paired_summary_preserves_discordant_direction():
    def outcome(value):
        return {
            "probe_reentry": value,
            "probe_reentry_observed": True,
        }
    pairs = [{
        "treatment_outcome": outcome(True),
        "control_outcome": outcome(False),
    }, {
        "treatment_outcome": outcome(False),
        "control_outcome": outcome(True),
    }, {
        "treatment_outcome": outcome(False),
        "control_outcome": outcome(True),
    }]

    summary = _paired_summary(pairs, "probe_reentry")

    assert summary["positive_discordant"] == 1
    assert summary["negative_discordant"] == 2
    assert summary["paired_rate_delta"] == -1.0 / 3.0
    assert summary["exact_two_sided_sign_p"] == 1.0
