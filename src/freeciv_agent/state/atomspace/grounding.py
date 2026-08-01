"""Typed dependency-declaring groundings for rich FDAS domain scopes."""

import math
from dataclasses import dataclass
from enum import Enum

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


class TypedGroundingRegistry(object):
    """Evaluate exact/derived scalar functions with dependency witnesses."""

    def __init__(self, ruleset_ir=None, specs=CITY_ECONOMY_GROUNDING_SPECS,
                 ruleset_digest=None):
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = ruleset_digest
        self._specs = dict((value.grounding_id, value) for value in specs)
        if len(self._specs) != len(tuple(specs)):
            raise ValueError("duplicate typed grounding ID")
        self._cache = {}
        self._fingerprint_cache = {}
        self._evaluations = 0
        self._cache_hits = 0
        self._rules = {}
        if ruleset_ir is not None:
            for rule in ruleset_ir.rules:
                self._rules.setdefault(
                    (rule.target_kind, rule.rule_name), []).append(rule)

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
            for snapshot_id in sorted(self._fingerprint_cache)[:-8]:
                self._fingerprint_cache.pop(snapshot_id, None)

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
        city = None
        if grounding_id.startswith("city."):
            if not args:
                raise ValueError("{} expects a city".format(grounding_id))
            city = self._city(snapshot, args[0])
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
        return tuple(path.format(city=city) for path in spec.dependency_paths)

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

        for path in self._resolved_paths(spec, args):
            if path in ("cities", "units"):
                prefix = path + "."
                dependencies.extend(
                    snapshot_dependency_ref(snapshot, key.path, fingerprints)
                    for key in sorted(fingerprints)
                    if key.path.startswith(prefix))
            else:
                dependencies.append(source_reference(path))
        if grounding_id in ("city.production-cost", "city.production-eta"):
            if self.ruleset_digest is None:
                raise ValueError(
                    "{} requires a ruleset digest".format(grounding_id))
            dependencies.append(DependencyRef(
                DependencyKey(
                    "ruleset-digest", self.ruleset_digest,
                    "target:{}:{}".format(args[-2], args[-1])),
                structural_hash({
                    "ruleset_digest": self.ruleset_digest,
                    "target_kind": args[-2],
                    "target": args[-1],
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
