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
    "atomspace_authority_decision",
    "episode_opened",
    "episode_effect_observed",
    "episode_relief_attributed",
    "episode_outcome_label_opened",
    "episode_outcome_label_observed",
    "operation_outcome_label_opened",
    "operation_outcome_label_product_observed",
    "operation_outcome_label_observed",
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
        def derivation_semantic(record):
            # A current-revision validity refresh is not a derivation fire.
            # Support, truth, lifecycle, provenance, or namespace changes are.
            return (
                record.key, record.authority, record.truth, record.supports,
                record.provenance_ids, record.lifecycle, record.tags)

        for atom_id in sorted(records):
            prior = prior_records.get(atom_id)
            if (prior is None
                    or derivation_semantic(prior)
                    != derivation_semantic(records[atom_id])):
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

    def emit_shadow_evaluation(
            self, writer, turn, revision, evaluation,
            ruleset_digest=None, caused_by=()):
        """Emit bounded goal/candidate/pressure evidence after legacy readout."""
        if not isinstance(revision, DependentAtomSpaceRevision):
            raise TypeError("shadow evaluation requires immutable revision")
        if (getattr(evaluation, "revision_id", None) != revision.revision_id
                or getattr(evaluation, "snapshot_id", None)
                != revision.snapshot_id):
            raise ValueError("shadow evaluation is not revision-current")
        emitted = []
        parent_ids = tuple(caused_by)
        detail_count = 0
        omitted_count = 0

        def emit(event_type, details, parents=None):
            event = self.emit_component(
                writer, event_type, turn, revision, details,
                caused_by=parent_ids if parents is None else tuple(parents),
                ruleset_digest=ruleset_digest,
                component_id="fdas-goal-pressure-shadow",
                component_version="1.0")
            emitted.append(event)
            return event

        for goal in evaluation.goals:
            if detail_count >= max(0, self.maximum_detail_events - 2):
                omitted_count += 1
                continue
            emit("goal_instantiated", {
                "deficit_atom_id": goal.deficit_atom_id,
                "deficit_predicate": goal.deficit_predicate,
                "explanation_hash": goal.explanation_hash,
                "goal_id": goal.goal.goal_id,
                "scope_id": goal.scope_id,
            })
            detail_count += 1
        for candidate in evaluation.candidates:
            if detail_count >= max(0, self.maximum_detail_events - 2):
                omitted_count += 1
                continue
            details = {
                    "action_key": candidate.action_key,
                    "authority_eligible": False,
                    "blockers": list(candidate.blockers),
                    "candidate_hash": candidate.candidate_hash,
                    "legal_bound": candidate.legal_bound,
                    "operation_id": candidate.operation.operation_id,
                    "operation_type": candidate.operation.operation_type,
                }
            assembly = getattr(candidate, "production_assembly", None)
            if assembly is not None:
                artifact = assembly.model_artifact
                details["grounded_production_operation"] = {
                    "completion_eta": artifact.get("completion_eta"),
                    "initial_step_index": assembly.initial_step_index,
                    "model_artifact_hash": structural_hash(artifact),
                    "policy_authority": False,
                    "queue_selection_is_goal_relief": False,
                    "requirement_set_id": (
                        assembly.requirement_set.requirement_set_id),
                    "resource_claim_count": len(
                        assembly.resource_request.claims),
                    "shadow_only": True,
                    "step_count": len(assembly.spec.steps),
                }
            emit(
                "operation_candidate_rejected" if candidate.blockers
                else "operation_candidate_instantiated", details)
            detail_count += 1
        pressure = evaluation.pressure
        instantiation = evaluation.candidate_instantiation
        pressure_event = emit("pressure_graph_built", {
            "candidate_atom_count": len(
                pressure.context.candidate_atom_ids),
            "candidate_instantiation_hash": (
                instantiation.instantiation_hash),
            "diagnostics": list(sorted(set(
                pressure.context.diagnostics + instantiation.diagnostics))),
            "evaluation_hash": pressure.evaluation_hash,
            "gap_atom_count": len(pressure.context.gap_atom_ids),
            "goal_count": len(pressure.context.goals),
            "graph_hash": pressure.context.graph.artifact_hash,
            "operation_count": len(pressure.context.operations),
            "omitted_unprotected_candidate_count": (
                instantiation.omitted_unprotected_count),
            "policy_authority": False,
            "status": pressure.status,
            "truncated": pressure.context.truncated,
        })
        comparison = evaluation.comparison
        comparison_details = None if comparison is None else {
            "authority_violations": list(comparison.authority_violations),
            "comparison_hash": comparison.comparison_hash,
            "explained_legacy_count": len(
                comparison.explained_legacy),
            "extra_fdas_count": len(comparison.extra_fdas),
            "fdas_candidate_count": comparison.fdas_candidate_count,
            "legal_binding_failures": list(
                comparison.legal_binding_failures),
            "legacy_candidate_count": comparison.legacy_candidate_count,
            "missing_legacy_count": len(comparison.missing_legacy),
            "overlap_count": len(comparison.overlapping_action_keys),
            "safety_downgrades": list(comparison.safety_downgrades),
        }
        emit("atomspace_shadow_decision", {
            "authority_eligible": False,
            "comparison": comparison_details,
            "evaluation_hash": pressure.evaluation_hash,
            "candidate_instantiation_hash": (
                instantiation.instantiation_hash),
            "decision_explanation_hash": (
                evaluation.decision_explanation.explanation_hash),
            "decision_route_kind": (
                evaluation.decision_explanation.route_kind),
            "decision_blockers": list(
                evaluation.decision_explanation.blockers),
            "latency_ms": evaluation.latency_ms,
            "omitted_detail_event_count": omitted_count,
            "reason": pressure.reason,
            "schedule_hash": pressure.schedule.get("structural_hash"),
            "selected_operation_id": pressure.schedule.get(
                "selected_operation_id"),
            "stage_latency_ms": dict(evaluation.stage_latency_ms),
            "status": pressure.status,
        }, (pressure_event["event_id"],))
        return tuple(emitted)

    def emit_authority_readout(
            self, writer, turn, revision, readout,
            ruleset_digest=None, caused_by=()):
        """Emit the exact FDAS authority or legacy-fallback decision."""
        if not isinstance(revision, DependentAtomSpaceRevision):
            raise TypeError("authority readout requires immutable revision")
        if (getattr(readout, "revision_id", None) != revision.revision_id
                or getattr(readout, "snapshot_id", None)
                != revision.snapshot_id):
            raise ValueError("authority readout is not revision-current")
        return self.emit_component(
            writer, "atomspace_authority_decision", turn, revision,
            readout.to_dict(), caused_by=tuple(caused_by),
            ruleset_digest=ruleset_digest,
            component_id="fdas-bounded-city-authority",
            component_version="1.0")
