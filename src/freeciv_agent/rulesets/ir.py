"""Typed canonical ruleset intermediate representation."""

from dataclasses import dataclass, field


CRISP_TV = {"strength": 1.0, "confidence": 0.99}


def _required_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


@dataclass(frozen=True)
class RequirementExpression:
    expression_id: str
    kind: str
    children: tuple = ()
    atom_template: object = None
    grounding_template: object = None
    completeness_spec: object = None

    def __post_init__(self):
        _required_text(self.expression_id, "requirement expression ID")
        if self.kind not in (
                "all", "any", "not", "atom", "grounded", "temporal",
                "resource", "operation", "visibility"):
            raise ValueError("invalid requirement expression kind")
        object.__setattr__(self, "children", tuple(self.children))
        if self.kind in ("all", "any") and not self.children:
            raise ValueError("all/any requirement needs children")
        if self.kind == "not":
            if len(self.children) != 1:
                raise ValueError("not requirement needs exactly one child")
            if self.completeness_spec is None:
                raise ValueError("not requirement needs completeness contract")
        if self.kind == "atom" and self.atom_template is None:
            raise ValueError("atom requirement needs atom template")
        if self.kind == "grounded" and self.grounding_template is None:
            raise ValueError("grounded requirement needs grounding template")

    def to_dict(self):
        return {
            "atom_template": self.atom_template,
            "children": list(self.children),
            "completeness_spec": self.completeness_spec,
            "expression_id": self.expression_id,
            "grounding_template": self.grounding_template,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    entity_kind: str
    source_entity_id: str
    requirements: object
    traits: tuple
    provenance: tuple

    def __post_init__(self):
        for value, name in (
                (self.capability_id, "capability ID"),
                (self.entity_kind, "capability entity kind"),
                (self.source_entity_id, "capability source entity")):
            _required_text(value, name)
        object.__setattr__(self, "traits", tuple(self.traits))
        object.__setattr__(self, "provenance", tuple(self.provenance))

    def to_dict(self):
        return {
            "capability_id": self.capability_id,
            "entity_kind": self.entity_kind,
            "provenance": list(self.provenance),
            "requirements": self.requirements,
            "source_entity_id": self.source_entity_id,
            "traits": [list(value) for value in self.traits],
        }


@dataclass(frozen=True)
class EffectSpec:
    effect_id: str
    effect_kind: str
    subject_template: object
    target_template: object
    requirements: object
    exact_grounding: object
    predictive_model: object
    completion_predicate: object
    confidence_cap: object
    provenance: tuple
    metadata: tuple = ()
    unknown_reason: object = None

    def __post_init__(self):
        _required_text(self.effect_id, "effect ID")
        _required_text(self.effect_kind, "effect kind")
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        if self.confidence_cap is not None:
            cap = float(self.confidence_cap)
            if not 0 <= cap <= 1:
                raise ValueError("effect confidence cap must be in 0..1")
        if self.unknown_reason is not None:
            _required_text(self.unknown_reason, "unknown effect reason")

    @property
    def known(self):
        return self.unknown_reason is None

    def to_dict(self):
        return {
            "completion_predicate": self.completion_predicate,
            "confidence_cap": self.confidence_cap,
            "effect_id": self.effect_id,
            "effect_kind": self.effect_kind,
            "exact_grounding": self.exact_grounding,
            "known": self.known,
            "metadata": [list(value) for value in self.metadata],
            "predictive_model": self.predictive_model,
            "provenance": list(self.provenance),
            "requirements": self.requirements,
            "subject_template": self.subject_template,
            "target_template": self.target_template,
            "unknown_reason": self.unknown_reason,
        }


@dataclass(frozen=True)
class ActionSchema:
    schema_id: str
    action_type: str
    actor_kind: str
    target_kind: object
    requirements: str
    effects: tuple
    resource_claim_templates: tuple
    duration_model: object
    transition_model: object
    legal_binding_required: bool
    provenance: tuple

    def __post_init__(self):
        for value, name in (
                (self.schema_id, "action schema ID"),
                (self.action_type, "action type"),
                (self.actor_kind, "action actor kind"),
                (self.requirements, "action requirement expression")):
            _required_text(value, name)
        object.__setattr__(self, "effects", tuple(self.effects))
        object.__setattr__(
            self, "resource_claim_templates",
            tuple(self.resource_claim_templates))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        if not isinstance(self.legal_binding_required, bool):
            raise ValueError("legal binding requirement must be boolean")

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "actor_kind": self.actor_kind,
            "duration_model": self.duration_model,
            "effects": list(self.effects),
            "legal_binding_required": self.legal_binding_required,
            "provenance": list(self.provenance),
            "requirements": self.requirements,
            "resource_claim_templates": list(self.resource_claim_templates),
            "schema_id": self.schema_id,
            "target_kind": self.target_kind,
            "transition_model": self.transition_model,
        }


