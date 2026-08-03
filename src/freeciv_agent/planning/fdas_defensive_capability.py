"""Ruleset-grounded defensive capability for shadow candidate comparison."""

from dataclasses import dataclass
import math
import re

from ..events.schema import structural_hash


DEFENSIVE_CAPABILITY_IDENTITY = "fdas-defensive-capability/1.0"
DEFENSIVE_EFFECT_KINDS = frozenset((
    "Defend_Bonus",
    "Fortify_Defense_Bonus",
    "Veteran_Combat",
))
_UNIT_REQUIREMENT_KINDS = frozenset((
    "UnitClass",
    "UnitFlag",
    "UnitType",
))


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _finite_nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("{} must be finite and non-negative".format(name))
    return value


def _quantity(rule, name):
    value = getattr(rule, "quantitative", {}).get(name)
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0.0 else None


def _trait_values(rule, name):
    value = getattr(rule, "traits", {}).get(name, {})
    if isinstance(value, dict):
        value = value.get("values", ())
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(sorted(set(
        str(item) for item in value
        if isinstance(item, str) and item)))


@dataclass(frozen=True)
class FdasDefensiveCapability:
    """The bounded ruleset facts used by defensive noninferiority."""

    ruleset_digest: str
    rule_id: str
    unit_class: str
    defense: float
    maximum_hitpoints: float
    firepower: float
    defensive_effect_signature: tuple
    identity: str = DEFENSIVE_CAPABILITY_IDENTITY

    def __post_init__(self):
        for value, name in (
                (self.identity, "identity"),
                (self.ruleset_digest, "ruleset digest"),
                (self.rule_id, "rule ID"),
                (self.unit_class, "unit class")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "defensive capability {} is required".format(name))
        if self.identity != DEFENSIVE_CAPABILITY_IDENTITY:
            raise ValueError("defensive capability identity differs")
        object.__setattr__(
            self, "defense",
            _finite_nonnegative(self.defense, "defense"))
        object.__setattr__(
            self, "maximum_hitpoints",
            _finite_nonnegative(
                self.maximum_hitpoints, "maximum hit points"))
        object.__setattr__(
            self, "firepower",
            _finite_nonnegative(self.firepower, "firepower"))
        signature = tuple(sorted(set(str(value) for value in
                                     self.defensive_effect_signature)))
        if any(not value for value in signature):
            raise ValueError("defensive effect signature is invalid")
        object.__setattr__(self, "defensive_effect_signature", signature)

    def to_dict(self):
        return {
            "defense": self.defense,
            "defensive_effect_signature": list(
                self.defensive_effect_signature),
            "firepower": self.firepower,
            "identity": self.identity,
            "maximum_hitpoints": self.maximum_hitpoints,
            "rule_id": self.rule_id,
            "ruleset_digest": self.ruleset_digest,
            "unit_class": self.unit_class,
        }


class FdasDefensiveCapabilityResolver:
    """Resolve a fail-closed defensive profile from compiled Ruleset IR.

    The effect signature records every potentially applicable ruleset effect
    that can change defensive or veteran combat behavior.  Context predicates
    such as buildings remain potential; unit class/type/flag predicates are
    evaluated against the unit rule.  Exact signature equality therefore
    prevents a differently flagged unit from silently losing a defensive
    modifier while allowing irrelevant movement/attack flags to differ.
    """

    def __init__(self, ruleset_ir):
        if ruleset_ir is None or not hasattr(ruleset_ir, "rules"):
            raise TypeError(
                "defensive capability resolver requires compiled ruleset IR")
        self.ruleset_ir = ruleset_ir
        self.ruleset_digest = structural_hash(ruleset_ir.to_dict())
        self._expressions = dict(
            (value.expression_id, value)
            for value in getattr(ruleset_ir, "requirement_expressions", ()))
        self._rules = {}
        for rule in getattr(ruleset_ir, "rules", ()):
            if getattr(rule, "target_kind", None) != "unit":
                continue
            for label in (
                    getattr(rule, "display_name", ""),
                    getattr(rule, "rule_name", "")):
                key = _normalized(label)
                if key:
                    self._rules.setdefault(key, []).append(rule)
        self._cache = {}

    @staticmethod
    def _unit_requirement(expression, rule):
        atom = getattr(expression, "atom_template", None)
        if not isinstance(atom, dict):
            return None
        predicate = str(atom.get("predicate", ""))
        prefix = "ruleset-requirement:"
        if not predicate.startswith(prefix):
            return None
        kind = predicate[len(prefix):]
        if kind not in _UNIT_REQUIREMENT_KINDS:
            # UnitClassFlag is determined entirely by the exact class, so it
            # may remain context-unknown and still compare identically.
            return None
        arguments = atom.get("arguments", ())
        if not isinstance(arguments, (list, tuple)) or not arguments:
            return None
        name = _normalized(arguments[0])
        if kind == "UnitClass":
            present = name in {
                _normalized(value) for value in _trait_values(rule, "class")}
        elif kind == "UnitFlag":
            present = name in {
                _normalized(value) for value in _trait_values(rule, "flags")}
        else:
            present = name in {
                _normalized(getattr(rule, "display_name", "")),
                _normalized(getattr(rule, "rule_name", "")),
            }
        completeness = getattr(expression, "completeness_spec", None)
        expected = (
            completeness.get("present", True)
            if isinstance(completeness, dict) else True)
        return present is bool(expected)

    def _expression_possible(self, expression_id, rule, visiting=()):
        if expression_id in visiting:
            return None
        expression = self._expressions.get(expression_id)
        if expression is None:
            return None
        kind = getattr(expression, "kind", None)
        if kind == "atom":
            return self._unit_requirement(expression, rule)
        children = tuple(getattr(expression, "children", ()))
        values = tuple(
            self._expression_possible(
                child, rule, visiting + (expression_id,))
            for child in children)
        if kind == "all":
            if False in values:
                return False
            return True if values and all(value is True for value in values) \
                else None
        if kind == "any":
            if True in values:
                return True
            return False if values and all(value is False for value in values) \
                else None
        if kind == "not" and len(values) == 1:
            return None if values[0] is None else not values[0]
        return None

    def _effect_signature(self, rule):
        return tuple(sorted(
            effect.effect_id
            for effect in getattr(self.ruleset_ir, "effects", ())
            if getattr(effect, "known", False)
            and effect.effect_kind in DEFENSIVE_EFFECT_KINDS
            and self._expression_possible(
                effect.requirements, rule) is not False))

    def resolve(self, unit_type):
        key = _normalized(unit_type)
        if key in self._cache:
            return self._cache[key]
        matches = tuple(dict(
            (str(getattr(rule, "rule_id", "")), rule)
            for rule in self._rules.get(key, ())).values())
        result = None
        if len(matches) == 1:
            rule = matches[0]
            classes = _trait_values(rule, "class")
            values = tuple(_quantity(rule, name) for name in (
                "defense", "hitpoints", "firepower"))
            if (len(classes) == 1 and all(value is not None for value in values)
                    and values[0] > 0.0 and values[1] > 0.0
                    and values[2] > 0.0):
                result = FdasDefensiveCapability(
                    self.ruleset_digest,
                    str(getattr(rule, "rule_id", "")),
                    classes[0],
                    values[0],
                    values[1],
                    values[2],
                    self._effect_signature(rule),
                )
        self._cache[key] = result
        return result
