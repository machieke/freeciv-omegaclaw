"""Independent ruleset extraction and compiler parity audit.

This module shares only secfile lexical parsing with the compiler. It deliberately does not
import compiler rule-building helpers, so target/edge/sample comparisons can detect compiler
mapping mistakes.
"""

import hashlib
import json
import os
import random

from .secfile import SecTable, parse


def _name(section):
    field = section.fields.get("rule_name") or section.fields.get("name")
    value = str(field.value)
    if value.startswith("?") and ":" in value:
        value = value.split(":", 1)[1]
    return value


def _req_tuple(kind, name, range_name, present=True):
    value = int(name) if kind == "MinSize" else str(name)
    return (str(kind), value, str(range_name), bool(present))


def _table_rows(field):
    if not isinstance(field.value, SecTable):
        raise ValueError("reference extractor expected table at {}:{}".format(
            field.location.path, field.location.line))
    output = []
    for row in field.value.dictionaries():
        output.append(_req_tuple(row["type"], row["name"], row["range"],
                                 True if row.get("present") is None else row["present"]))
    return output


def extract_reference(ruleset_root, ruleset):
    techs = parse(os.path.join(ruleset_root, ruleset, "techs.ruleset"))
    units = parse(os.path.join(ruleset_root, ruleset, "units.ruleset"))
    buildings = parse(os.path.join(ruleset_root, ruleset, "buildings.ruleset"))
    game = parse(os.path.join(ruleset_root, ruleset, "game.ruleset"))
    targets = {}
    edges = set()
    traits = {}
    for section in techs.matching("advance_"):
        target = _name(section)
        antecedents = []
        for field_name in ("req1", "req2", "root_req"):
            field = section.fields.get(field_name)
            if field is not None and field.value not in ("", "None", "Never"):
                item = _req_tuple("Tech", field.value, "Player")
                antecedents.append(item)
                edges.add(("tech", target, field_name, str(field.value)))
        field = section.fields.get("research_reqs")
        if field is not None:
            for item in _table_rows(field):
                antecedents.append(item)
                edges.add(("tech", target, "research_reqs", json.dumps(item)))
        targets[("tech", target)] = sorted(antecedents, key=str)
    for kind, secfile in (("unit", units), ("building", buildings)):
        for section in secfile.matching(kind + "_"):
            target = _name(section)
            field = section.fields.get("reqs")
            antecedents = [] if field is None else _table_rows(field)
            targets[(kind, target)] = sorted(antecedents, key=str)
            for item in antecedents:
                edges.add((kind, target, "reqs", json.dumps(item)))
            if kind == "unit":
                traits[(kind, target)] = {}
                for field_name in (
                        "class", "flags", "roles", "cargo", "targets"):
                    trait_field = section.fields.get(field_name)
                    if trait_field is None:
                        continue
                    values = trait_field.value
                    if isinstance(values, str):
                        values = [] if not values else [values]
                    traits[(kind, target)][field_name] = sorted(set(values))
    civstyle = next(row for row in game.sections if row.name == "civstyle")
    parameters = {
        name: civstyle.fields[name].value
        for name in ("granary_food_ini", "granary_food_inc")
    }
    return {"targets": targets, "edges": edges, "traits": traits,
            "parameters": parameters}


def _compiler_tuple(requirement):
    return (requirement.kind, requirement.name, requirement.range, requirement.present)


def compiler_projection(ir):
    targets = {}
    edges = set()
    traits = {}
    for rule in ir.rules:
        key = (rule.target_kind, rule.rule_name)
        targets[key] = sorted((_compiler_tuple(req) for req in rule.antecedents), key=str)
        for req in rule.antecedents:
            field = req.source["field"]
            encoded = req.name if rule.target_kind == "tech" and field in (
                "req1", "req2", "root_req") else json.dumps(_compiler_tuple(req))
            edges.add((rule.target_kind, rule.rule_name, field, str(encoded)))
        if rule.target_kind == "unit":
            traits[key] = {
                name: list(value.get("values", ()))
                for name, value in getattr(rule, "traits", {}).items()
            }
    parameters = {
        name: row.get("value")
        for name, row in getattr(ir, "parameters", {}).items()
    }
    return {"targets": targets, "edges": edges, "traits": traits,
            "parameters": parameters}