@dataclass(frozen=True)
class GroundingSpec:
    name: str
    arguments: tuple
    returns: str
    unit: str
    authority: str
    dependency_paths: tuple
    witness_schema: str

    def __post_init__(self):
        for value, name in (
                (self.name, "grounding name"),
                (self.returns, "grounding return type"),
                (self.unit, "grounding unit"),
                (self.authority, "grounding authority"),
                (self.witness_schema, "grounding witness schema")):
            _required_text(value, name)
        object.__setattr__(self, "arguments", tuple(self.arguments))
        object.__setattr__(
            self, "dependency_paths", tuple(self.dependency_paths))

    def to_dict(self):
        return {
            "arguments": list(self.arguments),
            "authority": self.authority,
            "dependency_paths": list(self.dependency_paths),
            "name": self.name,
            "returns": self.returns,
            "unit": self.unit,
            "witness_schema": self.witness_schema,
        }


@dataclass(frozen=True)
class Requirement:
    kind: str
    name: object
    range: str
    present: bool
    semantic: str
    predicate: str
    arguments: tuple
    source: dict
    survives: bool = False

    def to_dict(self):
        return {
            "arguments": list(self.arguments),
            "kind": self.kind,
            "name": self.name,
            "predicate": self.predicate,
            "present": self.present,
            "range": self.range,
            "semantic": self.semantic,
            "source": self.source,
            "survives": self.survives,
        }


@dataclass(frozen=True)
class Rule:
    rule_id: str
    target_kind: str
    rule_name: str
    display_name: str
    target_predicate: str
    target_arguments: tuple
    antecedents: tuple
    obsolescence: tuple
    quantitative: dict
    disabled: bool
    source: dict
    traits: dict = field(default_factory=dict)
    tv: dict = field(default_factory=lambda: dict(CRISP_TV))

    def to_dict(self):
        return {
            "antecedents": [item.to_dict() for item in self.antecedents],
            "disabled": self.disabled,
            "display_name": self.display_name,
            "obsolescence": [item.to_dict() for item in self.obsolescence],
            "quantitative": self.quantitative,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "source": self.source,
            "target": {"arguments": list(self.target_arguments),
                       "predicate": self.target_predicate},
            "target_kind": self.target_kind,
            "traits": self.traits,
            "tv": self.tv,
        }


@dataclass(frozen=True)
class RulesetIR:
    ruleset: str
    compiler_version: str
    source_hashes: dict
    rules: tuple
    grounded_signatures: tuple
    predicate_catalog: tuple
    parameters: dict = field(default_factory=dict)
    requirement_expressions: tuple = field(default_factory=tuple)
    capabilities: tuple = field(default_factory=tuple)
    effects: tuple = field(default_factory=tuple)
    action_schemas: tuple = field(default_factory=tuple)
    grounding_specs: tuple = field(default_factory=tuple)
    semantics_coverage: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "compiler_version": self.compiler_version,
            "grounded_signatures": list(self.grounded_signatures),
            "grounding_specs": [value.to_dict()
                                for value in self.grounding_specs],
            "capabilities": [value.to_dict() for value in self.capabilities],
            "effects": [value.to_dict() for value in self.effects],
            "action_schemas": [value.to_dict()
                               for value in self.action_schemas],
            "predicate_catalog": list(self.predicate_catalog),
            "parameters": self.parameters,
            "rules": [rule.to_dict() for rule in self.rules],
            "requirement_expressions": [
                value.to_dict() for value in self.requirement_expressions],
            "ruleset": self.ruleset,
            "schema_version": "2.0",
            "semantics_coverage": self.semantics_coverage,
            "source_hashes": self.source_hashes,
        }
