"""Component-only FDAS local goals and legally bound shadow operations."""

import json
from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.model import GoalState
from ..state.atomspace.model import AtomKey, AtomNamespace, EntityRef
from ..state.atomspace.grounding import (
    TypedGroundingRegistry,
    persistent_defender_type,
)
from .operations import (
    OPERATION_SCHEMA_VERSION,
    OperationParticipant,
    OperationSpec,
    OperationStep,
    operation_id_from_components,
)


@dataclass(frozen=True)
class LocalGoalContext:
    goal: GoalState
    global_goal_kind: str
    deficit_atom_id: str
    deficit_predicate: str
    target_key: AtomKey
    scope_id: str
    snapshot_id: str
    explanation_hash: str

    def to_dict(self):
        return {
            "deficit_atom_id": self.deficit_atom_id,
            "deficit_predicate": self.deficit_predicate,
            "explanation_hash": self.explanation_hash,
            "global_goal_kind": self.global_goal_kind,
            "goal": self.goal.to_dict(),
            "scope_id": self.scope_id,
            "snapshot_id": self.snapshot_id,
            "target_key": self.target_key.to_dict(),
        }


@dataclass(frozen=True)
class ShadowOperationCandidate:
    operation: OperationSpec
    action: dict
    action_key: str
    resource_keys: tuple
    legal_bound: bool
    authority_eligible: bool
    blockers: tuple
    provenance: tuple
    candidate_hash: str

    def __post_init__(self):
        if not isinstance(self.action, dict):
            raise TypeError("shadow operation action must be an object")
        if json.dumps(
                self.action, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False) != self.action_key:
            raise ValueError("shadow operation action key is not canonical")
        object.__setattr__(self, "resource_keys", tuple(self.resource_keys))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        if self.authority_eligible:
            raise ValueError("Phase 4 shadow operation cannot carry authority")

    def to_dict(self):
        return {
            "action": self.action,
            "action_key": self.action_key,
            "authority_eligible": self.authority_eligible,
            "blockers": list(self.blockers),
            "candidate_hash": self.candidate_hash,
            "legal_bound": self.legal_bound,
            "operation": self.operation.to_dict(),
            "provenance": list(self.provenance),
            "resource_keys": list(self.resource_keys),
        }


@dataclass(frozen=True)
class ShadowCandidateComparison:
    snapshot_id: str
    legacy_candidate_count: int
    fdas_candidate_count: int
    overlapping_action_keys: tuple
    missing_legacy: tuple
    extra_fdas: tuple
    legal_binding_failures: tuple
    authority_violations: tuple
    safety_downgrades: tuple
    comparison_hash: str

    def to_dict(self):
        return {
            "authority_violations": list(self.authority_violations),
            "comparison_hash": self.comparison_hash,
            "extra_fdas": list(self.extra_fdas),
            "fdas_candidate_count": self.fdas_candidate_count,
            "legacy_candidate_count": self.legacy_candidate_count,
            "legal_binding_failures": list(self.legal_binding_failures),
            "missing_legacy": list(self.missing_legacy),
            "overlapping_action_keys": list(self.overlapping_action_keys),
            "safety_downgrades": list(self.safety_downgrades),
            "snapshot_id": self.snapshot_id,
        }


def compare_shadow_candidates(snapshot, legacy_candidates, fdas_candidates):
    """Compare only the Phase-4 city/economy action surface."""
    action_types = frozenset((
        "city_governor", "city_production", "player_rates", "tech_research"))
    legacy = dict(
        (value.action_key, value)
        for value in legacy_candidates
        if value.action.get("action_type") in action_types)
    fdas = dict((value.action_key, value) for value in fdas_candidates)
    overlap = tuple(sorted(set(legacy).intersection(fdas)))
    missing = tuple(
        {
            "action_key": key,
            "category": legacy[key].category,
            "reason": "no-active-fdas-deficit-route",
        }
        for key in sorted(set(legacy).difference(fdas)))
    extra = tuple(
        {
            "action_key": key,
            "blockers": list(fdas[key].blockers),
            "operation_id": fdas[key].operation.operation_id,
        }
        for key in sorted(set(fdas).difference(legacy)))
    legal_failures = tuple(sorted(
        value.operation.operation_id for value in fdas.values()
        if (not value.legal_bound
            or value.action_key not in snapshot.legal_action_json)))
    authority_violations = tuple(sorted(
        value.operation.operation_id for value in fdas.values()
        if value.authority_eligible))
    semantic = {
        "authority_violations": list(authority_violations),
        "extra_fdas": list(extra),
        "fdas_candidate_count": len(fdas),
        "legacy_candidate_count": len(legacy),
        "legal_binding_failures": list(legal_failures),
        "missing_legacy": list(missing),
        "overlapping_action_keys": list(overlap),
        "safety_downgrades": [],
        "snapshot_id": snapshot.snapshot_id,
    }
    return ShadowCandidateComparison(
        snapshot.snapshot_id,
        len(legacy),
        len(fdas),
        overlap,
        missing,
        extra,
        legal_failures,
        authority_violations,
        (),
        structural_hash(semantic),
    )