def _semantic_audit(ir):
    issues = []
    expressions = dict(
        (value.expression_id, value)
        for value in getattr(ir, "requirement_expressions", ()))
    effects = dict(
        (value.effect_id, value)
        for value in getattr(ir, "effects", ()))
    capabilities = tuple(getattr(ir, "capabilities", ()))
    schemas = tuple(getattr(ir, "action_schemas", ()))
    groundings = tuple(getattr(ir, "grounding_specs", ()))
    for expression in expressions.values():
        if any(child not in expressions for child in expression.children):
            issues.append("requirement references unknown child: {}".format(
                expression.expression_id))
        if expression.kind == "not" and expression.completeness_spec is None:
            issues.append("negative requirement lacks completeness: {}".format(
                expression.expression_id))
    for capability in capabilities:
        if not capability.provenance:
            issues.append("capability lacks provenance: {}".format(
                capability.capability_id))
        if (capability.requirements is not None
                and capability.requirements not in expressions):
            issues.append("capability references unknown requirement: {}".format(
                capability.capability_id))
    for effect in effects.values():
        if not effect.provenance:
            issues.append("effect lacks provenance: {}".format(
                effect.effect_id))
        if not effect.known and not effect.unknown_reason:
            issues.append("unknown effect lacks reason: {}".format(
                effect.effect_id))
        if (effect.requirements is not None
                and effect.requirements not in expressions):
            issues.append("effect references unknown requirement: {}".format(
                effect.effect_id))
    for schema in schemas:
        if not schema.legal_binding_required:
            issues.append("action schema lacks legal binding: {}".format(
                schema.schema_id))
        if schema.requirements not in expressions:
            issues.append("action schema references unknown requirement: {}".format(
                schema.schema_id))
        if any(effect_id not in effects for effect_id in schema.effects):
            issues.append("action schema references unknown effect: {}".format(
                schema.schema_id))
    coverage = dict(getattr(ir, "semantics_coverage", {}))
    expected = {
        "action_schemas": len(schemas),
        "capability_bindings": len(capabilities),
        "exact_ruleset_effects": sum(value.known for value in effects.values()),
        "grounding_specs": len(groundings),
        "requirement_expressions": len(expressions),
        "unknown_effects": sum(not value.known for value in effects.values()),
    }
    if coverage != expected:
        issues.append("semantic coverage counters disagree with compiled IR")
    return {
        "coverage": coverage,
        "issues": sorted(issues),
        "unknown_effect_ids": sorted(
            value.effect_id for value in effects.values() if not value.known),
    }


def audit(ir, ruleset_root, sample_seed=20260717, sample_size=20):
    reference = extract_reference(ruleset_root, ir.ruleset)
    compiled = compiler_projection(ir)
    missing_targets = sorted(set(reference["targets"]) - set(compiled["targets"]))
    extra_targets = sorted(set(compiled["targets"]) - set(reference["targets"]))
    missing_edges = sorted(reference["edges"] - compiled["edges"], key=str)
    extra_edges = sorted(compiled["edges"] - reference["edges"], key=str)
    trait_mismatches = []
    for key in sorted(reference["traits"]):
        if reference["traits"][key] != compiled["traits"].get(key):
            trait_mismatches.append({
                "target": list(key),
                "reference": reference["traits"][key],
                "compiled": compiled["traits"].get(key),
            })
    parameter_mismatches = []
    for name in sorted(reference["parameters"]):
        if reference["parameters"][name] != compiled["parameters"].get(name):
            parameter_mismatches.append({
                "parameter": name,
                "reference": reference["parameters"][name],
                "compiled": compiled["parameters"].get(name),
            })
    rng = random.Random(sample_seed)
    samples = {}
    sample_mismatches = []
    for kind in ("tech", "unit"):
        population = sorted(key for key in reference["targets"] if key[0] == kind)
        selected = sorted(rng.sample(population, min(sample_size, len(population))))
        samples[kind] = [name for _, name in selected]
        for key in selected:
            if reference["targets"][key] != compiled["targets"].get(key):
                sample_mismatches.append({
                    "target": list(key),
                    "reference": reference["targets"][key],
                    "compiled": compiled["targets"].get(key),
                })
    counts = {
        "building_rules": sum(rule.target_kind == "building" for rule in ir.rules),
        "prerequisite_edges": len(reference["edges"]),
        "target_rules": len(ir.rules),
        "tech_rules": sum(rule.target_kind == "tech" for rule in ir.rules),
        "unit_rules": sum(rule.target_kind == "unit" for rule in ir.rules),
    }
    semantic = _semantic_audit(ir)
    return {
        "counts": counts,
        "extra_edges": extra_edges,
        "extra_targets": extra_targets,
        "missing_edges": missing_edges,
        "missing_targets": missing_targets,
        "parameter_mismatches": parameter_mismatches,
        "passed": not any((missing_targets, extra_targets, missing_edges, extra_edges,
                           sample_mismatches, trait_mismatches,
                           parameter_mismatches, semantic["issues"])),
        "sample_mismatches": sample_mismatches,
        "sample_seed": sample_seed,
        "samples": samples,
        "trait_mismatches": trait_mismatches,
        "semantic_coverage": semantic["coverage"],
        "semantic_issues": semantic["issues"],
        "unknown_effect_ids": semantic["unknown_effect_ids"],
    }


def audit_digest(report):
    material = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()
