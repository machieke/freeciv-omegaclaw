"""Provenance-idempotent uncertain belief store with declared decay."""

import copy
import math
import threading

from ..events.schema import canonical_json_bytes, structural_hash
from .model import BeliefKey, Contribution, Evidence, Revision, UncertainBelief


class EvidenceConflict(ValueError):
    pass


class BeliefStore(object):
    """Separate uncertain atomspace; never mutates authoritative state."""

    def __init__(self, config):
        self.config = copy.deepcopy(config)
        self._lock = threading.RLock()
        self._evidence = {}
        self._contributions = {}
        self._beliefs = {}

    def _schedule(self, predicate):
        return self.config["decay"].get(predicate, self.config["decay"]["default"])

    def _decay(self, predicate, contribution, turn):
        age = max(0, int(turn) - int(contribution.source_turn))
        window = self._schedule(predicate)["window_turns"]
        return contribution.confidence * max(0.0, 1.0 - float(age) / float(window))

    @staticmethod
    def _posterior(rows):
        if not rows:
            return 0.0, 0.0
        confidence = 1.0 - math.prod(1.0 - row[1] for row in rows)
        weight = sum(row[1] for row in rows)
        strength = sum(row[0] * row[1] for row in rows) / weight if weight else 0.0
        return round(strength, 12), round(confidence, 12)

    def _recompute(self, key, turn, operation, evidence_tv, formula):
        by_provenance = self._contributions.get(key, {})
        # One provenance contributes once even when it reaches the conclusion by many paths.
        rows = []
        paths = []
        for provenance_id, contribution in sorted(by_provenance.items()):
            decayed = self._decay(key.predicate, contribution, turn)
            if decayed > 0:
                rows.append((contribution.strength, decayed, provenance_id))
                paths.append((provenance_id,) + tuple(contribution.derivation_path))
        strength, confidence = self._posterior(rows)
        prior = self._beliefs.get(key)
        tv = {"confidence": confidence, "strength": strength}
        prior_tv = None if prior is None else prior.tv
        if prior is not None and prior_tv == tv:
            return prior, None
        provenance_ids = tuple(row[2] for row in rows)
        revision_material = {
            "formula": formula, "key": [key.predicate, list(key.arguments)],
            "operation": operation, "posterior": tv,
            "provenance_ids": provenance_ids, "turn": int(turn),
        }
        revision = Revision(
            "revision-" + structural_hash(revision_material)[:20], int(turn), operation,
            prior_tv, dict(evidence_tv), tv, provenance_ids, copy.deepcopy(formula))
        history = tuple() if prior is None else prior.history
        belief = UncertainBelief(
            key, strength, confidence, provenance_ids, tuple(paths), int(turn),
            history + (revision,))
        self._beliefs[key] = belief
        return belief, revision

    def observe(self, evidence):
        if not isinstance(evidence, Evidence):
            raise TypeError("observe accepts Evidence")
        with self._lock:
            prior = self._evidence.get(evidence.provenance_id)
            if prior is not None:
                if canonical_json_bytes(prior.to_dict()) != canonical_json_bytes(evidence.to_dict()):
                    raise EvidenceConflict("provenance ID reused with different evidence")
                return self._beliefs[evidence.key], None
            self._evidence[evidence.provenance_id] = evidence
            contribution = Contribution(
                evidence.provenance_id, evidence.strength, evidence.confidence,
                evidence.turn, (), "observation", 0.0)
            self._contributions.setdefault(evidence.key, {})[evidence.provenance_id] = contribution
            return self._recompute(
                evidence.key, evidence.turn, "apply", evidence_tv={
                    "strength": evidence.strength, "confidence": evidence.confidence,
                }, formula={"name": "provenance-union", "inputs": {
                    "unique_provenance": len(self._contributions[evidence.key])}},)

    def derive(self, key, support_ids, turn, strength, confidence,
               rule_id, derivation_path=(), dampening_lambda=None):
        if not isinstance(key, BeliefKey):
            raise TypeError("derive key must be BeliefKey")
        dampening = (self.config["dampening_lambda"] if dampening_lambda is None
                     else float(dampening_lambda))
        if not 0 <= dampening <= 1:
            raise ValueError("dampening lambda must be in [0,1]")
        with self._lock:
            unique = tuple(sorted(set(support_ids)))
            unknown = [value for value in unique if value not in self._evidence]
            if unknown:
                raise EvidenceConflict("unknown provenance support: {}".format(unknown))
            effective = max(0.0, float(confidence) * (1.0 - dampening))
            paths = tuple(derivation_path) + (str(rule_id),)
            target = self._contributions.setdefault(key, {})
            for provenance_id in unique:
                candidate = Contribution(
                    provenance_id, float(strength), effective,
                    self._evidence[provenance_id].turn,
                    paths, str(rule_id), dampening)
                prior = target.get(provenance_id)
                # Multiple paths rooted in the same evidence never compound. Keep a
                # deterministic maximum evidence contribution and canonical path.
                if (prior is None
                        or candidate.confidence > prior.confidence
                        or (candidate.confidence == prior.confidence
                            and candidate.strength > prior.strength)
                        or (candidate.confidence == prior.confidence
                            and candidate.strength == prior.strength
                            and candidate.derivation_path < prior.derivation_path)):
                    target[provenance_id] = candidate
            return self._recompute(
                key, turn, "apply", {"strength": float(strength),
                                     "confidence": effective},
                {"name": "uncertain-deduction", "inputs": {
                    "dampening_lambda": dampening, "rule_id": str(rule_id),
                    "support_ids": list(unique)}})

    def decay_to(self, turn):
        revisions = []
        with self._lock:
            for key in sorted(self._contributions):
                belief, revision = self._recompute(
                    key, turn, "decay", {"strength": 0.0, "confidence": 0.0},
                    {"name": "linear-window", "inputs": {
                        "turn": int(turn),
                        "window_turns": self._schedule(key.predicate)["window_turns"]}})
                if revision is not None:
                    revisions.append((belief, revision))
        return tuple(revisions)

    def get(self, key):
        with self._lock:
            return self._beliefs.get(key)

    def beliefs(self, floor=0.0):
        with self._lock:
            return tuple(self._beliefs[key] for key in sorted(self._beliefs)
                         if self._beliefs[key].confidence >= floor)

    @property
    def evidence(self):
        with self._lock:
            return tuple(self._evidence[key] for key in sorted(self._evidence))

    @property
    def artifact_hash(self):
        return structural_hash([belief.to_dict() for belief in self.beliefs()])

    def emit_observation(self, evidence, writer, caused_by=None):
        belief, revision = self.observe(evidence)
        observation = writer.emit("observation", evidence.turn, {
            "age_turns": 0, "atom": evidence.to_dict()["observed_atom"],
            "observation_id": "observation-" + structural_hash(evidence.to_dict())[:20],
            "provenance_id": evidence.provenance_id, "source": evidence.source_sensor,
        }, caused_by=caused_by)
        revision_event = None
        if revision is not None:
            revision_event = writer.emit("revision", evidence.turn, {
                "evidence_tv": revision.evidence_tv, "formula": revision.formula,
                "operation": revision.operation, "posterior_tv": revision.posterior_tv,
                "prior_tv": revision.prior_tv, "provenance_id": evidence.provenance_id,
                "target_atom": belief.atom(),
            }, caused_by=[observation["event_id"]])
        return belief, observation, revision_event
