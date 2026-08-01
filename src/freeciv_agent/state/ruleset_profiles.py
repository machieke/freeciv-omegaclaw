"""Shared conservative profiles derived from compiled ruleset IR."""

import math
import re


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _trait_values(rule, name):
    value = getattr(rule, "traits", {}).get(name, {})
    rows = value.get("values", ()) if isinstance(value, dict) else ()
    return tuple(sorted({_normalized(row) for row in rows if row}))


def population_recovery_profile(ruleset_ir, unit_type):
    """Return one exact founder join-city profile, otherwise unknown."""
    target = _normalized(unit_type)
    matches = []
    for rule in getattr(ruleset_ir, "rules", ()):
        if getattr(rule, "target_kind", None) != "unit":
            continue
        labels = {
            _normalized(getattr(rule, "display_name", "")),
            _normalized(getattr(rule, "rule_name", "")),
        }
        if target not in labels:
            continue
        value = getattr(rule, "quantitative", {}).get("pop_cost")
        if isinstance(value, dict):
            value = value.get("value")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or int(value) != value
                or int(value) <= 0):
            return None
        flags = _trait_values(rule, "flags")
        matches.append({
            "add_to_city": "addtocity" in flags,
            "founder_capable": "cities" in flags,
            "population_gain": int(value),
            "unit_type": str(getattr(rule, "display_name", unit_type)),
        })
    if len(matches) != 1:
        return None
    profile = matches[0]
    return profile if profile["add_to_city"] and profile[
        "founder_capable"] else None
