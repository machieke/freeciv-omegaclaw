"""Small independent graph oracle for generated proof reachability."""


def evaluate_reference(ruleset_ir, target):
    """Evaluate generated tech rules without invoking DeterministicRuleEngine."""
    alternatives = {}
    for rule in ruleset_ir.rules:
        if rule.disabled or rule.target_predicate != "researchable":
            continue
        dependencies = tuple(
            str(requirement.name) for requirement in rule.antecedents
            if (requirement.present and requirement.kind == "Tech"))
        grounded_blocked = any(
            requirement.semantic == "grounded"
            for requirement in rule.antecedents)
        alternatives.setdefault(str(rule.rule_name), []).append((
            rule.rule_id, dependencies, grounded_blocked))
    memo = {}
    active = set()
    visited = set()
    cycle_rejections = [0]
    visited_rules = set()

    def reachable(name):
        if name in memo:
            return memo[name]
        if name in active:
            cycle_rejections[0] += 1
            return False
        active.add(name)
        branches = alternatives.get(name, ())
        visited.add(name)
        branch_results = []
        for rule_id, dependencies, grounded_blocked in branches:
            visited_rules.add(rule_id)
            dependency_results = [reachable(dependency)
                                  for dependency in dependencies]
            branch_results.append(
                not grounded_blocked and all(dependency_results))
        result = any(branch_results)
        active.remove(name)
        memo[name] = result
        return result

    result = reachable(str(target))
    return {
        # Empty-state generated cases with a valid route are blocked on the
        # material facts; graph-unreachable cases are unreachable.
        "cycle_rejections": cycle_rejections[0],
        "reachable": result,
        "status": "BLOCKED" if result else "UNREACHABLE",
        "visited_names": tuple(sorted(visited)),
        "visited_rule_ids": tuple(sorted(visited_rules)),
    }
