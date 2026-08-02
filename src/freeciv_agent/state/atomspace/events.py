"""Bounded causal event emission for immutable FDAS revisions."""

from ...events.schema import structural_hash
from .scopes import ScopeActivationState
from .store import DependentAtomSpaceRevision


FDAS_EVENT_TYPES = frozenset((
    "atomspace_revision_started",
    "snapshot_delta_computed",
    "projection_batch_applied",
    "atom_support_added",
    "atom_support_retracted",
    "atom_invalidated",
    "atom_rederived",
    "atomspace_revision_committed",
    "scope_activation_requested",
    "scope_materialized",
    "scope_budget_exhausted",
    "grounding_evaluated",
    "grounding_cache_hit",
    "derivation_fired",
    "derivation_unknown",
    "completeness_witness_used",
    "goal_instantiated",
    "goal_resolved",
    "operation_projected",
    "operation_candidate_instantiated",
    "operation_candidate_rejected",
    "pressure_graph_built",
    "atomspace_shadow_decision",
    "episode_opened",
    "episode_effect_observed",
    "episode_relief_attributed",
    "conductance_sample_recorded",
    "induced_rule_quarantined",
    "induced_rule_promoted",
    "induced_rule_demoted",
))


class AtomSpaceEventEmitter(object):
    """Emit revision-bound events without modifying the represented revision."""

    COMPONENT_ID = "fdas-event-emitter"
    COMPONENT_VERSION = "1.0"

    def __init__(self, support_level="selected", maximum_detail_events=2000):
        if support_level not in ("none", "selected", "all"):
            raise ValueError("FDAS support event level is invalid")
        if (isinstance(maximum_detail_events, bool)
                or not isinstance(maximum_detail_events, int)
                or maximum_detail_events < 1):
            raise ValueError("FDAS detail event budget must be positive")
        self.support_level = support_level
        self.maximum_detail_events = maximum_detail_events

    @staticmethod
    def _ruleset_digest(revision, supplied=None):
        if supplied is not None:
            if not isinstance(supplied, str) or not supplied:
                raise ValueError("ruleset digest must be non-empty or absent")
            return supplied
        values = sorted(set(
            scope.validity.ruleset_digest for scope in revision.scopes
            if scope.validity.ruleset_digest is not None))
        if len(values) > 1:
            raise ValueError("revision contains multiple ruleset digests")
        return values[0] if values else "not-applicable"

    @classmethod
    def _payload(cls, revision, details, ruleset_digest,
                 component_id=None, component_version=None):
        semantic = {
            "component_id": component_id or cls.COMPONENT_ID,
            "component_version": component_version or cls.COMPONENT_VERSION,
            "details": details,
            "revision_id": revision.revision_id,
            "ruleset_digest": ruleset_digest,
            "snapshot_id": revision.snapshot_id,
        }
        semantic["structural_hash"] = structural_hash(semantic)
        return semantic

    def emit_component(self, writer, event_type, turn, revision, details,
                       caused_by=(), ruleset_digest=None,
                       component_id=None, component_version=None):
        if event_type not in FDAS_EVENT_TYPES:
            raise ValueError("unknown FDAS causal event type")
        if not isinstance(revision, DependentAtomSpaceRevision):
            raise TypeError("FDAS event requires immutable revision")
        if not isinstance(details, (dict, list, str, int, float, bool)) \
                and details is not None:
            raise TypeError("FDAS event details must be JSON-compatible")
        digest = self._ruleset_digest(revision, ruleset_digest)
        return writer.emit(
            event_type, int(turn), self._payload(
                revision, details, digest, component_id, component_version),
            caused_by=tuple(caused_by))

    @staticmethod
    def _record_maps(revision):
        records = dict((value.atom_id, value) for value in revision.records)
        supports = dict(revision.dependency_index.support_by_id)
        return records, supports

    def emit_revision(self, writer, turn, revision, prior_revision=None,
                      activation=None, ruleset_digest=None, caused_by=()):
        if not isinstance(revision, DependentAtomSpaceRevision):
            raise TypeError("revision emission requires immutable FDAS revision")
        if (prior_revision is not None
                and not isinstance(prior_revision, DependentAtomSpaceRevision)):
            raise TypeError("prior revision has the wrong type")
        if activation is not None and not isinstance(
                activation, ScopeActivationState):
            raise TypeError("revision activation has the wrong type")
        emitted = []

        def emit(event_type, details, parents=()):
            event = self.emit_component(
                writer, event_type, turn, revision, details,
                caused_by=parents, ruleset_digest=ruleset_digest)
            emitted.append(event)
            return event

        started = emit("atomspace_revision_started", {
            "build_hash": revision.build_hash,
            "cold_build": (
                None if revision.metrics is None
                else bool(revision.metrics.cold_build)),
            "prior_revision_id": (
                None if prior_revision is None else prior_revision.revision_id),
        }, tuple(caused_by))
        delta = emit("snapshot_delta_computed", {
            "delta": None if revision.delta is None else revision.delta.to_dict(),
            "metrics": (
                None if revision.metrics is None
                else revision.metrics.to_dict()),
        }, (started["event_id"],))
        if activation is not None:
            for request in activation.requests:
                emit("scope_activation_requested", request.to_dict(),
                     (started["event_id"],))
            for rejection in activation.rejected:
                emit("scope_budget_exhausted", dict(rejection),
                     (started["event_id"],))
        projected = emit("projection_batch_applied", {
            "atom_count": len(revision.records),
            "scope_count": len(revision.scopes),
            "support_count": len(revision.dependency_index.support_by_id),
        }, (delta["event_id"],))

        prior_records, prior_supports = (
            ({}, {}) if prior_revision is None
            else self._record_maps(prior_revision))
        records, supports = self._record_maps(revision)
        detail_count = 0
        omitted_count = 0

        def detail(event_type, value):
            nonlocal detail_count, omitted_count
            if detail_count >= self.maximum_detail_events:
                omitted_count += 1
                return None
            detail_count += 1
            return emit(event_type, value, (projected["event_id"],))

        for scope in revision.scopes:
            detail("scope_materialized", {
                "atom_count": len(
                    revision.dependency_index.scope_atom_ids.get(
                        scope.scope_id, ())),
                "scope_id": scope.scope_id,
                "scope_kind": scope.scope_kind,
            })
        for atom_id in sorted(set(prior_records).difference(records)):
            detail("atom_invalidated", {
                "atom_id": atom_id,
                "reason": "absent-from-current-committed-revision",
            })
        for atom_id in sorted(records):
            prior = prior_records.get(atom_id)
            if prior is None or prior != records[atom_id]:
                detail("atom_rederived", {
                    "atom_id": atom_id,
                    "predicate": records[atom_id].key.predicate,
                    "reason": (
                        "newly-projected" if prior is None
                        else "support-or-lifecycle-changed"),
                })
        if self.support_level != "none":
            added_supports = set(supports).difference(prior_supports)
            removed_supports = set(prior_supports).difference(supports)
            for support_id in sorted(added_supports):
                support = supports[support_id]
                detail("atom_support_added", {
                    "derivation_id": support.derivation_id,
                    "support_id": support_id,
                })
                detail("derivation_fired", {
                    "derivation_id": support.derivation_id,
                    "derivation_version": support.derivation_version,
                    "support_id": support_id,
                })
            for support_id in sorted(removed_supports):
                detail("atom_support_retracted", {
                    "derivation_id": prior_supports[support_id].derivation_id,
                    "support_id": support_id,
                })
        prior_operations = (
            frozenset() if prior_revision is None else
            frozenset(prior_revision.dependency_index.operation_atom_ids))
        for operation_id in sorted(set(
                revision.dependency_index.operation_atom_ids
        ).difference(prior_operations)):
            detail("operation_projected", {
                "atom_ids": list(
                    revision.dependency_index.operation_atom_ids[operation_id]),
                "operation_id": operation_id,
            })
        prior_episodes = frozenset(
            scope.root_entities[0].entity_id for scope in (
                () if prior_revision is None else prior_revision.scopes)
            if scope.scope_kind == "episode")
        for scope in revision.scopes:
            if (scope.scope_kind == "episode"
                    and scope.root_entities[0].entity_id not in prior_episodes):
                detail("episode_opened", {
                    "episode_id": scope.root_entities[0].entity_id,
                    "scope_id": scope.scope_id,
                })
        if omitted_count:
            emit("scope_budget_exhausted", {
                "budget": "maximum-detail-events",
                "limit": self.maximum_detail_events,
                "omitted_event_count": omitted_count,
            }, (projected["event_id"],))
        emit("atomspace_revision_committed", {
            "atom_count": len(revision.records),
            "build_hash": revision.build_hash,
            "detail_event_count": detail_count,
            "omitted_detail_event_count": omitted_count,
            "scope_count": len(revision.scopes),
            "support_count": len(supports),
        }, (projected["event_id"],))
        return tuple(emitted)
