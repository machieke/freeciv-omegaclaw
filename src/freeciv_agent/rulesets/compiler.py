"""Mechanical FreeCiv ruleset compiler: secfile -> canonical IR and MeTTa."""

import hashlib
import json
import os
import re

from .ir import (
    ActionSchema,
    CapabilitySpec,
    EffectSpec,
    GroundingSpec,
    Requirement,
    RequirementExpression,
    Rule,
    RulesetIR,
)
from .secfile import SecTable, SecfileError, parse


COMPILER_VERSION = "freeciv-ruleset-compiler/2.0"
FILES = (
    "techs.ruleset",
    "units.ruleset",
    "buildings.ruleset",
    "game.ruleset",
    "governments.ruleset",
    "terrain.ruleset",
    "actions.ruleset",
    "effects.ruleset",
)
ALLOWED_REQUIREMENT_COLUMNS = {"type", "name", "range", "present", "quiet", "survives"}
REQUIREMENT_PREDICATES = {
    "Tech": ("has-tech", "symbolic"),
    "Building": ("has-building", "symbolic"),
    "Gov": ("has-government", "symbolic"),
    "Extra": ("has-extra", "symbolic"),
    "Terrain": ("terrain-is", "symbolic"),
    "TerrainClass": ("terrain-class-is", "symbolic"),
    "TerrainFlag": ("terrain-has-flag", "symbolic"),
    "MinSize": ("city-size-at-least", "grounded"),
}

GROUNDED_SIGNATURES = (
    {"name": "beakers-per-turn", "arguments": ["snapshot", "player"], "returns": "number"},
    {"name": "build-cost", "arguments": ["ruleset", "target-kind", "target"], "returns": "integer"},
    {"name": "city-size", "arguments": ["snapshot", "city"], "returns": "integer"},
    {"name": "city-size-at-least", "arguments": ["snapshot", "city", "minimum"], "returns": "boolean"},
    {"name": "gold-at-least", "arguments": ["snapshot", "player", "minimum"], "returns": "boolean"},
    {"name": "gold-stockpile", "arguments": ["snapshot", "player"], "returns": "number"},
    {"name": "research-cost", "arguments": ["ruleset", "tech"], "returns": "integer"},
    {"name": "shield-stockpile", "arguments": ["snapshot", "city"], "returns": "number"},
    {"name": "shields-per-turn", "arguments": ["snapshot", "city"], "returns": "number"},
)

GROUNDING_METADATA = {
    "beakers-per-turn": (
        "beakers-per-turn", "snapshot_exact", ("research.beakers_per_turn",)),
    "build-cost": (
        "shields", "ruleset_exact", ("rules.*.quantitative.build_cost",)),
    "city-size": (
        "citizens", "snapshot_exact", ("cities.*.size",)),
    "city-size-at-least": (
        "boolean", "snapshot_exact", ("cities.*.size",)),
    "gold-at-least": (
        "boolean", "snapshot_exact", ("economy.gold",)),
    "gold-stockpile": (
        "gold", "snapshot_exact", ("economy.gold",)),
    "research-cost": (
        "beakers", "ruleset_exact", ("rules.*.quantitative.cost",)),
    "shield-stockpile": (
        "shields", "snapshot_exact", ("cities.*.shield_stock",)),
    "shields-per-turn": (
        "shields-per-turn", "snapshot_exact", ("cities.*.production",)),
}

PREDICATE_CATALOG = (
    {"name": "has-building", "arguments": ["scope", "building"], "role": "crisp-premise"},
    {"name": "has-tech", "arguments": ["player", "tech"], "role": "crisp-premise"},
    {"name": "buildable", "arguments": ["city", "target-kind", "target"], "role": "crisp-goal"},
    {"name": "researchable", "arguments": ["player", "tech"], "role": "crisp-goal"},
    {"name": "usable-action", "arguments": ["snapshot", "actor", "action"], "role": "crisp-goal"},
)

_INCLUDE = re.compile(r'^\s*\*include\s+"([^"]+)"')


