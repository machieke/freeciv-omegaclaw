"""Versioned pure derivations with declared, instrumented source access."""

from dataclasses import dataclass

from ...events.schema import structural_hash
from .model import AtomRecord, DependencyKey, DependencyRef


@dataclass(frozen=True)
class ProjectionBatch:
    projector_id: str
    projector_version: str
    scope_id: str
    upserts: tuple
    retract_support_ids: tuple
    dependency_fingerprints: tuple
    diagnostics: tuple = ()

    def __post_init__(self):
        for value, name in (
                (self.projector_id, "projector ID"),
                (self.projector_version, "projector version"),
                (self.scope_id, "projection scope ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        object.__setattr__(self, "upserts", tuple(self.upserts))
        object.__setattr__(self, "retract_support_ids", tuple(sorted(set(
            self.retract_support_ids))))
        object.__setattr__(self, "dependency_fingerprints", tuple(sorted(
            self.dependency_fingerprints)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if any(not isinstance(value, AtomRecord) for value in self.upserts):
            raise TypeError("projection upserts must be AtomRecord values")
        if any(not isinstance(value, str) or not value
               for value in self.retract_support_ids):
            raise ValueError("retracted support IDs must be non-empty strings")
        if any(not isinstance(value, DependencyRef)
               for value in self.dependency_fingerprints):
            raise TypeError(
                "projection fingerprints must be DependencyRef values")


def _negative_template(value):
    if isinstance(value, dict):
        return (
            value.get("negated") is True
            or value.get("polarity") == "negative")
    return (
        isinstance(value, (tuple, list))
        and bool(value)
        and value[0] == "not")


@dataclass(frozen=True)
class DerivationSpec:
    derivation_id: str
    version: str
    stratum: int
    scope_kinds: frozenset
    input_patterns: tuple
    grounding_calls: tuple
    output_templates: tuple
    evaluator: object
    completeness: object
    eager_policy: str
    cache_policy: str
    maximum_bindings: int
    maximum_outputs_per_binding: int
    export_policy: str
    depends_on: tuple = ()

    def __post_init__(self):
        for value, name in (
                (self.derivation_id, "derivation ID"),
                (self.version, "derivation version")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        if isinstance(self.stratum, bool) or not isinstance(self.stratum, int):
            raise ValueError("derivation stratum must be an integer")
        if self.stratum < 0:
            raise ValueError("derivation stratum must be non-negative")
        object.__setattr__(self, "scope_kinds", frozenset(self.scope_kinds))
        for name in (
                "input_patterns", "grounding_calls", "output_templates",
                "depends_on"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not self.scope_kinds:
            raise ValueError("derivation requires at least one scope kind")
        if not callable(self.evaluator):
            raise TypeError("derivation evaluator must be callable")
        if self.eager_policy not in ("always", "active-scope", "query-only"):
            raise ValueError("invalid derivation eager policy")
        if self.cache_policy not in (
                "revision", "turn", "persistent-static"):
            raise ValueError("invalid derivation cache policy")
        if self.export_policy not in ("local", "parent-summary", "global"):
            raise ValueError("invalid derivation export policy")
        if (any(_negative_template(value) for value in self.output_templates)
                and self.completeness is None):
            raise ValueError(
                "negative derivation output requires completeness witness")
        for value, name in (
                (self.maximum_bindings, "maximum bindings"),
                (self.maximum_outputs_per_binding,
                 "maximum outputs per binding")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("{} must be positive".format(name))


@dataclass(frozen=True)
class DerivationRun:
    derivation_id: str
    derivation_version: str
    outputs: tuple
    dependencies: tuple
    witness_hash: str


class DerivationContext(object):
    """Expose only declared source values and record every dependency read."""

    def __init__(self, sources, declared_keys):
        self._sources = dict(sources)
        self._declared = frozenset(declared_keys)
        self._accessed = {}

    def read(self, dependency_key):
        if not isinstance(dependency_key, DependencyKey):
            raise TypeError("derivation reads require DependencyKey")
        if dependency_key not in self._declared:
            raise RuntimeError(
                "undeclared derivation dependency: {}".format(
                    dependency_key.to_dict()))
        try:
            source = self._sources[dependency_key]
        except KeyError:
            raise KeyError(
                "declared derivation source is unavailable: {}".format(
                    dependency_key.to_dict()))
        if (isinstance(source, tuple) and len(source) == 2
                and isinstance(source[1], str)):
            value, fingerprint = source
        else:
            value = source
            fingerprint = structural_hash(value)
        reference = DependencyRef(dependency_key, fingerprint)
        self._accessed[dependency_key] = reference
        return value

    @property
    def accessed_dependencies(self):
        return tuple(self._accessed[key] for key in sorted(self._accessed))


class DerivationRegistry(object):
    def __init__(self, specs=()):
        self._specs = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec):
        if not isinstance(spec, DerivationSpec):
            raise TypeError("derivation registry requires DerivationSpec")
        if spec.derivation_id in self._specs:
            raise ValueError(
                "duplicate derivation: {}".format(spec.derivation_id))
        self._specs[spec.derivation_id] = spec
        return spec

    def validate(self):
        for spec in self._specs.values():
            for dependency_id in spec.depends_on:
                if dependency_id not in self._specs:
                    raise ValueError(
                        "unknown derivation dependency: {}".format(
                            dependency_id))
        visiting = set()
        visited = set()

        def visit(derivation_id):
            if derivation_id in visiting:
                raise ValueError("derivation dependency cycle")
            if derivation_id in visited:
                return
            visiting.add(derivation_id)
            for dependency_id in self._specs[derivation_id].depends_on:
                visit(dependency_id)
            visiting.remove(derivation_id)
            visited.add(derivation_id)

        for derivation_id in sorted(self._specs):
            visit(derivation_id)
        for spec in self._specs.values():
            for dependency_id in spec.depends_on:
                dependency = self._specs[dependency_id]
                if dependency.stratum >= spec.stratum:
                    raise ValueError(
                        "derivation strata must increase across dependencies")
        return True

    def require(self, derivation_id):
        try:
            return self._specs[str(derivation_id)]
        except KeyError:
            raise KeyError("unknown derivation: {}".format(derivation_id))

    def evaluate(self, derivation_id, scope_kind, sources, declared_keys):
        self.validate()
        spec = self.require(derivation_id)
        if scope_kind not in spec.scope_kinds:
            raise ValueError("derivation is invalid for requested scope")
        context = DerivationContext(sources, declared_keys)
        outputs = tuple(spec.evaluator(context))
        if len(outputs) > spec.maximum_outputs_per_binding:
            raise RuntimeError("derivation output budget exhausted")
        dependencies = context.accessed_dependencies
        return DerivationRun(
            spec.derivation_id,
            spec.version,
            outputs,
            dependencies,
            structural_hash({
                "dependencies": [value.to_dict() for value in dependencies],
                "derivation_id": spec.derivation_id,
                "outputs": outputs,
                "version": spec.version,
            }),
        )

    @property
    def derivation_ids(self):
        return tuple(sorted(self._specs))
