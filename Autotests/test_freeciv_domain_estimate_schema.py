"""Grounded transition authority, validity, and event-schema contracts."""

import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.planning.domain_models import (  # noqa: E402
    EstimateAuthority,
    EstimateValidity,
    GroundedTransitionEstimate,
    TransitionContextKey,
)
from freeciv_agent.pressure import ExpectedTransition  # noqa: E402


def _context(ruleset_digest="ruleset"):
    return TransitionContextKey(
        schema_version=1,
        action_category="tactical_attack",
        action_type="unit_attack",
        goal_id="survival",
        lifecycle_state="immediate",
        actor_class="riflemen",
        target_class="warriors",
        threat_regime="visible",
        terrain_bucket="plains",
        horizon_bucket="near",
        ruleset_digest=ruleset_digest)


def _validity(ruleset_digest="ruleset"):
    return EstimateValidity(
        snapshot_id="game:4:7:abc",
        legal_actions_digest="legal",
        ruleset_digest=ruleset_digest,
        estimated_at_turn=4,
        valid_through_turn=4)


def test_legacy_proxy_is_explicit_and_never_live_eligible():
    estimate = GroundedTransitionEstimate(
        transition=ExpectedTransition(
            "operation", (), 1.0, "legacy/1.0", "legacy",
            residual_goal_losses=(("*", 1.0),)),
        context_key=_context(),
        authority=EstimateAuthority.LEGACY_PROXY,
        confidence=0.0,
        validity=_validity(),
        estimator_id="legacy",
        estimator_version="1.0",
        provenance=("legacy-proxy",))

    assert estimate.to_dict()["authority"] == "legacy_proxy"
    assert not estimate.live_eligible(
        "game:4:7:abc", "legal", "ruleset", 4)


def test_validity_fails_closed_on_snapshot_legal_ruleset_or_turn_change():
    validity = _validity()

    assert validity.matches(
        "game:4:7:abc", "legal", "ruleset", 4)
    assert not validity.matches(
        "game:4:8:def", "legal", "ruleset", 4)
    assert not validity.matches(
        "game:4:7:abc", "changed", "ruleset", 4)
    assert not validity.matches(
        "game:4:7:abc", "legal", "changed", 4)
    assert not validity.matches(
        "game:4:7:abc", "legal", "ruleset", 5)


def test_abstention_requires_reason_and_exact_authority_rejects_unknown_mass():
    transition = ExpectedTransition(
        "operation", (), 1.0, "model", "group",
        residual_goal_losses=(("*", 1.0),))
    with pytest.raises(ValueError, match="abstention requires"):
        GroundedTransitionEstimate(
            transition, _context(),
            EstimateAuthority.ABSTAIN, 0.0, _validity(),
            "model", "1.0", ("test",))
    with pytest.raises(ValueError, match="cannot retain unknown"):
        GroundedTransitionEstimate(
            transition, _context(),
            EstimateAuthority.EXACT_AUTHORITATIVE,
            1.0, _validity(),
            "model", "1.0", ("test",))


def test_context_and_validity_ruleset_must_agree():
    with pytest.raises(ValueError, match="ruleset digests"):
        GroundedTransitionEstimate(
            ExpectedTransition(
                "operation", (), 1.0, "model", "group",
                residual_goal_losses=(("*", 1.0),)),
            _context("one"),
            EstimateAuthority.HEURISTIC,
            0.5,
            _validity("two"),
            "model", "1.0", ("test",))
