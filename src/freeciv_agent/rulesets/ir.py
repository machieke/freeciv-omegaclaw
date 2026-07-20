"""Typed canonical ruleset intermediate representation."""

from dataclasses import dataclass, field


CRISP_TV = {"strength": 1.0, "confidence": 0.99}


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

    def to_dict(self):
        return {
            "compiler_version": self.compiler_version,
            "grounded_signatures": list(self.grounded_signatures),
            "predicate_catalog": list(self.predicate_catalog),
            "parameters": self.parameters,
            "rules": [rule.to_dict() for rule in self.rules],
            "ruleset": self.ruleset,
            "schema_version": "1.2",
            "source_hashes": self.source_hashes,
        }