class CompileError(ValueError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _includes(path):
    result = []
    with open(path, encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            match = _INCLUDE.match(line)
            if match:
                result.append((match.group(1), line_number))
    return tuple(result)


def _logical_path(ruleset, filename):
    return "{}/{}".format(ruleset, filename)


def _source(location, ruleset, filename, line=None, field=None):
    return {
        "file": _logical_path(ruleset, filename),
        "field": location.field if field is None else field,
        "line": location.line if line is None else line,
        "section": location.section,
    }


def _display(value):
    value = str(value)
    if value.startswith("?") and ":" in value:
        return value.split(":", 1)[1]
    return value


def _field(section, name, default=None):
    value = section.fields.get(name)
    return default if value is None else value.value


def _scope_argument(range_name):
    return {
        "Player": "$player", "City": "$city", "Local": "$tile",
        "Tile": "$tile", "CAdjacent": "$city", "Adjacent": "$tile",
        "World": "$world", "Alliance": "$alliance", "Team": "$team",
        "Continent": "$continent", "Traderoute": "$trade-route",
    }.get(str(range_name), "$scope:" + str(range_name))


def _requirement(kind, name, range_name, present, survives, source):
    if kind not in REQUIREMENT_PREDICATES:
        raise CompileError("{file}:{line}: [{section}] {field}: unsupported requirement "
                           "kind {kind}".format(kind=kind, **source))
    predicate, semantic = REQUIREMENT_PREDICATES[kind]
    requirement_name = int(name) if kind == "MinSize" else str(name)
    return Requirement(
        kind=str(kind), name=requirement_name, range=str(range_name),
        present=bool(True if present is None else present), semantic=semantic,
        predicate=predicate,
        arguments=(_scope_argument(range_name), requirement_name),
        source=source, survives=bool(False if survives is None else survives),
    )


def _table_requirements(field, ruleset, filename):
    if not isinstance(field.value, SecTable):
        raise CompileError("{}:{}: [{}] {}: expected requirement table".format(
            _logical_path(ruleset, filename), field.location.line,
            field.location.section, field.name))
    unexpected = set(field.value.columns) - ALLOWED_REQUIREMENT_COLUMNS
    if unexpected:
        raise CompileError("{}:{}: [{}] {}: unsupported columns {}".format(
            _logical_path(ruleset, filename), field.location.line,
            field.location.section, field.name, sorted(unexpected)))
    required = {"type", "name", "range"}
    if not required.issubset(field.value.columns):
        raise CompileError("{}:{}: [{}] {}: missing columns {}".format(
            _logical_path(ruleset, filename), field.location.line,
            field.location.section, field.name, sorted(required - set(field.value.columns))))
    result = []
    for table_row, row in zip(field.value.rows, field.value.dictionaries()):
        location = _source(field.location, ruleset, filename, line=table_row.line)
        result.append(_requirement(row["type"], row["name"], row["range"],
                                   row.get("present"), row.get("survives"), location))
    return result


def _canonical_requirements(requirements):
    return tuple(sorted(requirements, key=lambda item: (
        item.predicate, json.dumps(item.arguments, sort_keys=True), not item.present,
        item.source["file"], item.source["line"], item.source["field"])))


def _direct_tech_requirement(section, field_name, ruleset, filename):
    field = section.fields.get(field_name)
    if field is None or field.value in ("", "None"):
        return None, False
    if field.value == "Never":
        return None, True
    source = _source(field.location, ruleset, filename)
    return _requirement("Tech", field.value, "Player", True, False, source), False


def _target_source(section, ruleset, filename):
    name_field = section.fields.get("rule_name") or section.fields.get("name")
    if name_field is None:
        raise CompileError("{}:{}: [{}] name: missing target name".format(
            _logical_path(ruleset, filename), section.line, section.name))
    return _source(name_field.location, ruleset, filename)


def _quantitative(section, ruleset, filename):
    result = {}
    for field_name in (
            "build_cost", "pop_cost", "upkeep", "cost",
            "uk_food", "uk_shield", "uk_gold", "happy_cost",
            "attack", "defense", "hitpoints", "firepower", "move_rate",
            "transport_cap", "fuel"):
        field = section.fields.get(field_name)
        if field is not None:
            if not isinstance(field.value, (int, float)):
                raise CompileError("{}:{}: [{}] {}: expected numeric value".format(
                    _logical_path(ruleset, filename), field.location.line,
                    section.name, field_name))
            result[field_name] = {"value": field.value,
                                  "source": _source(field.location, ruleset, filename)}
    return result


def _traits(section, ruleset, filename, kind):
    """Retain ruleset-declared categorical unit behavior with provenance.

    Flags and roles are not build prerequisites, so they do not belong in the
    implication antecedent.  They are still authoritative ruleset facts needed
    by downstream planners (for example, ``Cities`` distinguishes a real city
    founder from units that merely have the ``Settlers`` worker flag).
    """
    if kind != "unit":
        return {}
    result = {}
    for field_name in ("class", "flags", "roles", "cargo", "targets"):
        field = section.fields.get(field_name)
        if field is None:
            continue
        values = field.value
        if isinstance(values, str):
            values = [] if not values else [values]
        if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values):
            raise CompileError("{}:{}: [{}] {}: expected string vector".format(
                _logical_path(ruleset, filename), field.location.line,
                section.name, field_name))
        result[field_name] = {
            "source": _source(field.location, ruleset, filename),
            "values": sorted(set(values)),
        }
    return result


def _game_parameters(document, ruleset):
    """Compile the city-growth parameters needed by bounded projections."""
    section = next((row for row in document.sections if row.name == "civstyle"), None)
    if section is None:
        raise CompileError("{}/game.ruleset: missing [civstyle] section".format(ruleset))
    result = {}
    for field_name in ("granary_food_ini", "granary_food_inc"):
        field = section.fields.get(field_name)
        if field is None:
            raise CompileError("{}/game.ruleset: [{}] {}: missing field".format(
                ruleset, section.name, field_name))
        value = field.value
        values = value if isinstance(value, list) else [value]
        minimum = 0 if field_name == "granary_food_inc" else 1
        if (not values or any(isinstance(item, bool)
                              or not isinstance(item, (int, float))
                              or item < minimum for item in values)):
            raise CompileError("{}:{}: [{}] {}: expected numeric value(s) >= {}".format(
                _logical_path(ruleset, "game.ruleset"), field.location.line,
                section.name, field_name, minimum))
        result[field_name] = {
            "source": _source(field.location, ruleset, "game.ruleset"),
            "value": ([int(item) for item in values]
                      if isinstance(value, list) else int(value)),
        }
    return result


def _compile_tech(section, ruleset, filename):
    display_name = _display(_field(section, "name"))
    rule_name = _display(_field(section, "rule_name", display_name))
    antecedents = []
    disabled = False
    for field_name in ("req1", "req2", "root_req"):
        requirement, is_disabled = _direct_tech_requirement(section, field_name,
                                                             ruleset, filename)
        disabled = disabled or is_disabled
        if requirement:
            antecedents.append(requirement)
    research = section.fields.get("research_reqs")
    if research is not None:
        antecedents.extend(_table_requirements(research, ruleset, filename))
    return Rule(
        rule_id="{}:tech:{}".format(ruleset, rule_name), target_kind="tech",
        rule_name=rule_name, display_name=display_name,
        target_predicate="researchable", target_arguments=("$player", rule_name),
        antecedents=_canonical_requirements(antecedents), obsolescence=tuple(),
        quantitative=_quantitative(section, ruleset, filename), disabled=disabled,
        source=_target_source(section, ruleset, filename),
    )


def _compile_build_target(section, ruleset, filename, kind):
    display_name = _display(_field(section, "name"))
    rule_name = _display(_field(section, "rule_name", display_name))
    req_field = section.fields.get("reqs")
    antecedents = [] if req_field is None else _table_requirements(req_field, ruleset, filename)
    obsolete = []
    obsolete_field = section.fields.get("obsolete_by")
    if obsolete_field is not None:
        if isinstance(obsolete_field.value, SecTable):
            obsolete = _table_requirements(obsolete_field, ruleset, filename)
        elif obsolete_field.value not in ("", "None"):
            obsolete.append(Requirement(
                kind="Unit", name=str(obsolete_field.value), range="Player", present=True,
                semantic="symbolic", predicate="obsoleted-by-unit",
                arguments=("$player", rule_name, str(obsolete_field.value)),
                source=_source(obsolete_field.location, ruleset, filename),
            ))
    return Rule(
        rule_id="{}:{}:{}".format(ruleset, kind, rule_name), target_kind=kind,
        rule_name=rule_name, display_name=display_name,
        target_predicate="buildable", target_arguments=("$city", kind, rule_name),
        antecedents=_canonical_requirements(antecedents),
        obsolescence=_canonical_requirements(obsolete),
        quantitative=_quantitative(section, ruleset, filename), disabled=False,
        source=_target_source(section, ruleset, filename),
        traits=_traits(section, ruleset, filename, kind),
    )


def _stable_id(prefix, material):
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return "{}-{}".format(prefix, hashlib.sha256(encoded).hexdigest()[:24])


def _requirement_expressions(rules):
    expressions = {}
    roots = {}
    for rule in rules:
        children = []
        for requirement in rule.antecedents:
            material = requirement.to_dict()
            base_id = _stable_id("requirement", material)
            kind = (
                "grounded"
                if requirement.semantic == "grounded"
                else "atom")
            base = RequirementExpression(
                expression_id=base_id,
                kind=kind,
                atom_template=(
                    {
                        "arguments": list(requirement.arguments),
                        "predicate": requirement.predicate,
                    }
                    if kind == "atom" else None),
                grounding_template=(
                    {
                        "arguments": list(requirement.arguments),
                        "grounding": requirement.predicate,
                    }
                    if kind == "grounded" else None),
            )
            expressions[base.expression_id] = base
            child_id = base_id
            if not requirement.present:
                negative = RequirementExpression(
                    expression_id=_stable_id("requirement-not", material),
                    kind="not",
                    children=(base_id,),
                    completeness_spec={
                        "policy": "explicit-witness-at-evaluation",
                        "range": requirement.range,
                    },
                )
                expressions[negative.expression_id] = negative
                child_id = negative.expression_id
            children.append(child_id)
        if not children:
            unconditional = RequirementExpression(
                expression_id=_stable_id(
                    "requirement-true", {"rule_id": rule.rule_id}),
                kind="atom",
                atom_template={"predicate": "true", "arguments": []},
            )
            expressions[unconditional.expression_id] = unconditional
            root_id = unconditional.expression_id
        elif len(children) == 1:
            root_id = children[0]
        else:
            root = RequirementExpression(
                expression_id=_stable_id(
                    "requirement-all",
                    {"rule_id": rule.rule_id, "children": children}),
                kind="all",
                children=tuple(children),
            )
            expressions[root.expression_id] = root
            root_id = root.expression_id
        roots[rule.rule_id] = root_id
    return tuple(expressions[key] for key in sorted(expressions)), roots


def _provenance(source):
    return "{}:{}:{}:{}".format(
        source["file"], source["section"], source["field"], source["line"])


def _capabilities(rules, requirement_roots, parsed, ruleset):
    result = []
    for rule in rules:
        entity_kind = "{}-type".format(rule.target_kind)
        result.append(CapabilitySpec(
            capability_id="classification:{}:{}".format(
                rule.target_kind, rule.rule_name),
            entity_kind=entity_kind,
            source_entity_id=rule.rule_name,
            requirements=requirement_roots[rule.rule_id],
            traits=(("classification", rule.target_kind),),
            provenance=(_provenance(rule.source),),
        ))
        for trait_kind, trait in sorted(rule.traits.items()):
            for value in trait.get("values", ()):
                result.append(CapabilitySpec(
                    capability_id="trait:{}:{}:{}:{}".format(
                        rule.target_kind, rule.rule_name, trait_kind, value),
                    entity_kind=entity_kind,
                    source_entity_id=rule.rule_name,
                    requirements=requirement_roots[rule.rule_id],
                    traits=(("trait-kind", trait_kind),
                            ("trait-value", value)),
                    provenance=(_provenance(trait["source"]),),
                ))
    for filename, prefix, entity_kind in (
            ("governments.ruleset", "government_", "government"),
            ("terrain.ruleset", "terrain_", "terrain")):
        for section in parsed[filename].matching(prefix):
            name = _display(_field(section, "rule_name", _field(
                section, "name", section.name)))
            name_source = _target_source(section, ruleset, filename)
            result.append(CapabilitySpec(
                capability_id="classification:{}:{}".format(
                    entity_kind, name),
                entity_kind=entity_kind,
                source_entity_id=name,
                requirements=None,
                traits=(("classification", entity_kind),),
                provenance=(_provenance(name_source),),
            ))
            for field_name in ("class", "flags"):
                field = section.fields.get(field_name)
                if field is None:
                    continue
                values = field.value
                if isinstance(values, str):
                    values = (values,) if values else ()
                if not isinstance(values, (list, tuple)):
                    continue
                source = _source(field.location, ruleset, filename)
                for value in sorted(set(str(item) for item in values)):
                    result.append(CapabilitySpec(
                        capability_id="trait:{}:{}:{}:{}".format(
                            entity_kind, name, field_name, value),
                        entity_kind=entity_kind,
                        source_entity_id=name,
                        requirements=None,
                        traits=(("trait-kind", field_name),
                                ("trait-value", value)),
                        provenance=(_provenance(source),),
                    ))
    return tuple(sorted(result, key=lambda value: value.capability_id))


def _raw_requirement_expressions(field, ruleset, filename, section_name):
    if field is None:
        expression = RequirementExpression(
            _stable_id("requirement-true", {
                "file": filename, "section": section_name}),
            "atom",
            atom_template={"predicate": "true", "arguments": []},
        )
        return (expression,), expression.expression_id
    if not isinstance(field.value, SecTable):
        raise CompileError(
            "{}/{}:{}: [{}] reqs: expected requirement table".format(
                ruleset, filename, field.location.line, section_name))
    children = []
    result = []
    for row in field.value.dictionaries():
        material = {
            "kind": str(row.get("type")),
            "name": row.get("name"),
            "present": bool(True if row.get("present") is None
                            else row.get("present")),
            "range": str(row.get("range")),
        }
        expression = RequirementExpression(
            _stable_id("ruleset-requirement", material),
            "atom",
            atom_template={
                "arguments": [material["name"], material["range"]],
                "predicate": "ruleset-requirement:{}".format(
                    material["kind"]),
            },
            completeness_spec={
                "evaluation": "unknown-until-kind-is-registered",
                "present": material["present"],
            },
        )
        result.append(expression)
        children.append(expression.expression_id)
    if not children:
        expression = RequirementExpression(
            _stable_id("requirement-true", {
                "file": filename, "section": section_name}),
            "atom",
            atom_template={"predicate": "true", "arguments": []},
        )
        return (expression,), expression.expression_id
    if len(children) == 1:
        return tuple(result), children[0]
    root = RequirementExpression(
        _stable_id("requirement-all", {
            "file": filename, "section": section_name,
            "children": children}),
        "all",
        children=tuple(children),
    )
    result.append(root)
    return tuple(result), root.expression_id


def _effects(parsed, ruleset, unresolved_includes=()):
    expressions = {}
    effects = []
    filename = "effects.ruleset"
    for section in parsed[filename].matching("effect_"):
        effect_type = _field(section, "type")
        value = _field(section, "value")
        if effect_type is None or value is None:
            continue
        reqs, root_id = _raw_requirement_expressions(
            section.fields.get("reqs"), ruleset, filename, section.name)
        for expression in reqs:
            expressions[expression.expression_id] = expression
        source_field = section.fields.get("type")
        source = _source(source_field.location, ruleset, filename)
        metadata = [("value", value)]
        multiplier = _field(section, "multiplier")
        if multiplier is not None:
            metadata.append(("multiplier", multiplier))
        effects.append(EffectSpec(
            effect_id="{}:effect:{}".format(ruleset, section.name),
            effect_kind=str(effect_type),
            subject_template={"effect-section": section.name},
            target_template=None,
            requirements=root_id,
            exact_grounding="ruleset-effect-value",
            predictive_model=None,
            completion_predicate=None,
            confidence_cap=None,
            provenance=(_provenance(source),),
            metadata=tuple(metadata),
        ))
    for include_path, line_number in unresolved_includes:
        effects.append(EffectSpec(
            effect_id="{}:effect-include:{}".format(
                ruleset, include_path),
            effect_kind="unknown",
            subject_template={"include": include_path},
            target_template=None,
            requirements=None,
            exact_grounding=None,
            predictive_model=None,
            completion_predicate=None,
            confidence_cap=None,
            provenance=("{}/{}:{}".format(
                ruleset, filename, line_number),),
            unknown_reason=(
                "included effect file is source-hashed but not compiled"),
        ))
    return (
        tuple(expressions[key] for key in sorted(expressions)),
        tuple(sorted(effects, key=lambda value: value.effect_id)),
    )


_PROXY_ACTION_SCHEMAS = (
    ("end_turn", "player", None, "player-turn"),
    ("tech_research", "player", "technology", "research-selection"),
    ("government_change", "player", "government", "government-selection"),
    ("player_rates", "player", "rate-policy", "rate-selection"),
    ("city_production", "city", "production-target", "city-production-slot"),
    ("city_governor", "city", "governor-policy", "city-governor-slot"),
    ("unit_move", "unit", "tile", "unit-action-slot"),
    ("unit_build_city", "unit", "tile", "unit-action-slot"),
    ("unit_attack", "unit", "unit-or-tile", "unit-action-slot"),
    ("unit_fortify", "unit", None, "unit-action-slot"),
    ("unit_sentry", "unit", None, "unit-action-slot"),
)


def _action_semantics(ruleset):
    expressions = []
    effects = []
    schemas = []
    provenance = ("proxy-action-contract/1.0",)
    for action_type, actor_kind, target_kind, resource_kind in (
            _PROXY_ACTION_SCHEMAS):
        expression = RequirementExpression(
            expression_id="legal-action-binding:{}".format(action_type),
            kind="atom",
            atom_template={
                "arguments": ["$action", action_type],
                "predicate": "legal-action-type",
            },
        )
        effect = EffectSpec(
            effect_id="unknown-action-effect:{}".format(action_type),
            effect_kind="unknown",
            subject_template={"action_type": action_type},
            target_template=None,
            requirements=expression.expression_id,
            exact_grounding=None,
            predictive_model=None,
            completion_predicate=None,
            confidence_cap=None,
            provenance=provenance,
            unknown_reason=(
                "proxy contract exposes legality but no exact generic "
                "effect semantics"),
        )
        schema = ActionSchema(
            schema_id="{}:action-schema:{}".format(ruleset, action_type),
            action_type=action_type,
            actor_kind=actor_kind,
            target_kind=target_kind,
            requirements=expression.expression_id,
            effects=(effect.effect_id,),
            resource_claim_templates=({"kind": resource_kind},),
            duration_model=None,
            transition_model=None,
            legal_binding_required=True,
            provenance=provenance,
        )
        expressions.append(expression)
        effects.append(effect)
        schemas.append(schema)
    return tuple(expressions), tuple(effects), tuple(schemas)


def _grounding_specs():
    result = []
    for row in GROUNDED_SIGNATURES:
        unit, authority, paths = GROUNDING_METADATA[row["name"]]
        result.append(GroundingSpec(
            row["name"],
            tuple(row["arguments"]),
            row["returns"],
            unit,
            authority,
            tuple(paths),
            "grounding-witness/1.0",
        ))
    return tuple(sorted(result, key=lambda value: value.name))


def compile_ruleset(ruleset_root, ruleset):
    source_hashes = {}
    parsed = {}
    unresolved_effect_includes = ()
    for filename in FILES:
        path = os.path.join(ruleset_root, ruleset, filename)
        if not os.path.isfile(path):
            raise CompileError("missing ruleset source: {}/{}".format(ruleset, filename))
        source_hashes[_logical_path(ruleset, filename)] = _sha256(path)
        if filename == "effects.ruleset":
            unresolved_effect_includes = _includes(path)
            for include_path, _line in unresolved_effect_includes:
                included = os.path.join(ruleset_root, include_path)
                if os.path.isfile(included):
                    source_hashes["include/{}".format(include_path)] = (
                        _sha256(included))
        try:
            parsed[filename] = parse(path)
        except SecfileError as exc:
            raise CompileError(str(exc))
    rules = []
    for section in parsed["techs.ruleset"].matching("advance_"):
        rules.append(_compile_tech(section, ruleset, "techs.ruleset"))
    for section in parsed["units.ruleset"].matching("unit_"):
        rules.append(_compile_build_target(section, ruleset, "units.ruleset", "unit"))
    for section in parsed["buildings.ruleset"].matching("building_"):
        rules.append(_compile_build_target(section, ruleset, "buildings.ruleset", "building"))
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        duplicate = next(value for value in ids if ids.count(value) > 1)
        raise CompileError("duplicate stable target identity: {}".format(duplicate))
    rules = tuple(sorted(rules, key=lambda rule: rule.rule_id))
    rule_expressions, requirement_roots = _requirement_expressions(rules)
    effect_expressions, ruleset_effects = _effects(
        parsed, ruleset, unresolved_effect_includes)
    action_expressions, unknown_action_effects, action_schemas = (
        _action_semantics(ruleset))
    expressions = {}
    for expression in (
            rule_expressions + effect_expressions + action_expressions):
        existing = expressions.get(expression.expression_id)
        if existing is not None and existing != expression:
            raise CompileError(
                "requirement expression ID collision: {}".format(
                    expression.expression_id))
        expressions[expression.expression_id] = expression
    effects = tuple(sorted(
        ruleset_effects + unknown_action_effects,
        key=lambda value: value.effect_id))
    capabilities = _capabilities(
        rules, requirement_roots, parsed, ruleset)
    grounding_specs = _grounding_specs()
    semantics_coverage = {
        "action_schemas": len(action_schemas),
        "capability_bindings": len(capabilities),
        "exact_ruleset_effects": sum(value.known for value in effects),
        "grounding_specs": len(grounding_specs),
        "requirement_expressions": len(expressions),
        "unknown_effects": sum(not value.known for value in effects),
    }
    return RulesetIR(
        ruleset=ruleset, compiler_version=COMPILER_VERSION,
        source_hashes=dict(sorted(source_hashes.items())),
        rules=rules,
        grounded_signatures=tuple(sorted(GROUNDED_SIGNATURES, key=lambda row: row["name"])),
        predicate_catalog=tuple(sorted(PREDICATE_CATALOG, key=lambda row: row["name"])),
        parameters=_game_parameters(parsed["game.ruleset"], ruleset),
        requirement_expressions=tuple(
            expressions[key] for key in sorted(expressions)),
        capabilities=capabilities,
        effects=effects,
        action_schemas=action_schemas,
        grounding_specs=grounding_specs,
        semantics_coverage=semantics_coverage,
    )


def _metta_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def render_metta(ir):
    lines = [
        "; Generated by {}. DO NOT EDIT.".format(COMPILER_VERSION),
        "; Ruleset: {}".format(ir.ruleset),
        "; Crisp truth value for every implication: (stv 1.0 0.99)",
        "",
    ]
    for predicate in ir.predicate_catalog:
        lines.append("; predicate {}({}) [{}]".format(
            predicate["name"], ", ".join(predicate["arguments"]), predicate["role"]))
    lines.append("")
    for rule in ir.rules:
        target = "({} {})".format(rule.target_predicate, " ".join(
            value if str(value).startswith("$") else _metta_string(value)
            for value in rule.target_arguments))
        premises = []
        for req in rule.antecedents:
            atom = "({} {})".format(req.predicate, " ".join(
                value if str(value).startswith("$") else _metta_string(value)
                for value in req.arguments))
            premises.append(atom if req.present else "(Not {})".format(atom))
        if rule.disabled:
            premises.append("(disabled-target {})".format(_metta_string(rule.rule_name)))
        if not premises:
            antecedent = "(True)"
        elif len(premises) == 1:
            antecedent = premises[0]
        else:
            antecedent = "(And {})".format(" ".join(premises))
        lines.extend([
            "; {} {}:{}:{}".format(rule.rule_id, rule.source["file"],
                                    rule.source["line"], rule.source["section"]),
            "((Implication {} {}) (stv 1.0 0.99))".format(antecedent, target),
        ])
    return "\n".join(lines) + "\n"


def canonical_json(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
