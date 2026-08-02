"""Grounded current-step embark and disembark transition estimates."""

import math
import re
from dataclasses import dataclass

from ...events.schema import canonical_json_bytes
from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from .base import DomainEstimateRequest
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    canonical_model_artifact,
)
from .registry import context_key_for_request, residual_losses


def _normalized(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


def _trait_values(rule, name):
    value = getattr(
        rule, "traits", {}).get(
            name, {})
    if not isinstance(value, dict):
        return ()
    rows = value.get(
        "values", ())
    if not isinstance(
            rows, (list, tuple)):
        return ()
    return tuple(sorted({
        str(row)
        for row in rows
        if isinstance(row, str)
        and row
    }))


def _quantitative_integer(rule, name):
    value = getattr(
        rule, "quantitative", {}).get(
            name)
    if isinstance(value, dict):
        value = value.get("value")
    if (
            isinstance(value, bool)
            or not isinstance(
                value, (int, float))
            or not math.isfinite(
                float(value))
            or int(value) != value
            or int(value) < 0
    ):
        return None
    return int(value)


@dataclass(frozen=True)
class TransportUnitProfile:
    """Ruleset-grounded unit class, cargo, and founder capabilities."""

    unit_type: str
    unit_class: str
    transport_capacity: int
    cargo_classes: tuple
    founder_capable: bool

    def to_dict(self):
        return {
            "cargo_classes": list(
                self.cargo_classes),
            "founder_capable": bool(
                self.founder_capable),
            "transport_capacity": int(
                self.transport_capacity),
            "unit_class": self.unit_class,
            "unit_type": self.unit_type,
        }


def transport_unit_profile(
        ruleset_ir, unit_type):
    """Return one unambiguous compiler-backed unit profile or ``None``."""
    target = _normalized(
        unit_type)
    if not target:
        return None
    matches = []
    for rule in getattr(
            ruleset_ir, "rules", ()):
        if getattr(
                rule, "target_kind",
                None) != "unit":
            continue
        labels = {
            _normalized(getattr(
                rule, "display_name", "")),
            _normalized(getattr(
                rule, "rule_name", "")),
        }
        if target not in labels:
            continue
        classes = _trait_values(
            rule, "class")
        capacity = _quantitative_integer(
            rule, "transport_cap")
        if capacity is None:
            capacity = _quantitative_integer(
                rule, "transport_capacity")
        if (
                len(classes) != 1
                or capacity is None
        ):
            return None
        flags = _trait_values(
            rule, "flags")
        matches.append(
            TransportUnitProfile(
                unit_type=str(
                    getattr(
                        rule,
                        "display_name",
                        unit_type)),
                unit_class=classes[0],
                transport_capacity=capacity,
                cargo_classes=_trait_values(
                    rule, "cargo"),
                founder_capable=(
                    "Cities" in flags)))
    if len(matches) != 1:
        return None
    return matches[0]


class GroundedTransportTransitionModel:
    """Model only advertised current-step movement across a known carrier."""

    model_id = (
        "grounded_current_transport")
    model_version = "1.0"
    immutable_request_safe = True

    def supports(self, request):
        if (
                not isinstance(
                    request,
                    DomainEstimateRequest)
                or request.action_type
                    != "unit_move"
        ):
            return False
        action = request.legal_action
        actor_id = action.get(
            "actor_id") if isinstance(
                action, dict) else None
        actor = (
            request.snapshot.unit(
                actor_id)
            if callable(getattr(
                request.snapshot,
                "unit", None))
            else None)
        return bool(
            isinstance(action, dict)
            and (
                action.get(
                    "transport_required")
                is True
                or (
                    actor is not None
                    and actor.transported
                    is True)))

    def _abstain(
            self, request, reason_code,
            missing_fields=(),
            artifact_extra=None):
        artifact = {
            "carrier_id": None,
            "carrier_profile": None,
            "founder_capable": None,
            "legal_action": dict(
                request.legal_action)
            if isinstance(
                request.legal_action,
                dict) else None,
            "missing_fields": list(
                sorted(set(
                    missing_fields))),
            "mode": None,
            "reason_code": reason_code,
            "schema_version": "1.0",
            "seat_capacity_after": None,
            "seat_capacity_before": None,
            "supported_subset":
                "advertised-current-step-unique-visible-carrier",
            "unknown_mass": 1.0,
        }
        artifact.update(
            artifact_extra or {})
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request
                    .stable_operation_id),
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "transport:unsupported"),
                residual_goal_losses=(
                    residual_losses(
                        request))),
            context_key=(
                context_key_for_request(
                    request)),
            authority=(
                EstimateAuthority.ABSTAIN),
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "missing-grounded-transport-input",
            ),
            abstention_reason=(
                reason_code),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))

    def estimate(self, request):
        if not self.supports(
                request):
            return self._abstain(
                request,
                "transport-context-not-active",
                ("transport_context",))
        action = request.legal_action
        snapshot = request.snapshot
        advertised = (
            canonical_json_bytes(
                action).decode("utf-8")
            in set(getattr(
                snapshot,
                "legal_action_json", ())))
        actor_id = action.get(
            "actor_id")
        actor = snapshot.unit(
            actor_id)
        target = action.get(
            "target")
        missing = []
        if not advertised:
            missing.append(
                "advertised_legal_action")
        if actor is None:
            missing.append("actor")
        if (
                not isinstance(
                    target, dict)
                or isinstance(
                    target.get("x"), bool)
                or not isinstance(
                    target.get("x"), int)
                or isinstance(
                    target.get("y"), bool)
                or not isinstance(
                    target.get("y"), int)
        ):
            missing.append(
                "target_position")
        movement_cost = action.get(
            "movement_cost")
        if (
                isinstance(
                    movement_cost, bool)
                or not isinstance(
                    movement_cost,
                    (int, float))
                or not math.isfinite(
                    float(movement_cost))
                or float(movement_cost)
                    <= 0.0
        ):
            missing.append(
                "authoritative_movement_cost")
        if actor is not None:
            if actor.activity != "idle":
                missing.append(
                    "actor_idle_activity")
            if actor.done_moving is not False:
                missing.append(
                    "actor_done_moving_state")
            if actor.moves_left is None:
                missing.append(
                    "moves_left")
            elif (
                    movement_cost is not None
                    and isinstance(
                        movement_cost,
                        (int, float))
                    and not isinstance(
                        movement_cost, bool)
                    and float(movement_cost)
                        > actor.moves_left
            ):
                return self._abstain(
                    request,
                    "transport-cost-exceeds-available")
        if missing:
            return self._abstain(
                request,
                "transport-input-missing",
                missing)

        target_tile = (
            int(target["x"])
            + int(target["y"])
            * int(snapshot.map_width))
        if target_tile not in set(
                snapshot.visible_tile_ids):
            return self._abstain(
                request,
                "transport-target-not-visible",
                ("visible_target",))
        if any(
                unit.tile == target_tile
                for unit in
                snapshot.visible_enemy_units):
            return self._abstain(
                request,
                "transport-target-enemy-occupied")

        actor_profile = (
            transport_unit_profile(
                request.ruleset_ir,
                actor.unit_type))
        if actor_profile is None:
            return self._abstain(
                request,
                "transport-actor-rules-missing",
                ("actor_unit_profile",))

        mode = None
        carrier = None
        carrier_profile = None
        seats_before = None
        seats_after = None
        if action.get(
                "transport_required") is True:
            if actor.transported is not False:
                return self._abstain(
                    request,
                    "transport-embark-state-ambiguous",
                    ("actor_transport_state",))
            compatible = []
            for unit in snapshot.units:
                if unit.tile != target_tile:
                    continue
                profile = (
                    transport_unit_profile(
                        request.ruleset_ir,
                        unit.unit_type))
                if (
                        profile is None
                        or profile
                        .transport_capacity
                        <= 0
                        or actor_profile
                        .unit_class
                        not in profile
                        .cargo_classes
                        or unit.cargo_count
                        is None
                        or unit.cargo_count < 0
                        or unit.cargo_count
                        >= profile
                        .transport_capacity
                ):
                    continue
                compatible.append((
                    unit, profile))
            if len(compatible) != 1:
                return self._abstain(
                    request,
                    "transport-compatible-carrier-not-unique",
                    artifact_extra={
                        "compatible_carrier_ids": [
                            row[0].unit_id
                            for row in compatible
                        ],
                        "mode": "embark",
                    })
            carrier, carrier_profile = (
                compatible[0])
            seats_before = (
                carrier_profile
                .transport_capacity
                - carrier.cargo_count)
            seats_after = seats_before - 1
            mode = "embark"
            seat_delta = -1.0
        else:
            carrier_id = actor.transported_by
            if (
                    actor.transported is not True
                    or isinstance(
                        carrier_id, bool)
                    or not isinstance(
                        carrier_id, int)
                    or carrier_id <= 0
            ):
                return self._abstain(
                    request,
                    "transport-carrier-identity-missing",
                    ("transported_by",))
            carrier = snapshot.unit(
                carrier_id)
            if (
                    carrier is None
                    or carrier.tile
                        != actor.tile
            ):
                return self._abstain(
                    request,
                    "transport-carrier-state-mismatch")
            carrier_profile = (
                transport_unit_profile(
                    request.ruleset_ir,
                    carrier.unit_type))
            if (
                    carrier_profile is None
                    or carrier_profile
                    .transport_capacity <= 0
                    or actor_profile
                    .unit_class
                    not in carrier_profile
                    .cargo_classes
                    or carrier.cargo_count
                    is None
                    or carrier.cargo_count <= 0
            ):
                return self._abstain(
                    request,
                    "transport-carrier-rules-or-load-mismatch")
            seats_before = (
                carrier_profile
                .transport_capacity
                - carrier.cargo_count)
            seats_after = seats_before + 1
            mode = "disembark"
            seat_delta = 1.0

        movement_cost = float(
            movement_cost)
        artifact = {
            "carrier_id": (
                carrier.unit_id),
            "carrier_profile": (
                carrier_profile
                .to_dict()),
            "founder_capable": (
                actor_profile
                .founder_capable),
            "legal_action": dict(action),
            "missing_fields": [],
            "mode": mode,
            "reason_code": None,
            "schema_version": "1.0",
            "seat_capacity_after":
                seats_after,
            "seat_capacity_before":
                seats_before,
            "supported_subset":
                "advertised-current-step-unique-visible-carrier",
            "unknown_mass": 0.0,
        }
        goal_features = tuple(sorted(
            (goal_id, float(loss))
            for goal_id, loss in
            request.goal_losses))
        outcome = PredictedOutcome(
            outcome_id="{}:{}".format(
                request.stable_operation_id,
                mode),
            probability=1.0,
            next_truth_summaries=(),
            next_goal_features=(
                goal_features),
            resource_delta=(
                ("movement_points",
                 -movement_cost),
                (
                    "transport_seat:unit:{}"
                    .format(
                        carrier.unit_id),
                    seat_delta),
            ),
            completion_turn=float(
                snapshot.turn),
            adverse_loss=0.0,
            provenance=(
                "server-advertised-action",
                "authoritative-carrier-identity",
                "authoritative-cargo-count",
                "compiled-transport-capacity-and-cargo-class",
            ))
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request
                    .stable_operation_id),
                outcomes=(outcome,),
                residual_probability=0.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "transport:{}".format(
                        mode)),
                residual_goal_losses=(
                    residual_losses(
                        request))),
            context_key=(
                context_key_for_request(
                    request)),
            authority=(
                EstimateAuthority
                .EXACT_AUTHORITATIVE),
            confidence=1.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "authoritative-current-transport-state",
                "compiled-ruleset-transport-profile",
            ),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))
