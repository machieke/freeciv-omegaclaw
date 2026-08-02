"""Rich component-only city/economy FDAS projection and local facts."""

import json
from dataclasses import dataclass, replace

from ...events.schema import structural_hash
from .composite import ProjectionShardSpec
from .delta import snapshot_dependency_ref
from .grounding import TypedGroundingRegistry
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_CRISP = {"confidence": 1.0, "crisp": True, "strength": 1.0}
_CRISP_HASH = structural_hash(_CRISP)


@dataclass(frozen=True)
class CityEconomyPolicy:
    food_surplus_reserve: int = 1
    treasury_reserve_turns: int = 2
    treasury_minimum_gold: int = 5
    schema_version: str = "1.0"

    def __post_init__(self):
        for value, name, lower, upper in (
                (self.food_surplus_reserve, "food surplus reserve", 0, 10),
                (self.treasury_reserve_turns, "treasury reserve turns", 1, 20),
                (self.treasury_minimum_gold, "treasury minimum gold", 0, 1000)):
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not lower <= value <= upper):
                raise ValueError("{} must be in {}..{}".format(
                    name, lower, upper))

    @property
    def food_policy_id(self):
        return "food-surplus-reserve:{}:v{}".format(
            self.food_surplus_reserve, self.schema_version)

    @property
    def treasury_policy_id(self):
        return "treasury:min{}:runway{}:v{}".format(
            self.treasury_minimum_gold,
            self.treasury_reserve_turns,
            self.schema_version,
        )

    def dependency_refs(self):
        owner = "fdas-city-economy-policy:{}".format(self.schema_version)
        rows = {
            "food_surplus_reserve": self.food_surplus_reserve,
            "treasury_minimum_gold": self.treasury_minimum_gold,
            "treasury_reserve_turns": self.treasury_reserve_turns,
        }
        return tuple(
            DependencyRef(
                DependencyKey("policy", owner, name), structural_hash(value))
            for name, value in sorted(rows.items()))


def _spec(predicate, arguments, namespaces, scopes, truth="crisp",
          completeness="explicit-witness", export="parent-summary"):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset(namespaces),
        truth,
        frozenset(scopes),
        completeness,
        export,
        "1.0",
    )


def city_economy_predicate_registry():
    authoritative = (AtomNamespace.AUTHORITATIVE,)
    derived = (AtomNamespace.DERIVED,)
    return legacy_predicate_registry().extended((
        _spec("active-government", (("player",), ("government",)),
              authoritative, ("empire",), completeness="closed"),
        _spec("current-player", (("player",),), authoritative,
              ("empire",), completeness="closed", export="global"),
        _spec("current-turn", (("player",), ("turn",)), authoritative,
              ("empire",), completeness="closed", export="global"),
        _spec("research-target", (("player",), ("technology",)),
              authoritative, ("empire",), completeness="closed"),
        _spec("city-has-building", (("city",), ("building-type",)),
              authoritative, ("city-facts",), completeness="closed"),
        _spec("city-governor-active", (("city",), ("governor-policy",)),
              authoritative, ("city-facts",), completeness="closed"),
        _spec("city-in-disorder", (("city",),), authoritative,
              ("city-facts",), completeness="closed"),
        _spec("city-famine-recorded", (("city",),), authoritative,
              ("city-facts",), completeness="closed"),
        _spec("legal-action-for", (
            ("action",), ("player", "city", "unit")), authoritative,
            ("empire",), completeness="closed"),
        _spec("legal-action-type", (("action",), ("action-type",)),
              authoritative, ("empire",), completeness="closed"),
        _spec("city-food-secure", (("city",), ("food-policy",)), derived,
              ("city-facts",)),
        _spec("city-food-deficit", (("city",), ("food-policy",)), derived,
              ("city-facts",)),
        _spec("city-order-stable", (("city",),), derived,
              ("city-facts",)),
        _spec("city-order-deficit", (("city",),), derived,
              ("city-facts",)),
        _spec("city-production-active", (("city",),), derived,
              ("city-facts",)),
        _spec("city-production-stalled", (("city",),), derived,
              ("city-facts",)),
        _spec("city-queue-funded", (
            ("city",), ("production-target",)), derived, ("city-facts",)),
        _spec("city-queue-unfunded", (
            ("city",), ("production-target",)), derived, ("city-facts",)),
        _spec("treasury-below-reserve", (
            ("player",), ("treasury-policy",)), derived, ("empire",)),
        _spec("treasury-structurally-safe", (
            ("player",), ("treasury-policy",)), derived, ("empire",)),
        _spec("research-throughput-active", (("player",),), derived,
              ("empire",)),
        _spec("research-throughput-stalled", (("player",),), derived,
              ("empire",)),
    ))


