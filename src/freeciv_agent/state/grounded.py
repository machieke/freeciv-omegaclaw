"""Generated-signature grounded numeric accessors over versioned snapshots."""

import hashlib
from dataclasses import dataclass

from ..events.schema import canonical_json_bytes


@dataclass(frozen=True)
class GroundedCheck:
    check_id: str
    predicate: str
    args: tuple
    snapshot_id: str
    value: object
    satisfied: bool
    available: bool
    diagnostic: object = None

    @property
    def executable(self):
        return self.available and self.satisfied

    def event_payload(self):
        return {
            "args": list(self.args), "available": self.available,
            "check_id": self.check_id, "diagnostic": self.diagnostic,
            "predicate": self.predicate, "satisfied": self.satisfied,
            "snapshot_id": self.snapshot_id, "value": self.value,
        }


def _check_id(predicate, snapshot_id, args):
    return "check-" + hashlib.sha256(canonical_json_bytes(
        {"args": list(args), "predicate": predicate,
         "snapshot_id": snapshot_id})).hexdigest()[:20]


class GroundedRegistry(object):
    """Registry entries are admitted only when declared by the Phase 2 IR."""

    IMPLEMENTED = frozenset({
        "beakers-per-turn", "build-cost", "city-size", "city-size-at-least",
        "gold-at-least", "gold-stockpile", "research-cost", "shield-stockpile",
        "shields-per-turn",
    })

    def __init__(self, ir, snapshot_store):
        self.ir = ir
        self.snapshot_store = snapshot_store
        signatures = {row["name"]: dict(row) for row in ir.grounded_signatures}
        unsupported = set(signatures) - self.IMPLEMENTED
        if unsupported:
            raise ValueError("unimplemented grounded signatures: {}".format(sorted(unsupported)))
        self.signatures = signatures
        self._rules = {}
        for rule in ir.rules:
            self._rules.setdefault((rule.target_kind, rule.rule_name), []).append(rule)

    def _snapshot(self, snapshot_id):
        return self.snapshot_store.require_snapshot(snapshot_id)

    def _result(self, predicate, snapshot_id, args, value, satisfied=True,
                available=True, diagnostic=None):
        return GroundedCheck(_check_id(predicate, snapshot_id, args), predicate,
                             tuple(args), snapshot_id, value, bool(satisfied),
                             bool(available), diagnostic)

    def _unavailable(self, predicate, snapshot_id, args, diagnostic):
        return self._result(predicate, snapshot_id, args, None, False, False, diagnostic)

    def check(self, predicate, snapshot_id, *args):
        if predicate not in self.signatures:
            raise KeyError("grounded predicate is not declared by ruleset IR: {}".format(predicate))
        snapshot = self._snapshot(snapshot_id)
        if predicate == "beakers-per-turn":
            if not snapshot.research.available or snapshot.research.beakers_per_turn is None:
                return self._unavailable(predicate, snapshot_id, args,
                                         snapshot.research.diagnostic)
            return self._result(predicate, snapshot_id, args,
                                snapshot.research.beakers_per_turn)
        if predicate == "gold-stockpile":
            if snapshot.economy.gold is None:
                return self._unavailable(predicate, snapshot_id, args,
                                         snapshot.economy.diagnostic)
            return self._result(predicate, snapshot_id, args, snapshot.economy.gold)
        if predicate == "gold-at-least":
            if len(args) < 2:
                raise ValueError("gold-at-least expects player and minimum")
            if snapshot.economy.gold is None:
                return self._unavailable(predicate, snapshot_id, args,
                                         snapshot.economy.diagnostic)
            minimum = int(args[-1])
            return self._result(predicate, snapshot_id, args, snapshot.economy.gold,
                                snapshot.economy.gold >= minimum)
        if predicate in ("city-size", "city-size-at-least", "shield-stockpile",
                         "shields-per-turn"):
            if not args:
                raise ValueError("{} expects city".format(predicate))
            city = snapshot.city(args[0])
            if city is None:
                return self._unavailable(predicate, snapshot_id, args, "unknown own city")
            if predicate == "city-size":
                return self._result(predicate, snapshot_id, args, city.size)
            if predicate == "city-size-at-least":
                if len(args) < 2:
                    raise ValueError("city-size-at-least expects city and minimum")
                return self._result(predicate, snapshot_id, args, city.size,
                                    city.size >= int(args[-1]))
            if predicate == "shield-stockpile":
                if city.shield_stock is None:
                    return self._unavailable(predicate, snapshot_id, args,
                                             "city shield_stock missing")
                return self._result(predicate, snapshot_id, args, city.shield_stock)
            # O_SHIELD is output index 1 in the FreeCiv protocol.
            if len(city.production) <= 1:
                return self._unavailable(predicate, snapshot_id, args,
                                         "city prod[O_SHIELD] missing")
            return self._result(predicate, snapshot_id, args, city.production[1])
        if predicate in ("build-cost", "research-cost"):
            if predicate == "research-cost":
                if len(args) < 2:
                    raise ValueError("research-cost expects ruleset and tech")
                kind, target = "tech", str(args[-1])
                snapshot = self._snapshot(snapshot_id)
                if snapshot.research.target_name == target and snapshot.research.cost is not None:
                    return self._result(predicate, snapshot_id, args, snapshot.research.cost)
            else:
                if len(args) < 3:
                    raise ValueError("build-cost expects ruleset, target-kind, target")
                kind, target = str(args[-2]), str(args[-1])
            rules = self._rules.get((kind, target), [])
            if not rules:
                return self._unavailable(predicate, snapshot_id, args,
                                         "target absent from compiled ruleset IR")
            values = []
            for rule in rules:
                cost = rule.quantitative.get("build_cost")
                if cost is not None:
                    values.append(int(cost["value"] if isinstance(cost, dict) else cost))
            if not values:
                return self._unavailable(predicate, snapshot_id, args,
                                         "compiled target has no cost")
            if len(set(values)) != 1:
                return self._unavailable(predicate, snapshot_id, args,
                                         "ambiguous target cost")
            return self._result(predicate, snapshot_id, args, values[0])
        raise AssertionError(predicate)

    def emit_check(self, predicate, snapshot_id, writer, turn, *args, **kwargs):
        result = self.check(predicate, snapshot_id, *args)
        event = writer.emit("grounded_check", turn, result.event_payload(),
                            caused_by=kwargs.get("caused_by"))
        return result, event
