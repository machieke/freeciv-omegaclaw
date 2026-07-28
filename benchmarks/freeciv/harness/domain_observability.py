"""Typed, trace-only projections for FreeCiv domain observability.

The browser intentionally does not reconstruct game semantics from generic
snapshots.  This emitter translates authoritative snapshots and the compiled
ruleset into explicit technology, production, and unit-lifecycle events at the
engine boundary where those semantics are available.
"""

import hashlib
import math

from freeciv_agent.rulesets.compiler import canonical_json


_YIELDS = ("food", "shield", "trade", "gold", "luxury", "science")
_PRODUCTION_KINDS = {3: "improvement", 6: "unit"}
_FOUNDER_TYPES = frozenset(("Settlers", "Migrants", "Engineers"))


def _ir_hash(ir):
    return hashlib.sha256(canonical_json(ir.to_dict())).hexdigest()


def _yield_vector(values):
    values = tuple(values or ())
    return {
        name: int(values[index]) if index < len(values) and values[index] is not None else None
        for index, name in enumerate(_YIELDS)
    }


def _target(city):
    kind = city.production_kind
    value = city.production_value
    expected = _PRODUCTION_KINDS.get(kind)
    name = next((
        str(item[2]) for item in city.buildable
        if len(item) >= 3 and item[0] == expected and int(item[1]) == value
    ), None)
    return {"kind": kind, "value": value, "name": name}


def _tech_rules(ir):
    return tuple(
        rule for rule in ir.rules
        if rule.target_kind == "tech" and not rule.disabled)


def technology_catalog_payload(ir):
    """Build a hash-pinned technology dependency catalog from compiled IR."""
    technologies = []
    for rule in _tech_rules(ir):
        prerequisites = sorted({
            str(requirement.name)
            for requirement in rule.antecedents
            if requirement.kind == "Tech" and requirement.present
        })
        technologies.append({
            "name": rule.rule_name,
            "rule_id": rule.rule_id,
            "prerequisites": prerequisites,
            "source": dict(rule.source),
        })
    technologies.sort(key=lambda item: item["name"])
    digest = _ir_hash(ir)
    return {
        "catalog_id": "{}:{}".format(ir.ruleset, digest[:16]),
        "ruleset": ir.ruleset,
        "ir_hash": digest,
        "technologies": technologies,
    }


def _raw_research_name(raw):
    if not isinstance(raw, dict):
        return None
    row = raw.get("authoritative", {}).get("research", {})
    value = row.get("researching_name") if isinstance(row, dict) else None
    return str(value) if value else None


def _raw_lifecycle(raw):
    if not isinstance(raw, dict):
        return ()
    authoritative = raw.get("authoritative", {})
    rows = authoritative.get("unit_lifecycle", ()) if isinstance(authoritative, dict) else ()
    return tuple(row for row in rows if isinstance(row, dict))


def _final_feeling(values):
    values = tuple(values or ())
    return int(values[-1]) if values else None


def _city_mood(city):
    final = {
        "happy": _final_feeling(city.feeling_happy),
        "content": _final_feeling(city.feeling_content),
        "unhappy": _final_feeling(city.feeling_unhappy),
        "angry": _final_feeling(city.feeling_angry),
    }
    margin = None
    if all(value is not None for value in final.values()):
        margin = (
            final["happy"] - final["unhappy"] - 2 * final["angry"])
    return {
        "final": final,
        "stages": {
            "happy": list(city.feeling_happy),
            "content": list(city.feeling_content),
            "unhappy": list(city.feeling_unhappy),
            "angry": list(city.feeling_angry),
        },
        "disorder": city.disorder,
        "margin": margin,
        "was_happy": city.was_happy,
    }


