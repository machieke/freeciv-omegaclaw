"""Provenance-idempotent uncertain belief store with declared decay."""

import copy
import threading

from ..events.schema import canonical_json_bytes, structural_hash
from ..pressure.provenance import confidence_to_weight, weight_to_confidence
from .model import (
    BeliefKey,
    ConflictAtom,
    ContextQuarantineOperation,
    Contribution,
    Evidence,
    Revision,
    UncertainBelief,
)


class EvidenceConflict(ValueError):
    pass


class SelfSupportingProof(EvidenceConflict):
    pass


class ContextQuarantineConflict(ValueError):
    pass


class BeliefStore(object):
    """Separate uncertain atomspace; never mutates authoritative state."""

    def __init__(self, config):
        self.config = copy.deepcopy(config)
        self._lock = threading.RLock()
        self._evidence = {}
        self._contributions = {}
        self._beliefs = {}
        self._conflicts = {}
        self._quarantines = {}

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
        weighted = [
            (row[0], confidence_to_weight(min(row[1], 1.0 - 1e-12)))
            for row in rows]
        weight = sum(row[1] for row in weighted)
        strength = (
            sum(row[0] * row[1] for row in weighted) / weight
            if weight else 0.0)
        confidence = weight_to_confidence(weight)
        return round(strength, 12), round(confidence, 12)

    def _conflict_thresholds(self):
        return (
            float(self.config["conflict_min_confidence"]),
            float(self.config["conflict_severity_threshold"]),
        )

    def _refresh_conflicts(self, key, turn):
        """Materialize current pairwise conflicts over independent token lineages."""
        prior_conflicts = {}
        for conflict_id, conflict in tuple(self._conflicts.items()):
            if conflict.key == key:
                prior_conflicts[conflict_id] = conflict
                del self._conflicts[conflict_id]
        contributions = self._contributions.get(key, {})
        minimum_confidence, severity_threshold = self._conflict_thresholds()
        eligible = []
        for provenance_id, contribution in sorted(contributions.items()):
            confidence = self._decay(key.predicate, contribution, turn)
            if confidence >= minimum_confidence:
                eligible.append((provenance_id, contribution, confidence))
        for index, (left_id, left, left_confidence) in enumerate(eligible):
            for right_id, right, right_confidence in eligible[index + 1:]:
                left_lineage = self._evidence[left_id].lineage_id
                right_lineage = self._evidence[right_id].lineage_id
                # Token identity is not evidence-source independence. Multiple
                # immutable observations from one declared lineage cannot
                # manufacture a conflict merely by changing token IDs.
                if left_lineage == right_lineage:
                    continue
                overlap = 0.0
                severity = (
                    left_confidence * right_confidence
                    * abs(float(left.strength) - float(right.strength))
                    * (1.0 - overlap))
                if severity < severity_threshold:
                    continue
                material = {
                    "key": [key.predicate, list(key.arguments)],
                    "left": [left_id],
                    "left_source_lineage": [left_lineage],
                    "right": [right_id],
                    "right_source_lineage": [right_lineage],
                }
                conflict_id = "conflict-" + structural_hash(material)[:20]
                contexts = tuple(sorted({
                    self._evidence[left_id].context_id,
                    self._evidence[right_id].context_id,
                }))
                prior = prior_conflicts.get(conflict_id)
                self._conflicts[conflict_id] = ConflictAtom(
                    conflict_id=conflict_id,
                    key=key,
                    left_provenance_ids=(left_id,),
                    right_provenance_ids=(right_id,),
                    left_tv={
                        "confidence": round(left_confidence, 12),
                        "strength": float(left.strength),
                    },
                    right_tv={
                        "confidence": round(right_confidence, 12),
                        "strength": float(right.strength),
                    },
                    overlap=overlap,
                    severity=round(severity, 12),
                    context_ids=contexts,
                    detected_turn=(
                        int(turn) if prior is None else prior.detected_turn),
                    left_source_lineage_ids=(left_lineage,),
                    right_source_lineage_ids=(right_lineage,),
                )

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
        self._refresh_conflicts(key, turn)
        prior = self._beliefs.get(key)
        tv = {"confidence": confidence, "strength": strength}
        prior_tv = None if prior is None else prior.tv
        provenance_ids = tuple(row[2] for row in rows)
        support_paths = tuple(paths)
        if prior is not None and prior_tv == tv:
            if (prior.provenance_ids == provenance_ids
                    and prior.support_paths == support_paths):
                return prior, None
            belief = UncertainBelief(
                key, strength, confidence, provenance_ids, support_paths,
                int(turn), prior.history)
            self._beliefs[key] = belief
            return belief, None
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
            key, strength, confidence, provenance_ids, support_paths, int(turn),
            history + (revision,))
        self._beliefs[key] = belief
        return belief, revision

    def observe(self, evidence):
        if not isinstance(evidence, Evidence):
            raise TypeError("observe accepts Evidence")
        with self._lock:
            if (evidence.model_provenance is not None
                    and not evidence.model_provenance.exact
                    and evidence.confidence
                    > float(self.config["simulation_confidence_cap"])):
                raise EvidenceConflict(
                    "inexact simulator evidence exceeds configured confidence cap")
            prior = self._evidence.get(evidence.provenance_id)
            if prior is not None:
                if canonical_json_bytes(prior.to_dict()) != canonical_json_bytes(evidence.to_dict()):
                    raise EvidenceConflict("provenance ID reused with different evidence")
                return self._beliefs[evidence.key], None
            self._evidence[evidence.provenance_id] = evidence
            selection_policy = evidence.selection_policy
            propensity = (
                getattr(selection_policy, "propensity", None)
                if selection_policy is not None else None)
            if propensity is None and isinstance(selection_policy, dict):
                propensity = selection_policy.get("propensity")
            selection_factor = (
                1.0 if selection_policy is None
                else float(self.config["selection_unknown_discount"])
                if propensity is None
                else float(propensity))
            corrected_confidence = evidence.confidence * selection_factor
            contribution = Contribution(
                evidence.provenance_id, evidence.strength, corrected_confidence,
                evidence.turn, (), "observation", 0.0)
            self._contributions.setdefault(evidence.key, {})[evidence.provenance_id] = contribution
            return self._recompute(
                evidence.key, evidence.turn, "apply", evidence_tv={
                    "strength": evidence.strength, "confidence": evidence.confidence,
                }, formula={"name": "provenance-union", "inputs": {
                    "selection_factor": selection_factor,
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
            unique = tuple(sorted(set(str(value) for value in support_ids)))
            unknown = [value for value in unique if value not in self._evidence]
            if unknown:
                raise EvidenceConflict("unknown provenance support: {}".format(unknown))
            paths = tuple(str(value) for value in derivation_path) + (str(rule_id),)
            if key.atom_id in paths:
                raise SelfSupportingProof(
                    "derived atom {} occurs in its own proof ancestry".format(key.atom_id))
            self_support = [
                provenance_id for provenance_id in unique
                if self._evidence[provenance_id].key == key]
            if self_support:
                raise SelfSupportingProof(
                    "derived atom {} reuses its own evidence {}".format(
                        key.atom_id, self_support))
            effective = max(0.0, float(confidence) * (1.0 - dampening))
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

    def get_in_context(self, key, context_id, turn):
        """Return a non-mutating belief view with context quarantines applied."""
        with self._lock:
            excluded = set()
            for operation in self._quarantines.values():
                if (operation.target_atom_id == key.atom_id
                        and operation.context_id == str(context_id)):
                    excluded.update(operation.excluded_provenance_ids)
            rows = []
            paths = []
            for provenance_id, contribution in sorted(
                    self._contributions.get(key, {}).items()):
                if provenance_id in excluded:
                    continue
                decayed = self._decay(key.predicate, contribution, turn)
                if decayed > 0:
                    rows.append((contribution.strength, decayed, provenance_id))
                    paths.append(
                        (provenance_id,) + tuple(contribution.derivation_path))
            strength, confidence = self._posterior(rows)
            prior = self._beliefs.get(key)
            return UncertainBelief(
                key=key,
                strength=strength,
                confidence=confidence,
                provenance_ids=tuple(row[2] for row in rows),
                support_paths=tuple(paths),
                last_revised_turn=int(turn),
                history=tuple() if prior is None else prior.history,
            )

    def conflict(self, conflict_id):
        with self._lock:
            return self._conflicts.get(str(conflict_id))

    def conflicts(self, floor=0.0):
        with self._lock:
            return tuple(
                self._conflicts[key] for key in sorted(self._conflicts)
                if self._conflicts[key].severity >= float(floor))

    def context_quarantine_operations(self, conflict_id, turn):
        """Propose deterministic context-local separation operations."""
        with self._lock:
            conflict = self._conflicts.get(str(conflict_id))
            if conflict is None:
                raise KeyError("unknown active conflict {}".format(conflict_id))
            all_ids = set(conflict.provenance_ids)
            result = []
            for context_id in conflict.context_ids:
                retained = tuple(sorted(
                    provenance_id for provenance_id in all_ids
                    if self._evidence[provenance_id].context_id == context_id))
                excluded = tuple(sorted(all_ids - set(retained)))
                if not retained or not excluded:
                    continue
                material = {
                    "conflict_id": conflict.conflict_id,
                    "context_id": context_id,
                    "excluded": list(excluded),
                    "retained": list(retained),
                    "turn": int(turn),
                }
                result.append(ContextQuarantineOperation(
                    operation_id=(
                        "context-quarantine-" + structural_hash(material)[:20]),
                    conflict_id=conflict.conflict_id,
                    target_atom_id=conflict.key.atom_id,
                    context_id=context_id,
                    excluded_provenance_ids=excluded,
                    retained_provenance_ids=retained,
                    reason="provenance-distinct conflicting context",
                    turn=int(turn),
                ))
            return tuple(result)

    def apply_context_quarantine(self, operation):
        if not isinstance(operation, ContextQuarantineOperation):
            raise TypeError(
                "apply_context_quarantine accepts ContextQuarantineOperation")
        with self._lock:
            conflict = self._conflicts.get(operation.conflict_id)
            if conflict is None:
                raise ContextQuarantineConflict(
                    "unknown active conflict {}".format(operation.conflict_id))
            if conflict.key.atom_id != operation.target_atom_id:
                raise ContextQuarantineConflict(
                    "quarantine target does not match conflict")
            conflict_ids = set(conflict.provenance_ids)
            partition = (
                set(operation.excluded_provenance_ids)
                | set(operation.retained_provenance_ids))
            if partition != conflict_ids:
                raise ContextQuarantineConflict(
                    "quarantine must partition the complete conflict lineage")
            if any(
                    self._evidence[value].context_id != operation.context_id
                    for value in operation.retained_provenance_ids):
                raise ContextQuarantineConflict(
                    "retained evidence does not belong to quarantine context")
            expected = self.context_quarantine_operations(
                conflict.conflict_id, operation.turn)
            canonical = dict((row.operation_id, row) for row in expected)
            if canonical.get(operation.operation_id) != operation:
                raise ContextQuarantineConflict(
                    "quarantine operation is not the canonical context partition")
            prior = self._quarantines.get(operation.operation_id)
            if prior is not None and prior != operation:
                raise ContextQuarantineConflict(
                    "quarantine operation ID reused with different content")
            self._quarantines[operation.operation_id] = operation
            return operation

    @property
    def quarantines(self):
        with self._lock:
            return tuple(
                self._quarantines[key] for key in sorted(self._quarantines))

    def beliefs(self, floor=0.0):
        with self._lock:
            return tuple(self._beliefs[key] for key in sorted(self._beliefs)
                         if self._beliefs[key].confidence >= floor)

    def lineage_overlap(self, left_key, right_key, turn):
        """Weighted Jaccard overlap over current decayed provenance support."""
        with self._lock:
            left = self._contributions.get(left_key, {})
            right = self._contributions.get(right_key, {})
            union = set(left) | set(right)
            if not union:
                return 0.0
            weights = {}
            for provenance_id in union:
                values = []
                if provenance_id in left:
                    values.append(self._decay(
                        left_key.predicate, left[provenance_id], turn))
                if provenance_id in right:
                    values.append(self._decay(
                        right_key.predicate, right[provenance_id], turn))
                confidence = max(values)
                weights[provenance_id] = confidence_to_weight(
                    min(confidence, 1.0 - 1e-12))
            denominator = sum(weights.values())
            return (
                sum(weights[value] for value in set(left) & set(right))
                / denominator if denominator else 0.0)

    @property
    def evidence(self):
        with self._lock:
            return tuple(self._evidence[key] for key in sorted(self._evidence))

    @property
    def artifact_hash(self):
        return structural_hash({
            "beliefs": [belief.to_dict() for belief in self.beliefs()],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts()],
            "context_quarantines": [
                operation.to_dict() for operation in self.quarantines],
        })

    def emit_observation(self, evidence, writer, caused_by=None):
        belief, revision = self.observe(evidence)
        payload = {
            "age_turns": 0, "atom": evidence.to_dict()["observed_atom"],
            "observation_id": "observation-" + structural_hash(evidence.to_dict())[:20],
            "provenance_id": evidence.provenance_id, "source": evidence.source_sensor,
        }
        if evidence.selection_policy is not None:
            payload["selection_policy"] = (
                evidence.selection_policy.to_dict()
                if hasattr(evidence.selection_policy, "to_dict")
                else copy.deepcopy(evidence.selection_policy))
        if evidence.model_provenance is not None:
            payload["model_provenance"] = evidence.model_provenance.to_dict()
        if evidence.source_lineage_id is not None:
            payload["source_lineage_id"] = evidence.source_lineage_id
        observation = writer.emit(
            "observation", evidence.turn, payload, caused_by=caused_by)
        revision_event = None
        if revision is not None:
            revision_event = writer.emit("revision", evidence.turn, {
                "evidence_tv": revision.evidence_tv, "formula": revision.formula,
                "operation": revision.operation, "posterior_tv": revision.posterior_tv,
                "prior_tv": revision.prior_tv, "provenance_id": evidence.provenance_id,
                "target_atom": belief.atom(),
            }, caused_by=[observation["event_id"]])
        return belief, observation, revision_event

    def emit_conflict(self, conflict_id, writer, caused_by=None):
        conflict = self.conflict(conflict_id)
        if conflict is None:
            raise KeyError("unknown active conflict {}".format(conflict_id))
        return writer.emit(
            "belief_conflict", conflict.detected_turn, conflict.to_dict(),
            caused_by=caused_by)

    def emit_context_quarantine(self, operation, writer, caused_by=None):
        applied = self.apply_context_quarantine(operation)
        return writer.emit(
            "context_quarantine", applied.turn, applied.to_dict(),
            caused_by=caused_by)
