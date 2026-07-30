"""Grounded combat estimates with strict contextual abstention."""

import math
import re

from ...events.schema import canonical_json_bytes
from ...pressure.transitions import ExpectedTransition, PredictedOutcome
from .base import DomainEstimateRequest
from .combat_rules import finite_duel_distribution
from .context import (
    EstimateAuthority,
    GroundedTransitionEstimate,
    canonical_model_artifact,
)
from .registry import context_key_for_request, residual_losses


_COMBAT_ACTION_TYPES = frozenset((
    "unit_attack",
    "unit_bombard",
    "unit_capture",
    "unit_conquer_city",
    "unit_suicide_attack",
    "unit_wipe",
))


def _normalized_type(value):
    return re.sub(
        r"[^a-z0-9]+", "",
        str(value or "").lower())


def _quantity(rule, name):
    value = getattr(
        rule, "quantitative", {}).get(name)
    if isinstance(value, dict):
        value = value.get("value")
    if (isinstance(value, bool)
            or not isinstance(value, (int, float))):
        return None
    value = float(value)
    return value if math.isfinite(
        value) else None


def _unit_spec(ruleset_ir, unit_type):
    target = _normalized_type(
        unit_type)
    matches = []
    for rule in getattr(
            ruleset_ir, "rules", ()):
        if getattr(
                rule, "target_kind", None) != "unit":
            continue
        labels = {
            _normalized_type(getattr(
                rule, "display_name", "")),
            _normalized_type(getattr(
                rule, "rule_name", "")),
        }
        if target in labels:
            matches.append(rule)
    if len(matches) != 1:
        return None
    rule = matches[0]
    values = {
        name: _quantity(rule, name)
        for name in (
            "attack", "defense", "hitpoints",
            "firepower", "build_cost")
    }
    if any(value is None for value in values.values()):
        return None
    values["rule_id"] = getattr(
        rule, "rule_id", "unknown")
    return values