class GoalFactory(object):
    """Instantiate utility separately from deterministic local deficits."""

    _MAPPING = {
        "city-food-deficit": (
            "city-food-secure", "food_sustainability", 1.5, True),
        "city-order-deficit": (
            "city-order-stable", "governance", 1.5, True),
        "city-production-stalled": (
            "city-production-active", "production_continuity", 1.2, False),
        "city-garrison-deficit": (
            "city-garrison-covered", "survival", 2.0, True),
        "treasury-below-reserve": (
            "treasury-structurally-safe", "treasury_sustainability", 1.6,
            True),
        "research-throughput-stalled": (
            "research-throughput-active", "research_sustainability", 1.3,
            False),
    }

    def instantiate(self, revision, query_context=None):
        query_context = query_context
        result = []
        for record in revision.records:
            mapping = self._MAPPING.get(record.key.predicate)
            if mapping is None or record.key.namespace != AtomNamespace.DERIVED:
                continue
            target_predicate, global_kind, utility, safety = mapping
            target_key = AtomKey(
                AtomNamespace.DERIVED,
                target_predicate,
                record.key.arguments,
                record.key.scope_id,
            )
            goal_id = "fdas-goal-" + structural_hash({
                "deficit_atom_id": record.atom_id,
                "global_goal_kind": global_kind,
                "snapshot_id": revision.snapshot_id,
                "target_atom_id": target_key.atom_id,
            })[:28]
            explanation_hash = (
                query_context.explain(record.atom_id)["structural_hash"]
                if query_context is not None else
                structural_hash(record.to_dict()))
            goal = GoalState(
                goal_id,
                target_key.atom_id,
                target_strength=1.0,
                utility=utility,
                urgency=1.0,
                commitment=1.0,
                deadline=None,
                risk_sensitivity=0.75 if safety else 0.25,
                safety=safety,
                context=(
                    ("deficit_atom_id", record.atom_id),
                    ("global_goal_kind", global_kind),
                    ("scope_id", record.key.scope_id),
                    ("snapshot_id", revision.snapshot_id),
                ),
            )
            result.append(LocalGoalContext(
                goal,
                global_kind,
                record.atom_id,
                record.key.predicate,
                target_key,
                record.key.scope_id,
                revision.snapshot_id,
                explanation_hash,
            ))
        return tuple(sorted(result, key=lambda value: value.goal.goal_id))