def city_economy_scopes(snapshot):
    world, empire = snapshot_scopes(snapshot)
    registry = city_economy_predicate_registry()
    empire = replace(
        empire,
        namespaces=frozenset((
            AtomNamespace.AUTHORITATIVE, AtomNamespace.DERIVED)),
        exported_predicates=tuple(sorted(set(empire.exported_predicates).union(
            predicate for predicate in registry.predicates
            if predicate in (
                "treasury-below-reserve", "treasury-structurally-safe",
                "research-throughput-active", "research-throughput-stalled")))),
    )
    scopes = [world, empire]
    for city in sorted(snapshot.cities, key=lambda value: value.city_id):
        scopes.append(ScopeSpec(
            "{}:city:{}:facts".format(
                empire.scope_id.rsplit(":empire", 1)[0], city.city_id),
            "city-facts",
            snapshot.player_id,
            (EntityRef("city", str(city.city_id)),),
            (empire.scope_id,),
            ("active-government", "owns-city"),
            tuple(sorted(predicate for predicate in registry.predicates
                         if predicate.startswith("city-"))),
            frozenset((AtomNamespace.AUTHORITATIVE, AtomNamespace.DERIVED)),
            500,
            2000,
            1000,
            2,
            "snapshot-revision",
            empire.validity,
        ))
    return tuple(scopes)


def _scope_map(scopes):
    empire = next(value for value in scopes if value.scope_kind == "empire")
    cities = dict(
        (value.root_entities[0].entity_id, value)
        for value in scopes if value.scope_kind == "city-facts")
    return empire, cities


def _support(derivation, binding, dependencies, witness, provenance,
             version="1.0"):
    return SupportRecord.create(
        derivation, version, binding, tuple(sorted(set(dependencies))), witness,
        (provenance,))


def _record(scope, namespace, predicate, arguments, authority, validity,
            support, provenance, tags=()):
    key = AtomKey(namespace, predicate, tuple(arguments), scope.scope_id)
    return AtomRecord.create(
        key, authority, _CRISP, validity, (support,), (provenance,),
        tags=tags, truth_hash=_CRISP_HASH)


