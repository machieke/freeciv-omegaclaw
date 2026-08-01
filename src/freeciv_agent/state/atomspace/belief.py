"""Read-only FDAS projection of revised uncertain opponent beliefs."""

from ...events.schema import structural_hash
from .model import (
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    EntityRef,
    SupportRecord,
    SymbolRef,
)
from .predicates import PredicateSpec, legacy_predicate_registry
from .scopes import ScopeSpec, snapshot_scopes


_STRUCTURAL = {"structural": True}
_STRUCTURAL_HASH = structural_hash(_STRUCTURAL)


def _spec(predicate, arguments, namespace, truth_kind):
    return PredicateSpec(
        predicate, len(arguments), tuple(tuple(value) for value in arguments),
        frozenset((namespace,)), truth_kind,
        frozenset(("opponent-belief",)), "explicit-witness", "local", "1.0")


def belief_predicate_registry():
    return legacy_predicate_registry().extended((
        _spec("belief-about-opponent", (
            ("belief",), ("player",)), AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-proposition", (
            ("belief",), ("belief-predicate",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-context", (
            ("belief",), ("belief-context",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-supported-by-evidence", (
            ("belief",), ("evidence",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-current-revision", (
            ("belief",), ("belief-revision",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-model-source", (
            ("belief",), ("simulation-model",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-selection-adjusted", (
            ("belief",), ("selection-policy",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-conflict-target", (
            ("belief-conflict",), ("belief",)),
            AtomNamespace.BELIEF, "uncertain"),
        _spec("belief-conflict-lineage", (
            ("belief-conflict",), ("evidence",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
        _spec("belief-context-quarantine", (
            ("belief-quarantine",), ("belief-conflict",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
        _spec("belief-quarantine-target", (
            ("belief-quarantine",), ("belief",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
        _spec("belief-quarantine-context", (
            ("belief-quarantine",), ("belief-context",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
        _spec("belief-quarantines-evidence", (
            ("belief-quarantine",), ("evidence",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
        _spec("belief-retains-evidence", (
            ("belief-quarantine",), ("evidence",)),
            AtomNamespace.DIAGNOSTIC, "structural"),
    ))


class BeliefProjector(object):
    """Project BeliefStore output without revising or decaying it."""

    projector_id = "fdas-belief-projector"
    version = "1.0"

    def __init__(self, belief_store, confidence_floor=0.0):
        from ...beliefs import BeliefStore
        if not isinstance(belief_store, BeliefStore):
            raise TypeError("belief projection requires BeliefStore")
        confidence_floor = float(confidence_floor)
        if not 0.0 <= confidence_floor <= 1.0:
            raise ValueError("belief confidence floor must be in 0..1")
        self.belief_store = belief_store
        self.confidence_floor = confidence_floor
        self.predicate_registry = belief_predicate_registry()

    @staticmethod
    def _belief_dependency(belief):
        return DependencyRef(
            DependencyKey("belief-revision", belief.atom_id, "current"),
            structural_hash(belief.to_dict()))

    @staticmethod
    def _evidence_dependency(evidence):
        return DependencyRef(
            DependencyKey(
                "belief-evidence", evidence.provenance_id, "record"),
            structural_hash(evidence.to_dict()))

    @staticmethod
    def _conflict_dependency(conflict):
        return DependencyRef(
            DependencyKey("belief-conflict", conflict.conflict_id, "record"),
            structural_hash(conflict.to_dict()))

    @staticmethod
    def _quarantine_dependency(quarantine):
        return DependencyRef(
            DependencyKey(
                "belief-quarantine", quarantine.operation_id, "record"),
            structural_hash(quarantine.to_dict()))

    def _view(self, snapshot):
        evidence_by_id = dict(
            (value.provenance_id, value)
            for value in self.belief_store.evidence)
        beliefs = tuple(
            value for value in self.belief_store.beliefs(self.confidence_floor)
            if value.confidence > 0.0)
        if any(value.last_revised_turn != int(snapshot.turn)
               for value in beliefs):
            raise ValueError(
                "belief store must be decayed to the current snapshot turn")
        belief_by_atom = dict((value.atom_id, value) for value in beliefs)
        if len(belief_by_atom) != len(beliefs):
            raise ValueError("belief store contains duplicate belief identity")
        opponent_by_belief = {}
        for belief in beliefs:
            rows = tuple(
                evidence_by_id[value] for value in belief.provenance_ids)
            if len(rows) != len(belief.provenance_ids):
                raise ValueError("belief revision names unknown evidence")
            game_ids = {value.game_id for value in rows}
            opponents = {value.opponent_id for value in rows}
            if game_ids != {snapshot.identity.game_id}:
                raise ValueError("belief projection crosses game identity")
            if len(opponents) != 1:
                raise ValueError("belief mixes opponent identities")
            opponent_by_belief[belief.atom_id] = next(iter(opponents))
        conflicts = tuple(
            value for value in self.belief_store.conflicts()
            if value.key.atom_id in belief_by_atom)
        conflict_by_id = dict((value.conflict_id, value) for value in conflicts)
        quarantines = tuple(
            value for value in self.belief_store.quarantines
            if value.target_atom_id in belief_by_atom)
        return {
            "belief_by_atom": belief_by_atom,
            "beliefs": beliefs,
            "conflict_by_id": conflict_by_id,
            "conflicts": conflicts,
            "evidence_by_id": evidence_by_id,
            "opponent_by_belief": opponent_by_belief,
            "quarantines": quarantines,
        }

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for belief in self.belief_store.beliefs(self.confidence_floor):
            dependency = self._belief_dependency(belief)
            result[dependency.key] = dependency.fingerprint
        for evidence in self.belief_store.evidence:
            dependency = self._evidence_dependency(evidence)
            result[dependency.key] = dependency.fingerprint
        for conflict in self.belief_store.conflicts():
            dependency = self._conflict_dependency(conflict)
            result[dependency.key] = dependency.fingerprint
        for quarantine in self.belief_store.quarantines:
            dependency = self._quarantine_dependency(quarantine)
            result[dependency.key] = dependency.fingerprint
        return result

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        view = self._view(snapshot)
        opponents = sorted(set(view["opponent_by_belief"].values()))
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith("belief-")))
        for opponent_id in opponents:
            scopes.append(ScopeSpec(
                "{}:opponent-belief:{}".format(prefix, opponent_id),
                "opponent-belief", snapshot.player_id,
                (EntityRef("opponent-belief", str(opponent_id)),),
                (empire.scope_id,), (), predicates,
                frozenset((AtomNamespace.BELIEF, AtomNamespace.DIAGNOSTIC)),
                2000, 500, 250, 2, "durable-with-explicit-decay",
                empire.validity))
        return tuple(scopes)

    @staticmethod
    def _scope_map(scopes):
        return dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "opponent-belief")

    def _record(self, scope, namespace, predicate, arguments, truth,
                dependencies, witness, provenance_ids, confidence_cap=None):
        key = AtomKey(namespace, predicate, tuple(arguments), scope.scope_id)
        support = SupportRecord.create(
            self.projector_id, self.version, key.to_dict(),
            tuple(sorted(set(dependencies))), witness,
            tuple(provenance_ids), confidence_cap=confidence_cap)
        authority = (
            AuthorityClass.UNCERTAIN_BELIEF
            if namespace == AtomNamespace.BELIEF else
            AuthorityClass.CONTROL_MODEL)
        return AtomRecord.create(
            key, authority, truth, scope.validity, (support,),
            tuple(provenance_ids),
            tags=(("domain", "opponent-belief"),
                  ("epistemic", "uncertain-belief-store")),
            truth_hash=structural_hash(truth))

    def project(self, snapshot, scopes, fingerprints):
        view = self._view(snapshot)
        scope_by_opponent = self._scope_map(scopes)
        records = []
        for belief in view["beliefs"]:
            opponent_id = view["opponent_by_belief"][belief.atom_id]
            scope = scope_by_opponent[opponent_id]
            belief_ref = EntityRef("belief", belief.atom_id)
            evidence = tuple(
                view["evidence_by_id"][value]
                for value in belief.provenance_ids)
            dependencies = (
                (self._belief_dependency(belief),)
                + tuple(self._evidence_dependency(value) for value in evidence))
            truth = {
                "confidence": float(belief.confidence),
                "crisp": False,
                "strength": float(belief.strength),
                "uncertain": True,
            }
            witness = {
                "belief": belief.to_dict(),
                "belief_key": {
                    "arguments": list(belief.key.arguments),
                    "predicate": belief.key.predicate,
                },
            }
            provenance_ids = (self.projector_id,) + belief.provenance_ids

            def add(predicate, arguments, deps=dependencies, row=witness,
                    cap=None):
                records.append(self._record(
                    scope, AtomNamespace.BELIEF, predicate, arguments, truth,
                    deps, row, provenance_ids, confidence_cap=cap))

            add("belief-about-opponent", (
                belief_ref, EntityRef("player", str(opponent_id))))
            add("belief-proposition", (
                belief_ref,
                SymbolRef("belief-predicate", belief.key.predicate)))
            for context_id in sorted({value.context_id for value in evidence}):
                add("belief-context", (
                    belief_ref, EntityRef("belief-context", context_id)))
            for source in evidence:
                evidence_dependency = self._evidence_dependency(source)
                evidence_ref = EntityRef("evidence", source.provenance_id)
                add("belief-supported-by-evidence", (
                    belief_ref, evidence_ref),
                    (self._belief_dependency(belief), evidence_dependency),
                    source.to_dict())
                if source.model_provenance is not None:
                    model = source.model_provenance
                    model_id = "simulation-model-" + structural_hash(
                        model.to_dict())[:24]
                    add("belief-model-source", (
                        belief_ref, EntityRef("simulation-model", model_id)),
                        (self._belief_dependency(belief), evidence_dependency),
                        model.to_dict(), cap=model.confidence_cap)
                if source.selection_policy is not None:
                    policy = (
                        source.selection_policy.to_dict()
                        if hasattr(source.selection_policy, "to_dict") else
                        source.selection_policy)
                    add("belief-selection-adjusted", (
                        belief_ref,
                        EntityRef(
                            "selection-policy", "selection-policy-" +
                            structural_hash(policy)[:24])),
                        (self._belief_dependency(belief), evidence_dependency),
                        policy)
            if belief.history:
                revision = belief.history[-1]
                add("belief-current-revision", (
                    belief_ref,
                    EntityRef("belief-revision", revision.revision_id)),
                    dependencies, revision.to_dict())

        for conflict in view["conflicts"]:
            belief = view["belief_by_atom"][conflict.key.atom_id]
            opponent_id = view["opponent_by_belief"][belief.atom_id]
            scope = scope_by_opponent[opponent_id]
            conflict_ref = EntityRef("belief-conflict", conflict.conflict_id)
            conflict_dependency = self._conflict_dependency(conflict)
            belief_dependency = self._belief_dependency(belief)
            truth = {
                "confidence": float(conflict.atom()["tv"]["confidence"]),
                "crisp": False,
                "strength": float(conflict.severity),
                "uncertain": True,
            }
            provenance = (self.projector_id,) + conflict.provenance_ids
            records.append(self._record(
                scope, AtomNamespace.BELIEF, "belief-conflict-target",
                (conflict_ref, EntityRef("belief", belief.atom_id)), truth,
                (belief_dependency, conflict_dependency), conflict.to_dict(),
                provenance))
            for provenance_id in conflict.provenance_ids:
                records.append(self._record(
                    scope, AtomNamespace.DIAGNOSTIC,
                    "belief-conflict-lineage",
                    (conflict_ref, EntityRef("evidence", provenance_id)),
                    _STRUCTURAL,
                    (conflict_dependency,
                     self._evidence_dependency(
                         view["evidence_by_id"][provenance_id])),
                    conflict.to_dict(), provenance))

        for quarantine in view["quarantines"]:
            belief = view["belief_by_atom"][quarantine.target_atom_id]
            opponent_id = view["opponent_by_belief"][belief.atom_id]
            scope = scope_by_opponent[opponent_id]
            quarantine_ref = EntityRef(
                "belief-quarantine", quarantine.operation_id)
            conflict_ref = EntityRef(
                "belief-conflict", quarantine.conflict_id)
            quarantine_dependency = self._quarantine_dependency(quarantine)
            dependencies = [quarantine_dependency]
            conflict = view["conflict_by_id"].get(quarantine.conflict_id)
            if conflict is not None:
                dependencies.append(self._conflict_dependency(conflict))
            provenance = (
                self.projector_id, quarantine.operation_id,
            ) + quarantine.excluded_provenance_ids + (
                quarantine.retained_provenance_ids)

            def add_diagnostic(predicate, arguments, row=quarantine.to_dict()):
                records.append(self._record(
                    scope, AtomNamespace.DIAGNOSTIC, predicate, arguments,
                    _STRUCTURAL, tuple(dependencies), row, provenance))

            add_diagnostic("belief-context-quarantine", (
                quarantine_ref, conflict_ref))
            add_diagnostic("belief-quarantine-target", (
                quarantine_ref, EntityRef("belief", belief.atom_id)))
            add_diagnostic("belief-quarantine-context", (
                quarantine_ref,
                EntityRef("belief-context", quarantine.context_id)))
            for provenance_id in quarantine.excluded_provenance_ids:
                add_diagnostic("belief-quarantines-evidence", (
                    quarantine_ref, EntityRef("evidence", provenance_id)))
            for provenance_id in quarantine.retained_provenance_ids:
                add_diagnostic("belief-retains-evidence", (
                    quarantine_ref, EntityRef("evidence", provenance_id)))
        return tuple(sorted(records, key=lambda value: value.atom_id))