class GroundedCombatTransitionModel:
    """Prefer native odds, with a clean-room duel as a narrow fallback."""

    model_id = "grounded_combat_transition"
    model_version = "2.0"
    immutable_request_safe = True

    def supports(self, request):
        return (
            isinstance(request, DomainEstimateRequest)
            and request.action_type
            in _COMBAT_ACTION_TYPES)

    @staticmethod
    def _target_units(request):
        action = request.legal_action
        target = action.get("target")
        if not isinstance(target, dict):
            return ()
        target_id = target.get(
            "target_unit_id",
            action.get("target_id"))
        snapshot = request.snapshot
        if target_id is not None:
            target_unit = (
                snapshot.visible_enemy_unit(
                    target_id)
                if callable(getattr(
                    snapshot,
                    "visible_enemy_unit",
                    None))
                else None)
            return (() if target_unit is None
                    else (target_unit,))
        x = target.get("x")
        y = target.get("y")
        if x is None or y is None:
            return ()
        return tuple(sorted(
            (
                unit for unit in getattr(
                    snapshot,
                    "visible_enemy_units", ())
                if (unit.x, unit.y)
                == (x, y)
            ),
            key=lambda unit: unit.unit_id))

    def _abstain(
            self, request, reason_code,
            missing_fields, target_ids=()):
        artifact = {
            "adverse_loss_distribution": [],
            "city_capture_probability": None,
            "expected_enemy_shield_equivalent_loss":
                None,
            "expected_friendly_shield_equivalent_loss":
                None,
            "immediate_goal_feature_deltas": {},
            "missing_fields": list(sorted(
                set(missing_fields))),
            "parity_status": "unverified",
            "post_action_exposure": {
                "status": "not-modeled",
            },
            "probability_attacker_survives": None,
            "probability_target_destroyed": None,
            "reason_code": reason_code,
            "residual_unknown_mass": 1.0,
            "schema_version": "1.0",
            "supported_subset":
                "explicit-unmodified-one-versus-one",
            "target_unit_ids": [
                int(value)
                for value in target_ids],
        }
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request.stable_operation_id),
                outcomes=(),
                residual_probability=1.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "combat:unsupported"),
                residual_goal_losses=(
                    residual_losses(request))),
            context_key=context_key_for_request(
                request),
            authority=EstimateAuthority.ABSTAIN,
            confidence=0.0,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "missing-grounded-combat-input",
            ),
            abstention_reason=reason_code,
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))

    def _native_estimate(
            self, request, attacker,
            target_tile, specified_target_id):
        snapshot = request.snapshot
        result = (
            snapshot.combat_probability(
                attacker.unit_id,
                target_tile)
            if callable(getattr(
                snapshot,
                "combat_probability",
                None))
            else None)
        if result is None:
            return None
        selected_target_id = (
            result.target_unit_id)
        if (
            selected_target_id == 0
            or (
                specified_target_id
                is not None
                and int(specified_target_id)
                    != selected_target_id)
        ):
            return None
        defender = (
            snapshot.visible_enemy_unit(
                selected_target_id)
            if callable(getattr(
                snapshot,
                "visible_enemy_unit",
                None))
            else None)
        if (
            defender is None
            or defender.tile
                != target_tile
        ):
            return None
        probability = (
            result.action_probability(
                "attack"))
        if (
            probability is None
            or probability.status
                != "bounded"
        ):
            return None
        lower = (
            probability.lower_probability)
        upper = (
            probability.upper_probability)
        if (
            lower is None or upper is None
            or not 0.0 <= lower
                <= upper <= 1.0
        ):
            return None
        definite_loss = 1.0 - upper
        residual = upper - lower
        current_turn = int(getattr(
            snapshot, "turn", 0))
        goal_features = tuple(sorted(
            (goal_id, float(loss))
            for goal_id, loss
            in request.goal_losses))
        outcomes = []
        if lower > 0.0:
            outcomes.append(
                PredictedOutcome(
                    outcome_id=(
                        "{}:native-attacker-wins"
                        .format(
                            request
                            .stable_operation_id)),
                    probability=lower,
                    next_truth_summaries=(),
                    next_goal_features=(
                        goal_features),
                    resource_delta=(),
                    completion_turn=float(
                        current_turn),
                    adverse_loss=0.0,
                    provenance=(
                        "freeciv-server-action-probability-lower-bound",
                        "server-selected-defender",
                    )))
        if definite_loss > 0.0:
            outcomes.append(
                PredictedOutcome(
                    outcome_id=(
                        "{}:native-defender-wins"
                        .format(
                            request
                            .stable_operation_id)),
                    probability=(
                        definite_loss),
                    next_truth_summaries=(),
                    next_goal_features=(
                        goal_features),
                    resource_delta=(),
                    completion_turn=float(
                        current_turn),
                    # The protocol proves terminal loss probability but does
                    # not expose damage-conditioned material value.
                    adverse_loss=0.0,
                    provenance=(
                        "freeciv-server-action-probability-upper-complement",
                        "server-selected-defender",
                    )))
        artifact = {
            "action_probability_half_percent": {
                "maximum":
                    probability.maximum,
                "minimum":
                    probability.minimum,
            },
            "adverse_loss_distribution": [],
            "city_capture_probability": None,
            "expected_enemy_shield_equivalent_loss":
                None,
            "expected_friendly_shield_equivalent_loss":
                None,
            "immediate_goal_feature_deltas": {},
            "missing_fields": [
                "damage_conditioned_survivor_hp",
                "material_loss_distribution",
                "post_action_exposure",
            ],
            "parity_status":
                "native-authoritative",
            "post_action_exposure": {
                "status": "not-exposed-by-action-probability-packet",
            },
            "probability_attacker_survives":
                lower,
            "probability_attacker_survives_upper":
                upper,
            "probability_target_destroyed":
                lower,
            "probability_target_destroyed_upper":
                upper,
            "reason_code": None,
            "residual_unknown_mass":
                residual,
            "schema_version": "2.0",
            "selected_target_unit_id":
                selected_target_id,
            "supported_subset":
                "server-selected-one-versus-one-action-probability",
            "target_unit_ids": [
                selected_target_id],
        }
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request.stable_operation_id),
                outcomes=tuple(outcomes),
                residual_probability=(
                    residual),
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "combat:native-action-probability"),
                residual_goal_losses=(
                    residual_losses(request))),
            context_key=context_key_for_request(
                request),
            authority=(
                EstimateAuthority
                .DETERMINISTIC_DERIVED),
            confidence=max(
                0.0, 1.0 - residual),
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "freeciv-server-action-probability",
                "server-selected-defender",
                "interval-residual-preserved",
            ),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))

    def estimate(self, request):
        if not self.supports(request):
            return self._abstain(
                request,
                "unsupported-action-type",
                ("action_type",))
        if request.action_type != "unit_attack":
            return self._abstain(
                request,
                "unsupported-combat-action-kind",
                ("supported_unit_attack",))
        snapshot = request.snapshot
        action = request.legal_action
        if (canonical_json_bytes(
                action).decode("utf-8")
                not in set(getattr(
                    snapshot,
                    "legal_action_json", ()))):
            return self._abstain(
                request,
                "combat-action-not-advertised",
                ("advertised_legal_action",))
        actor_id = action.get(
            "actor_id", action.get("unit_id"))
        attacker = (
            snapshot.unit(actor_id)
            if callable(getattr(
                snapshot, "unit", None))
            else None)
        target = action.get("target")
        target = (
            target if isinstance(
                target, dict) else {})
        target_x = target.get("x")
        target_y = target.get("y")
        target_tile = None
        if (
            isinstance(target_x, int)
            and not isinstance(
                target_x, bool)
            and isinstance(target_y, int)
            and not isinstance(
                target_y, bool)
            and isinstance(getattr(
                snapshot,
                "map_width", None), int)
            and snapshot.map_width > 0
        ):
            target_tile = (
                target_x
                + target_y
                * snapshot.map_width)
        specified_target_id = (
            target.get(
                "target_unit_id",
                action.get("target_id")))
        if (
            attacker is not None
            and target_tile is not None
        ):
            native = self._native_estimate(
                request,
                attacker,
                target_tile,
                specified_target_id)
            if native is not None:
                return native
        targets = self._target_units(
            request)
        target_ids = tuple(
            unit.unit_id for unit in targets)
        missing = []
        if attacker is None:
            missing.append("attacker")
        if len(targets) != 1:
            missing.append(
                "unique_selected_defender")
        defender = (
            targets[0]
            if len(targets) == 1
            else None)
        ruleset_ir = request.ruleset_ir
        if ruleset_ir is None:
            missing.append("ruleset_ir")
        attacker_spec = (
            None if attacker is None
            else _unit_spec(
                ruleset_ir,
                attacker.unit_type))
        defender_spec = (
            None if defender is None
            else _unit_spec(
                ruleset_ir,
                defender.unit_type))
        if attacker_spec is None:
            missing.append(
                "attacker_ruleset_stats")
        if defender_spec is None:
            missing.append(
                "defender_ruleset_stats")
        for unit, prefix in (
                (attacker, "attacker"),
                (defender, "defender")):
            if unit is None:
                continue
            if unit.hp is None:
                missing.append(
                    "{}_hp".format(prefix))
            if unit.veteran is None:
                missing.append(
                    "{}_veteran".format(
                        prefix))
            elif unit.veteran != 0:
                missing.append(
                    "{}_veteran_modifier".format(
                        prefix))
            if unit.activity != "idle":
                missing.append(
                    "{}_activity_modifier".format(
                        prefix))
            if unit.transported is not False:
                missing.append(
                    "{}_transport_state".format(
                        prefix))
        context = action.get(
            "combat_context")
        if not isinstance(context, dict):
            missing.append(
                "combat_context")
        else:
            required_unity = (
                "city_defense_multiplier",
                "fortification_multiplier",
                "terrain_defense_multiplier",
            )
            for name in required_unity:
                value = context.get(name)
                if (isinstance(value, bool)
                        or not isinstance(
                            value, (int, float))
                        or float(value) != 1.0):
                    missing.append(name)
            if context.get(
                    "effects_complete") is not True:
                missing.append(
                    "complete_effect_context")
            if context.get(
                    "city_target") is not False:
                missing.append(
                    "non_city_target")
            if (context.get(
                    "attacker_advances_on_win")
                    is not True):
                missing.append(
                    "post_action_position")
            selected = context.get(
                "selected_defender_id")
            if (defender is not None
                    and selected
                    != defender.unit_id):
                missing.append(
                    "selected_defender_id")
        if missing:
            return self._abstain(
                request,
                "combat-input-missing",
                tuple(missing),
                target_ids=target_ids)
        required_positive = (
            attacker_spec["attack"],
            attacker_spec["hitpoints"],
            attacker_spec["firepower"],
            attacker_spec["build_cost"],
            defender_spec["defense"],
            defender_spec["hitpoints"],
            defender_spec["firepower"],
            defender_spec["build_cost"],
        )
        if (any(
                value <= 0.0
                for value in required_positive)
                or attacker.hp <= 0
                or defender.hp <= 0
                or float(attacker.hp)
                > attacker_spec["hitpoints"]
                or float(defender.hp)
                > defender_spec["hitpoints"]):
            return self._abstain(
                request,
                "combat-nonpositive-mechanics",
                (), target_ids=target_ids)
        try:
            distribution = finite_duel_distribution(
                attacker_spec["attack"],
                defender_spec["defense"],
                attacker.hp,
                defender.hp,
                attacker_spec["firepower"],
                defender_spec["firepower"])
        except (ArithmeticError, TypeError, ValueError):
            return self._abstain(
                request,
                "combat-mechanics-unsupported",
                ("bounded_finite_duel",),
                target_ids=target_ids)
        attacker_max_hp = max(
            1.0,
            attacker_spec["hitpoints"])
        defender_max_hp = max(
            1.0,
            defender_spec["hitpoints"])
        expected_friendly_loss = sum(
            row.probability
            * attacker_spec["build_cost"]
            * (
                float(attacker.hp)
                - row.attacker_hp_remaining)
            / attacker_max_hp
            for row in distribution
            .terminal_outcomes)
        expected_enemy_loss = sum(
            row.probability
            * defender_spec["build_cost"]
            * (
                float(defender.hp)
                - row.defender_hp_remaining)
            / defender_max_hp
            for row in distribution
            .terminal_outcomes)
        expected_friendly_loss = min(
            attacker_spec["build_cost"],
            max(0.0,
                expected_friendly_loss))
        expected_enemy_loss = min(
            defender_spec["build_cost"],
            max(0.0,
                expected_enemy_loss))
        attacker_win = (
            distribution
            .attacker_win_probability)
        defender_win = (
            distribution
            .defender_win_probability)
        defender_remaining_value = (
            defender_spec["build_cost"]
            * float(defender.hp)
            / defender_max_hp)
        goal_features = tuple(sorted(
            (goal_id, float(loss))
            for goal_id, loss
            in request.goal_losses))
        win_rows = tuple(
            row for row in distribution
            .terminal_outcomes
            if row.winner == "attacker")
        loss_rows = tuple(
            row for row in distribution
            .terminal_outcomes
            if row.winner == "defender")

        def conditional_friendly_loss(rows, probability):
            return (
                0.0 if probability <= 0.0 else
                sum(
                    row.probability
                    * attacker_spec[
                        "build_cost"]
                    * (
                        float(attacker.hp)
                        - row
                        .attacker_hp_remaining)
                    / attacker_max_hp
                    for row in rows)
                / probability)

        def conditional_enemy_loss(rows, probability):
            return (
                0.0 if probability <= 0.0 else
                sum(
                    row.probability
                    * defender_spec[
                        "build_cost"]
                    * (
                        float(defender.hp)
                        - row
                        .defender_hp_remaining)
                    / defender_max_hp
                    for row in rows)
                / probability)

        current_turn = int(getattr(
            snapshot, "turn", 0))
        outcomes = (
            PredictedOutcome(
                outcome_id=(
                    "{}:attacker-wins".format(
                        request
                        .stable_operation_id)),
                probability=attacker_win,
                next_truth_summaries=(),
                next_goal_features=(
                    goal_features),
                resource_delta=(
                    ("enemy_shield_equivalent",
                     -defender_remaining_value),
                    ("friendly_shield_equivalent",
                     -conditional_friendly_loss(
                         win_rows,
                         attacker_win)),
                ),
                completion_turn=float(
                    current_turn),
                adverse_loss=(
                    conditional_friendly_loss(
                        win_rows,
                        attacker_win)),
                provenance=(
                    "finite-duel-attacker-terminal",
                )),
            PredictedOutcome(
                outcome_id=(
                    "{}:defender-wins".format(
                        request
                        .stable_operation_id)),
                probability=defender_win,
                next_truth_summaries=(),
                next_goal_features=(
                    goal_features),
                resource_delta=(
                    ("enemy_shield_equivalent",
                     -conditional_enemy_loss(
                         loss_rows,
                         defender_win)),
                    ("friendly_shield_equivalent",
                     -attacker_spec[
                         "build_cost"]
                     * float(attacker.hp)
                     / attacker_max_hp),
                ),
                completion_turn=float(
                    current_turn),
                adverse_loss=(
                    attacker_spec[
                        "build_cost"]
                    * float(attacker.hp)
                    / attacker_max_hp),
                provenance=(
                    "finite-duel-defender-terminal",
                )),
        )
        artifact = {
            "adverse_loss_distribution": [
                {
                    "adverse_loss":
                        outcome.adverse_loss,
                    "outcome_id":
                        outcome.outcome_id,
                    "probability":
                        outcome.probability,
                }
                for outcome in outcomes],
            "city_capture_probability": 0.0,
            "duel": distribution.to_dict(),
            "expected_enemy_shield_equivalent_loss":
                expected_enemy_loss,
            "expected_friendly_shield_equivalent_loss":
                expected_friendly_loss,
            "immediate_goal_feature_deltas": {
                goal_id: 0.0
                for goal_id, _
                in request.goal_losses
            },
            "missing_fields": [],
            "parity_status": "unverified",
            "post_action_exposure": {
                "status": "not-modeled",
            },
            "probability_attacker_survives":
                attacker_win,
            "probability_target_destroyed":
                attacker_win,
            "reason_code": None,
            "residual_unknown_mass": 0.0,
            "schema_version": "1.0",
            "supported_subset":
                "explicit-unmodified-one-versus-one",
            "target_unit_ids": list(
                target_ids),
        }
        return GroundedTransitionEstimate(
            transition=ExpectedTransition(
                operation_id=(
                    request.stable_operation_id),
                outcomes=outcomes,
                residual_probability=0.0,
                model_id="{}/{}".format(
                    self.model_id,
                    self.model_version),
                calibration_group=(
                    "combat:unmodified-duel"),
                residual_goal_losses=(
                    residual_losses(request))),
            context_key=context_key_for_request(
                request),
            # The mathematical kernel is deterministic, but its mapping to
            # Freeciv remains heuristic until native parity is established.
            authority=EstimateAuthority.HEURISTIC,
            confidence=0.25,
            validity=request.validity,
            estimator_id=self.model_id,
            estimator_version=(
                self.model_version),
            provenance=(
                "server-advertised-action",
                "clean-room-finite-duel-kernel",
                "native-parity-not-yet-established",
            ),
            model_artifact_json=(
                canonical_model_artifact(
                    artifact)))
