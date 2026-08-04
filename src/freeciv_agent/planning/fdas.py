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
    production_assembly: object = None

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
        if self.production_assembly is not None:
            from .production_operations import ProductionOperationAssembly
            if not isinstance(
                    self.production_assembly, ProductionOperationAssembly):
                raise TypeError(
                    "shadow production evidence must be a grounded assembly")
            if (
                    self.operation != self.production_assembly.spec
                    or self.action != self.production_assembly.queue_action()
            ):
                raise ValueError(
                    "shadow production candidate and assembly differ")
            if (
                    self.authority_eligible
                    or not self.production_assembly.shadow_only
                    or self.production_assembly.policy_authority
                    or "delayed-production-completion-unobserved"
                    not in self.blockers
            ):
                raise ValueError(
                    "grounded production candidate overstates delayed authority")
        if self.authority_eligible:
            target = self.action.get("target")
            reserve = (
                target.get("food_surplus_reserve")
                if isinstance(target, dict) else None)
            city_stability = bool(
                self.legal_bound
                and not self.blockers
                and self.action.get("action_type") == "city_governor"
                and not isinstance(reserve, bool)
                and isinstance(reserve, int)
                and 1 <= reserve <= 10
                and "fdas-bounded-city-stability/1.0"
                in self.provenance)
            defense_fortification = bool(
                self.legal_bound
                and not self.blockers
                and self.action.get("action_type") == "unit_fortify"
                and set(self.action) == {"action_type", "actor_id"}
                and "fdas-bounded-defense-fortification/1.0"
                in self.provenance)
            defense_alternative = bool(
                self.legal_bound
                and not self.blockers
                and self.action.get("action_type") in (
                    "unit_fortify", "unit_move")
                and any(value in self.provenance for value in (
                    "fdas-safe-alternative-outcome-collection/1.0",
                    "fdas-safe-alternative-outcome-collection/1.1",
                    "fdas-safe-alternative-outcome-collection/1.2",
                    "fdas-safe-alternative-outcome-collection/1.3",
                    "fdas-safe-alternative-outcome-collection/2.0",
                    "fdas-safe-alternative-outcome-collection/3.0",
                    "fdas-safe-alternative-outcome-collection/4.0",
                )))
            if not (
                    city_stability
                    or defense_fortification
                    or defense_alternative):
                raise ValueError(
                    "FDAS authority candidate violates every bounded "
                    "authority contract")
            if defense_fortification and (
                    isinstance(self.action.get("actor_id"), bool)
                    or not isinstance(self.action.get("actor_id"), int)
            ):
                raise ValueError(
                    "FDAS defense authority candidate violates the bounded "
                    "fortification action shape")
            if defense_alternative and (
                    isinstance(self.action.get("actor_id"), bool)
                    or not isinstance(self.action.get("actor_id"), int)
                    or (self.action.get("action_type") == "unit_fortify"
                        and set(self.action)
                        != {"action_type", "actor_id"})
                    or (self.action.get("action_type") == "unit_move"
                        and not isinstance(self.action.get("target"), dict))
            ):
                raise ValueError(
                    "FDAS alternative outcome candidate violates the bounded "
                    "defense action shape")

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
            "production_assembly": (
                None if self.production_assembly is None
                else self.production_assembly.to_dict()),
            "resource_keys": list(self.resource_keys),
        }


@dataclass(frozen=True)
class CandidateInstantiation:
    candidates: tuple
    omitted_unprotected_count: int
    protected_action_keys: tuple
    diagnostics: tuple
    instantiation_hash: str

    def to_dict(self):
        return {
            "candidate_count": len(self.candidates),
            "diagnostics": list(self.diagnostics),
            "instantiation_hash": self.instantiation_hash,
            "omitted_unprotected_count": self.omitted_unprotected_count,
            "protected_action_keys": list(self.protected_action_keys),
        }


_LEGACY_CATEGORY_GOAL_ROUTES = {
    "city_defense": ("unit-fortification-opportunity",),
    "production_defense": ("city-garrison-deficit",),
    "production_food_stabilization": ("city-food-deficit",),
    "production_repurpose": ("city-production-stalled",),
    "production_treasury_stabilization": ("treasury-below-reserve",),
}