class CandidateOperationFactory(object):
    """Bind local deficit routes only to canonical current legal actions."""

    _ACTION_TYPES = {
        "city-food-deficit": frozenset(("city_governor",)),
        "city-order-deficit": frozenset(("city_governor",)),
        "city-production-stalled": frozenset(("city_production",)),
        "city-garrison-deficit": frozenset(("unit_move",)),
        "treasury-below-reserve": frozenset(("player_rates",)),
        "research-throughput-stalled": frozenset(("tech_research",)),
    }
    _GARRISON_POLICY_LIMIT = 3

    def __init__(self, ruleset_ir, ruleset_digest):
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = str(ruleset_digest)
        self._schemas = dict(
            (schema.action_type, schema)
            for schema in ruleset_ir.action_schemas)
        self._effects = dict(
            (effect.effect_id, effect) for effect in ruleset_ir.effects)
        self._groundings = TypedGroundingRegistry(
            ruleset_ir, ruleset_digest=self.ruleset_digest)
        self._defender_types = set(
            str(rule.rule_name).strip().lower().replace("_", " ")
            for rule in ruleset_ir.rules
            if (rule.target_kind == "unit"
                and persistent_defender_type(ruleset_ir, rule.rule_name)))

    @staticmethod
    def _city_id(goal):
        for argument in goal.target_key.arguments:
            if isinstance(argument, EntityRef) and argument.kind == "city":
                return argument.entity_id
        return None

    def _action_matches(self, goal, action, player_id, snapshot=None):
        city_id = CandidateOperationFactory._city_id(goal)
        if city_id is not None:
            if goal.deficit_predicate == "city-garrison-deficit":
                if action.get("action_type") != "unit_move" or snapshot is None:
                    return False
                city = snapshot.city(city_id)
                actor = snapshot.unit(action.get("actor_id"))
                target = action.get("target") or {}
                if not bool(
                    city is not None and actor is not None
                    and str(actor.unit_type).strip().lower().replace(
                        "_", " ") in self._defender_types
                    and city.tile is not None
                    and city.x is not None and city.y is not None):
                    return False
                if target.get("x") == city.x and target.get("y") == city.y:
                    return True
                route = snapshot.movement_route(actor.unit_id, city.tile)
                if not bool(
                        route is not None
                        and route.authority == "freeciv-server-pathfinder"
                        and route.schema_version == "1.0"
                        and route.reachable
                        and route.origin_tile == actor.tile
                        and route.turn == snapshot.turn
                        and route.source_seq <= snapshot.identity.source_seq
                        and snapshot.map_width > 0):
                    return False
                first_x = route.first_step_tile % snapshot.map_width
                first_y = route.first_step_tile // snapshot.map_width
                return target.get("x") == first_x and target.get("y") == first_y
            if str(action.get("city_id")) != city_id:
                return False
            target = action.get("target") or {}
            if goal.deficit_predicate == "city-food-deficit":
                return "food_surplus_reserve" in target
            if goal.deficit_predicate == "city-order-deficit":
                return (
                    target.get("require_happy") is True
                    or target.get("allow_disorder") is False)
            return True
        actor = action.get("actor_id", player_id)
        return str(actor) == str(player_id)

    @staticmethod
    def _resource(action, player_id):
        action_type = action.get("action_type")
        if action_type == "city_production":
            return ("city-production-slot:{}".format(action["city_id"]),)
        if action_type == "city_governor":
            return ("city-governor-slot:{}".format(action["city_id"]),)
        if action_type == "player_rates":
            return ("player-rate-action:{}".format(player_id),)
        if action_type == "tech_research":
            return ("research-choice:{}".format(player_id),)
        if str(action_type).startswith("unit_"):
            return ("unit-action:{}".format(action.get("actor_id")),)
        return ("action-budget:{}".format(player_id),)

    def _effect_blockers(self, action_type):
        schema = self._schemas.get(str(action_type))
        if schema is None:
            return ("action-schema-unavailable",)
        effects = tuple(self._effects[value] for value in schema.effects)
        if not effects or any(not value.known for value in effects):
            return ("uncompiled-action-effect",)
        return ()

    def _route_blockers(self, goal, action, snapshot):
        blockers = list(self._effect_blockers(action.get("action_type")))
        if goal.deficit_predicate != "city-garrison-deficit":
            return tuple(blockers)
        actor = snapshot.unit(action.get("actor_id"))
        if actor is None:
            blockers.append("unit-actor-unavailable")
            return tuple(sorted(set(blockers)))
        removal = self._groundings.evaluate(
            "defense.removal-deficit", snapshot, actor.unit_id,
            self._GARRISON_POLICY_LIMIT)
        if not removal.available:
            blockers.append("source-garrison-opportunity-cost-unavailable")
        elif removal.value["creates_deficit"] is True:
            blockers.append("protected-source-garrison")
        return tuple(sorted(set(blockers)))

    def _coordinated_replacement_candidates(
            self, snapshot, goal_contexts, revision):
        if revision is None:
            return ()
        if revision.snapshot_id != snapshot.snapshot_id:
            raise ValueError(
                "coordinated replacement requires the current FDAS revision")
        coordinated = tuple(
            value for value in revision.records
            if (value.key.namespace == AtomNamespace.DERIVED
                and value.key.predicate
                == "unit-coordinated-replacement-for"))
        reinforcement = {
            (value.key.arguments[0].entity_id,
             value.key.arguments[1].entity_id): value
            for value in revision.records
            if (value.key.namespace == AtomNamespace.DERIVED
                and value.key.predicate == "unit-reinforcement-route")
        }
        if not coordinated or not reinforcement:
            return ()
        legal = tuple(
            (json.loads(value), value) for value in snapshot.legal_action_json)
        result = []
        for goal in goal_contexts:
            if goal.deficit_predicate != "city-garrison-deficit":
                continue
            target_city_id = self._city_id(goal)
            target_city = snapshot.city(target_city_id)
            if target_city is None or target_city.tile is None:
                continue
            for relation in coordinated:
                replacement_id = relation.key.arguments[0].entity_id
                protected_id = relation.key.arguments[1].entity_id
                source_city_id = relation.key.arguments[2].entity_id
                if source_city_id == target_city_id:
                    continue
                source_city = snapshot.city(source_city_id)
                replacement_unit = snapshot.unit(replacement_id)
                protected_unit = snapshot.unit(protected_id)
                target_relation = reinforcement.get((
                    protected_id, target_city_id))
                if (source_city is None or source_city.tile is None
                        or replacement_unit is None or protected_unit is None
                        or target_relation is None):
                    continue
                replacement_route = snapshot.movement_route(
                    replacement_id, source_city.tile)
                target_route = snapshot.movement_route(
                    protected_id, target_city.tile)
                if not bool(
                        replacement_route is not None
                        and replacement_route.reachable
                        and target_route is not None
                        and target_route.reachable
                        and snapshot.map_width > 0):
                    continue
                first_x = (
                    replacement_route.first_step_tile % snapshot.map_width)
                first_y = (
                    replacement_route.first_step_tile // snapshot.map_width)
                action_row = next((
                    (action, action_key)
                    for action, action_key in legal
                    if (action.get("action_type") == "unit_move"
                        and str(action.get("actor_id")) == replacement_id
                        and isinstance(action.get("target"), dict)
                        and action["target"].get("x") == first_x
                        and action["target"].get("y") == first_y)
                ), None)
                if action_row is None:
                    continue
                action, action_key = action_row
                participants = (
                    OperationParticipant(
                        "replacement", replacement_id, "unit", True),
                    OperationParticipant(
                        "reinforcement", protected_id, "unit", True),
                )
                operation_type = "fdas-defense:coordinated-replacement"
                operation_id = operation_id_from_components(
                    operation_type, (goal.goal.goal_id,), participants,
                    "city:{}".format(target_city_id), self.ruleset_digest,
                    snapshot.turn)
                source_requirement = "requirements-" + structural_hash({
                    "coordinated_atom_id": relation.atom_id,
                    "operation_id": operation_id,
                    "phase": "replacement",
                    "snapshot_id": snapshot.snapshot_id,
                })[:28]
                target_requirement = "requirements-" + structural_hash({
                    "deficit_atom_id": goal.deficit_atom_id,
                    "operation_id": operation_id,
                    "phase": "reinforcement",
                    "route_atom_id": target_relation.atom_id,
                    "snapshot_id": snapshot.snapshot_id,
                })[:28]
                arrival_turn = (
                    int(snapshot.turn)
                    + int(replacement_route.estimated_turns)
                    + int(target_route.estimated_turns))
                expiry_turn = max(int(snapshot.turn) + 1, arrival_turn)
                steps = (
                    OperationStep(
                        "step-" + structural_hash({
                            "operation_id": operation_id,
                            "phase": "replacement",
                        })[:28],
                        "unit_move", "replacement",
                        "city:{}".format(source_city_id),
                        source_requirement,
                        "city-defense:replacement-at-source-city",
                        max(1, int(replacement_route.estimated_turns) + 1)),
                    OperationStep(
                        "step-" + structural_hash({
                            "operation_id": operation_id,
                            "phase": "reinforcement",
                        })[:28],
                        "unit_move", "reinforcement",
                        "city:{}".format(target_city_id),
                        target_requirement,
                        "city-defense:protected-defender-at-target-city",
                        max(1, int(target_route.estimated_turns) + 1)),
                )
                operation = OperationSpec(
                    OPERATION_SCHEMA_VERSION,
                    operation_id,
                    operation_type,
                    (goal.goal.goal_id,),
                    participants,
                    "city:{}".format(target_city_id),
                    steps,
                    int(snapshot.turn),
                    expiry_turn,
                    0.0,
                    (
                        "fdas-coordinated-replacement-shadow/1.0",
                        "exact-replacement-relation",
                        "native-server-route-eta",
                        "current-byte-identical-first-action",
                        "future-second-step-requires-refresh",
                        "no-action-authority",
                    ),
                    self.ruleset_digest,
                )
                blockers = tuple(sorted(set(
                    self._effect_blockers("unit_move"))))
                resource_keys = (
                    "unit-action:{}:current".format(replacement_id),
                    "unit-action:{}:conditional-future".format(protected_id),
                )
                provenance = (
                    "fdas-coordinated-replacement-shadow/1.0",
                    "atom:{}".format(relation.atom_id),
                    "atom:{}".format(target_relation.atom_id),
                ) + tuple(
                    "support:{}".format(value.support_id)
                    for value in relation.supports + target_relation.supports)
                semantic = {
                    "action_key": action_key,
                    "arrival_turn": arrival_turn,
                    "blockers": list(blockers),
                    "operation": operation.to_dict(),
                    "provenance": list(provenance),
                    "resource_keys": list(resource_keys),
                }
                result.append(ShadowOperationCandidate(
                    operation, action, action_key, resource_keys,
                    action_key in snapshot.legal_action_json,
                    False, blockers, provenance, structural_hash(semantic)))
        return tuple(result)

    def instantiate(self, snapshot, goal_contexts, revision=None):
        legal = tuple(
            (json.loads(value), value) for value in snapshot.legal_action_json)
        candidates = []
        for goal in goal_contexts:
            accepted_types = self._ACTION_TYPES.get(
                goal.deficit_predicate, frozenset())
            for action, action_key in legal:
                action_type = str(action.get("action_type"))
                if (action_type not in accepted_types
                        or not self._action_matches(
                            goal, action, snapshot.player_id, snapshot)):
                    continue
                city_id = self._city_id(goal)
                unit_action = str(action_type).startswith("unit_")
                actor_id = (
                    str(action.get("actor_id")) if unit_action
                    else city_id or str(snapshot.player_id))
                actor_class = (
                    "unit" if unit_action else
                    "city" if city_id is not None else "player")
                participant = OperationParticipant(
                    "controller", str(actor_id), actor_class, True)
                target_ref = (
                    "city:{}".format(city_id) if city_id is not None
                    else "player:{}".format(snapshot.player_id))
                operation_type = "fdas-shadow:{}:{}".format(
                    goal.deficit_predicate, action_type)
                operation_id = operation_id_from_components(
                    operation_type,
                    (goal.goal.goal_id,),
                    (participant,),
                    target_ref,
                    self.ruleset_digest,
                    snapshot.turn,
                )
                requirement_id = "requirements-" + structural_hash({
                    "action_key": action_key,
                    "deficit_atom_id": goal.deficit_atom_id,
                    "legal_actions_digest": snapshot.legal_actions_digest,
                    "snapshot_id": snapshot.snapshot_id,
                })[:28]
                step = OperationStep(
                    "step-" + structural_hash({
                        "action_key": action_key,
                        "operation_id": operation_id,
                    })[:28],
                    action_type,
                    "controller",
                    target_ref,
                    requirement_id,
                    "observe:{}".format(goal.target_key.predicate),
                    1,
                )
                operation = OperationSpec(
                    OPERATION_SCHEMA_VERSION,
                    operation_id,
                    operation_type,
                    (goal.goal.goal_id,),
                    (participant,),
                    target_ref,
                    (step,),
                    int(snapshot.turn),
                    int(snapshot.turn) + 1,
                    0.0,
                    (
                        "fdas-city-economy-shadow/1.0",
                        "current-byte-identical-legal-action",
                        "no-action-authority",
                    ),
                    self.ruleset_digest,
                )
                blockers = self._route_blockers(goal, action, snapshot)
                semantic = {
                    "action_key": action_key,
                    "blockers": list(blockers),
                    "goal_id": goal.goal.goal_id,
                    "operation": operation.to_dict(),
                    "resource_keys": list(self._resource(
                        action, snapshot.player_id)),
                }
                candidates.append(ShadowOperationCandidate(
                    operation,
                    action,
                    action_key,
                    self._resource(action, snapshot.player_id),
                    action_key in snapshot.legal_action_json,
                    False,
                    blockers,
                    (
                        "fdas-city-economy-shadow/1.0",
                        "ruleset-ir-action-schema/2.0",
                    ),
                    structural_hash(semantic),
                ))
        candidates.extend(self._coordinated_replacement_candidates(
            snapshot, goal_contexts, revision))
        return tuple(sorted(
            candidates,
            key=lambda value: (
                value.operation.operation_id, value.action_key)))