class CityEconomyProjector(object):
    """Cold-reference rich projection; no policy or action authority."""

    projector_id = "fdas-city-economy-shadow"
    version = "1.0"
    incremental_dependency_roots = frozenset((
        "cities", "economy", "government", "legal_actions", "player_id",
        "research", "turn", "units",
    ))
    incremental_dependency_kinds = frozenset(("policy", "ruleset-digest"))

    def __init__(self, ruleset_ir=None, ruleset_digest=None, policy=None):
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self.policy = policy or CityEconomyPolicy()
        self.groundings = TypedGroundingRegistry(
            ruleset_ir, ruleset_digest=ruleset_digest)
        self.predicate_registry = city_economy_predicate_registry()

    def scopes(self, snapshot):
        return city_economy_scopes(snapshot)

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for dependency in self.policy.dependency_refs():
            result[dependency.key] = dependency.fingerprint
        if self.ruleset_digest:
            for grounding in ("city.production-cost", "city.production-eta"):
                key = DependencyKey(
                    "ruleset-digest", self.ruleset_digest, grounding)
                result[key] = structural_hash(self.ruleset_digest)
            for rule in (self.ruleset_ir.rules if self.ruleset_ir else ()):
                kinds = (rule.target_kind,)
                if rule.target_kind == "building":
                    kinds += ("improvement",)
                for kind in kinds:
                    for label in {
                            rule.rule_name,
                            getattr(rule, "display_name", None)}:
                        if not label:
                            continue
                        key = DependencyKey(
                            "ruleset-digest", self.ruleset_digest,
                            "target:{}:{}".format(kind, label))
                        result[key] = structural_hash({
                            "ruleset_digest": self.ruleset_digest,
                            "target_kind": kind,
                            "target": label,
                        })
        return result

    @staticmethod
    def _snapshot_dep(snapshot, path, fingerprints):
        return snapshot_dependency_ref(snapshot, path, fingerprints)

    def _base(self, snapshot, scope, predicate, arguments, paths,
              fingerprints):
        dependencies = tuple(
            self._snapshot_dep(snapshot, path, fingerprints) for path in paths)
        key = AtomKey(
            AtomNamespace.AUTHORITATIVE, predicate, tuple(arguments),
            scope.scope_id)
        support = _support(
            self.projector_id, key.to_dict(), dependencies,
            {"atom": key.to_dict(), "paths": list(paths)},
            self.projector_id, self.version)
        return _record(
            scope, AtomNamespace.AUTHORITATIVE, predicate, arguments,
            AuthorityClass.ENGINE_AUTHORITATIVE, scope.validity, support,
            self.projector_id, (("domain", "city-economy-shadow"),))

    def _derived(self, scope, predicate, arguments, grounding_results,
                 policy_refs=(), witness=None):
        dependencies = tuple(
            dependency for result in grounding_results
            for dependency in result.dependencies) + tuple(policy_refs)
        key = AtomKey(
            AtomNamespace.DERIVED, predicate, tuple(arguments), scope.scope_id)
        grounding_hashes = tuple(
            result.result_hash for result in grounding_results)
        semantic_witness = {
            "completeness": "authoritative-field-present",
            "grounding_result_hashes": list(grounding_hashes),
            "predicate": predicate,
            "witness": witness,
        }
        support = _support(
            "derive-{}".format(predicate), key.to_dict(), dependencies,
            semantic_witness, self.projector_id, self.version)
        return _record(
            scope, AtomNamespace.DERIVED, predicate, arguments,
            AuthorityClass.DETERMINISTIC_DERIVED, scope.validity, support,
            self.projector_id, (("domain", "city-economy-shadow"),))

    @staticmethod
    def _current_production(city):
        expected_kind = {"unit": 6, "improvement": 3}
        return next((
            (str(kind), str(name))
            for kind, item_id, name in city.buildable
            if (expected_kind.get(str(kind).lower()) == city.production_kind
                and int(item_id) == city.production_value)
        ), None)

    def _target_upkeep(self, kind, target):
        target_kind = "building" if kind == "improvement" else kind
        rules = tuple(
            rule for rule in (self.ruleset_ir.rules if self.ruleset_ir else ())
            if rule.target_kind == target_kind and target in {
                rule.rule_name, getattr(rule, "display_name", None)})
        if not rules:
            return 0, 0

        def value(name):
            values = []
            for rule in rules:
                row = rule.quantitative.get(name)
                if row is not None:
                    values.append(int(
                        row["value"] if isinstance(row, dict) else row))
            return values[0] if values and len(set(values)) == 1 else 0

        return value("uk_food"), value("uk_gold")

    @staticmethod
    def _legal_actor(action, player_id):
        if "city_id" in action:
            return EntityRef("city", str(action["city_id"]))
        if "actor_id" in action:
            kind = "player" if action.get("action_type") in (
                "player_rates", "tech_research", "government_change") else "unit"
            return EntityRef(kind, str(action["actor_id"]))
        return EntityRef("player", str(player_id))

    def projection_shards(self, scopes):
        """Split global facts from stable per-city factual microspaces."""
        empire, city_scopes = _scope_map(scopes)
        kinds = self.incremental_dependency_kinds
        shards = [ProjectionShardSpec(
            "empire",
            (
                "cities", "economy", "government", "legal_actions",
                "player_id", "research", "turn", "units",
            ),
            kinds,
            (empire.scope_id,),
        )]
        shards.extend(
            ProjectionShardSpec(
                "city:{}".format(city_id),
                (
                    "cities.{}".format(city_id), "economy", "player_id",
                    "units",
                ),
                kinds,
                (scope.scope_id,),
            )
            for city_id, scope in sorted(city_scopes.items()))
        return tuple(shards)

    def _project_empire(self, snapshot, empire, fingerprints):
        player = EntityRef("player", str(snapshot.player_id))
        records = []
        records.append(self._base(
            snapshot, empire, "current-player", (player,), ("player_id",),
            fingerprints))
        records.append(self._base(
            snapshot, empire, "current-turn",
            (player, SymbolRef("turn", "turn:{}".format(snapshot.turn))),
            ("turn",), fingerprints))
        if snapshot.research.target_name:
            records.append(self._base(
                snapshot, empire, "research-target",
                (player, EntityRef(
                    "technology", str(snapshot.research.target_name))),
                ("research.target_name",), fingerprints))
        if snapshot.government.current_name:
            records.append(self._base(
                snapshot, empire, "active-government",
                (player, EntityRef(
                    "government", str(snapshot.government.current_name))),
                ("government.current_name",), fingerprints))
        for action_json in snapshot.legal_action_json:
            action = json.loads(action_json)
            action_hash = structural_hash(action_json)
            action_ref = EntityRef(
                "action", "legal-" + action_hash[:24])
            dependency_path = "legal_actions.{}".format(
                action_hash)
            actor = self._legal_actor(action, snapshot.player_id)
            action_type = SymbolRef(
                "action-type", str(action.get("action_type")))
            dependency = self._snapshot_dep(
                snapshot, dependency_path, fingerprints)
            support = SupportRecord.from_hashes(
                self.projector_id, self.version, action_hash, (dependency,),
                structural_hash({
                    "action": action_ref.to_dict(),
                    "actor": actor.to_dict(),
                    "action_type": action_type.to_dict(),
                }), (self.projector_id,))
            for predicate, arguments in (
                    ("legal-action-for", (action_ref, actor)),
                    ("legal-action-type", (action_ref, action_type))):
                records.append(_record(
                    empire, AtomNamespace.AUTHORITATIVE, predicate,
                    arguments, AuthorityClass.ENGINE_AUTHORITATIVE,
                    empire.validity, support, self.projector_id,
                    (("domain", "city-economy-shadow"),)))

        policy_refs = self.policy.dependency_refs()
        treasury_policy = SymbolRef(
            "treasury-policy", self.policy.treasury_policy_id)
        gold = self.groundings.evaluate(
            "economy.gold-stockpile", snapshot, snapshot.player_id)
        net = self.groundings.evaluate(
            "economy.net-gpt", snapshot, snapshot.player_id)
        upkeep = self.groundings.evaluate(
            "economy.turn-start-upkeep-reserve", snapshot,
            snapshot.player_id)
        if gold.available and net.available and upkeep.available:
            reserve = max(
                self.policy.treasury_minimum_gold,
                int(upkeep.value) * self.policy.treasury_reserve_turns)
            deficit = bool(
                int(gold.value) < reserve
                or (int(net.value) < 0
                    and int(gold.value) + int(net.value)
                    * self.policy.treasury_reserve_turns < reserve))
            records.append(self._derived(
                empire,
                "treasury-below-reserve" if deficit
                else "treasury-structurally-safe",
                (player, treasury_policy), (gold, net, upkeep),
                policy_refs[1:], {
                    "gold": gold.value,
                    "net_gpt": net.value,
                    "reserve": reserve,
                }))
        beakers = self.groundings.evaluate(
            "research.beakers-per-turn", snapshot, snapshot.player_id)
        if beakers.available:
            records.append(self._derived(
                empire,
                "research-throughput-active" if int(beakers.value) > 0
                else "research-throughput-stalled",
                (player,), (beakers,), witness={
                    "observed_beakers_per_turn": beakers.value,
                }))
        return tuple(records)

    def _project_city(self, snapshot, city, scope, fingerprints):
        records = []
        city_id = str(city.city_id)
        city_ref = EntityRef("city", city_id)
        if city.disorder is True:
            records.append(self._base(
                snapshot, scope, "city-in-disorder", (city_ref,),
                ("cities.{}.disorder".format(city_id),), fingerprints))
        if city.had_famine is True:
            records.append(self._base(
                snapshot, scope, "city-famine-recorded", (city_ref,),
                ("cities.{}.had_famine".format(city_id),), fingerprints))
        if city.governor_enabled is True:
            records.append(self._base(
                snapshot, scope, "city-governor-active",
                (city_ref, SymbolRef(
                    "governor-policy", "server-current")),
                ("cities.{}.governor.enabled".format(city_id),),
                fingerprints))
        for building in city.buildings:
            records.append(self._base(
                snapshot, scope, "city-has-building",
                (city_ref, EntityRef("building-type", building.name)),
                ("cities.{}.buildings".format(city_id),), fingerprints))

        policy_refs = self.policy.dependency_refs()
        food_policy = SymbolRef("food-policy", self.policy.food_policy_id)
        food = self.groundings.evaluate(
            "city.food-surplus", snapshot, city.city_id)
        if food.available:
            predicate = (
                "city-food-secure"
                if int(food.value) >= self.policy.food_surplus_reserve
                else "city-food-deficit")
            records.append(self._derived(
                scope, predicate, (city_ref, food_policy), (food,),
                (policy_refs[0],), {
                    "minimum": self.policy.food_surplus_reserve,
                    "observed": food.value,
                }))
        disorder = self.groundings.evaluate(
            "city.disorder-active", snapshot, city.city_id)
        if disorder.available:
            records.append(self._derived(
                scope,
                "city-order-deficit" if disorder.value
                else "city-order-stable",
                (city_ref,), (disorder,), witness={
                    "closed_field": "city.disorder",
                    "observed": disorder.value,
                }))
        shields = self.groundings.evaluate(
            "city.shield-surplus", snapshot, city.city_id)
        if shields.available:
            records.append(self._derived(
                scope,
                "city-production-active" if int(shields.value) > 0
                else "city-production-stalled",
                (city_ref,), (shields,), witness={
                    "observed_shields_per_turn": shields.value,
                }))

        current = self._current_production(city)
        if current is not None and self.ruleset_digest is not None:
            target_kind, target_name = current
            eta = self.groundings.evaluate(
                "city.production-eta", snapshot, city.city_id,
                target_kind, target_name)
            gold = self.groundings.evaluate(
                "economy.gold-stockpile", snapshot, snapshot.player_id)
            net = self.groundings.evaluate(
                "economy.net-gpt", snapshot, snapshot.player_id)
            upkeep = self.groundings.evaluate(
                "economy.turn-start-upkeep-reserve", snapshot,
                snapshot.player_id)
            food_upkeep, gold_upkeep = self._target_upkeep(
                target_kind, target_name)
            inputs_available = all(value.available for value in (
                eta, gold, net, upkeep, food))
            reserve = max(
                self.policy.treasury_minimum_gold,
                (int(upkeep.value) + gold_upkeep)
                * self.policy.treasury_reserve_turns,
            ) if inputs_available else None
            eta_value = eta.value if eta.available else None
            funded = bool(
                inputs_available
                and eta_value is not None
                and int(food.value) - food_upkeep
                >= self.policy.food_surplus_reserve
                and int(gold.value) + int(net.value) * int(eta_value)
                >= reserve)
            records.append(self._derived(
                scope,
                "city-queue-funded" if funded
                else "city-queue-unfunded",
                (city_ref, EntityRef(
                    "production-target", target_name)),
                (eta, gold, net, upkeep, food),
                policy_refs,
                {
                    "completion_eta": eta_value,
                    "food_surplus_after_upkeep": (
                        int(food.value) - food_upkeep
                        if food.available else None),
                    "gold_upkeep": gold_upkeep,
                    "reserve_at_completion": reserve,
                    "target_kind": target_kind,
                    "target_name": target_name,
                }))
        return tuple(records)

    def project_shard(self, shard_id, snapshot, scopes, fingerprints):
        self.groundings.prime(snapshot, fingerprints)
        empire, city_scopes = _scope_map(scopes)
        if shard_id == "empire":
            records = self._project_empire(snapshot, empire, fingerprints)
        elif str(shard_id).startswith("city:"):
            city_id = str(shard_id).split(":", 1)[1]
            city = snapshot.city(city_id)
            if city is None or city_id not in city_scopes:
                raise ValueError(
                    "city projection shard has no current city scope")
            records = self._project_city(
                snapshot, city, city_scopes[city_id], fingerprints)
        else:
            raise ValueError("unknown city/economy projection shard")
        return tuple(sorted(records, key=lambda value: value.atom_id))

    def project(self, snapshot, scopes, fingerprints):
        self.groundings.prime(snapshot, fingerprints)
        empire, city_scopes = _scope_map(scopes)
        records = list(self._project_empire(
            snapshot, empire, fingerprints))
        for city in sorted(snapshot.cities, key=lambda value: value.city_id):
            records.extend(self._project_city(
                snapshot, city, city_scopes[str(city.city_id)], fingerprints))
        return tuple(sorted(records, key=lambda value: value.atom_id))
