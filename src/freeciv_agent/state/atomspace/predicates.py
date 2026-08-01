"""Typed predicate schemas for the FDAS compatibility projection."""

from dataclasses import dataclass

from .model import AtomKey, AtomNamespace, term_kind


@dataclass(frozen=True)
class PredicateSpec:
    predicate: str
    arity: int
    argument_kinds: tuple
    namespaces: frozenset
    truth_kind: str
    allowed_scope_kinds: frozenset
    completeness_policy: str
    export_policy: str
    schema_version: str

    def __post_init__(self):
        if not isinstance(self.predicate, str) or not self.predicate:
            raise ValueError("predicate name is required")
        if (isinstance(self.arity, bool)
                or not isinstance(self.arity, int)
                or self.arity < 0):
            raise ValueError("predicate arity must be non-negative")
        object.__setattr__(self, "argument_kinds", tuple(
            tuple(value) for value in self.argument_kinds))
        object.__setattr__(self, "namespaces", frozenset(
            AtomNamespace(value) for value in self.namespaces))
        object.__setattr__(self, "allowed_scope_kinds", frozenset(
            self.allowed_scope_kinds))
        if len(self.argument_kinds) != self.arity:
            raise ValueError("argument kind count must match predicate arity")
        if any(not values for values in self.argument_kinds):
            raise ValueError("every predicate argument requires an allowed kind")
        if not self.namespaces:
            raise ValueError("predicate requires at least one namespace")
        if not self.allowed_scope_kinds:
            raise ValueError("predicate requires at least one scope kind")
        if self.truth_kind not in ("crisp", "uncertain", "structural"):
            raise ValueError("unknown predicate truth kind")
        if self.completeness_policy not in (
                "open", "closed", "explicit-witness"):
            raise ValueError("unknown predicate completeness policy")
        if self.export_policy not in (
                "local", "parent-summary", "global"):
            raise ValueError("unknown predicate export policy")
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise ValueError("predicate schema version is required")

    def validate(self, key, scope_kind):
        if not isinstance(key, AtomKey):
            raise TypeError("predicate validation requires AtomKey")
        if key.predicate != self.predicate:
            raise ValueError("predicate key does not match specification")
        if len(key.arguments) != self.arity:
            raise ValueError(
                "{} expects {} arguments".format(self.predicate, self.arity))
        if key.namespace not in self.namespaces:
            raise ValueError(
                "{} is not valid in namespace {}".format(
                    self.predicate, key.namespace.value))
        if scope_kind not in self.allowed_scope_kinds:
            raise ValueError(
                "{} is not valid in scope kind {}".format(
                    self.predicate, scope_kind))
        for index, (term, allowed) in enumerate(zip(
                key.arguments, self.argument_kinds)):
            actual = term_kind(term)
            if actual not in allowed:
                raise ValueError(
                    "{} argument {} requires {}, got {}".format(
                        self.predicate, index, sorted(allowed), actual))
        return key

    def to_dict(self):
        return {
            "allowed_scope_kinds": sorted(self.allowed_scope_kinds),
            "argument_kinds": [list(value) for value in self.argument_kinds],
            "arity": self.arity,
            "completeness_policy": self.completeness_policy,
            "export_policy": self.export_policy,
            "namespaces": sorted(value.value for value in self.namespaces),
            "predicate": self.predicate,
            "schema_version": self.schema_version,
            "truth_kind": self.truth_kind,
        }


class PredicateRegistry(object):
    def __init__(self, specs=()):
        self._specs = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec):
        if not isinstance(spec, PredicateSpec):
            raise TypeError("predicate registry requires PredicateSpec")
        if spec.predicate in self._specs:
            raise ValueError(
                "duplicate predicate specification: {}".format(
                    spec.predicate))
        self._specs[spec.predicate] = spec
        return spec

    def require(self, predicate):
        try:
            return self._specs[str(predicate)]
        except KeyError:
            raise KeyError(
                "unregistered predicate: {}".format(predicate))

    def validate(self, key, scope_kind):
        return self.require(key.predicate).validate(key, scope_kind)

    @property
    def predicates(self):
        return tuple(sorted(self._specs))

    @property
    def specs(self):
        return tuple(self._specs[key] for key in sorted(self._specs))

    def extended(self, specs):
        """Return a new registry without mutating either input registry."""
        return PredicateRegistry(self.specs + tuple(specs))

    def to_dict(self):
        return {
            "predicates": [self._specs[key].to_dict()
                           for key in sorted(self._specs)],
            "schema_version": "1.0",
        }


def _spec(predicate, arguments, namespace, scope_kind,
          completeness="closed", export="parent-summary"):
    return PredicateSpec(
        predicate=predicate,
        arity=len(arguments),
        argument_kinds=tuple((value,) for value in arguments),
        namespaces=frozenset((namespace,)),
        truth_kind="crisp",
        allowed_scope_kinds=frozenset((scope_kind,)),
        completeness_policy=completeness,
        export_policy=export,
        schema_version="1.0",
    )


def legacy_predicate_registry():
    """Return a fresh registry for exactly the current flat projection."""
    return PredicateRegistry((
        _spec("buildable", ("city", "production-kind", "production-target"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("city-at", ("city", "tile"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("city-producing", (
            "city", "production-kind", "production-target"),
            AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("has-tech", ("player", "technology"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("owns-city", ("player", "city"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("owns-unit", ("player", "unit"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("tile-visible", ("tile",),
              AtomNamespace.OBSERVATION, "world", export="global"),
        _spec("unit-activity", ("unit", "activity"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("unit-at", ("unit", "tile"),
              AtomNamespace.AUTHORITATIVE, "empire"),
        _spec("unit-type", ("unit", "unit-type"),
              AtomNamespace.AUTHORITATIVE, "empire"),
    ))
