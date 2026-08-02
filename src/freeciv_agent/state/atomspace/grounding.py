"""Typed dependency-declaring groundings for rich FDAS domain scopes."""

import math
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase

from ...events.schema import structural_hash
from .delta import snapshot_dependency_fingerprints, snapshot_dependency_ref
from .model import DependencyKey, DependencyRef


class GroundingAuthority(str, Enum):
    SNAPSHOT_EXACT = "snapshot_exact"
    RULESET_EXACT = "ruleset_exact"
    SERVER_EXACT = "server_exact"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    CONTROL_MODEL = "control_model"


@dataclass(frozen=True)
class GroundingSpec:
    grounding_id: str
    version: str
    input_schema: tuple
    output_schema: str
    units: object
    authority: GroundingAuthority
    deterministic: bool
    cache_policy: str
    dependency_paths: tuple
    confidence_cap: object = None
    residual_unknown_required: bool = False

    def __post_init__(self):
        for value, name in (
                (self.grounding_id, "grounding ID"),
                (self.version, "grounding version"),
                (self.output_schema, "grounding output schema")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        object.__setattr__(self, "input_schema", tuple(self.input_schema))
        object.__setattr__(
            self, "authority", GroundingAuthority(self.authority))
        object.__setattr__(
            self, "dependency_paths", tuple(self.dependency_paths))
        if self.cache_policy not in (
                "revision", "turn", "persistent-static", "none"):
            raise ValueError("invalid grounding cache policy")
        if self.confidence_cap is not None:
            cap = float(self.confidence_cap)
            if not 0.0 <= cap <= 1.0:
                raise ValueError("grounding confidence cap must be in 0..1")
        if (self.authority == GroundingAuthority.CONTROL_MODEL
                and not self.residual_unknown_required):
            raise ValueError(
                "control-model grounding requires residual unknown mass")


@dataclass(frozen=True)
class GroundingResult:
    grounding_id: str
    version: str
    arguments: tuple
    value: object
    units: object
    authority: GroundingAuthority
    snapshot_id: str
    ruleset_digest: object
    dependencies: tuple
    witness: object
    result_hash: str
    available: bool = True
    diagnostic: object = None
    confidence_cap: object = None

    def __post_init__(self):
        object.__setattr__(self, "arguments", tuple(self.arguments))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(
            self, "authority", GroundingAuthority(self.authority))

    def to_dict(self):
        return {
            "arguments": list(self.arguments),
            "authority": self.authority.value,
            "available": self.available,
            "confidence_cap": self.confidence_cap,
            "dependencies": [value.to_dict() for value in self.dependencies],
            "diagnostic": self.diagnostic,
            "grounding_id": self.grounding_id,
            "result_hash": self.result_hash,
            "ruleset_digest": self.ruleset_digest,
            "snapshot_id": self.snapshot_id,
            "units": self.units,
            "value": self.value,
            "version": self.version,
            "witness": self.witness,
        }


def _spec(name, inputs, output, units, paths,
          authority=GroundingAuthority.SNAPSHOT_EXACT):
    return GroundingSpec(
        name, "1.0", tuple(inputs), output, units, authority, True,
        "revision", tuple(paths))


CITY_ECONOMY_GROUNDING_SPECS = (
    _spec("city.food-stock", ("city",), "integer", "food",
          ("cities.{city}.food_stock",)),
    _spec("city.food-produced", ("city",), "integer", "food/turn",
          ("cities.{city}.production.0",)),
    _spec("city.food-used", ("city",), "integer", "food/turn",
          ("cities.{city}.usage.0",)),
    _spec("city.food-surplus", ("city",), "integer", "food/turn",
          ("cities.{city}.surplus.0",)),
    _spec("city.shield-stock", ("city",), "integer", "shields",
          ("cities.{city}.shield_stock",)),
    _spec("city.shield-produced", ("city",), "integer", "shields/turn",
          ("cities.{city}.production.1",)),
    _spec("city.shield-used", ("city",), "integer", "shields/turn",
          ("cities.{city}.usage.1",)),
    _spec("city.shield-surplus", ("city",), "integer", "shields/turn",
          ("cities.{city}.surplus.1",)),
    _spec("city.output-vector", ("city",), "integer-vector", "output/turn",
          ("cities.{city}.production", "cities.{city}.surplus",
           "cities.{city}.usage")),
    _spec("city.disorder-active", ("city",), "boolean", None,
          ("cities.{city}.disorder",)),
    _spec("city.buildability", ("city", "target-kind", "target"),
          "boolean", None,
          ("cities.{city}.buildability_available",
           "cities.{city}.buildable")),
    _spec("city.production-cost", ("city", "target-kind", "target"),
          "integer", "shields", (), GroundingAuthority.RULESET_EXACT),
    _spec("city.production-eta", ("city", "target-kind", "target"),
          "integer-or-unknown", "turns",
          ("cities.{city}.shield_stock", "cities.{city}.surplus.1"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("economy.gold-stockpile", ("player",), "integer", "gold",
          ("economy.gold",)),
    _spec("economy.gross-gpt", ("player",), "integer", "gold/turn",
          ("economy.city_gold_surplus_per_turn",)),
    _spec("economy.net-gpt", ("player",), "integer", "gold/turn",
          ("economy.gold_per_turn", "economy.gold_upkeep_style",
           "economy.city_gold_surplus_per_turn", "economy.unit_gold_upkeep",
           "cities", "units"), GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("economy.turn-start-upkeep-reserve", ("player",), "integer",
          "gold", ("economy.gold_upkeep_reserve",
                   "economy.unit_gold_upkeep", "units"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("economy.operating-runway", ("player",), "number-or-unbounded",
          "turns", ("economy.gold", "economy.operating_gold_per_turn"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("economy.rate-tuple", ("player",), "integer-vector", "percent",
          ("economy.tax_rate", "economy.science_rate",
           "economy.luxury_rate")),
    _spec("research.progress", ("player",), "integer", "beakers",
          ("research.progress",)),
    _spec("research.cost", ("player",), "integer", "beakers",
          ("research.cost",)),
    _spec("research.beakers-per-turn", ("player",), "integer",
          "beakers/turn", ("research.beakers_per_turn",)),
    _spec("research.completion-eta", ("player",), "integer-or-unknown",
          "turns", ("research.progress", "research.cost",
                    "research.beakers_per_turn"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
)


UNIT_DEFENSE_GROUNDING_SPECS = (
    _spec("unit.combat-profile", ("unit",), "combat-profile", None,
          ("units.{unit}.type",), GroundingAuthority.RULESET_EXACT),
    _spec("unit.persistent-defender", ("unit",), "boolean", None,
          ("units.{unit}.type",),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("city.required-garrison-count", ("city", "policy-limit"),
          "integer", "units",
          ("cities.{city}.disorder", "cities.{city}.size",
           "cities.{city}.citizen_mood.happy",
           "cities.{city}.citizen_mood.unhappy",
           "cities.{city}.citizen_mood.angry"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("city.local-garrison-count", ("city",), "integer", "units",
          ("cities.{city}.tile", "units.__members__",
           "units.*.tile", "units.*.type"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
    _spec("movement.shortest-route", ("unit", "destination-tile"),
          "route-or-unknown", None,
          ("source_seq", "movement_routes.{route}.*"),
          GroundingAuthority.SERVER_EXACT),
    _spec("movement.arrival-eta", ("unit", "destination-tile"),
          "integer-or-unknown", "turns",
          ("source_seq", "movement_routes.{route}.*"),
          GroundingAuthority.SERVER_EXACT),
    GroundingSpec(
        "defense.visible-threat-eta", "1.0", ("city", "enemy-unit"),
        "threat-eta-estimate", "turns", GroundingAuthority.CONTROL_MODEL,
        True, "revision", (
            "cities.{city}.x", "cities.{city}.y",
            "visible_enemy_units.{enemy}.x",
            "visible_enemy_units.{enemy}.y",
            "visible_enemy_units.{enemy}.type",
            "map_width", "map_height", "map_wrap_x", "map_wrap_y",
            "turn"),
        confidence_cap=0.45,
        residual_unknown_required=True,
    ),
    _spec("defense.removal-deficit", ("unit", "policy-limit"),
          "removal-deficit", "units",
          ("units.{unit}.tile", "cities.__members__",
           "cities.*.tile", "cities.*.disorder", "cities.*.size",
           "cities.*.citizen_mood.happy",
           "cities.*.citizen_mood.unhappy",
           "cities.*.citizen_mood.angry",
           "units.__members__", "units.*.tile", "units.*.type"),
          GroundingAuthority.DETERMINISTIC_DERIVED),
)


ALL_GROUNDING_SPECS = (
    CITY_ECONOMY_GROUNDING_SPECS + UNIT_DEFENSE_GROUNDING_SPECS)


_EXPLICIT_PERSISTENT_DEFENDERS = frozenset((
    "mech. inf.", "alpine troops", "riflemen", "musketeers", "pikemen",
    "phalanx", "legion", "warriors"))


def persistent_defender_type(ruleset_ir, unit_type):
    """Return the shared ruleset-grounded durable garrison classification."""
    normalized = str(unit_type or "").strip().lower().replace("_", " ")
    if normalized in _EXPLICIT_PERSISTENT_DEFENDERS:
        return True
    rows = tuple(
        value for value in (ruleset_ir.rules if ruleset_ir is not None else ())
        if value.target_kind == "unit" and str(unit_type) in {
            value.rule_name, getattr(value, "display_name", None)})
    if len(rows) != 1:
        return False
    rule = rows[0]

    def numeric(name):
        value = rule.quantitative.get(name, 0)
        if isinstance(value, dict):
            value = value.get("value", 0)
        return (0 if isinstance(value, bool)
                or not isinstance(value, (int, float)) else value)

    class_trait = rule.traits.get("class", {})
    classes = class_trait.get("values", ()) if isinstance(
        class_trait, dict) else ()
    return bool(
        any(str(value).strip().lower() == "land" for value in classes)
        and numeric("defense") > 0
        and numeric("defense") >= numeric("attack"))


class TypedGroundingRegistry(object):
    """Evaluate exact/derived scalar functions with dependency witnesses."""

    def __init__(self, ruleset_ir=None, specs=ALL_GROUNDING_SPECS,
                 ruleset_digest=None):
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self._specs = dict((value.grounding_id, value) for value in specs)
        if len(self._specs) != len(tuple(specs)):
            raise ValueError("duplicate typed grounding ID")
        self._cache = {}
        self._fingerprint_cache = {}
        self._path_dependency_cache = {}
        self._evaluations = 0
        self._cache_hits = 0
        self._rules = {}
        self._persistent_defender_cache = {}
        if ruleset_ir is not None:
            for rule in ruleset_ir.rules:
                for label in {
                        rule.rule_name, getattr(rule, "display_name", None)}:
                    if label:
                        self._rules.setdefault(
                            (rule.target_kind, label), []).append(rule)

    @staticmethod
    def _normalized_type(value):
        return str(value or "").strip().lower().replace("_", " ")

    @staticmethod
    def _quantitative(rule, name):
        value = rule.quantitative.get(name, 0)
        if isinstance(value, dict):
            value = value.get("value", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        return max(0, int(value))

    def _unit_rule(self, unit_type):
        rows = tuple(self._rules.get(("unit", str(unit_type)), ()))
        if len(rows) != 1:
            raise LookupError("unit type has no unambiguous ruleset record")
        return rows[0]

    def _combat_profile(self, unit_type):
        rule = self._unit_rule(unit_type)
        class_trait = rule.traits.get("class", {})
        unit_class = tuple(sorted(
            str(value) for value in (
                class_trait.get("values", ())
                if isinstance(class_trait, dict) else ())))
        return {
            "attack": self._quantitative(rule, "attack"),
            "defense": self._quantitative(rule, "defense"),
            "firepower": self._quantitative(rule, "firepower"),
            "hitpoints": self._quantitative(rule, "hitpoints"),
            "move_rate": self._quantitative(rule, "move_rate"),
            "unit_class": list(unit_class),
        }

    def _persistent_defender(self, unit_type):
        key = str(unit_type)
        if key not in self._persistent_defender_cache:
            self._persistent_defender_cache[key] = persistent_defender_type(
                self.ruleset_ir, unit_type)
        return self._persistent_defender_cache[key]

    @staticmethod
    def _city_mood_margin(city):
        values = (
            city.feeling_happy, city.feeling_unhappy, city.feeling_angry)
        if not all(value for value in values):
            return None
        return (
            int(city.feeling_happy[-1])
            - int(city.feeling_unhappy[-1])
            - 2 * int(city.feeling_angry[-1]))

    @staticmethod
    def _city_martial_law_relief(city):
        unhappy = tuple(city.feeling_unhappy or ())
        angry = tuple(city.feeling_angry or ())
        if len(unhappy) < 5 or len(angry) < 5:
            return None
        before = int(unhappy[3]) + 2 * int(angry[3])
        after = int(unhappy[4]) + 2 * int(angry[4])
        return max(0, before - after)

    def _required_garrison(self, city, limit):
        limit = int(limit)
        if limit < 1:
            raise ValueError("garrison policy limit must be positive")
        if city.disorder is True:
            return min(limit, max(1, int(city.size or 1)))
        relief = self._city_martial_law_relief(city)
        margin = self._city_mood_margin(city)
        if relief is not None and margin is not None:
            return min(limit, max(1, max(0, relief - max(0, margin))))
        return 1

    @property
    def grounding_ids(self):
        return tuple(sorted(self._specs))

    def spec(self, grounding_id):
        try:
            return self._specs[str(grounding_id)]
        except KeyError:
            raise KeyError("unknown typed grounding: {}".format(grounding_id))

    def prime(self, snapshot, fingerprints):
        """Reuse the transaction's canonical snapshot fingerprints."""
        self._fingerprint_cache[snapshot.snapshot_id] = dict(fingerprints)
        if len(self._fingerprint_cache) > 8:
            evicted = tuple(self._fingerprint_cache)[:-8]
            for snapshot_id in evicted:
                self._fingerprint_cache.pop(snapshot_id, None)
            self._cache = dict(
                (key, value) for key, value in self._cache.items()
                if key[3] not in evicted)
            self._path_dependency_cache = dict(
                (key, value)
                for key, value in self._path_dependency_cache.items()
                if key[0] not in evicted)

    @property
    def metrics(self):
        return {
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "evaluations": self._evaluations,
        }

    @staticmethod
    def _city(snapshot, value):
        city = snapshot.city(value)
        if city is None:
            raise LookupError("unknown own city")
        return city

    @staticmethod
    def _index(values, index, name):
        values = tuple(values or ())
        if len(values) <= index:
            raise LookupError("{} is unavailable".format(name))
        return int(values[index])

    @staticmethod
    def _unit_gold_upkeep(snapshot):
        observed = sum(
            int(unit.upkeep[3]) if len(tuple(unit.upkeep or ())) > 3 else 0
            for unit in snapshot.units)
        declared = snapshot.economy.unit_gold_upkeep
        return observed if declared is None else max(observed, int(declared))

    @staticmethod
    def _city_gold_surplus(snapshot):
        declared = snapshot.economy.city_gold_surplus_per_turn
        if declared is not None:
            return int(declared)
        return sum(
            int(city.surplus[3]) if len(tuple(city.surplus or ())) > 3 else 0
            for city in snapshot.cities)

    def _build_cost(self, kind, target):
        normalized_kind = {
            "improvement": "building", "building": "building",
            "unit": "unit", "tech": "tech",
        }.get(str(kind).lower(), str(kind).lower())
        values = []
        for rule in self._rules.get((normalized_kind, str(target)), ()):
            item = rule.quantitative.get("build_cost")
            if item is not None:
                values.append(int(item["value"] if isinstance(item, dict)
                                  else item))
        if len(set(values)) != 1:
            raise LookupError("compiled target has no unambiguous build cost")
        return values[0]

    def _evaluate(self, grounding_id, snapshot, args):
        if grounding_id == "defense.removal-deficit":
            if len(args) != 2:
                raise ValueError(
                    "defense.removal-deficit expects unit and policy limit")
            actor = snapshot.unit(args[0])
            if actor is None:
                raise LookupError("unknown own unit")
            source_city = next((
                value for value in snapshot.cities
                if value.tile is not None and value.tile == actor.tile), None)
            if source_city is None:
                return {
                    "creates_deficit": False,
                    "current_city_id": None,
                    "current_garrison": 0,
                    "remaining_garrison": 0,
                    "required_garrison": 0,
                }
            current = sum(
                value.tile is not None
                and value.tile == source_city.tile
                and self._persistent_defender(value.unit_type)
                for value in snapshot.units)
            required = self._required_garrison(source_city, args[1])
            actor_counts = self._persistent_defender(actor.unit_type)
            remaining = max(0, current - (1 if actor_counts else 0))
            return {
                "creates_deficit": remaining < required,
                "current_city_id": source_city.city_id,
                "current_garrison": current,
                "remaining_garrison": remaining,
                "required_garrison": required,
            }
        if grounding_id == "defense.visible-threat-eta":
            if len(args) != 2:
                raise ValueError(
                    "defense.visible-threat-eta expects city and enemy unit")
            city = self._city(snapshot, args[0])
            enemy = snapshot.visible_enemy_unit(args[1])
            if enemy is None:
                raise LookupError("visible enemy unit is unavailable")
            if (None in (city.x, city.y, enemy.x, enemy.y,
                         snapshot.map_wrap_x, snapshot.map_wrap_y)
                    or snapshot.map_width <= 0 or snapshot.map_height <= 0):
                raise LookupError("exact map topology is unavailable")
            dx = abs(int(city.x) - int(enemy.x))
            dy = abs(int(city.y) - int(enemy.y))
            if snapshot.map_wrap_x:
                dx = min(dx, snapshot.map_width - dx)
            if snapshot.map_wrap_y:
                dy = min(dy, snapshot.map_height - dy)
            distance = max(dx, dy)
            move_rate = self._combat_profile(enemy.unit_type)["move_rate"]
            if (isinstance(move_rate, bool)
                    or not isinstance(move_rate, (int, float))
                    or float(move_rate) <= 0.0):
                raise LookupError("enemy movement rate is unavailable")
            approach_tiles = max(0, distance - 1)
            eta_turns = int(math.ceil(
                float(approach_tiles) / float(move_rate)))
            return {
                "basis": "ruleset-move-rate-geometric-lower-bound",
                "confidence": 0.45,
                "distance_tiles": distance,
                "earliest_attack_turn": int(snapshot.turn) + eta_turns,
                "eta_turns": eta_turns,
                "movement_rate": float(move_rate),
                "unknown_mass": 0.55,
            }
        if grounding_id.startswith("movement."):
            if len(args) != 2:
                raise ValueError(
                    "{} expects unit and destination tile".format(
                        grounding_id))
            route = snapshot.movement_route(args[0], args[1])
            if route is None:
                raise LookupError("native movement route is unavailable")
            actor = snapshot.unit(args[0])
            if (
                    route.authority != "freeciv-server-pathfinder"
                    or route.schema_version != "1.0"
                    or actor is None
                    or actor.tile != route.origin_tile
                    or route.turn != snapshot.turn
                    or route.source_seq > snapshot.identity.source_seq):
                raise LookupError(
                    "native movement route does not match current revision")
            if not route.reachable:
                raise LookupError("native movement route reports unreachable")
            if grounding_id == "movement.shortest-route":
                return route.to_dict()
            if grounding_id == "movement.arrival-eta":
                return int(route.estimated_turns)
            raise AssertionError(grounding_id)
        city = None
        if grounding_id.startswith("city."):
            if not args:
                raise ValueError("{} expects a city".format(grounding_id))
            city = self._city(snapshot, args[0])
        unit = None
        if grounding_id.startswith("unit."):
            if not args:
                raise ValueError("{} expects a unit".format(grounding_id))
            unit = snapshot.unit(args[0])
            if unit is None:
                raise LookupError("unknown own unit")
        if grounding_id == "unit.combat-profile":
            return self._combat_profile(unit.unit_type)
        if grounding_id == "unit.persistent-defender":
            return self._persistent_defender(unit.unit_type)
        if grounding_id == "city.required-garrison-count":
            if len(args) != 2:
                raise ValueError(
                    "city.required-garrison-count expects city and limit")
            return self._required_garrison(city, args[1])
        if grounding_id == "city.local-garrison-count":
            return sum(
                value.tile is not None
                and value.tile == city.tile
                and self._persistent_defender(value.unit_type)
                for value in snapshot.units)
        if grounding_id == "city.food-stock":
            if city.food_stock is None:
                raise LookupError("city food stock is unavailable")
            return int(city.food_stock)
        if grounding_id == "city.food-produced":
            return self._index(city.production, 0, "city food production")
        if grounding_id == "city.food-used":
            return self._index(city.usage, 0, "city food usage")
        if grounding_id == "city.food-surplus":
            return self._index(city.surplus, 0, "city food surplus")
        if grounding_id == "city.shield-stock":
            if city.shield_stock is None:
                raise LookupError("city shield stock is unavailable")
            return int(city.shield_stock)
        if grounding_id == "city.shield-produced":
            return self._index(city.production, 1, "city shield production")
        if grounding_id == "city.shield-used":
            return self._index(city.usage, 1, "city shield usage")
        if grounding_id == "city.shield-surplus":
            return self._index(city.surplus, 1, "city shield surplus")
        if grounding_id == "city.output-vector":
            return {
                "produced": list(city.production),
                "surplus": list(city.surplus),
                "used": list(city.usage),
            }
        if grounding_id == "city.disorder-active":
            if city.disorder is None:
                raise LookupError("city disorder state is unavailable")
            return bool(city.disorder)
        if grounding_id == "city.buildability":
            if len(args) != 3:
                raise ValueError("city.buildability expects city, kind, target")
            if not city.buildability_available:
                raise LookupError(city.buildability_diagnostic or
                                  "city buildability is unavailable")
            kind = str(args[1]).lower()
            target = str(args[2])
            aliases = {"building": "improvement", "improvement": "building"}
            return any(
                str(row_kind).lower() in (kind, aliases.get(kind))
                and str(row_name) == target
                for row_kind, _row_id, row_name in city.buildable)
        if grounding_id == "city.production-cost":
            if len(args) != 3:
                raise ValueError(
                    "city.production-cost expects city, kind, target")
            return self._build_cost(args[1], args[2])
        if grounding_id == "city.production-eta":
            if len(args) != 3:
                raise ValueError("city.production-eta expects city, kind, target")
            cost = self._build_cost(args[1], args[2])
            stock = int(city.shield_stock or 0)
            shields = self._index(city.surplus, 1, "city shield surplus")
            if stock >= cost:
                return 0
            if shields <= 0:
                return None
            return int(math.ceil((cost - stock) / float(shields)))
        if grounding_id == "economy.gold-stockpile":
            if snapshot.economy.gold is None:
                raise LookupError("gold stockpile is unavailable")
            return int(snapshot.economy.gold)
        if grounding_id == "economy.gross-gpt":
            return self._city_gold_surplus(snapshot)
        if grounding_id == "economy.net-gpt":
            economy = snapshot.economy
            if (economy.gold_per_turn is not None
                    and economy.gold_upkeep_style is not None):
                return int(economy.gold_per_turn)
            if economy.gold_upkeep_style == "City":
                return self._city_gold_surplus(snapshot)
            return self._city_gold_surplus(snapshot) - self._unit_gold_upkeep(snapshot)
        if grounding_id == "economy.turn-start-upkeep-reserve":
            return max(
                self._unit_gold_upkeep(snapshot),
                int(snapshot.economy.gold_upkeep_reserve or 0))
        if grounding_id == "economy.operating-runway":
            gold = snapshot.economy.gold
            operating = snapshot.economy.operating_gold_per_turn
            if gold is None or operating is None:
                raise LookupError("operating economy is unavailable")
            return None if int(operating) >= 0 else max(
                0.0, float(gold) / float(-int(operating)))
        if grounding_id == "economy.rate-tuple":
            values = (snapshot.economy.tax_rate,
                      snapshot.economy.science_rate,
                      snapshot.economy.luxury_rate)
            if any(value is None for value in values):
                raise LookupError("economy rates are unavailable")
            return tuple(int(value) for value in values)
        if grounding_id == "research.progress":
            value = snapshot.research.progress
        elif grounding_id == "research.cost":
            value = snapshot.research.cost
        elif grounding_id == "research.beakers-per-turn":
            value = snapshot.research.beakers_per_turn
        elif grounding_id == "research.completion-eta":
            progress = snapshot.research.progress
            cost = snapshot.research.cost
            rate = snapshot.research.beakers_per_turn
            if None in (progress, cost, rate):
                raise LookupError("research completion inputs are unavailable")
            if int(progress) >= int(cost):
                return 0
            return (None if int(rate) <= 0 else
                    int(math.ceil((int(cost) - int(progress)) / float(rate))))
        else:
            raise AssertionError(grounding_id)
        if value is None:
            raise LookupError("{} is unavailable".format(grounding_id))
        return int(value)

    @staticmethod
    def _resolved_paths(spec, args):
        city = str(args[0]) if args and spec.grounding_id.startswith("city.") else None
        unit = str(args[0]) if args and spec.grounding_id.startswith("unit.") else None
        route = (
            "{}:{}".format(args[0], args[1])
            if len(args) >= 2 and spec.grounding_id.startswith("movement.")
            else None)
        if spec.grounding_id.startswith("defense."):
            if spec.grounding_id == "defense.removal-deficit":
                unit = str(args[0]) if args else None
            else:
                city = str(args[0]) if args else None
        enemy = (
            str(args[1])
            if (len(args) >= 2
                and spec.grounding_id == "defense.visible-threat-eta")
            else None)
        return tuple(path.format(
            city=city, unit=unit, route=route, enemy=enemy)
                     for path in spec.dependency_paths)

    def evaluate(self, grounding_id, snapshot, *args):
        spec = self.spec(grounding_id)
        args = tuple(str(value) if isinstance(value, int) else value
                     for value in args)
        fingerprints = self._fingerprint_cache.get(snapshot.snapshot_id)
        if fingerprints is None:
            fingerprints = snapshot_dependency_fingerprints(snapshot)
            self.prime(snapshot, fingerprints)
        dependencies = []

        def source_reference(path):
            candidate = path
            while candidate:
                try:
                    return snapshot_dependency_ref(
                        snapshot, candidate, fingerprints)
                except KeyError:
                    if "." not in candidate:
                        raise
                    candidate = candidate.rsplit(".", 1)[0]
            raise KeyError("grounding dependency is unavailable: {}".format(
                path))

        def path_dependencies(path):
            cache_key = (snapshot.snapshot_id, path)
            cached = self._path_dependency_cache.get(cache_key)
            if cached is not None:
                return cached
            if "*" in path and not path.endswith(".*"):
                keys = tuple(
                    key for key in sorted(fingerprints)
                    if fnmatchcase(key.path, path))
            elif path.endswith(".*"):
                prefix = path[:-1]
                keys = tuple(
                    key for key in sorted(fingerprints)
                    if key.path.startswith(prefix))
            elif path in ("cities", "units"):
                prefix = path + "."
                keys = tuple(
                    key for key in sorted(fingerprints)
                    if key.path.startswith(prefix))
            else:
                result = (source_reference(path),)
                self._path_dependency_cache[cache_key] = result
                return result
            result = tuple(
                snapshot_dependency_ref(snapshot, key.path, fingerprints)
                for key in keys)
            self._path_dependency_cache[cache_key] = result
            return result

        for path in self._resolved_paths(spec, args):
            dependencies.extend(path_dependencies(path))
        if grounding_id in (
                "city.production-cost", "city.production-eta",
                "unit.combat-profile", "unit.persistent-defender",
                "city.local-garrison-count",
                "defense.visible-threat-eta",
                "defense.removal-deficit"):
            if self.ruleset_digest is None:
                raise ValueError(
                    "{} requires a ruleset digest".format(grounding_id))
            if grounding_id == "defense.removal-deficit":
                target_kind, target = "unit", "defender-catalog"
            elif grounding_id == "defense.visible-threat-eta":
                target_kind = "unit"
                target = snapshot.visible_enemy_unit(args[1]).unit_type
            elif grounding_id.startswith("unit."):
                target_kind, target = "unit", snapshot.unit(args[0]).unit_type
            elif grounding_id == "city.local-garrison-count":
                target_kind, target = "unit", "defender-catalog"
            else:
                target_kind, target = args[-2], args[-1]
            dependencies.append(DependencyRef(
                DependencyKey(
                    "ruleset-digest", self.ruleset_digest,
                    "target:{}:{}".format(target_kind, target)),
                structural_hash({
                    "ruleset_digest": self.ruleset_digest,
                    "target_kind": target_kind,
                    "target": target,
                }),
            ))
        dependencies = tuple(sorted(set(dependencies)))
        dependency_hash = structural_hash(
            [value.to_dict() for value in dependencies])
        cache_key = (
            grounding_id, spec.version, args, snapshot.snapshot_id,
            dependency_hash, self.ruleset_digest)
        if spec.cache_policy != "none" and cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]
        self._evaluations += 1
        available = True
        diagnostic = None
        try:
            value = self._evaluate(grounding_id, snapshot, args)
        except LookupError as error:
            value = None
            available = False
            diagnostic = str(error)
        witness = {
            "arguments": list(args),
            "available": available,
            "dependency_hash": dependency_hash,
            "diagnostic": diagnostic,
            "grounding_id": grounding_id,
            "value": value,
            "version": spec.version,
        }
        result = GroundingResult(
            grounding_id, spec.version, args, value, spec.units,
            spec.authority, snapshot.snapshot_id, self.ruleset_digest,
            tuple(dependencies), witness, structural_hash(witness),
            available, diagnostic, spec.confidence_cap)
        if spec.cache_policy != "none":
            self._cache[cache_key] = result
        return result
