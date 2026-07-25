"""Abduction and uncertain deductions over the mechanically compiled IR."""

from .model import BeliefKey


class UncertainInference(object):
    def __init__(self, ruleset_ir, store):
        self.ir = ruleset_ir
        self.store = store
        self._rules = {(rule.target_kind, rule.rule_name): rule
                       for rule in ruleset_ir.rules if not rule.disabled}

    def _tech_closure(self, tech, active=None):
        active = set() if active is None else set(active)
        if tech in active:
            return set()
        active.add(tech)
        result = {tech}
        rule = self._rules.get(("tech", str(tech)))
        if rule is not None:
            for requirement in rule.antecedents:
                if requirement.kind == "Tech" and requirement.present:
                    result.update(self._tech_closure(str(requirement.name), active))
        return result

    def abduce_prerequisites(self, observed_kind, observed_name, opponent_id,
                             support_ids, turn, strength, confidence):
        rule = self._rules.get((str(observed_kind), str(observed_name)))
        if rule is None:
            return tuple()
        technologies = set()
        for requirement in rule.antecedents:
            if requirement.kind == "Tech" and requirement.present:
                technologies.update(self._tech_closure(str(requirement.name)))
        result = []
        for tech in sorted(technologies):
            key = BeliefKey("has-tech", (str(opponent_id), tech))
            belief, revision = self.store.derive(
                key, support_ids, turn, strength, confidence,
                "abduce:{}:{}->{}".format(observed_kind, observed_name, tech),
                derivation_path=(rule.rule_id,))
            result.append((belief, revision))
        return tuple(result)

    def deduce(self, predicate, arguments, premise_beliefs, turn, rule_id,
               dampening_lambda=None):
        if not premise_beliefs:
            raise ValueError("uncertain deduction requires premises")
        support = set()
        strength = 1.0
        confidence = 1.0
        paths = []
        for belief in premise_beliefs:
            support.update(belief.provenance_ids)
            strength = min(strength, belief.strength)
            confidence = min(confidence, belief.confidence)
            paths.append(belief.atom_id)
            for support_path in belief.support_paths:
                # The first item is the immutable evidence token. The remainder
                # is proof ancestry and must follow deductions so a later edge
                # cannot close a self-supporting loop.
                paths.extend(str(value) for value in support_path[1:])
        return self.store.derive(
            BeliefKey(str(predicate), tuple(arguments)), support, turn,
            strength, confidence, rule_id, tuple(sorted(set(paths))),
            dampening_lambda)