def legacy_shadow_goal_routes(legacy_candidates):
    """Describe legacy-only control routes without asserting causal truth."""
    return tuple(sorted(set(
        (candidate.action_key, deficit_predicate)
        for candidate in legacy_candidates
        for deficit_predicate in _LEGACY_CATEGORY_GOAL_ROUTES.get(
            candidate.category, ()))))


@dataclass(frozen=True)
class ShadowCandidateComparison:
    snapshot_id: str
    legacy_candidate_count: int
    fdas_candidate_count: int
    overlapping_action_keys: tuple
    explained_legacy: tuple
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
            "explained_legacy": list(self.explained_legacy),
            "missing_legacy": list(self.missing_legacy),
            "overlapping_action_keys": list(self.overlapping_action_keys),
            "safety_downgrades": list(self.safety_downgrades),
            "snapshot_id": self.snapshot_id,
        }


def _goal_target_city(goal):
    for argument in goal.target_key.arguments:
        if isinstance(argument, EntityRef) and argument.kind == "city":
            return argument.entity_id
    return None


def compare_shadow_candidates(
        snapshot, legacy_candidates, fdas_candidates, goal_contexts=()):
    """Compare the activated city/economy and local-defense action surface."""
    action_types = frozenset((
        "city_governor", "city_production", "player_rates", "tech_research",
        "unit_fortify", "unit_move"))
    legacy = dict(
        (value.action_key, value)
        for value in legacy_candidates
        if value.action.get("action_type") in action_types)
    fdas = dict((value.action_key, value) for value in fdas_candidates)
    overlap = tuple(sorted(set(legacy).intersection(fdas)))
    active_routes = frozenset(
        (goal.deficit_predicate, _goal_target_city(goal))
        for goal in goal_contexts)
    explained = []
    missing = []
    for key in sorted(set(legacy).difference(fdas)):
        candidate = legacy[key]
        routes = _LEGACY_CATEGORY_GOAL_ROUTES.get(candidate.category, ())
        city_id = candidate.action.get("city_id")
        target_city = None if city_id is None else str(city_id)
        route_active = any(
            (predicate, target_city) in active_routes
            or (predicate, None) in active_routes
            for predicate in routes)
        value = {
            "action_key": key,
            "category": candidate.category,
            "reason": (
                "active-fdas-route-did-not-instantiate"
                if route_active else
                "no-active-fdas-deficit-route"
                if routes else
                "legacy-category-outside-current-fdas-ontology"),
            "route_predicates": list(routes),
        }
        if (key not in snapshot.legal_action_json or route_active):
            missing.append(value)
        else:
            explained.append(value)
    explained = tuple(explained)
    missing = tuple(missing)
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
        "explained_legacy": list(explained),
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
        explained,
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
        "city-replacement-capacity-deficit": (
            "city-replacement-capacity-ready", "survival", 1.9, True),
        "unit-fortification-opportunity": (
            "unit-fortified-ready", "survival", 1.8, True),
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
        "city-replacement-capacity-deficit": frozenset((
            "city_production",)),
        "unit-fortification-opportunity": frozenset(("unit_fortify",)),
        "treasury-below-reserve": frozenset(("player_rates",)),
        "research-throughput-stalled": frozenset(("tech_research",)),
    }
    _GARRISON_POLICY_LIMIT = 3
    _REPLACEMENT_CAPACITY_COMPLETION_HORIZON_TURNS = 64

    def __init__(self, ruleset_ir, ruleset_digest,
                 maximum_unprotected_candidates_per_goal=8,
                 replacement_capacity_production_operations_enabled=False):
        if (isinstance(maximum_unprotected_candidates_per_goal, bool)
                or not isinstance(
                    maximum_unprotected_candidates_per_goal, int)
                or maximum_unprotected_candidates_per_goal < 1):
            raise ValueError(
                "maximum unprotected candidates per goal must be positive")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = str(ruleset_digest)
        self.maximum_unprotected_candidates_per_goal = (
            maximum_unprotected_candidates_per_goal)
        if not isinstance(
                replacement_capacity_production_operations_enabled, bool):
            raise TypeError(
                "replacement capacity production operation gate must be boolean")
        self.replacement_capacity_production_operations_enabled = (
            replacement_capacity_production_operations_enabled)
        self._schemas = dict(
            (schema.action_type, schema)
            for schema in ruleset_ir.action_schemas)
        self._effects = dict(
            (effect.effect_id, effect) for effect in ruleset_ir.effects)
        self._groundings = TypedGroundingRegistry(
            ruleset_ir, ruleset_digest=self.ruleset_digest)
        self._defender_types = set(
            str(label).strip().lower().replace("_", " ")
            for rule in ruleset_ir.rules
            if rule.target_kind == "unit"
            for label in (
                rule.rule_name, getattr(rule, "display_name", None))
            if (label and persistent_defender_type(ruleset_ir, label)))

    @staticmethod
    def _city_id(goal):
        for argument in goal.target_key.arguments:
            if isinstance(argument, EntityRef) and argument.kind == "city":
                return argument.entity_id
        return None

    def _action_matches(self, goal, action, player_id, snapshot=None):
        city_id = CandidateOperationFactory._city_id(goal)
        if goal.deficit_predicate == "unit-fortification-opportunity":
            unit_ids = tuple(
                argument.entity_id for argument in goal.target_key.arguments
                if isinstance(argument, EntityRef) and argument.kind == "unit")
            return bool(
                len(unit_ids) == 1
                and action.get("action_type") == "unit_fortify"
                and str(action.get("actor_id")) == unit_ids[0])
        if city_id is not None:
            if goal.deficit_predicate == (
                    "city-replacement-capacity-deficit"):
                if (action.get("action_type") != "city_production"
                        or snapshot is None
                        or str(action.get("city_id")) != city_id):
                    return False
                production_type = str(
                    (action.get("target") or {}).get(
                        "production_type", "")).strip().lower().replace(
                            "_", " ")
                if production_type not in self._defender_types:
                    return False
                city = snapshot.city(city_id)
                return bool(
                    city is not None
                    and (
                        self.replacement_capacity_production_operations_enabled
                        or not (
                        action.get("production_kind") == city.production_kind
                        and action.get("production_value")
                        == city.production_value)))
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
        if action.get("action_type") != "unit_move":
            # Legacy production-defense candidates are protected comparison
            # routes, not unit-removal operations.  Their uncompiled causal
            # effect remains explicit and cannot authorize an action.
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

    def _replacement_capacity_production_assembly(
            self, snapshot, goal, action, action_key):
        """Ground queue selection without equating it to defender delivery."""
        from .domain_models import (
            DomainEstimateRequest,
            EstimateAuthority,
            EstimateValidity,
            GroundedProductionTransitionModel,
        )
        from .impact import ImpactCandidate
        from .production_operations import (
            ProductionEnablingIntent,
            ProductionEnablingOperationAssembler,
        )

        target = action.get("target")
        target_name = (
            target.get("production_type")
            if isinstance(target, dict) else None)
        fields = (
            action.get("city_id"),
            action.get("production_kind"),
            action.get("production_value"),
        )
        if (
                not isinstance(target_name, str)
                or not target_name
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in fields)
        ):
            return None, ("grounded-production-action-shape-invalid",)
        deadline = (
            int(snapshot.turn)
            + self._REPLACEMENT_CAPACITY_COMPLETION_HORIZON_TURNS)
        request_id = structural_hash({
            "action_key": action_key,
            "component": "fdas-replacement-capacity-production/1.0",
            "goal_id": goal.goal.goal_id,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "ruleset_digest": self.ruleset_digest,
            "snapshot_id": snapshot.snapshot_id,
        })
        candidate = ImpactCandidate(
            action=dict(action),
            category="production_defense",
            utility=float(goal.goal.weight_basis),
            rationale="grounded replacement-capacity shadow route",
            projection={})
        request = DomainEstimateRequest(
            request_id=request_id,
            snapshot=snapshot,
            ruleset_ir=self.ruleset_ir,
            legal_action=dict(action),
            candidate=candidate,
            goal_losses=((goal.goal.goal_id, 1.0),),
            operation_context=None,
            validity=EstimateValidity(
                snapshot_id=snapshot.snapshot_id,
                legal_actions_digest=snapshot.legal_actions_digest,
                ruleset_digest=self.ruleset_digest,
                estimated_at_turn=int(snapshot.turn),
                valid_through_turn=int(snapshot.turn)),
            horizon_turn=deadline)
        estimate = GroundedProductionTransitionModel().estimate(request)
        if estimate.authority == EstimateAuthority.ABSTAIN:
            return None, ("grounded-production-model-abstained",)
        artifact = estimate.to_dict().get("model_artifact")
        if not isinstance(artifact, dict):
            return None, ("grounded-production-model-abstained",)
        eta = artifact.get("completion_eta")
        if not isinstance(eta, dict):
            return None, ("production-completion-eta-unavailable",)
        latest_completion = eta.get("latest_completion_turn")
        if (
                isinstance(latest_completion, bool)
                or not isinstance(latest_completion, int)
        ):
            return None, ("production-completion-eta-unavailable",)
        if latest_completion > deadline:
            return None, (
                "production-completion-beyond-observation-horizon",)
        intent = ProductionEnablingIntent(
            operation_type=(
                "fdas-shadow:city-replacement-capacity-deficit:"
                "city_production"),
            city_id=int(fields[0]),
            production_kind=int(fields[1]),
            production_value=int(fields[2]),
            target_name=target_name,
            downstream_operation_id=(
                "fdas-replacement-capacity:{}".format(
                    goal.deficit_atom_id)),
            completion_deadline_turn=deadline,
            scheduling_bid=max(0.0, float(goal.goal.weight_basis)),
            emergency=False)
        assembly = ProductionEnablingOperationAssembler.assemble(
            snapshot, intent, estimate, (goal.goal.goal_id,),
            self.ruleset_digest)
        if assembly is None:
            return None, ("grounded-production-operation-unavailable",)
        return assembly, ("delayed-production-completion-unobserved",)

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
                    snapshot.turn, binding_identity=action_key)
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
                        max(1, int(replacement_route.path_length) + 1)),
                    OperationStep(
                        "step-" + structural_hash({
                            "operation_id": operation_id,
                            "phase": "reinforcement",
                        })[:28],
                        "unit_move", "reinforcement",
                        "city:{}".format(target_city_id),
                        target_requirement,
                        "city-defense:protected-defender-at-target-city",
                        max(1, int(target_route.path_length) + 1)),
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

    def instantiate_report(self, snapshot, goal_contexts, revision=None,
                           protected_action_keys=(),
                           protected_goal_routes=()):
        protected_action_keys = tuple(sorted(set(
            str(value) for value in protected_action_keys)))
        protected = frozenset(protected_action_keys)
        protected_goal_routes = frozenset(
            (str(action_key), str(predicate))
            for action_key, predicate in protected_goal_routes)
        legal = tuple(
            (json.loads(value), value) for value in snapshot.legal_action_json)
        candidates = []
        omitted_unprotected_count = 0
        for goal in goal_contexts:
            accepted_types = self._ACTION_TYPES.get(
                goal.deficit_predicate, frozenset())
            matching = []
            for action, action_key in legal:
                action_type = str(action.get("action_type"))
                control_routed = (
                    action_key, goal.deficit_predicate
                ) in protected_goal_routes
                native_routed = (
                    action_type in accepted_types
                    and self._action_matches(
                        goal, action, snapshot.player_id, snapshot))
                if control_routed:
                    city_id = self._city_id(goal)
                    control_routed = bool(
                        city_id is None
                        or str(action.get("city_id")) == city_id)
                if not native_routed and not control_routed:
                    continue
                matching.append((action, action_key, control_routed))
            matching = tuple(sorted(matching, key=lambda value: value[1]))
            protected_matching = tuple(
                value for value in matching if value[1] in protected)
            optional = tuple(
                value for value in matching if value[1] not in protected)
            selected = protected_matching + optional[
                :self.maximum_unprotected_candidates_per_goal]
            omitted_unprotected_count += max(
                0, len(optional)
                - self.maximum_unprotected_candidates_per_goal)
            for action, action_key, control_routed in selected:
                action_type = str(action.get("action_type"))
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
                    binding_identity=action_key,
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
                latest_turn = int(snapshot.turn) + 1
                route_window_grounded = False
                if (goal.deficit_predicate == "city-garrison-deficit"
                        and action_type == "unit_move"
                        and city_id is not None):
                    city = snapshot.city(city_id)
                    route = snapshot.movement_route(
                        action.get("actor_id"),
                        None if city is None else city.tile)
                    if (route is not None and route.reachable
                            and isinstance(route.estimated_turns, int)
                            and not isinstance(route.estimated_turns, bool)
                            and route.estimated_turns > 0):
                        latest_turn = int(snapshot.turn) + max(
                            1, int(route.estimated_turns))
                        route_window_grounded = True
                operation = OperationSpec(
                    OPERATION_SCHEMA_VERSION,
                    operation_id,
                    operation_type,
                    (goal.goal.goal_id,),
                    (participant,),
                    target_ref,
                    (step,),
                    int(snapshot.turn),
                    latest_turn,
                    0.0,
                    (
                        "fdas-city-economy-shadow/1.0",
                        "current-byte-identical-legal-action",
                        "no-action-authority",
                    ) + (("server-route-goal-relief-window",)
                         if route_window_grounded else ()),
                    self.ruleset_digest,
                )
                production_assembly = None
                if (
                        self.replacement_capacity_production_operations_enabled
                        and goal.deficit_predicate
                        == "city-replacement-capacity-deficit"
                        and action_type == "city_production"
                ):
                    production_assembly, blockers = (
                        self._replacement_capacity_production_assembly(
                            snapshot, goal, action, action_key))
                    if production_assembly is not None:
                        operation = production_assembly.spec
                else:
                    blockers = self._route_blockers(goal, action, snapshot)
                if control_routed:
                    blockers = tuple(sorted(set(blockers).union((
                        "legacy-shadow-control-route-uncompiled",))))
                provenance = (
                    "fdas-city-economy-shadow/1.0",
                    "ruleset-ir-action-schema/2.0",
                ) + ((
                    "fdas-replacement-capacity-production/1.0",
                    "grounded-production-transition-model",
                    "queue-selection-is-not-goal-relief",
                    "authoritative-product-observation-required",
                ) if production_assembly is not None else ()) + ((
                    "legacy-impact-control-route/1.0",)
                    if control_routed else ())
                semantic = {
                    "action_key": action_key,
                    "blockers": list(blockers),
                    "goal_id": goal.goal.goal_id,
                    "operation": operation.to_dict(),
                    "production_assembly": (
                        None if production_assembly is None
                        else production_assembly.to_dict()),
                    "provenance": list(provenance),
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
                    provenance,
                    structural_hash(semantic),
                    production_assembly=production_assembly,
                ))
        candidates.extend(self._coordinated_replacement_candidates(
            snapshot, goal_contexts, revision))
        candidates = tuple(sorted(
            candidates,
            key=lambda value: (
                value.operation.operation_id, value.action_key)))
        diagnostics = (() if not omitted_unprotected_count else (
            "unprotected-candidate-budget-exhausted:{}".format(
                omitted_unprotected_count),))
        control_route_count = sum(
            "legacy-shadow-control-route-uncompiled" in candidate.blockers
            for candidate in candidates)
        if control_route_count:
            diagnostics += (
                "legacy-shadow-control-routes:{}".format(
                    control_route_count),)
        semantic = {
            "candidate_hashes": [
                value.candidate_hash for value in candidates],
            "diagnostics": list(diagnostics),
            "omitted_unprotected_count": omitted_unprotected_count,
            "protected_action_keys": list(protected_action_keys),
            "protected_goal_routes": [
                list(value) for value in sorted(protected_goal_routes)],
            "snapshot_id": snapshot.snapshot_id,
        }
        return CandidateInstantiation(
            candidates, omitted_unprotected_count, protected_action_keys,
            diagnostics, structural_hash(semantic))

    def instantiate(self, snapshot, goal_contexts, revision=None,
                    protected_action_keys=(), protected_goal_routes=()):
        return self.instantiate_report(
            snapshot, goal_contexts, revision,
            protected_action_keys, protected_goal_routes).candidates
