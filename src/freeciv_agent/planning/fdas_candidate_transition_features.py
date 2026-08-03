"""Outcome-free grounded transition features for FDAS move candidates.

The frozen candidate calibration model intentionally sees only coarse episode
context.  This projection records the exact-turn mechanical facts needed by a
later candidate-specific model without changing that model or granting any
selection authority.  Missing or inconsistent native path data is represented
as an explicit grounding status; it is never imputed.
"""

from ..pressure.induction import InductionFeatureQuery
from .fdas import ShadowOperationCandidate


CANDIDATE_TRANSITION_FEATURE_SCHEMA = (
    "fdas-candidate-transition-features/1.0")
CANDIDATE_TRANSITION_OPERATION_TYPE = (
    "fdas-shadow:city-garrison-deficit:unit_move")
CANDIDATE_TRANSITION_FEATURE_KEYS = (
    "actor_hp_band",
    "actor_unit_type",
    "route_estimated_turns_band",
    "route_first_step_movement_cost_band",
    "route_path_length_band",
    "route_total_movement_cost_band",
    "source_city_relation",
    "source_other_fortified_units_band",
    "source_other_own_units_band",
    "transition_grounding_status",
)


def _count_band(value):
    value = max(0, int(value))
    return str(value) if value < 2 else "2+"


def _hp_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 3:
        return "1-3"
    if value <= 6:
        return "4-6"
    if value <= 9:
        return "7-9"
    return "10+"


def _turn_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 1:
        return "1"
    if value == 2:
        return "2"
    return "3+"


def _cost_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 2:
        return "0-2"
    if value <= 5:
        return "3-5"
    return "6+"


def _path_length_band(value):
    if value is None:
        return "unknown"
    value = int(value)
    if value <= 1:
        return "1"
    if value <= 3:
        return "2-3"
    return "4+"


def _unknown_features(status):
    return {
        "actor_hp_band": "unknown",
        "actor_unit_type": "unknown",
        "route_estimated_turns_band": "unknown",
        "route_first_step_movement_cost_band": "unknown",
        "route_path_length_band": "unknown",
        "route_total_movement_cost_band": "unknown",
        "source_city_relation": "unknown",
        "source_other_fortified_units_band": "unknown",
        "source_other_own_units_band": "unknown",
        "transition_grounding_status": status,
    }


def _grounded_features(candidate, snapshot):
    actor_id = candidate.action.get("actor_id")
    if (isinstance(actor_id, bool) or not isinstance(actor_id, int)):
        return _unknown_features("actor-id-unavailable")
    target_ref = candidate.operation.target_ref
    if (not isinstance(target_ref, str)
            or not target_ref.startswith("city:")):
        return _unknown_features("target-city-unavailable")
    try:
        target_city_id = int(target_ref.split(":", 1)[1])
    except ValueError:
        return _unknown_features("target-city-unavailable")
    actor = snapshot.unit(actor_id)
    target_city = snapshot.city(target_city_id)
    if actor is None:
        return _unknown_features("actor-unavailable")
    if target_city is None or target_city.tile is None:
        return _unknown_features("target-city-unavailable")
    route = snapshot.movement_route(actor_id, target_city.tile)
    if route is None:
        return _unknown_features("route-unavailable")
    if (route.turn != snapshot.turn
            or route.source_seq > snapshot.identity.source_seq):
        return _unknown_features("route-stale")
    if not route.reachable:
        return _unknown_features("route-unreachable")
    if (route.origin_tile != actor.tile
            or route.moves_left_at_request != actor.moves_left
            or route.transported_at_request != bool(actor.transported)
            or candidate.action.get("movement_cost")
            != route.first_step_movement_cost):
        return _unknown_features("route-action-mismatch")
    action_target = candidate.action.get("target")
    first_step_tile = next((
        value for value in snapshot.map_tiles
        if isinstance(value, dict)
        and value.get("index") == route.first_step_tile), None)
    if (not isinstance(action_target, dict)
            or first_step_tile is None
            or action_target.get("x") != first_step_tile.get("x")
            or action_target.get("y") != first_step_tile.get("y")):
        return _unknown_features("route-action-mismatch")
    if any(value is None for value in (
            actor.hp, actor.unit_type, route.estimated_turns,
            route.first_step_movement_cost, route.path_length,
            route.total_movement_cost)):
        return _unknown_features("transition-fields-unavailable")

    source_city = next((
        value for value in snapshot.cities
        if value.tile is not None and value.tile == actor.tile), None)
    source_relation = (
        "none" if source_city is None else
        "target" if source_city.city_id == target_city_id else "other")
    other_source_units = tuple(
        value for value in snapshot.units
        if value.unit_id != actor_id
        and value.tile == actor.tile
        and value.transported is not True)
    fortified_activities = frozenset((
        "fortify", "fortified", "fortifying"))
    other_source_fortified = tuple(
        value for value in other_source_units
        if str(value.activity or "").lower() in fortified_activities)
    return {
        "actor_hp_band": _hp_band(actor.hp),
        "actor_unit_type": str(actor.unit_type),
        "route_estimated_turns_band": _turn_band(route.estimated_turns),
        "route_first_step_movement_cost_band": _cost_band(
            route.first_step_movement_cost),
        "route_path_length_band": _path_length_band(route.path_length),
        "route_total_movement_cost_band": _cost_band(
            route.total_movement_cost),
        "source_city_relation": source_relation,
        "source_other_fortified_units_band": _count_band(
            len(other_source_fortified)),
        "source_other_own_units_band": _count_band(
            len(other_source_units)),
        "transition_grounding_status": "complete",
    }


def candidate_transition_feature_query(query, candidate, snapshot):
    """Append hash-stable candidate mechanics to an outcome-free query.

    The query ID and original causal features are preserved.  The frozen v1
    calibration model ignores the added features, while future models can
    require the explicit schema and ``complete`` grounding status.
    """
    if not isinstance(query, InductionFeatureQuery):
        raise TypeError("candidate transition projection requires a query")
    if not isinstance(candidate, ShadowOperationCandidate):
        raise TypeError("candidate transition projection requires a candidate")
    operation_type = dict(query.context).get("operation_type")
    if (operation_type != CANDIDATE_TRANSITION_OPERATION_TYPE
            or candidate.operation.operation_type != operation_type
            or candidate.action.get("action_type") != "unit_move"):
        raise ValueError(
            "candidate transition projection supports reinforcement moves")
    context = dict(query.context)
    if "candidate_transition_feature_schema" in context:
        raise ValueError("candidate transition query is already projected")
    context["candidate_transition_feature_schema"] = (
        CANDIDATE_TRANSITION_FEATURE_SCHEMA)
    features = _grounded_features(candidate, snapshot)
    if set(features) != set(CANDIDATE_TRANSITION_FEATURE_KEYS):
        raise RuntimeError("candidate transition feature schema is incomplete")
    appended = tuple(
        "candidate-transition:{}={}".format(key, features[key])
        for key in CANDIDATE_TRANSITION_FEATURE_KEYS)
    return InductionFeatureQuery(
        query.query_id,
        tuple(sorted(context.items())),
        tuple(query.features) + appended,
        tuple(query.provenance_ids) + (
            "candidate-transition-feature-schema:"
            + CANDIDATE_TRANSITION_FEATURE_SCHEMA,
            "candidate-transition-grounding:"
            + features["transition_grounding_status"],
        ))