class DomainObservabilityEmitter(object):
    """Emit replayable domain events without changing agent decisions."""

    def __init__(self, writer, ir):
        self.writer = writer
        self.ir = ir
        self.catalog = technology_catalog_payload(ir)
        self._catalog_emitted = False
        self._previous = None
        self._previous_event_id = None
        self._previous_known = set()
        self._research_key = None
        self._research_turn = None
        self._stalled_turns = 0

    def _emit_catalog(self, snapshot, parent):
        if self._catalog_emitted:
            return
        self.writer.emit(
            "technology_catalog", snapshot.turn, self.catalog,
            caused_by=[parent])
        self._catalog_emitted = True

    def _technology_payload(self, snapshot, raw):
        research = snapshot.research
        known = set(research.known_techs)
        acquired = (
            [] if self._previous is None
            else sorted(known - self._previous_known))
        researchable = []
        blocked = []
        for rule in _tech_rules(self.ir):
            if rule.rule_name in known:
                continue
            prerequisites = {
                str(requirement.name)
                for requirement in rule.antecedents
                if requirement.kind == "Tech" and requirement.present
            }
            missing = sorted(prerequisites - known)
            if missing:
                blocked.append({
                    "name": rule.rule_name,
                    "missing_prerequisites": missing,
                })
            else:
                researchable.append(rule.rule_name)

        target_name = research.target_name or _raw_research_name(raw)
        target = None
        status = "unavailable" if not research.available else "idle"
        if target_name:
            progress = research.progress
            cost = research.cost
            remaining = (
                max(0, int(cost) - int(progress))
                if cost is not None and progress is not None else None)
            rate = research.beakers_per_turn
            eta = (
                int(math.ceil(remaining / float(rate)))
                if remaining is not None and remaining > 0 and rate is not None and rate > 0
                else 0 if remaining == 0 else None)
            if remaining == 0:
                status = "complete"
            elif rate is not None and rate > 0:
                status = "researching"
            else:
                status = "stalled"
            key = (target_name, progress)
            unchanged_across_turn = bool(
                self._research_key == key
                and self._research_turn is not None
                and snapshot.turn > self._research_turn
                and remaining is not None
                and remaining > 0)
            if unchanged_across_turn:
                status = "stalled"
                self._stalled_turns += snapshot.turn - self._research_turn
            elif status == "stalled":
                if self._research_key != key:
                    self._stalled_turns = 0
            else:
                self._stalled_turns = 0
            self._research_key = key
            self._research_turn = snapshot.turn
            target = {
                "id": research.target_id,
                "name": target_name,
                "progress": progress,
                "cost": cost,
                "remaining": remaining,
                "beakers_per_turn": rate,
                "eta_turns": eta,
            }
        else:
            self._research_key = None
            self._research_turn = snapshot.turn
            self._stalled_turns = 0
        self._previous_known = known
        return {
            "snapshot_id": snapshot.snapshot_id,
            "available": research.available,
            "diagnostic": research.diagnostic,
            "known_techs": sorted(known),
            "researchable_techs": sorted(researchable),
            "blocked_technologies": sorted(
                blocked, key=lambda item: item["name"]),
            "acquired_techs": acquired,
            "target": target,
            "status": status,
            "stalled_turns": self._stalled_turns,
            "stall_reason": (
                "government_anarchy"
                if status == "stalled" and snapshot.government.in_revolution
                else "city_disorder"
                if status == "stalled"
                and any(city.disorder is True for city in snapshot.cities)
                else "zero_science_output"
                if status == "stalled"
                and (research.beakers_per_turn is None
                     or research.beakers_per_turn <= 0)
                else "research_progress_not_advancing"
                if status == "stalled" else None),
            "government": snapshot.government.to_dict(),
        }

    def _production_payload(self, snapshot):
        economy = snapshot.economy
        support = {}
        for unit in snapshot.units:
            if unit.homecity is None or unit.homecity <= 0:
                continue
            row = support.setdefault(
                unit.homecity, {"count": 0, "food": 0, "shield": 0, "gold": 0})
            row["count"] += 1
            upkeep = tuple(unit.upkeep or ())
            row["food"] += int(upkeep[0]) if len(upkeep) > 0 else 0
            row["shield"] += int(upkeep[1]) if len(upkeep) > 1 else 0
            row["gold"] += int(upkeep[3]) if len(upkeep) > 3 else 0
        observed_unit_gold_upkeep = sum(
            row["gold"] for row in support.values())
        city_gold_surplus_per_turn = economy.city_gold_surplus_per_turn
        if city_gold_surplus_per_turn is None:
            city_gold = [
                int(city.surplus[3]) for city in snapshot.cities
                if len(city.surplus) > 3]
            city_gold_surplus_per_turn = (
                sum(city_gold)
                if len(city_gold) == len(snapshot.cities) else None)
        unit_gold_upkeep = (
            economy.unit_gold_upkeep
            if economy.unit_gold_upkeep is not None
            else observed_unit_gold_upkeep)
        net_gold_per_turn = (
            economy.gold_per_turn
            if economy.gold_per_turn is not None
            else (
                city_gold_surplus_per_turn - unit_gold_upkeep
                if city_gold_surplus_per_turn is not None else None))
        previous_cities = {
            city.city_id: city for city in self._previous.cities
        } if self._previous is not None else {}

        def city_payload(city):
            previous = previous_cities.get(city.city_id)
            previous_buildings = {
                item.improvement_id: item
                for item in previous.buildings
            } if previous is not None else {}
            current_buildings = {
                item.improvement_id: item for item in city.buildings
            }
            building_changes = []
            for improvement_id in sorted(
                    set(previous_buildings) | set(current_buildings)):
                before = previous_buildings.get(improvement_id)
                after = current_buildings.get(improvement_id)
                if (before is None) == (after is None):
                    continue
                building = after or before
                building_changes.append({
                    "transition": "completed" if after is not None else "removed",
                    "improvement_id": building.improvement_id,
                    "name": building.name,
                    "upkeep": building.upkeep,
                })
            return {
                "city_id": city.city_id,
                "name": city.name,
                "size": city.size,
                "food_stock": city.food_stock,
                "shield_stock": city.shield_stock,
                "outputs": _yield_vector(city.production),
                "usage": _yield_vector(city.usage),
                "surplus": _yield_vector(city.surplus),
                "target": _target(city),
                "buildable_count": len(city.buildable),
                "buildings": [
                    building.to_dict() for building in city.buildings
                ],
                "building_changes": building_changes,
                "building_upkeep": sum(
                    int(building.upkeep or 0) for building in city.buildings),
                "mood": _city_mood(city),
                "support": dict(support.get(
                    city.city_id,
                    {"count": 0, "food": 0, "shield": 0, "gold": 0})),
                "had_famine": city.had_famine,
                "governor": {
                    "available": city.governor_available,
                    "enabled": city.governor_enabled,
                    "minimal_surplus": list(
                        city.governor_minimal_surplus),
                    "factor": list(city.governor_factor),
                    "require_happy": city.governor_require_happy,
                    "allow_disorder": city.governor_allow_disorder,
                    "max_growth": city.governor_max_growth,
                    "allow_specialists": (
                        city.governor_allow_specialists),
                    "happy_factor": city.governor_happy_factor,
                },
            }

        scored_opponents = [
            row for row in snapshot.opponent_scores
            if row.score is not None and row.score >= 0
            and row.is_alive is not False
        ]
        leader = max(scored_opponents, key=lambda row: row.score, default=None)
        score_gap = (
            snapshot.own_score - leader.score
            if snapshot.own_score is not None and snapshot.own_score >= 0
            and leader is not None else None)
        return {
            "snapshot_id": snapshot.snapshot_id,
            "government": snapshot.government.to_dict(),
            "research_flow": {
                "gross_beakers_per_turn": (
                    snapshot.research.gross_beakers_per_turn),
                "tech_upkeep": snapshot.research.tech_upkeep,
                "net_beakers_per_turn": snapshot.research.beakers_per_turn,
            },
            "score": {
                "own": snapshot.own_score,
                "leader": leader.to_dict() if leader is not None else None,
                "gap_to_leader": score_gap,
                "opponents": [
                    row.to_dict() for row in snapshot.opponent_scores
                ],
            },
            "economy": {
                "available": economy.available,
                "diagnostic": economy.diagnostic,
                "gold": economy.gold,
                "gold_per_turn": net_gold_per_turn,
                "operating_gold_per_turn": economy.operating_gold_per_turn,
                "capitalization_gold_per_turn": (
                    economy.capitalization_gold_per_turn),
                "gold_upkeep_reserve": (
                    economy.gold_upkeep_reserve
                    if economy.gold_upkeep_reserve is not None
                    else unit_gold_upkeep),
                "city_gold_surplus_per_turn": city_gold_surplus_per_turn,
                "gold_upkeep_style": economy.gold_upkeep_style,
                "tax_rate": economy.tax_rate,
                "science_rate": economy.science_rate,
                "luxury_rate": economy.luxury_rate,
                "unit_gold_upkeep": unit_gold_upkeep,
            },
            "cities": [city_payload(city) for city in snapshot.cities],
        }

    def _removal_evidence(self, unit, raw, previous_source_seq):
        rows = [
            row for row in _raw_lifecycle(raw)
            if row.get("transition") == "disappeared"
            and row.get("unit_id") == unit.unit_id
            and int(row.get("source_seq", -1)) > previous_source_seq
        ]
        if not rows:
            return None
        row = max(rows, key=lambda item: int(item.get("source_seq", -1)))
        cause = str(row.get("cause", "engine_removed"))
        allowed = {
            "combat_attacker_lost", "combat_defender_lost", "engine_removed",
            "city_founded", "upkeep_gold", "upkeep_food",
            "combat_stack_collateral", "transport_lost",
        }
        if cause not in allowed:
            cause = "engine_removed"
        default_quality = (
            "exact" if cause in {
                "combat_attacker_lost", "combat_defender_lost",
                "city_founded", "upkeep_gold", "upkeep_food",
            }
            else "inferred" if cause in {
                "combat_stack_collateral", "transport_lost",
            }
            else "unattributed")
        quality = str(row.get("evidence_quality", default_quality))
        if quality not in {"exact", "inferred", "unattributed"}:
            quality = default_quality
        evidence = [
            str(value) for value in row.get("evidence_event_ids", ())
            if value]
        return cause, quality, row.get("detail"), evidence

    def _lifecycle_payloads(self, snapshot, raw, state_event_id):
        current = {unit.unit_id: unit for unit in snapshot.units}
        if self._previous is None:
            return [{
                "lifecycle_id": "{}:appeared:{}".format(
                    snapshot.snapshot_id, unit.unit_id),
                "transition": "appeared",
                "unit_id": unit.unit_id,
                "unit_type": unit.unit_type,
                "cause": "initial_state",
                "evidence_quality": "exact",
                "from_snapshot_id": None,
                "to_snapshot_id": snapshot.snapshot_id,
                "evidence_event_ids": [state_event_id],
                "last_position": {"x": unit.x, "y": unit.y},
                "detail": "Unit is present in the first authoritative snapshot.",
            } for unit in sorted(current.values(), key=lambda item: item.unit_id)]

        previous = {unit.unit_id: unit for unit in self._previous.units}
        results = []
        new_cities = {
            (city.x, city.y) for city in snapshot.cities
            if city.city_id not in {old.city_id for old in self._previous.cities}
        }
        previous_targets = [
            (city.x, city.y, _target(city).get("name"))
            for city in self._previous.cities
        ]
        for unit_id in sorted(set(current) - set(previous)):
            unit = current[unit_id]
            produced = any(
                x == unit.x and y == unit.y and name == unit.unit_type
                for x, y, name in previous_targets)
            results.append({
                "lifecycle_id": "{}:appeared:{}".format(
                    snapshot.snapshot_id, unit.unit_id),
                "transition": "appeared",
                "unit_id": unit.unit_id,
                "unit_type": unit.unit_type,
                "cause": "production_completed" if produced else "observed_appearance",
                "evidence_quality": "inferred",
                "from_snapshot_id": self._previous.snapshot_id,
                "to_snapshot_id": snapshot.snapshot_id,
                "evidence_event_ids": [
                    value for value in (self._previous_event_id, state_event_id) if value],
                "last_position": {"x": unit.x, "y": unit.y},
                "detail": (
                    "Appearance matches the prior city production queue."
                    if produced else
                    "First observed in the authoritative own-unit snapshot."),
            })
        for unit_id in sorted(set(previous) - set(current)):
            unit = previous[unit_id]
            proxy_evidence = self._removal_evidence(
                unit, raw, self._previous.identity.source_seq)
            city_founded = (
                unit.unit_type in _FOUNDER_TYPES
                and (unit.x, unit.y) in new_cities)
            # A generic PACKET_UNIT_REMOVE proves disappearance, not its cause.
            # Prefer simultaneous authoritative city evidence for founders,
            # while retaining exact combat correlation from the proxy journal.
            if proxy_evidence is not None and proxy_evidence[1] == "exact":
                cause, quality, detail, extra_evidence = proxy_evidence
            elif city_founded:
                cause, quality = "city_founded", "inferred"
                detail = "A new city appeared at the founder's last observed position."
                extra_evidence = []
            elif proxy_evidence is not None:
                cause, quality, detail, extra_evidence = proxy_evidence
            else:
                cause, quality = "unknown_turn_boundary", "unattributed"
                detail = (
                    "The unit vanished between snapshots; this trace contains no "
                    "causal removal packet.")
                extra_evidence = []
            results.append({
                "lifecycle_id": "{}:disappeared:{}".format(
                    snapshot.snapshot_id, unit.unit_id),
                "transition": "disappeared",
                "unit_id": unit.unit_id,
                "unit_type": unit.unit_type,
                "cause": cause,
                "evidence_quality": quality,
                "from_snapshot_id": self._previous.snapshot_id,
                "to_snapshot_id": snapshot.snapshot_id,
                "evidence_event_ids": list(dict.fromkeys([
                    value for value in (
                        self._previous_event_id, state_event_id, *extra_evidence)
                    if value])),
                "last_position": {"x": unit.x, "y": unit.y},
                "detail": detail,
            })
        return results

    def emit_snapshot(self, snapshot, state_event_id, raw=None):
        """Emit typed projections caused by one already-persisted snapshot."""
        self._emit_catalog(snapshot, state_event_id)
        self.writer.emit(
            "technology_progress", snapshot.turn,
            self._technology_payload(snapshot, raw),
            caused_by=[state_event_id])
        self.writer.emit(
            "production_state", snapshot.turn,
            self._production_payload(snapshot),
            caused_by=[state_event_id])
        for payload in self._lifecycle_payloads(snapshot, raw, state_event_id):
            self.writer.emit(
                "unit_lifecycle", snapshot.turn, payload,
                caused_by=[state_event_id])
        self._previous = snapshot
        self._previous_event_id = state_event_id
