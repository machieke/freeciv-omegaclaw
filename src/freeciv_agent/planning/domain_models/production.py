"""Grounded current-step city-production transition estimates.

The model deliberately separates the exact queue-selection action from the
future completion of the selected item.  Freeciv advertises the former in the
legal-action set.  The latter depends on future city output and, after a
switch, production-history fields that are not present in the version-1
snapshot contract.
"""

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


def _quantity(rule, name, default=None):
    value = getattr(
        rule, "quantitative", {}).get(
        name, default)
    if isinstance(value, dict):
        value = value.get(
            "value", default)
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


@dataclass(frozen=True)
class ProductionTargetProfile:
    """Compiler-backed cost, upkeep, and capability data for one target."""

    target_name: str
    target_kind: str
    rule_id: str
    build_cost: int
    population_cost: int
    food_upkeep: int
    shield_upkeep: int
    gold_upkeep: int
    happiness_cost: int
    building_upkeep: int
    unit_class: object
    flags: tuple
    roles: tuple

    @property
    def is_unit(self):
        return self.target_kind == "unit"

    def to_dict(self):
        return {
            "build_cost": int(
                self.build_cost),
            "building_upkeep": int(
                self.building_upkeep),
            "flags": list(
                self.flags),
            "gold_upkeep": int(
                self.gold_upkeep),
            "happiness_cost": int(
                self.happiness_cost),
            "is_unit": bool(
                self.is_unit),
            "population_cost": int(
                self.population_cost),
            "roles": list(
                self.roles),
            "rule_id": self.rule_id,
            "shield_upkeep": int(
                self.shield_upkeep),
            "food_upkeep": int(
                self.food_upkeep),
            "target_kind":
                self.target_kind,
            "target_name":
                self.target_name,
            "unit_class":
                self.unit_class,
        }


def production_target_profile(
        ruleset_ir, target_name):
    """Return one unambiguous compiler-backed production profile."""
    target = _normalized(
        target_name)
    if not target:
        return None
    matches = []
    for rule in getattr(
            ruleset_ir, "rules", ()):
        if getattr(
                rule, "target_kind",
                None) not in (
                    "unit", "building",
                    "improvement"):
            continue
        labels = {
            _normalized(getattr(
                rule, "display_name", "")),
            _normalized(getattr(
                rule, "rule_name", "")),
        }
        if target not in labels:
            continue
        build_cost = _quantity(
            rule, "build_cost")
        if (
                build_cost is None
                or build_cost <= 0
        ):
            return None
        target_kind = str(
            getattr(
                rule, "target_kind"))
        classes = _trait_values(
            rule, "class")
        if (
                target_kind == "unit"
                and len(classes) != 1
        ):
            return None
        values = {}
        for name in (
                "pop_cost", "uk_food",
                "uk_shield", "uk_gold",
                "happy_cost", "upkeep"):
            value = _quantity(
                rule, name, 0)
            if value is None:
                return None
            values[name] = value
        matches.append(
            ProductionTargetProfile(
                target_name=str(
                    getattr(
                        rule,
                        "display_name",
                        target_name)),
                target_kind=target_kind,
                rule_id=str(
                    getattr(
                        rule, "rule_id",
                        "unknown")),
                build_cost=build_cost,
                population_cost=values[
                    "pop_cost"],
                food_upkeep=values[
                    "uk_food"],
                shield_upkeep=values[
                    "uk_shield"],
                gold_upkeep=values[
                    "uk_gold"],
                happiness_cost=values[
                    "happy_cost"],
                building_upkeep=values[
                    "upkeep"],
                unit_class=(
                    classes[0]
                    if classes else None),
                flags=_trait_values(
                    rule, "flags"),
                roles=_trait_values(
                    rule, "roles")))
    if len(matches) != 1:
        return None
    return matches[0]


def _turns_at_constant_rate(
        build_cost, retained_stock,
        shield_rate):
    if retained_stock >= build_cost:
        return 1
    if shield_rate <= 0:
        return None
    return int(math.ceil(
        float(
            build_cost
            - retained_stock)
        / float(shield_rate)))


