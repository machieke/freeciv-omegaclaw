"""Allowed symbol and canonical target catalog generated from M0 IR."""


class SymbolCatalog(object):
    def __init__(self, ruleset_ir):
        self.ruleset = ruleset_ir.ruleset
        self.targets = {rule.rule_id: rule for rule in ruleset_ir.rules if not rule.disabled}
        self.predicates = frozenset(row["name"] for row in ruleset_ir.predicate_catalog)
        self.predicates = self.predicates | frozenset({
            "owns-city", "owns-unit", "unit-type", "unit-at", "city-at",
            "tile-visible", "at", "threat-at", "observed-unit", "tile-clear",
        })

    def validate_goal(self, goal):
        rule = self.targets.get(goal.target_id)
        if rule is None:
            return False, "unknown_target_id"
        if goal.predicate != rule.target_predicate:
            return False, "target_predicate_mismatch"
        expected = 2 if rule.target_kind == "tech" else 3
        if len(goal.arguments) != expected:
            return False, "goal_argument_arity"
        if str(goal.arguments[-1]) != rule.rule_name:
            return False, "target_argument_mismatch"
        if goal.predicate == "buildable" and str(goal.arguments[-2]) != rule.target_kind:
            return False, "target_kind_mismatch"
        return True, None

    def validate_claim(self, claim):
        if claim.predicate not in self.predicates:
            return False, "unknown_claim_predicate"
        if not claim.arguments:
            return False, "claim_arguments_empty"
        return True, None

    def prompt_catalog(self):
        return {
            "goal_targets": [{
                "predicate": rule.target_predicate, "target_id": rule.rule_id,
                "target_kind": rule.target_kind, "target_name": rule.rule_name,
            } for _, rule in sorted(self.targets.items())],
            "claim_predicates": sorted(self.predicates), "ruleset": self.ruleset,
        }