class GroundedProductionTransitionModel:
    """Model an advertised queue selection without inventing a built asset."""

    model_id = (
        "grounded_city_production_queue")
    model_version = "1.0"
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(
                request,
                DomainEstimateRequest)
            and request.action_type
                == "city_production")

    def _abstain(
            self, request, reason_code,
            missing_fields=(),
            artifact_extra=None):
        artifact = {
            "availability": {
                "product_available_now":
                    False,
                "queueable_now": None,
                "requires_completion_observation":
                    True,
            },
            "city_id": (
                request.legal_action.get(
                    "city_id")
                if isinstance(
                    request.legal_action,
                    dict) else None),
            "completion_eta": None,
            "legal_action": (
                dict(request.legal_action)
                if isinstance(
                    request.legal_action,
                    dict) else None),
            "missing_fields": list(
                sorted(set(
                    missing_fields))),
            "reason_code": reason_code,
            "schema_version": "1.0",
            "supported_subset":
                "advertised-buildable-current-city-queue-selection",
            "switch_cost": None,
            "target_profile": None,
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
                    "production:unsupported"),
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
                "missing-grounded-production-input",
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
                "unsupported-action-type",
                ("action_type",))
        action = request.legal_action
        snapshot = request.snapshot
        target = action.get(
            "target")
        city_id = action.get(
            "city_id")
        target_name = (
            target.get(
                "production_type")
            if isinstance(
                target, dict)
            else None)
        production_kind = action.get(
            "production_kind")
        production_value = action.get(
            "production_value")
        missing = []
        advertised = (
            canonical_json_bytes(
                action).decode("utf-8")
            in set(getattr(
                snapshot,
                "legal_action_json", ())))
        if not advertised:
            missing.append(
                "advertised_legal_action")
        if (
                isinstance(city_id, bool)
                or not isinstance(
                    city_id, int)
        ):
            missing.append("city_id")
        city = (
            snapshot.city(city_id)
            if (
                not isinstance(
                    city_id, bool)
                and isinstance(
                    city_id, int)
                and callable(getattr(
                    snapshot,
                    "city", None)))
            else None)
        if city is None:
            missing.append("city")
        elif city.owner != getattr(
                snapshot, "player_id",
                city.owner):
            missing.append(
                "owned_city")
        if not isinstance(
                target_name, str
                ) or not target_name:
            missing.append(
                "target.production_type")
        for value, name in (
                (production_kind,
                 "production_kind"),
                (production_value,
                 "production_value")):
            if (
                    isinstance(value, bool)
                    or not isinstance(
                        value, int)
                    or value < 0
            ):
                missing.append(name)
        profile = (
            production_target_profile(
                request.ruleset_ir,
                target_name)
            if isinstance(
                target_name, str)
            and target_name else None)
        if profile is None:
            missing.append(
                "unambiguous_ruleset_target")
        buildable_match = None
        if city is not None:
            if city.buildability_available is not True:
                missing.append(
                    "city_buildability")
            elif (
                    isinstance(
                        production_value,
                        int)
                    and not isinstance(
                        production_value,
                        bool)
                    and isinstance(
                        target_name, str)
            ):
                matches = tuple(
                    row for row
                    in city.buildable
                    if (
                        int(row[1])
                            == production_value
                        and _normalized(
                            row[2])
                            == _normalized(
                                target_name)))
                if len(matches) == 1:
                    buildable_match = (
                        matches[0])
                else:
                    missing.append(
                        "exact_buildable_target")
        if (
                buildable_match is not None
                and profile is not None
        ):
            buildable_kind = (
                buildable_match[0])
            kind_matches = bool(
                (
                    buildable_kind
                        == "unit"
                    and profile.target_kind
                        == "unit")
                or (
                    buildable_kind
                        == "improvement"
                    and profile.target_kind
                        in (
                            "building",
                            "improvement")))
            if not kind_matches:
                missing.append(
                    "buildability_ruleset_kind_parity")
        if city is not None:
            for value, name in (
                    (city.production_kind,
                     "city.production_kind"),
                    (city.production_value,
                     "city.production_value"),
                    (city.shield_stock,
                     "city.shield_stock")):
                if (
                        isinstance(value, bool)
                        or not isinstance(
                            value, int)
                        or value < 0
                ):
                    missing.append(name)
            if (
                    not isinstance(
                        city.surplus,
                        tuple)
                    or len(city.surplus)
                        <= 1
                    or isinstance(
                        city.surplus[1],
                        bool)
                    or not isinstance(
                        city.surplus[1],
                        (int, float))
                    or not math.isfinite(
                        float(
                            city.surplus[1]))
                    or int(
                        city.surplus[1])
                        != city.surplus[1]
            ):
                missing.append(
                    "city.shield_surplus")
        if missing:
            return self._abstain(
                request,
                "production-input-missing",
                tuple(missing),
                artifact_extra={
                    "availability": {
                        "product_available_now":
                            False,
                        "queueable_now": (
                            True
                            if advertised
                            else False),
                        "requires_completion_observation":
                            True,
                    },
                    "target_profile": (
                        None if profile
                        is None else
                        profile.to_dict()),
                })

        current_turn = int(
            snapshot.turn)
        stock = int(
            city.shield_stock)
        shield_rate = int(
            city.surplus[1])
        build_cost = int(
            profile.build_cost)
        same_target = bool(
            city.production_kind
                == production_kind
            and city.production_value
                == production_value)
        if same_target:
            earliest_eta = (
                _turns_at_constant_rate(
                    build_cost, stock,
                    shield_rate))
            latest_eta = earliest_eta
            switch_cost = {
                "history_fields_available":
                    True,
                "observed_stock_at_risk":
                    0,
                "reason":
                    "target-already-current",
                "retained_shields_lower":
                    stock,
                "retained_shields_upper":
                    stock,
                "status": "none",
            }
            eta_status = (
                "current-target-constant-rate"
                if earliest_eta is not None
                else
                "stalled-current-output")
        else:
            # The v1 city snapshot omits before_change_shields,
            # changed_from, last_turns_shield_surplus, caravan_shields, and
            # disbanded_shields.  They are all read by
            # city_change_production_penalty().  Zero retained shields gives
            # a conservative latest completion under a fixed current rate;
            # an earliest completion of one turn permits an unobserved
            # restoration when switching back to the original class.
            earliest_eta = 1
            latest_eta = (
                _turns_at_constant_rate(
                    build_cost, 0,
                    shield_rate))
            switch_cost = {
                "history_fields_available":
                    False,
                "missing_history_fields": [
                    "before_change_shields",
                    "caravan_shields",
                    "changed_from",
                    "disbanded_shields",
                    "last_turns_shield_surplus",
                ],
                "observed_stock_at_risk":
                    stock,
                "reason":
                    "freeciv-switch-penalty-history-not-in-snapshot-v1",
                "retained_shields_lower":
                    0,
                "retained_shields_upper":
                    None,
                "status": "unresolved",
            }
            eta_status = (
                "switch-interval-constant-rate"
                if latest_eta is not None
                else
                "switch-latest-stalled-current-output")
        earliest_turn = (
            current_turn
            + earliest_eta
            if earliest_eta
            is not None else None)
        latest_turn = (
            current_turn
            + latest_eta
            if latest_eta
            is not None else None)
        horizon = int(
            request.horizon_turn)
        possible_by_horizon = bool(
            earliest_turn is not None
            and earliest_turn <= horizon)
        guaranteed_by_horizon = bool(
            latest_turn is not None
            and latest_turn <= horizon)
        completion_eta = {
            "assumptions": [
                "current-shield-surplus-remains-constant",
                "no-buy-disband-caravan-or-worklist-intervention",
                "server-city-turn-production-order",
            ],
            "earliest_completion_turn":
                earliest_turn,
            "earliest_turns":
                earliest_eta,
            "guaranteed_by_request_horizon":
                guaranteed_by_horizon,
            "latest_completion_turn":
                latest_turn,
            "latest_turns":
                latest_eta,
            "possible_by_request_horizon":
                possible_by_horizon,
            "projection_authority":
                "deterministic-current-rate-bound",
            "request_horizon_turn":
                horizon,
            "status": eta_status,
        }
        artifact = {
            "availability": {
                "product_available_now":
                    False,
                "queueable_now": True,
                "requires_completion_observation":
                    True,
                "unit_under_construction_is_participant":
                    False,
            },
            "buildability": {
                "option_id":
                    buildable_match[1],
                "option_kind":
                    buildable_match[0],
                "option_name":
                    buildable_match[2],
                "source":
                    "authoritative-city-buildability",
            },
            "city_id": city_id,
            "city_name": city.name,
            "completion_eta":
                completion_eta,
            "current_production": {
                "production_kind":
                    city.production_kind,
                "production_value":
                    city.production_value,
                "same_target":
                    same_target,
                "shield_stock": stock,
                "shield_surplus_per_turn":
                    shield_rate,
            },
            "downstream_operation": {
                "goal_ids": [
                    goal_id for
                    goal_id, _ in
                    request.goal_losses],
                "product_identity_created":
                    False,
                "requires_separate_completion_observation":
                    True,
            },
            "legal_action":
                dict(action),
            "missing_fields": [],
            "reason_code": None,
            "schema_version": "1.0",
            "supported_subset":
                "advertised-buildable-current-city-queue-selection",
            "switch_cost":
                switch_cost,
            "target_profile":
                profile.to_dict(),
            "unknown_mass": 0.0,
            "upkeep_timing": (
                "only-after-observed-completion"),
        }
        outcome = PredictedOutcome(
            outcome_id="{}:queue-selected".format(
                request
                .stable_operation_id),
            probability=1.0,
            next_truth_summaries=(),
            # Selecting the queue does not itself relieve the downstream
            # goal.  Completion is an independently observed lifecycle step.
            next_goal_features=tuple(
                request.goal_losses),
            resource_delta=(
                (
                    "city_production_slot:city:{}".format(
                        city_id),
                    -1.0),
            ),
            completion_turn=float(
                current_turn),
            adverse_loss=0.0,
            provenance=(
                "server-advertised-action",
                "authoritative-city-buildability",
                "compiled-ruleset-cost-and-upkeep",
                "queue-selection-not-product-completion",
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
                    "production:{}:{}".format(
                        profile.target_kind,
                        "retain"
                        if same_target
                        else "switch")),
                residual_goal_losses=(
                    residual_losses(
                        request))),
            context_key=(
                context_key_for_request(
                    request)),
            authority=(
                EstimateAuthority
                .DETERMINISTIC_DERIVED),
            confidence=1.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "authoritative-city-buildability",
                "compiled-ruleset-production-profile",
                "freeciv-production-queue-semantics",
            ),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))
