"""Aggregate, versioned event emission for the unified control boundary."""

import json
import math
import time

from ..events.schema import (
    canonical_json_bytes,
    structural_hash,
)
from .impact_flow_adapter import (
    ControlDecision,
    ControlOutcomeRecord,
    ControlQuery,
)
from .combat_lifecycle import (
    CombatOperationLifecycle,
)
from .operation_assembler import (
    assemble_city_defense_operation,
)
from .operation_store import (
    OperationStore,
    OperationStoreError,
    OperationTransitionError,
)
from .operations import (
    OperationAuthorityKind,
    OperationAuthorityReadout,
    OperationState,
)


CONTROL_EVENT_SCHEMA_VERSION = "1.0"


def _flow_artifact(decision):
    """Return a nested unified-flow artifact without inventing provenance."""
    artifact = decision.artifact
    if not isinstance(artifact, dict):
        return None
    if isinstance(artifact.get("flow"), dict):
        return artifact
    target = artifact.get("target_artifact")
    if (isinstance(target, dict)
            and isinstance(
                target.get("artifact"), dict)):
        return _flow_artifact(
            ControlDecision(
                ordered_candidate_keys=tuple(
                    target.get(
                        "ordered_candidate_keys", ())),
                selected_candidate_key=target.get(
                    "selected_candidate_key"),
                packet_schedule=None,
                controller_mode=str(target.get(
                    "controller_mode", "unified_flow")),
                artifact=target["artifact"],
                health=str(target.get(
                    "health", "unavailable")),
                fallback_chain=tuple(
                    target.get("fallback_chain", ()))))
    advisory = artifact.get("advisory")
    if (isinstance(advisory, dict)
            and isinstance(
                advisory.get("artifact"), dict)):
        nested = advisory["artifact"].get(
            "target_artifact")
        if (isinstance(nested, dict)
                and isinstance(
                    nested.get("artifact"), dict)):
            return nested["artifact"]
    for row in artifact.get(
            "shadow_decisions", ()):
        if (isinstance(row, dict)
                and row.get("controller_mode")
                == "unified_flow"
                and isinstance(
                    row.get("decision"), dict)
                and isinstance(
                    row["decision"].get(
                        "artifact"), dict)):
            return row["decision"]["artifact"]
    return None


def _topology_generation(query, flow_artifact):
    try:
        return int(
            flow_artifact["flow"][
                "factorization"]["view"][
                    "topology_generation"])
    except (KeyError, TypeError, ValueError):
        return int(query.pressure_generation)


def _compact_transport_readout(value):
    if not isinstance(value, dict):
        return value
    selected_id = value.get(
        "selected_operation_id")
    scalar_id = value.get(
        "scalar_selected_operation_id")
    candidates = []
    seen = set()
    rows = value.get(
        "candidate_readouts", ())
    if isinstance(rows, list):
        priority = [
            row for row in rows
            if (isinstance(row, dict)
                and row.get("operation_id")
                in (selected_id, scalar_id))]
        priority.extend(
            row for row in rows[:8]
            if isinstance(row, dict))
        for row in priority:
            operation_id = row.get(
                "operation_id")
            if operation_id in seen:
                continue
            seen.add(operation_id)
            candidates.append(row)
    return {
        "candidate_union": value.get(
            "candidate_union"),
        "candidate_readouts": candidates,
        "candidate_regions": value.get(
            "candidate_regions", ()),
        "disagrees_with_scalar": value.get(
            "disagrees_with_scalar"),
        "maximum_overlap": value.get(
            "maximum_overlap"),
        "scalar_selected_operation_id":
            scalar_id,
        "selected_node_id": value.get(
            "selected_node_id"),
        "selected_operation_id":
            selected_id,
        "selected_overlap": value.get(
            "selected_overlap"),
    }


def _protected_bridge_union(value):
    """Return a logged direct-bridge union without reconstructing it."""
    if not isinstance(value, dict):
        return None
    for row in reversed(
            value.get("goal_selections", ())):
        if not isinstance(row, dict):
            continue
        candidate = row.get(
            "protected_candidate_union")
        if isinstance(candidate, dict):
            return candidate
    return None


def _flow_candidate_key(decision, flow_artifact):
    """Identify the flow proposal even when shadow/advisory falls back."""
    keys = flow_artifact.get(
        "admissible_candidate_keys", ())
    if (isinstance(keys, (list, tuple))
            and len(keys) == 1
            and isinstance(keys[0], str)
            and keys[0]):
        return keys[0]
    return decision.selected_candidate_key


def _flow_selection_disposition(decision):
    artifact = decision.artifact
    if decision.controller_mode == "unified_shadow":
        return "shadow-only"
    if artifact.get("advisory_accepted") is False:
        return "guarded-fallback"
    if artifact.get("advisory_accepted") is True:
        return "advisory-accepted"
    if decision.controller_mode == "unified_flow_live":
        return "live-accepted"
    return "controller-selected"


class ControlEventEmitter:
    """Write compact semantic-boundary events, never per-probe/path events."""

    EMITTER_IDENTITY = "unified-control-events/1.0"

    def __init__(self):
        # Completed asynchronous shadow batches may remain cached and be
        # surfaced by more than one decision.  A request is one observation,
        # so emit it once per run-scoped emitter.
        self._emitted_domain_request_ids = set()
        self._emitted_resource_batch_ids = set()
        self._emitted_combat_snapshot_ids = set()
        self._emitted_city_defense_snapshot_ids = set()
        self._city_defense_authority_games = set()
        # Capacity events describe changes across decisions.  Index by the
        # stable resource identity rather than snapshot-scoped capacity ID.
        self._last_resource_capacity = {}
        self._operation_stores = {}
        self._operation_payloads = {}
        self._operation_action_keys = {}
        self._operation_event_ids = {}
        self._combat_lifecycles = {}
        self._production_lifecycles = {}
        self._replacement_capacity_production_lifecycles = {}
        self._research_lifecycles = {}
        self._prepared_enabling_actions = set()
        self._emitted_production_persistence_guards = set()

    def _operation_store_for(self, writer):
        game_id = str(
            writer.game_id)
        store = self._operation_stores.get(
            game_id)
        if store is None:
            store = OperationStore(
                "game:{}".format(
                    game_id))
            self._operation_stores[
                game_id] = store
        return store

    def fdas_operation_records(self, game_id):
        """Return one immutable, deduplicated view of durable operations.

        FDAS projection is a read-only consumer.  Asking for this view never
        creates a lifecycle or operation store and therefore cannot change
        planner behavior merely because shadow projection is enabled.
        """
        game_id = str(game_id)
        stores = []
        direct = self._operation_stores.get(game_id)
        if direct is not None:
            stores.append(direct)
        for lifecycles in (
                self._combat_lifecycles,
                self._production_lifecycles,
                self._research_lifecycles):
            lifecycle = lifecycles.get(game_id)
            if lifecycle is not None:
                stores.append(lifecycle.store)
        records = {}
        for store in stores:
            if store.quarantined:
                raise ValueError(
                    "quarantined operation source cannot enter FDAS")
            for record in store.records():
                operation_id = record.spec.operation_id
                prior = records.get(operation_id)
                if prior is not None and prior != record:
                    raise ValueError(
                        "conflicting durable operation identity: {}".format(
                            operation_id))
                records[operation_id] = record
        return tuple(records[key] for key in sorted(records))

    def _combat_lifecycle_for(
            self, writer):
        game_id = str(
            writer.game_id)
        lifecycle = (
            self._combat_lifecycles
            .get(game_id))
        if lifecycle is None:
            lifecycle = (
                CombatOperationLifecycle(
                    game_id))
            self._combat_lifecycles[
                game_id] = lifecycle
        return lifecycle

    def _production_lifecycle_for(
            self, writer):
        from .production_lifecycle import (
            ProductionOperationLifecycle,
        )

        game_id = str(writer.game_id)
        lifecycle = self._production_lifecycles.get(
            game_id)
        if lifecycle is None:
            lifecycle = ProductionOperationLifecycle(
                game_id)
            self._production_lifecycles[
                game_id] = lifecycle
        return lifecycle

    def _replacement_capacity_production_lifecycle_for(
            self, writer):
        from .production_lifecycle import ProductionOperationLifecycle

        game_id = str(writer.game_id)
        lifecycle = self._replacement_capacity_production_lifecycles.get(
            game_id)
        if lifecycle is None:
            lifecycle = ProductionOperationLifecycle(
                "fdas-replacement-capacity:{}".format(game_id))
            self._replacement_capacity_production_lifecycles[
                game_id] = lifecycle
        return lifecycle

    def _research_lifecycle_for(
            self, writer):
        from .research_lifecycle import (
            ResearchOperationLifecycle,
        )

        game_id = str(writer.game_id)
        lifecycle = self._research_lifecycles.get(
            game_id)
        if lifecycle is None:
            lifecycle = ResearchOperationLifecycle(
                game_id)
            self._research_lifecycles[
                game_id] = lifecycle
        return lifecycle

    def _active_city_defense_record(
            self, store, payload, turn):
        """Find the persistent operation owning a newly grounded route step."""
        if not isinstance(payload, dict):
            return None
        matches = []
        for record in (
                store.nonterminal_records()):
            if (record.progress.state
                    != OperationState.ACTIVE
                    or record.spec.expiry_turn
                    < int(turn)):
                continue
            previous = (
                self._operation_payloads
                .get(
                    record.spec
                    .operation_id))
            if (
                    isinstance(previous, dict)
                    and previous.get(
                        "operation_type")
                    == payload.get(
                        "operation_type")
                    and previous.get(
                        "actor_id")
                    == payload.get(
                        "actor_id")
                    and previous.get(
                        "target_id")
                    == payload.get(
                        "target_id")
            ):
                matches.append(record)
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda row: (
                row.spec.expiry_turn,
                row.spec.operation_id))[0]

    def operation_authority_readout(
            self, writer, snapshot,
            city_defense_enabled=False,
            combat_enabled=False):
        """Return one exact, reserved next step for a bounded live slice.

        Scheduling and lifecycle observation remain responsible for producing
        the reservation.  This boundary only exposes a byte-identical current
        legal action and fails closed when provenance, reservation, deadline,
        or current-step support is incomplete.
        """
        if snapshot is None:
            return None
        snapshot_id = str(
            getattr(
                snapshot, "snapshot_id", ""))
        legal_actions_digest = str(
            getattr(
                snapshot,
                "legal_actions_digest", ""))
        legal_keys = frozenset(
            str(value) for value in
            getattr(
                snapshot,
                "legal_action_json", ()))
        if (not snapshot_id
                or not legal_actions_digest
                or not legal_keys):
            return None
        turn = int(
            getattr(snapshot, "turn", 0))
        candidates = []
        if city_defense_enabled:
            store = self._operation_store_for(
                writer)
            for record in (
                    store
                    .nonterminal_records()):
                operation_id = (
                    record.spec.operation_id)
                payload = (
                    self._operation_payloads
                    .get(operation_id))
                action_key = (
                    self._operation_action_keys
                    .get(operation_id))
                if (
                    record.progress.state
                    not in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE)
                    or record.progress
                    .last_snapshot_id
                    != snapshot_id
                    or record.spec.expiry_turn
                    < turn
                    or not isinstance(
                        payload, dict)
                    or action_key
                    not in legal_keys
                    or not isinstance(
                        payload.get(
                            "next_action"),
                        dict)
                ):
                    continue
                step = record.spec.steps[
                    record.progress
                    .current_step_index]
                if (
                        record.progress.state
                        == OperationState.ACTIVE
                        and record.progress
                        .attempt_count
                        >= step
                        .maximum_attempts
                ):
                    continue
                readout = OperationAuthorityReadout(
                    authority_kind=(
                        OperationAuthorityKind
                        .CITY_DEFENSE),
                    operation_id=operation_id,
                    operation_type=(
                        record.spec
                        .operation_type),
                    action=dict(
                        payload[
                            "next_action"]),
                    action_key=action_key,
                    candidate_category=(
                        "city_defense"),
                    snapshot_id=snapshot_id,
                    legal_actions_digest=(
                        legal_actions_digest),
                    bid=float(
                        payload.get(
                            "bid", 0.0)),
                    provenance=tuple(
                        payload.get(
                            "provenance")
                        or (
                            "city-defense-exact-assignment",
                        )))
                candidates.append((
                    0,
                    -float(
                        payload.get(
                            "expected_prevented_loss",
                            readout.bid)),
                    operation_id,
                    readout))
        if combat_enabled:
            from .combat_operations import (
                CombatOperationAssembler,
            )
            lifecycle = (
                self._combat_lifecycle_for(
                    writer))
            for record in (
                    lifecycle.store
                    .nonterminal_records()):
                operation_id = (
                    record.spec.operation_id)
                assembly = (
                    lifecycle.assembly(
                        operation_id))
                reservation = (
                    lifecycle.ledger
                    .reservation(
                        operation_id))
                payload = (
                    self._operation_payloads
                    .get(operation_id))
                if (
                    record.progress.state
                    not in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE)
                    or record.spec.expiry_turn
                    < turn
                    or assembly is None
                    or reservation is None
                    or not reservation.active
                    or not isinstance(
                        payload, dict)
                ):
                    continue
                step_index = (
                    record.progress
                    .current_step_index)
                if step_index >= len(
                        assembly.spec.steps):
                    continue
                domain_readout = (
                    CombatOperationAssembler
                    .readout(
                        assembly, snapshot,
                        step_index))
                action = (
                    domain_readout
                    .next_action)
                if (
                    domain_readout
                    .disposition
                    != "reservable"
                    or not isinstance(
                        action, dict)
                ):
                    continue
                action_key = (
                    canonical_json_bytes(
                        action)
                    .decode("utf-8"))
                if action_key not in (
                        legal_keys):
                    continue
                bid = float(
                    domain_readout
                    .material_estimate
                    .conservative_bid)
                if bid <= 0.0:
                    continue
                readout = OperationAuthorityReadout(
                    authority_kind=(
                        OperationAuthorityKind
                        .COMBAT),
                    operation_id=operation_id,
                    operation_type=(
                        record.spec
                        .operation_type),
                    action=dict(action),
                    action_key=action_key,
                    candidate_category=(
                        "tactical_attack"),
                    snapshot_id=snapshot_id,
                    legal_actions_digest=(
                        legal_actions_digest),
                    bid=bid,
                    provenance=tuple(
                        payload.get(
                            "provenance")
                        or (
                            "combat-exact-schedule",
                        )))
                candidates.append((
                    1, -bid,
                    operation_id,
                    readout))
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda row: (
                row[0], row[1],
                row[2]))[0][3]

    def prepare_city_defense_authority(
            self, writer, snapshot,
            ruleset_ir, candidates,
            threat_radius, node_budget,
            ruleset_digest,
            caused_by=()):
        """Prepare one current-snapshot exact city-defence reservation.

        The ordinary GDO-4 resource schedule remains asynchronous shadow work.
        A bounded live pilot cannot consume that result because it is stale by
        the time it is polled.  This default-off boundary computes only the
        city-defence subproblem synchronously, emits the same artifact and
        lifecycle events, then exposes an exact current legal step through the
        existing authority readout.
        """
        if snapshot is None:
            return None, (), None
        snapshot_id = str(
            getattr(
                snapshot, "snapshot_id", ""))
        if not snapshot_id:
            return None, (), None
        artifact = None
        emitted = ()
        if snapshot_id not in (
                self
                ._emitted_city_defense_snapshot_ids):
            from .domain_models import (
                build_city_defense_assignment_artifact,
            )
            preparation_started = (
                time.perf_counter())
            artifact = (
                build_city_defense_assignment_artifact(
                    snapshot,
                    ruleset_ir,
                    tuple(candidates),
                    threat_radius,
                    node_budget,
                    ruleset_digest,
                    analysis_operation_types=(
                        "fortify_existing_defender",
                        "hold_sole_defender",
                    ),
                    live_operation_types=(
                        "fortify_existing_defender",
                    ),
                    maximum_authority_lead_turns=1))
            build_finished = (
                time.perf_counter())
            artifact = dict(
                artifact)
            artifact[
                "synchronous_authority_preparation"
            ] = True
            artifact["artifact_hash"] = (
                structural_hash({
                    key: value
                    for key, value
                    in artifact.items()
                    if key != "artifact_hash"
                }))
            self._city_defense_authority_games.add(
                str(writer.game_id))
            emitted = (
                self
                .emit_city_defense_operations(
                    writer,
                    int(snapshot.turn),
                    artifact,
                    caused_by=(
                        caused_by),
                    selected_only=True))
            emission_finished = (
                time.perf_counter())
            build_latency = writer.emit(
                "metric_sample",
                int(snapshot.turn), {
                    "labels": {
                        "authority_kind":
                            "city_defense",
                        "component":
                            "bounded-operation-authority",
                    },
                    "name":
                        "city_defense_authority_build_latency_ms",
                    "unit": "ms",
                    "value": (
                        build_finished
                        - preparation_started)
                    * 1000.0,
                },
                caused_by=(
                    [emitted[-1]["event_id"]]
                    if emitted
                    else list(caused_by)))
            event_latency = writer.emit(
                "metric_sample",
                int(snapshot.turn), {
                    "labels": {
                        "authority_kind":
                            "city_defense",
                        "component":
                            "bounded-operation-authority",
                    },
                    "name":
                        "city_defense_authority_event_latency_ms",
                    "unit": "ms",
                    "value": (
                        emission_finished
                        - build_finished)
                    * 1000.0,
                },
                caused_by=[
                    build_latency[
                        "event_id"]])
            latency = writer.emit(
                "metric_sample",
                int(snapshot.turn), {
                    "labels": {
                        "authority_kind":
                            "city_defense",
                        "component":
                            "bounded-operation-authority",
                    },
                    "name":
                        "city_defense_authority_preparation_latency_ms",
                    "unit": "ms",
                    "value": (
                        time.perf_counter()
                        - preparation_started)
                    * 1000.0,
                },
                caused_by=[
                    event_latency[
                        "event_id"]])
            emitted = emitted + (
                build_latency,
                event_latency,
                latency)
            self._emitted_city_defense_snapshot_ids.add(
                snapshot_id)
        readout = (
            self.operation_authority_readout(
                writer, snapshot,
                city_defense_enabled=True,
                combat_enabled=False))
        return artifact, emitted, readout

    def abandon_city_defense_authority(
            self, writer, turn,
            readout, snapshot_id,
            reason_code,
            caused_by=()):
        """Release an exact assignment that the current planner did not use."""
        if (
                not isinstance(
                    readout,
                    OperationAuthorityReadout)
                or readout.authority_kind
                != OperationAuthorityKind
                .CITY_DEFENSE
        ):
            return ()
        if (not isinstance(
                reason_code, str)
                or not reason_code):
            raise ValueError(
                "authority abandonment requires a reason")
        store = self._operation_store_for(
            writer)
        record = store.get(
            readout.operation_id)
        if (
                record is None
                or record.progress.state
                not in (
                    OperationState.RESERVED,
                    OperationState.ACTIVE)
        ):
            return ()
        record = store.transition(
            readout.operation_id,
            OperationState.ABANDONED,
            str(snapshot_id),
            int(turn),
            reason=reason_code)
        event = self._emit_operation_state(
            writer, int(turn),
            readout.operation_id,
            "operation_abandoned",
            "abandoned",
            reason_code,
            str(snapshot_id),
            tuple(caused_by),
            resolution_status=(
                "censored_operation_abort"))
        self._operation_action_keys.pop(
            readout.operation_id, None)
        return (event,)

    def emit_operation_authority_selection(
            self, writer, turn,
            readout, baseline_candidate_key,
            caused_by=()):
        """Record the exact point where a default-off slice changes readout."""
        if not isinstance(
                readout,
                OperationAuthorityReadout):
            raise TypeError(
                "operation authority selection requires a readout")
        payload = self._operation_payloads.get(
            readout.operation_id)
        if not isinstance(payload, dict):
            raise ValueError(
                "operation authority selection has no retained payload")
        payload["policy_authority"] = True
        payload["shadow_only"] = False
        provenance = tuple(
            payload.get(
                "provenance") or ())
        marker = (
            "bounded-{}-operation-authority/1.0"
            .format(
                readout
                .authority_kind.value))
        payload["provenance"] = list(
            dict.fromkeys(
                provenance
                + (marker,)))
        selected = dict(payload)
        selected.update({
            "reason_code":
                "bounded-operation-authority",
            "selected": True,
            "snapshot_id":
                readout.snapshot_id,
            "state": "step_selected",
        })
        event = writer.emit(
            "operation_step_selected",
            int(turn), selected,
            caused_by=list(
                caused_by))
        self._operation_event_ids[
            readout.operation_id] = (
                event["event_id"])
        metric = writer.emit(
            "metric_sample",
            int(turn), {
                "labels": {
                    "authority_kind":
                        readout
                        .authority_kind.value,
                    "changed_winner": str(
                        baseline_candidate_key
                        != readout.action_key)
                    .lower(),
                    "component":
                        "bounded-operation-authority",
                    "operation_type":
                        readout.operation_type,
                },
                "name":
                    "operation_authority_selection",
                "unit": "count",
                "value": 1.0,
            },
            caused_by=[
                event["event_id"]])
        return (event, metric)

    def _apply_combat_lifecycle_update(
            self, lifecycle, update):
        payload = self._operation_payloads[
            update.operation_id]
        assembly = lifecycle.assembly(
            update.operation_id)
        if assembly is None:
            raise ValueError(
                "combat lifecycle update has no assembly")
        step = assembly.spec.steps[
            min(
                update.step_index,
                len(
                    assembly.spec.steps)
                - 1)]
        participant = next(
            row for row in
            assembly.spec.participants
            if row.role
            == step.actor_role)
        payload["actor_id"] = (
            participant.actor_id)
        if update.next_action is not None:
            payload["next_action"] = (
                update.next_action)
        if (
            update.probability_interval
            is not None
        ):
            payload["probability_interval"] = (
                update
                .probability_interval
                .to_dict())
        if update.schedule is not None:
            payload["assignment_digest"] = (
                update.schedule
                .decision_digest)
            request = next((
                row for row in
                update.schedule.requests
                if row.operation_id
                == update.operation_id
            ), None)
            if request is not None:
                payload["bid"] = float(
                    request.bid)
                payload["claims"] = [
                    claim.to_dict()
                    for claim in
                    request.claims]
        return payload

    def _emit_operation_state(
            self, writer, turn,
            operation_id, event_type,
            state, reason_code,
            snapshot_id, caused_by,
            action_id=None,
            resolution_status=None):
        payload = dict(
            self._operation_payloads[
                operation_id])
        payload.update({
            "reason_code":
                reason_code,
            "selected": True,
            "snapshot_id":
                snapshot_id,
            "state": state,
        })
        if action_id is not None:
            payload["action_id"] = str(
                action_id)
        if resolution_status is not None:
            payload[
                "resolution_snapshot_id"
            ] = snapshot_id
            payload[
                "resolution_status"
            ] = resolution_status
        event = writer.emit(
            event_type, turn,
            payload,
            caused_by=list(
                caused_by))
        self._operation_event_ids[
            operation_id] = (
                event["event_id"])
        return event

    @staticmethod
    def _resource_schedule_artifact(pressure):
        if not isinstance(pressure, dict):
            return None
        artifact = pressure.get(
            "identity_resource_schedule")
        if not isinstance(artifact, dict):
            return None
        schedule = artifact.get("exact")
        if not isinstance(schedule, dict):
            return None
        return artifact, schedule

    @staticmethod
    def _resource_snapshot_id(schedule):
        snapshot_ids = sorted(set(
            str(row.get("snapshot_id"))
            for row in schedule.get(
                "capacities", ())
            if isinstance(row, dict)
            and row.get("snapshot_id")))
        if len(snapshot_ids) == 1:
            return snapshot_ids[0]
        if snapshot_ids:
            return structural_hash(
                snapshot_ids)
        return "capacityless-shadow"

    @staticmethod
    def _resource_claim_payload(
            schedule, claim, disposition,
            reason=None, entry=None,
            snapshot_id=None):
        entry = (
            entry
            if isinstance(entry, dict)
            else {})
        return {
            "claim_id":
                structural_hash(claim),
            "conflict_resource_ids":
                list(entry.get(
                    "conflict_resource_ids",
                    ())),
            "conflicting_operation_ids":
                list(entry.get(
                    "conflicting_operation_ids",
                    ())),
            "disposition": disposition,
            "event_schema_version":
                CONTROL_EVENT_SCHEMA_VERSION,
            "exclusive": bool(
                claim["exclusive"]),
            "hardness": claim["hardness"],
            "operation_id":
                claim[
                    "source_operation_id"],
            "quantity": int(
                claim["quantity"]),
            "reason": reason,
            "resource": claim["resource"],
            "schedule_digest":
                schedule["decision_digest"],
            "scheduler_identity":
                schedule[
                    "scheduler_identity"],
            "shadow_only": True,
            "snapshot_id": (
                snapshot_id
                or ControlEventEmitter
                ._resource_snapshot_id(
                    schedule)),
            "source_step_id":
                claim["source_step_id"],
            "window": claim["window"],
        }

    def emit_resource_schedule_artifacts(
            self, writer, turn, schedule,
            caused_by=()):
        """Emit full identity/window resource evidence for one shadow schedule."""
        if not isinstance(schedule, dict):
            return ()
        parents = tuple(caused_by)
        emitted = []
        for capacity in schedule.get(
                "capacities", ()):
            if not isinstance(capacity, dict):
                continue
            resource = capacity.get(
                "resource")
            window = capacity.get(
                "window")
            if (not isinstance(resource, dict)
                    or not isinstance(
                        window, dict)):
                continue
            resource_id = structural_hash(
                resource)
            capacity_id = structural_hash(
                capacity)
            previous = (
                self
                ._last_resource_capacity
                .get(resource_id))
            if (previous is not None
                    and previous[
                        "capacity_id"]
                    == capacity_id):
                continue
            event = writer.emit(
                "resource_capacity_changed",
                turn, {
                    "authority":
                        capacity["authority"],
                    "capacity_id":
                        capacity_id,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "previous_capacity_id":
                        (
                            previous[
                                "capacity_id"]
                            if previous
                            is not None
                            else None),
                    "previous_quantity":
                        (
                            previous[
                                "quantity"]
                            if previous
                            is not None
                            else None),
                    "quantity": int(
                        capacity[
                            "quantity"]),
                    "reason": (
                        "snapshot-changed"
                        if previous
                        is not None
                        else
                        "initial-observation"),
                    "resource": resource,
                    "shadow_only": True,
                    "snapshot_id":
                        capacity[
                            "snapshot_id"],
                    "window": window,
                }, caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
            self._last_resource_capacity[
                resource_id] = {
                    "capacity_id":
                        capacity_id,
                    "quantity": int(
                        capacity[
                            "quantity"]),
                }
        entries = {
            row["operation_id"]: row
            for row in schedule.get(
                "entries", ())
            if isinstance(row, dict)
            and isinstance(
                row.get(
                    "operation_id"),
                str)
        }
        snapshot_id = (
            self._resource_snapshot_id(
                schedule))
        for request in schedule.get(
                "requests", ()):
            if not isinstance(request, dict):
                continue
            operation_id = request.get(
                "operation_id")
            entry = entries.get(
                operation_id, {})
            selected = bool(
                entry.get(
                    "selected", False))
            reason = (
                None
                if selected
                else str(
                    entry.get(
                        "reason")
                    or "scheduler-rejected"))
            for claim in request.get(
                    "claims", ()):
                if not isinstance(claim, dict):
                    continue
                requested = writer.emit(
                    "resource_claim_requested",
                    turn,
                    self._resource_claim_payload(
                        schedule, claim,
                        "requested",
                        entry=entry,
                        snapshot_id=(
                            snapshot_id)),
                    caused_by=list(parents))
                emitted.append(
                    requested)
                parents = (
                    requested[
                        "event_id"],)
                event_type = (
                    "resource_claim_reserved"
                    if selected
                    else
                    "resource_claim_rejected")
                disposition = (
                    "reserved"
                    if selected
                    else "rejected")
                result = writer.emit(
                    event_type, turn,
                    self._resource_claim_payload(
                        schedule, claim,
                        disposition,
                        reason=reason,
                        entry=entry,
                        snapshot_id=(
                            snapshot_id)),
                    caused_by=list(parents))
                emitted.append(result)
                parents = (
                    result["event_id"],)
        return tuple(emitted)

    def emit_city_defense_operations(
            self, writer, turn, artifact,
            caused_by=(),
            selected_only=False):
        """Emit the shadow proposal graph and exact assignment readout."""
        if not isinstance(artifact, dict):
            return ()
        analysis = artifact.get(
            "analysis")
        assignment = artifact.get(
            "assignment")
        if (not isinstance(analysis, dict)
                or not isinstance(
                    assignment, dict)):
            return ()
        entries = {
            row.get("operation_id"): row
            for row in assignment.get(
                "entries", ())
            if isinstance(row, dict)
            and isinstance(
                row.get("operation_id"),
                str)
        }
        assignment_digest = (
            assignment.get(
                "decision_digest"))
        selected_action_key = (
            artifact.get(
                "selected_action_key"))
        synchronous_authority = bool(
            artifact.get(
                "synchronous_authority_preparation",
                False))
        authority_game = (
            str(writer.game_id)
            in self
            ._city_defense_authority_games)
        snapshot_id = str(
            analysis.get(
                "snapshot_id")
            or "unknown-city-defense-snapshot")
        parents = tuple(caused_by)
        emitted = []
        current_lifecycle_ids = set()
        operations = sorted(
            (
                row for row
                in analysis.get(
                    "operations", ())
                if isinstance(row, dict)
                and isinstance(
                    row.get(
                        "operation_id"),
                    str)
            ),
            key=lambda row:
            row["operation_id"])
        if selected_only:
            operations = [
                row for row in operations
                if (
                    row.get(
                        "operation_type")
                    == "hold_sole_defender"
                    or (
                        entries.get(
                            row[
                                "operation_id"],
                            {}).get(
                                "selected")
                        is True
                        and selected_action_key
                        is not None
                        and isinstance(
                            row.get(
                                "next_action"),
                            dict)
                        and canonical_json_bytes(
                            row[
                                "next_action"])
                        .decode("utf-8")
                        == selected_action_key))
            ]
        for operation in operations:
            operation_id = (
                operation[
                    "operation_id"])
            entry = entries.get(
                operation_id, {})
            assigned = bool(
                entry.get(
                    "selected", False))
            operation_action = (
                operation.get(
                    "next_action"))
            operation_action_key = (
                canonical_json_bytes(
                    operation_action)
                .decode("utf-8")
                if isinstance(
                    operation_action, dict)
                else None)
            selected = bool(
                assigned
                and selected_action_key
                is not None
                and operation_action_key
                == selected_action_key)
            reason = entry.get(
                "reason")
            if (
                    selected
                    and authority_game
                    and not
                    synchronous_authority
            ):
                selected = False
                reason = (
                    "asynchronous-shadow-superseded-by-current-authority")
            if (assigned
                    and not selected):
                reason = (
                    reason
                    or
                    "assignment-selected-awaiting-readout")
            if reason is None:
                reason = operation.get(
                    "support_reason")
            payload = {
                "actor_id": (
                    None
                    if operation.get(
                        "actor_id")
                    is None
                    else str(
                        operation[
                            "actor_id"])),
                "assignment_digest":
                    assignment_digest,
                "bid": float(
                    operation.get(
                        "bid", 0.0)),
                "claims": list(
                    operation.get(
                        "claims", ())),
                "deadline_turn":
                    operation.get(
                        "deadline_turn"),
                "event_schema_version":
                    CONTROL_EVENT_SCHEMA_VERSION,
                "expected_prevented_loss":
                    float(
                        operation.get(
                            "expected_prevented_loss",
                            0.0)),
                "next_action":
                    operation.get(
                        "next_action"),
                "operation_digest":
                    structural_hash(
                        operation),
                "operation_id":
                    operation_id,
                "operation_type": str(
                    operation.get(
                        "operation_type")
                    or "unknown"),
                "opportunity_cost":
                    float(
                        operation.get(
                            "opportunity_cost",
                            0.0)),
                "policy_authority":
                    False,
                "provenance": list(
                    operation.get(
                        "provenance")
                    or (
                        "city-defense-shadow",)),
                "reason_code": (
                    None
                    if selected
                    else str(
                        reason
                        or "not-selected")),
                "requirement_id":
                    operation.get(
                        "requirement_id"),
                "selected": selected,
                "shadow_only": True,
                "snapshot_id":
                    snapshot_id,
                "state": "proposed",
                "target_id": (
                    "city:{}".format(
                        operation[
                            "city_id"])
                    if operation.get(
                        "city_id")
                    is not None
                    else None),
            }
            proposed = writer.emit(
                "operation_proposed",
                turn, payload,
                caused_by=list(parents))
            emitted.append(
                proposed)
            parents = (
                proposed[
                    "event_id"],)
            if not selected:
                continue
            store = self._operation_store_for(
                writer)
            lifecycle_operation_id = (
                operation_id)
            active_record = (
                self._active_city_defense_record(
                    store, payload,
                    int(
                        artifact.get(
                            "source_turn",
                            turn))))
            if active_record is not None:
                lifecycle_operation_id = (
                    active_record.spec
                    .operation_id)
                payload = dict(payload)
                payload["operation_id"] = (
                    lifecycle_operation_id)
                payload["deadline_turn"] = (
                    active_record.spec
                    .expiry_turn)
                payload["operation_digest"] = (
                    active_record.spec
                    .spec_digest)
                payload["claims"] = [
                    {
                        **claim,
                        "source_operation_id":
                            lifecycle_operation_id,
                    }
                    if isinstance(claim, dict)
                    else claim
                    for claim in payload.get(
                        "claims", ())
                ]
                active_step = (
                    active_record.spec.steps[
                        active_record.progress
                        .current_step_index])
                if (
                        active_record.progress
                        .attempt_count
                        >= active_step
                        .maximum_attempts
                ):
                    reason = (
                        "operation-step-attempt-limit-exceeded")
                    store.transition(
                        lifecycle_operation_id,
                        OperationState.ABANDONED,
                        snapshot_id,
                        int(
                            artifact.get(
                                "source_turn",
                                turn)),
                        reason=reason)
                    event = (
                        self._emit_operation_state(
                            writer,
                            int(
                                artifact.get(
                                    "source_turn",
                                    turn)),
                            lifecycle_operation_id,
                            "operation_abandoned",
                            "abandoned",
                            reason,
                            snapshot_id,
                            tuple(parents),
                            resolution_status=(
                                "censored_operation_abort")))
                    emitted.append(event)
                    parents = (
                        event["event_id"],)
                    self._operation_action_keys.pop(
                        lifecycle_operation_id,
                        None)
                    continue
            elif (
                    store.get(
                        lifecycle_operation_id)
                    is not None
                    and store.get(
                        lifecycle_operation_id)
                    .progress.state
                    in (
                        OperationState.COMPLETED,
                        OperationState.FAILED,
                        OperationState.ABANDONED,
                        OperationState.EXPIRED)
            ):
                # Domain graph edges intentionally have stable content IDs.
                # A later exact snapshot may validly select the same edge
                # after an earlier lifecycle was terminally abandoned or
                # completed. Give that new reservation its own creation
                # epoch while retaining the graph edge in the proposal event.
                lifecycle_operation_id = (
                    structural_hash({
                        "domain_operation_id":
                            operation_id,
                        "schema_version":
                            "city-defense-lifecycle/1.0",
                        "snapshot_id":
                            snapshot_id,
                    }))
                payload = dict(payload)
                payload["operation_id"] = (
                    lifecycle_operation_id)
                payload["claims"] = [
                    {
                        **claim,
                        "source_operation_id":
                            lifecycle_operation_id,
                    }
                    if isinstance(claim, dict)
                    else claim
                    for claim in payload.get(
                        "claims", ())
                ]
            try:
                record = store.get(
                    lifecycle_operation_id)
                if record is None:
                    lifecycle_operation = dict(
                        operation)
                    lifecycle_operation[
                        "operation_id"] = (
                            lifecycle_operation_id)
                    spec = (
                        assemble_city_defense_operation(
                            lifecycle_operation,
                            int(
                                artifact.get(
                                    "source_turn",
                                    turn)),
                            str(
                                artifact.get(
                                    "ruleset_digest")
                                or "ruleset-digest-unavailable")))
                    record = store.propose(
                        spec, snapshot_id,
                        int(
                            artifact.get(
                                "source_turn",
                                turn)))
                    record = store.transition(
                        lifecycle_operation_id,
                        OperationState
                        .RESERVABLE,
                        snapshot_id,
                        int(
                            artifact.get(
                                "source_turn",
                                turn)))
                    record = store.transition(
                        lifecycle_operation_id,
                        OperationState
                        .RESERVED,
                        snapshot_id,
                        int(
                            artifact.get(
                                "source_turn",
                                turn)))
                elif (
                    record.progress.state
                    in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE)
                    and record.progress
                    .last_snapshot_id
                    != snapshot_id
                ):
                    record = (
                        store.record_observation(
                            lifecycle_operation_id,
                            snapshot_id,
                            int(
                                artifact.get(
                                    "source_turn",
                                    turn))))
                if record.progress.state not in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE):
                    raise (
                        OperationTransitionError(
                            "operation is not eligible for a current step"))
            except (
                    OperationStoreError,
                    OperationTransitionError,
                    TypeError,
                    ValueError):
                blocked_payload = dict(
                    payload)
                blocked_payload[
                    "selected"] = False
                blocked_payload[
                    "state"] = "blocked"
                blocked_payload[
                    "reason_code"] = (
                        "operation-lifecycle-registration-failed")
                blocked_event = writer.emit(
                    "operation_blocked",
                    turn,
                    blocked_payload,
                    caused_by=list(
                        parents))
                emitted.append(
                    blocked_event)
                parents = (
                    blocked_event[
                        "event_id"],)
                continue
            self._operation_payloads[
                lifecycle_operation_id] = dict(
                    payload)
            self._operation_action_keys[
                lifecycle_operation_id] = (
                    operation_action_key)
            current_lifecycle_ids.add(
                lifecycle_operation_id)
            if (record.progress.state
                    == OperationState.RESERVED):
                reserved_payload = dict(
                    payload)
                reserved_payload[
                    "state"] = "reserved"
                reserved_payload[
                    "reason_code"] = None
                reserved_event = writer.emit(
                    "operation_reserved",
                    turn,
                    reserved_payload,
                    caused_by=list(parents))
                emitted.append(
                    reserved_event)
                parents = (
                    reserved_event[
                        "event_id"],)
            selected_payload = dict(
                payload)
            selected_payload[
                "state"] = (
                    "step_selected")
            selected_payload[
                "reason_code"] = None
            selected_event = writer.emit(
                "operation_step_selected",
                turn,
                selected_payload,
                caused_by=list(parents))
            emitted.append(
                selected_event)
            self._operation_event_ids[
                lifecycle_operation_id] = (
                    selected_event[
                        "event_id"])
            parents = (
                selected_event[
                    "event_id"],)
        if synchronous_authority:
            store = self._operation_store_for(
                writer)
            source_turn = int(
                artifact.get(
                    "source_turn",
                    turn))
            for record in (
                    store.nonterminal_records()):
                operation_id = (
                    record.spec.operation_id)
                if (
                        record.progress.state
                        != OperationState.ACTIVE
                        or operation_id
                        in current_lifecycle_ids
                        or operation_id
                        not in self
                        ._operation_payloads
                ):
                    continue
                reason = (
                    "current-assignment-no-longer-supports-active-step")
                store.transition(
                    operation_id,
                    OperationState.ABANDONED,
                    snapshot_id,
                    source_turn,
                    reason=reason)
                event = (
                    self._emit_operation_state(
                        writer, source_turn,
                        operation_id,
                        "operation_abandoned",
                        "abandoned",
                        reason,
                        snapshot_id,
                        tuple(parents),
                        resolution_status=(
                            "censored_operation_abort")))
                emitted.append(event)
                parents = (
                    event["event_id"],)
                self._operation_action_keys.pop(
                    operation_id, None)
        return tuple(emitted)

    def emit_city_defense_action_outcome(
            self, writer, turn,
            snapshot, action,
            outcome, caused_by=()):
        """Attribute an actually submitted current action to one shadow step.

        A selected assignment is not a commit.  It becomes active only when
        the runtime's current action is byte-identical and the existing
        execution gate reports acceptance.
        """
        if (not isinstance(action, dict)
                or snapshot is None
                or outcome is None):
            return ()
        action_key = (
            canonical_json_bytes(
                action)
            .decode("utf-8"))
        store = self._operation_store_for(
            writer)
        matches = []
        for operation_id, expected in (
                self._operation_action_keys
                .items()):
            record = store.get(
                operation_id)
            if (expected == action_key
                    and record is not None
                    and record.progress.state
                    in (
                        OperationState.RESERVED,
                        OperationState.ACTIVE)
                    and record.progress
                    .last_snapshot_id
                    == snapshot.snapshot_id):
                matches.append(
                    record)
        if not matches:
            return ()
        # One engine action may activate only one operation step. Prefer the
        # newest selected observation, then stable identity.
        record = sorted(
            matches,
            key=lambda row: (
                -row.progress
                .last_updated_turn,
                row.spec.operation_id))[0]
        operation_id = (
            record.spec.operation_id)
        parent_ids = tuple(
            dict.fromkeys(
                tuple(caused_by)
                + tuple(
                    value for value in (
                        self
                        ._operation_event_ids
                        .get(operation_id),
                    )
                    if value)))
        action_id = getattr(
            outcome, "action_id", None)
        if int(turn) > (
                record.spec.expiry_turn):
            reason = (
                "operation-deadline-passed-before-commit")
            store.transition(
                operation_id,
                OperationState.EXPIRED,
                snapshot.snapshot_id,
                int(turn),
                reason=reason)
            event = self._emit_operation_state(
                writer, turn,
                operation_id,
                "operation_expired",
                "expired", reason,
                snapshot.snapshot_id,
                parent_ids,
                action_id=action_id,
                resolution_status=(
                    "censored_operation_abort"))
            self._operation_action_keys.pop(
                operation_id, None)
            return (event,)
        accepted = bool(
            getattr(
                outcome,
                "submitted", False)
            and getattr(
                outcome,
                "status", None)
            == "accepted")
        if not accepted:
            reason = str(
                getattr(
                    outcome,
                    "reason", None)
                or "current-action-not-accepted")
            store.transition(
                operation_id,
                OperationState.FAILED,
                snapshot.snapshot_id,
                int(turn),
                reason=reason)
            event = self._emit_operation_state(
                writer, turn,
                operation_id,
                "operation_failed",
                "failed", reason,
                snapshot.snapshot_id,
                parent_ids,
                action_id=action_id,
                resolution_status=(
                    "resolved_failure"))
            self._operation_action_keys.pop(
                operation_id, None)
            return (event,)
        newly_active = (
            record.progress.state
            == OperationState.RESERVED)
        if newly_active:
            store.transition(
                operation_id,
                OperationState.ACTIVE,
                snapshot.snapshot_id,
                int(turn))
        try:
            store.record_attempt(
                operation_id,
                snapshot.snapshot_id,
                int(turn))
        except OperationTransitionError:
            reason = (
                "operation-step-attempt-limit-exceeded")
            store.transition(
                operation_id,
                OperationState.ABANDONED,
                snapshot.snapshot_id,
                int(turn),
                reason=reason)
            event = self._emit_operation_state(
                writer, turn,
                operation_id,
                "operation_abandoned",
                "abandoned", reason,
                snapshot.snapshot_id,
                parent_ids,
                action_id=action_id,
                resolution_status=(
                    "censored_operation_abort"))
            self._operation_action_keys.pop(
                operation_id, None)
            return (event,)
        activated = None
        if newly_active:
            activated = (
                self._emit_operation_state(
                    writer, turn,
                    operation_id,
                    "operation_activated",
                    "activated", None,
                    snapshot.snapshot_id,
                    parent_ids,
                    action_id=action_id))
            parent_ids = (
                activated[
                    "event_id"],)
        revalidated = (
            self._emit_operation_state(
                writer, turn,
                operation_id,
                "operation_step_revalidated",
                "step_revalidated",
                None,
                snapshot.snapshot_id,
                parent_ids,
                action_id=action_id))
        committed = (
            self._emit_operation_state(
                writer, turn,
                operation_id,
                "operation_step_committed",
                "step_committed",
                None,
                snapshot.snapshot_id,
                (revalidated[
                    "event_id"],),
                action_id=action_id))
        return tuple(
            event for event in (
                activated,
                revalidated,
                committed)
            if event is not None)

    def resolve_city_defense_operations(
            self, writer, snapshot,
            caused_by=()):
        """Resolve committed city-defence steps from authoritative state."""
        if snapshot is None:
            return ()
        store = self._operation_store_for(
            writer)
        emitted = []
        for record in (
                store.nonterminal_records()):
            operation_id = (
                record.spec.operation_id)
            if operation_id not in (
                    self._operation_payloads):
                continue
            progress = record.progress
            if (progress.last_snapshot_id
                    == snapshot.snapshot_id):
                continue
            parent_ids = tuple(
                dict.fromkeys(
                    tuple(caused_by)
                    + tuple(
                        value for value
                        in (
                            self
                            ._operation_event_ids
                            .get(
                                operation_id),
                        )
                        if value)))
            terminal_event = None
            terminal_state = None
            reason = None
            resolution = None
            payload = (
                self
                ._operation_payloads[
                    operation_id])
            target_id = str(
                payload.get(
                    "target_id")
                or "")
            city_id = (
                target_id[5:]
                if target_id.startswith(
                    "city:")
                else target_id)
            city = (
                snapshot.city(
                    int(city_id))
                if city_id.isdigit()
                else None)
            if (progress.state
                    == OperationState.ACTIVE):
                actor_id = payload.get(
                    "actor_id")
                unit = (
                    snapshot.unit(
                        int(actor_id))
                    if (isinstance(
                        actor_id, str)
                        and actor_id
                        .isdigit())
                    else None)
                operation_type = (
                    payload.get(
                        "operation_type"))
                if city is None:
                    terminal_state = (
                        OperationState.FAILED)
                    terminal_event = (
                        "operation_failed")
                    reason = (
                        "target-city-unavailable")
                    resolution = (
                        "resolved_failure")
                elif (actor_id is not None
                        and unit is None):
                    terminal_state = (
                        OperationState.FAILED)
                    terminal_event = (
                        "operation_failed")
                    reason = (
                        "required-participant-unavailable")
                    resolution = (
                        "resolved_failure")
                elif (operation_type
                        == "move_defender_to_city"
                        and unit is not None
                        and None not in (
                            unit.x, unit.y,
                            city.x, city.y)
                        and (
                            unit.x, unit.y)
                        == (
                            city.x, city.y)):
                    terminal_state = (
                        OperationState.COMPLETED)
                    terminal_event = (
                        "operation_completed")
                    reason = (
                        "completion-predicate-satisfied")
                    resolution = (
                        "resolved_success")
                elif (operation_type
                        == "fortify_existing_defender"
                        and unit is not None
                        and None not in (
                            unit.x, unit.y,
                            city.x, city.y)
                        and (
                            unit.x, unit.y)
                        == (
                            city.x, city.y)
                        and str(
                            unit.activity
                            or "").lower()
                        in (
                            "fortify",
                            "fortifying",
                            "fortified")):
                    terminal_state = (
                        OperationState.COMPLETED)
                    terminal_event = (
                        "operation_completed")
                    reason = (
                        "completion-predicate-satisfied")
                    resolution = (
                        "resolved_success")
            if (terminal_event is None
                    and int(snapshot.turn)
                    > record.spec.expiry_turn):
                terminal_state = (
                    OperationState.EXPIRED)
                terminal_event = (
                    "operation_expired")
                reason = (
                    "operation-deadline-passed"
                    if progress.state
                    != OperationState.ACTIVE
                    else
                    "committed-step-unresolved-at-deadline")
                resolution = (
                    "unresolved_unknown"
                    if progress.state
                    == OperationState.ACTIVE
                    else
                    "censored_operation_abort")
            if terminal_event is None:
                continue
            store.transition(
                operation_id,
                terminal_state,
                snapshot.snapshot_id,
                int(snapshot.turn),
                reason=reason)
            event = self._emit_operation_state(
                writer, snapshot.turn,
                operation_id,
                terminal_event,
                terminal_state.value,
                reason,
                snapshot.snapshot_id,
                parent_ids,
                resolution_status=(
                    resolution))
            emitted.append(event)
            self._operation_action_keys.pop(
                operation_id, None)
        return tuple(emitted)

    def emit_resource_schedule_results(
            self, writer, turn, artifacts,
            caused_by=()):
        """Emit completed resource batches once, including final drains."""
        parents = tuple(caused_by)
        emitted = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            batch_id = artifact.get(
                "batch_id")
            schedule = artifact.get(
                "exact")
            if (not isinstance(batch_id, str)
                    or not batch_id
                    or batch_id in
                    self._emitted_resource_batch_ids
                    or not isinstance(
                        schedule, dict)):
                continue
            entries = tuple(
                row
                for row in schedule.get(
                    "entries", ())
                if isinstance(row, dict))
            event = writer.emit(
                "resource_schedule_decided",
                turn, {
                    "artifact_hash":
                        artifact[
                            "artifact_hash"],
                    "batch_id": batch_id,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "exact_status":
                        schedule["status"],
                    "fallback_reason":
                        schedule.get(
                            "fallback_reason"),
                    "packet_committed_operation_ids":
                        list(artifact.get(
                            "packet_committed_operation_ids",
                            ())),
                    "packet_exact_selection_equal":
                        bool(artifact.get(
                            "packet_exact_selection_equal",
                            False)),
                    "policy_authority": False,
                    "rejected_operation_count":
                        sum(
                            not row.get(
                                "selected",
                                False)
                            for row in entries),
                    "request_count": int(
                        artifact.get(
                            "request_count",
                            len(schedule.get(
                                "requests", ())))),
                    "schedule_digest":
                        schedule[
                            "decision_digest"],
                    "scheduler_identity":
                        schedule[
                            "scheduler_identity"],
                    "selected_operation_ids":
                        list(schedule.get(
                            "selected_operation_ids",
                            ())),
                    "shadow_only": True,
                }, caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
            details = (
                self.emit_resource_schedule_artifacts(
                    writer, turn, schedule,
                    caused_by=parents))
            emitted.extend(details)
            if details:
                parents = (
                    details[-1][
                        "event_id"],)
            operation_events = (
                self
                .emit_city_defense_operations(
                    writer, turn,
                    artifact.get(
                        "city_defense"),
                    caused_by=parents))
            emitted.extend(
                operation_events)
            if operation_events:
                parents = (
                    operation_events[-1][
                        "event_id"],)
            self._emitted_resource_batch_ids.add(
                batch_id)
        return tuple(emitted)

    @staticmethod
    def _grounded_enabling_assembly(
            snapshot, ruleset_ir,
            ruleset_digest, action,
            completion_deadline_turn,
            candidate=None):
        """Ground one chosen production/research action without policy input."""
        from .domain_models import (
            DomainEstimateRequest,
            EstimateValidity,
            GroundedProductionTransitionModel,
            GroundedResearchTransitionModel,
        )
        from .impact import ImpactCandidate
        from .production_operations import (
            ProductionEnablingIntent,
            ProductionEnablingOperationAssembler,
        )
        from .research_operations import (
            ResearchEnablingIntent,
            ResearchEnablingOperationAssembler,
        )

        action_type = str(
            action.get("action_type", ""))
        if action_type not in (
                "city_production",
                "tech_research"):
            return None
        if candidate is None:
            candidate = ImpactCandidate(
                action=dict(action),
                category=(
                    "research_strategy"
                    if action_type
                    == "tech_research"
                    else "production_enabling"),
                utility=1.0,
                rationale=(
                    "observed existing-policy selection"),
                projection={})
        projection = dict(
            getattr(
                candidate,
                "projection", None)
            or {})
        target = action.get("target")
        if action_type == "tech_research":
            immediate_tech = (
                target.get("tech_name")
                if isinstance(target, dict)
                else None)
            if not isinstance(
                    immediate_tech, str
                    ) or not immediate_tech:
                return None
            projection.setdefault(
                "strategic_target_tech",
                immediate_tech)
            candidate = ImpactCandidate(
                action=dict(action),
                category=str(getattr(
                    candidate, "category",
                    "research_strategy")),
                utility=float(getattr(
                    candidate, "utility", 1.0)),
                rationale=str(getattr(
                    candidate, "rationale",
                    "observed existing-policy selection")),
                projection=projection)
            goal_id = "pf-impact:science"
        else:
            goal_id = "pf-impact:{}".format(
                str(getattr(
                    candidate, "category",
                    "production_enabling")))
        action_key = canonical_json_bytes(
            action).decode("utf-8")
        request_id = structural_hash({
            "action": action_key,
            "component":
                "gdo7-live-enabling-shadow/1.0",
            "goal_id": goal_id,
            "legal_actions_digest":
                snapshot.legal_actions_digest,
            "ruleset_digest":
                str(ruleset_digest),
            "snapshot_id": snapshot.snapshot_id,
        })
        request = DomainEstimateRequest(
            request_id=request_id,
            snapshot=snapshot,
            ruleset_ir=ruleset_ir,
            legal_action=dict(action),
            candidate=candidate,
            goal_losses=((goal_id, 1.0),),
            operation_context=None,
            validity=EstimateValidity(
                snapshot_id=snapshot.snapshot_id,
                legal_actions_digest=(
                    snapshot.legal_actions_digest),
                ruleset_digest=str(
                    ruleset_digest),
                estimated_at_turn=int(
                    snapshot.turn),
                valid_through_turn=int(
                    snapshot.turn)),
            horizon_turn=int(
                completion_deadline_turn))
        if action_type == "city_production":
            estimate = (
                GroundedProductionTransitionModel()
                .estimate(request))
            if not isinstance(target, dict):
                return estimate, None, request, goal_id
            target_name = target.get(
                "production_type")
            fields = (
                action.get("city_id"),
                action.get("production_kind"),
                action.get("production_value"))
            if (
                    not isinstance(target_name, str)
                    or not target_name
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                        for value in fields)
            ):
                return estimate, None, request, goal_id
            intent = ProductionEnablingIntent(
                operation_type=(
                    "BUILD_ENABLING_PRODUCT"),
                city_id=int(fields[0]),
                production_kind=int(fields[1]),
                production_value=int(fields[2]),
                target_name=target_name,
                downstream_operation_id=(
                    "policy-action:{}".format(
                        structural_hash({
                            "category":
                                candidate.category,
                            "goal": goal_id,
                        })[:24])),
                completion_deadline_turn=int(
                    completion_deadline_turn),
                scheduling_bid=1.0,
                emergency=False)
            assembly = (
                ProductionEnablingOperationAssembler
                .assemble(
                    snapshot, intent,
                    estimate, (goal_id,),
                    str(ruleset_digest)))
        else:
            estimate = (
                GroundedResearchTransitionModel()
                .estimate(request))
            strategic_target = projection[
                "strategic_target_tech"]
            intent = ResearchEnablingIntent(
                operation_type=(
                    "RESEARCH_ENABLER"),
                immediate_tech=immediate_tech,
                strategic_target_tech=(
                    strategic_target),
                downstream_operation_id=(
                    "policy-action:{}".format(
                        structural_hash({
                            "goal": goal_id,
                            "strategic_target":
                                strategic_target,
                        })[:24])),
                completion_deadline_turn=int(
                    completion_deadline_turn),
                scheduling_bid=1.0,
                emergency=False)
            assembly = (
                ResearchEnablingOperationAssembler
                .assemble(
                    snapshot, intent,
                    estimate, (goal_id,),
                    str(ruleset_digest)))
        return estimate, assembly, request, goal_id

    def _emit_grounded_enabling_estimate(
            self, writer, snapshot,
            estimate, request, candidate,
            caused_by=()):
        from ..pressure.teleology import (
            typed_expected_reliefs,
        )

        if request.request_id in (
                self._emitted_domain_request_ids):
            return ()
        estimate_dict = estimate.to_dict()
        action = request.legal_action
        authority = estimate.authority.value
        target = action.get("target")
        target_id = action.get(
            "city_id", action.get("target_id"))
        if isinstance(target, dict):
            target_id = target.get(
                "tech_name",
                target.get(
                    "production_type",
                    target_id))
        payload = {
            "action_category": str(getattr(
                candidate, "category",
                "research_strategy"
                if request.action_type
                == "tech_research"
                else "production_enabling")),
            "action_type": request.action_type,
            "actor_id": (
                None
                if action.get(
                    "actor_id",
                    action.get("city_id"))
                is None
                else str(action.get(
                    "actor_id",
                    action.get("city_id")))),
            "adverse_risk": float(
                estimate.transition
                .expected_adverse_loss),
            "authority": authority,
            "candidate_action_id":
                structural_hash(action),
            "confidence": float(
                estimate.confidence),
            "context_key":
                estimate_dict["context_key"],
            "estimator_id":
                estimate.estimator_id,
            "estimator_version":
                estimate.estimator_version,
            "expected_relief": dict(
                typed_expected_reliefs(
                    estimate.transition,
                    request.goal_losses)),
            "latency_ms": 0.0,
            "operation_id":
                estimate.transition.operation_id,
            "provenance": list(
                estimate.provenance),
            "request_id": request.request_id,
            "target_id": (
                None if target_id is None
                else str(target_id)),
            "transition":
                estimate_dict["transition"],
            "validity":
                estimate_dict["validity"],
        }
        if "model_artifact" in estimate_dict:
            payload["model_artifact"] = (
                estimate_dict[
                    "model_artifact"])
        event_type = "domain_estimate_emitted"
        if authority == "abstain":
            event_type = "domain_estimate_abstained"
            payload["abstention_reason"] = (
                estimate.abstention_reason)
            artifact = estimate_dict.get(
                "model_artifact")
            payload["missing_fields"] = list(
                artifact.get(
                    "missing_fields", ())
                if isinstance(artifact, dict)
                else ())
        event = writer.emit(
            event_type,
            int(snapshot.turn),
            payload,
            caused_by=list(caused_by))
        self._emitted_domain_request_ids.add(
            request.request_id)
        return (event,)

    @staticmethod
    def _grounded_enabling_payload(
            assembly, request, goal_id,
            snapshot, selected, reason):
        spec = assembly.spec
        participant = spec.participants[0]
        payload = {
            "actor_id": participant.actor_id,
            "assignment_digest": None,
            "bid": float(
                assembly.resource_request.bid),
            "claims": [
                claim.to_dict()
                for claim in
                assembly.resource_request.claims],
            "deadline_turn": spec.expiry_turn,
            "event_schema_version":
                CONTROL_EVENT_SCHEMA_VERSION,
            "expected_prevented_loss": 0.0,
            "goal_ids": list(spec.goal_ids),
            "next_action": (
                assembly.queue_action()
                if hasattr(assembly, "queue_action")
                else assembly.selection_action()),
            "operation_digest":
                structural_hash(spec.to_dict()),
            "operation_id": spec.operation_id,
            "operation_type": spec.operation_type,
            "opportunity_cost": 0.0,
            "participants": [
                row.to_dict()
                for row in spec.participants],
            "policy_authority": False,
            "provenance": list(spec.provenance),
            "reason_code": reason,
            "requirement_id":
                assembly.requirement_set
                .requirement_set_id,
            "requirement_set":
                assembly.requirement_set.to_dict(),
            "selected": bool(selected),
            "shadow_only": True,
            "snapshot_id": snapshot.snapshot_id,
            "state": "proposed",
            "target_id": spec.target_ref,
            "downstream_operation_id": (
                assembly.intent
                .downstream_operation_id),
            "grounded_goal_id": goal_id,
            "mechanism": (
                "gdo7a-production-enabling"
                if hasattr(assembly, "queue_action")
                else "gdo7b-research-enabling"),
        }
        if request is not None:
            payload["domain_estimate_request_id"] = request.request_id
        return payload

    def prepare_replacement_capacity_production_operation(
            self, writer, snapshot, candidate, caused_by=()):
        """Register one exact legacy-selected capacity route in isolation."""
        assembly = getattr(candidate, "production_assembly", None)
        if (
                snapshot is None
                or assembly is None
                or assembly.spec.operation_type != (
                    "fdas-shadow:city-replacement-capacity-deficit:"
                    "city_production")
                or getattr(candidate, "authority_eligible", True)
                or getattr(candidate, "action_key", None)
                    not in snapshot.legal_action_json
                or candidate.action != assembly.queue_action()
                or "delayed-production-completion-unobserved"
                    not in getattr(candidate, "blockers", ())
        ):
            return ()
        lifecycle = self._replacement_capacity_production_lifecycle_for(
            writer)
        updates = lifecycle.register(assembly, snapshot)
        if not updates:
            return ()
        selected = updates[0].disposition != "blocked"
        payload = self._grounded_enabling_payload(
            assembly, None, assembly.spec.goal_ids[0],
            snapshot, selected, updates[0].reason)
        payload["mechanism"] = (
            "fdas-replacement-capacity-production-lifecycle")
        payload["provenance"] = list(payload["provenance"]) + [
            "fdas-capacity-candidate:{}".format(candidate.candidate_hash),
            "legacy-selected-action-byte-exact-match",
            "queue-acceptance-is-not-product-observation",
            "zero-immediate-capacity-goal-relief",
        ]
        proposed = writer.emit(
            "operation_proposed", int(snapshot.turn), payload,
            caused_by=list(caused_by))
        self._operation_payloads[assembly.spec.operation_id] = dict(payload)
        self._operation_event_ids[assembly.spec.operation_id] = (
            proposed["event_id"])
        emitted = [proposed]
        parents = (proposed["event_id"],)
        for update in updates:
            events = self._emit_grounded_enabling_update(
                writer, snapshot, lifecycle, update,
                "fdas-replacement-capacity-production-lifecycle",
                caused_by=parents)
            emitted.extend(events)
            if events:
                parents = (events[-1]["event_id"],)
        return tuple(emitted)

    @staticmethod
    def replacement_capacity_production_matches(candidates, action_key):
        """Return every grounded capacity route matching one policy action."""
        if not isinstance(action_key, str) or not action_key:
            return ()
        return tuple(
            value for value in candidates
            if getattr(value, "production_assembly", None) is not None
            and getattr(value, "action_key", None) == action_key
            and getattr(
                getattr(value, "operation", None),
                "operation_type", None) == (
                    "fdas-shadow:city-replacement-capacity-deficit:"
                    "city_production"))

    def emit_replacement_capacity_production_action_outcome(
            self, writer, snapshot, action, outcome, caused_by=()):
        """Separate engine queue acceptance from later product observation."""
        if (
                snapshot is None
                or not isinstance(action, dict)
                or action.get("action_type") != "city_production"
                or outcome is None
        ):
            return ()
        lifecycle = self._replacement_capacity_production_lifecycle_for(
            writer)
        accepted = bool(
            getattr(outcome, "submitted", False)
            and getattr(outcome, "status", None) == "accepted")
        updates = lifecycle.commit_matching_action(
            snapshot, action, accepted=accepted,
            reason=getattr(outcome, "reason", None))
        emitted = []
        parents = tuple(caused_by)
        for update in updates:
            events = self._emit_grounded_enabling_update(
                writer, snapshot, lifecycle, update,
                "fdas-replacement-capacity-production-lifecycle",
                caused_by=parents,
                action_id=getattr(outcome, "action_id", None))
            emitted.extend(events)
            if events:
                parents = (events[-1]["event_id"],)
        return tuple(emitted)

    def resolve_replacement_capacity_production_operations(
            self, writer, snapshot, caused_by=()):
        """Observe queue and product identity from later authoritative state."""
        if snapshot is None:
            return ()
        lifecycle = self._replacement_capacity_production_lifecycle_for(
            writer)
        emitted = []
        parents = tuple(caused_by)
        for update in lifecycle.observe(snapshot):
            events = self._emit_grounded_enabling_update(
                writer, snapshot, lifecycle, update,
                "fdas-replacement-capacity-production-lifecycle",
                caused_by=parents)
            emitted.extend(events)
            if events:
                parents = (events[-1]["event_id"],)
        return tuple(emitted)

    def _apply_grounded_enabling_update(
            self, lifecycle, update):
        payload = self._operation_payloads[
            update.operation_id]
        assembly = lifecycle.assembly(
            update.operation_id)
        payload["state"] = update.state
        payload["step_index"] = (
            update.step_index)
        payload["reason_code"] = (
            update.reason)
        if update.next_action is not None:
            payload["next_action"] = dict(
                update.next_action)
        if update.schedule is not None:
            payload["assignment_digest"] = (
                update.schedule
                .decision_digest)
            request = next((
                row for row in
                update.schedule.requests
                if row.operation_id
                == update.operation_id
            ), None)
            if request is not None:
                payload["claims"] = [
                    claim.to_dict()
                    for claim in request.claims]
        product_ref = getattr(
            update, "product_ref", None)
        technology_ref = getattr(
            update, "technology_ref", None)
        if product_ref is not None:
            payload["product_ref"] = product_ref
        if technology_ref is not None:
            payload["technology_ref"] = (
                technology_ref)
        for name in (
                "dependency_ready",
                "downstream_ready",
                "replan_required"):
            if hasattr(update, name):
                payload[name] = bool(
                    getattr(update, name))
        downstream_id = getattr(
            update,
            "downstream_operation_id",
            None)
        if downstream_id is not None:
            payload[
                "released_downstream_operation_id"
            ] = downstream_id
        return payload, assembly

    def _emit_grounded_enabling_schedule(
            self, writer, snapshot,
            update, component,
            caused_by=()):
        if update.schedule is None:
            return ()
        schedule = update.schedule
        batch_id = structural_hash({
            "component": component,
            "operation_id":
                update.operation_id,
            "snapshot_id":
                snapshot.snapshot_id,
            "step_index":
                update.step_index,
        })
        artifact = {
            "batch_id": batch_id,
            "exact": schedule.to_dict(),
            "packet_committed_operation_ids":
                list(schedule
                     .selected_operation_ids),
            "packet_exact_selection_equal": True,
            "request_count": len(
                schedule.requests),
        }
        artifact["artifact_hash"] = (
            structural_hash(artifact))
        return self.emit_resource_schedule_results(
            writer, int(snapshot.turn),
            (artifact,), caused_by=caused_by)

    def _emit_grounded_enabling_update(
            self, writer, snapshot,
            lifecycle, update,
            component, caused_by=(),
            action_id=None):
        self._apply_grounded_enabling_update(
            lifecycle, update)
        parents = tuple(dict.fromkeys(
            tuple(caused_by)
            + tuple(
                value for value in (
                    self._operation_event_ids.get(
                        update.operation_id),)
                if value)))
        emitted = []
        schedule_events = (
            self._emit_grounded_enabling_schedule(
                writer, snapshot, update,
                component, caused_by=parents))
        emitted.extend(schedule_events)
        if schedule_events:
            parents = (
                schedule_events[-1][
                    "event_id"],)
        common = (
            writer, int(snapshot.turn),
            update.operation_id)

        def emit_state(
                event_type, state,
                reason=None,
                resolution_status=None):
            nonlocal parents
            event = self._emit_operation_state(
                *common, event_type, state,
                reason,
                snapshot.snapshot_id,
                parents,
                action_id=action_id,
                resolution_status=(
                    resolution_status))
            emitted.append(event)
            parents = (event["event_id"],)

        if update.disposition == "reserved":
            emit_state(
                "operation_reserved",
                "reserved")
            emit_state(
                "operation_step_selected",
                "step_selected")
        elif update.disposition == (
                "step_committed"):
            if update.previous_state == (
                    OperationState.RESERVED.value):
                emit_state(
                    "operation_activated",
                    "activated")
            emit_state(
                "operation_step_revalidated",
                "step_revalidated")
            emit_state(
                "operation_step_committed",
                "step_committed")
        elif update.disposition in (
                "waiting", "step_revalidated"):
            if update.previous_state in (
                    OperationState.RESERVED.value,
                    OperationState.BLOCKED.value):
                emit_state(
                    "operation_activated",
                    "activated")
            emit_state(
                "operation_step_revalidated",
                "step_revalidated",
                update.reason)
        elif update.disposition == "completed":
            emit_state(
                "operation_completed",
                "completed", update.reason,
                "resolved_success")
        elif update.disposition == "failed":
            emit_state(
                "operation_failed",
                "failed", update.reason,
                "resolved_failure")
        elif update.disposition == "blocked":
            emit_state(
                "operation_blocked",
                "blocked", update.reason)
        elif update.disposition == "repaired":
            emit_state(
                "operation_repaired",
                "repaired", update.reason)
        elif update.disposition in (
                "abandoned", "expired"):
            emit_state(
                "operation_abandoned"
                if update.disposition
                == "abandoned"
                else "operation_expired",
                update.disposition,
                update.reason,
                "censored_operation_abort")
        if update.released_reservation is not None:
            releases = self.emit_resource_releases(
                writer, int(snapshot.turn),
                (update.released_reservation,),
                lifecycle.ledger.ledger_digest,
                lifecycle.ledger.LEDGER_IDENTITY,
                caused_by=parents)
            emitted.extend(releases)
        return tuple(emitted)

    def prepare_grounded_enabling_operation(
            self, writer, snapshot,
            ruleset_ir, ruleset_digest,
            action, completion_deadline_turn,
            candidate=None, caused_by=()):
        """Register a shadow GDO-7 operation for an existing-policy action."""
        if (
                snapshot is None
                or not isinstance(action, dict)
                or not isinstance(
                    completion_deadline_turn, int)
                or isinstance(
                    completion_deadline_turn, bool)
                or completion_deadline_turn
                    <= int(snapshot.turn)
        ):
            return ()
        action_type = str(
            action.get("action_type", ""))
        if action_type not in (
                "city_production",
                "tech_research"):
            return ()
        key = (
            str(writer.game_id),
            str(snapshot.snapshot_id),
            canonical_json_bytes(
                action).decode("utf-8"))
        if key in self._prepared_enabling_actions:
            return ()
        self._prepared_enabling_actions.add(key)
        result = self._grounded_enabling_assembly(
            snapshot, ruleset_ir,
            ruleset_digest, action,
            completion_deadline_turn,
            candidate=candidate)
        if result is None:
            return ()
        estimate, assembly, request, goal_id = (
            result)
        candidate_for_event = candidate
        if candidate_for_event is None:
            from .impact import ImpactCandidate
            candidate_for_event = ImpactCandidate(
                dict(action),
                "research_strategy"
                if action_type
                == "tech_research"
                else "production_enabling",
                1.0,
                "observed existing-policy selection")
        estimate_events = (
            self._emit_grounded_enabling_estimate(
                writer, snapshot,
                estimate, request,
                candidate_for_event,
                caused_by=caused_by))
        parents = (
            (estimate_events[-1]["event_id"],)
            if estimate_events
            else tuple(caused_by))
        if assembly is None:
            return estimate_events
        lifecycle = (
            self._production_lifecycle_for(writer)
            if action_type == "city_production"
            else self._research_lifecycle_for(writer))
        updates = lifecycle.register(
            assembly, snapshot)
        selected = bool(
            updates
            and updates[0].disposition
            != "blocked")
        reason = (
            updates[0].reason
            if updates else
            "duplicate-operation-identity")
        payload = self._grounded_enabling_payload(
            assembly, request, goal_id,
            snapshot, selected, reason)
        proposed = writer.emit(
            "operation_proposed",
            int(snapshot.turn), payload,
            caused_by=list(parents))
        self._operation_payloads[
            assembly.spec.operation_id] = (
                dict(payload))
        self._operation_event_ids[
            assembly.spec.operation_id] = (
                proposed["event_id"])
        emitted = list(estimate_events)
        emitted.append(proposed)
        parents = (proposed["event_id"],)
        component = (
            "gdo7a-production-lifecycle"
            if action_type
            == "city_production"
            else "gdo7b-research-lifecycle")
        for update in updates:
            events = self._emit_grounded_enabling_update(
                writer, snapshot, lifecycle,
                update, component,
                caused_by=parents)
            emitted.extend(events)
            if events:
                parents = (
                    events[-1]["event_id"],)
        return tuple(emitted)

    def emit_grounded_enabling_action_outcome(
            self, writer, snapshot,
            action, outcome,
            caused_by=()):
        """Attribute an accepted engine action to its exact GDO-7 shadow."""
        if (
                snapshot is None
                or not isinstance(action, dict)
                or outcome is None
        ):
            return ()
        action_type = str(
            action.get("action_type", ""))
        if action_type == "city_production":
            lifecycle = self._production_lifecycle_for(
                writer)
            component = (
                "gdo7a-production-lifecycle")
        elif action_type == "tech_research":
            lifecycle = self._research_lifecycle_for(
                writer)
            component = (
                "gdo7b-research-lifecycle")
        else:
            return ()
        accepted = bool(
            getattr(outcome, "submitted", False)
            and getattr(outcome, "status", None)
            == "accepted")
        updates = lifecycle.commit_matching_action(
            snapshot, action,
            accepted=accepted,
            reason=getattr(
                outcome, "reason", None))
        emitted = []
        parents = tuple(caused_by)
        for update in updates:
            events = self._emit_grounded_enabling_update(
                writer, snapshot, lifecycle,
                update, component,
                caused_by=parents,
                action_id=getattr(
                    outcome, "action_id", None))
            emitted.extend(events)
            if events:
                parents = (
                    events[-1]["event_id"],)
        return tuple(emitted)

    def resolve_grounded_enabling_operations(
            self, writer, snapshot,
            production_enabled=False,
            research_enabled=False,
            caused_by=()):
        """Resolve GDO-7 shadows from one later authoritative snapshot."""
        if snapshot is None:
            return ()
        lifecycles = []
        if production_enabled:
            lifecycles.append((
                self._production_lifecycle_for(
                    writer),
                "gdo7a-production-lifecycle"))
        if research_enabled:
            lifecycles.append((
                self._research_lifecycle_for(
                    writer),
                "gdo7b-research-lifecycle"))
        emitted = []
        parents = tuple(caused_by)
        for lifecycle, component in lifecycles:
            for update in lifecycle.observe(
                    snapshot):
                events = self._emit_grounded_enabling_update(
                    writer, snapshot,
                    lifecycle, update,
                    component,
                    caused_by=parents)
                emitted.extend(events)
                if events:
                    parents = (
                        events[-1]["event_id"],)
        return tuple(emitted)

    @staticmethod
    def _production_guard_distance(
            left_x, left_y, right_x, right_y,
            width, height, wrap_x, wrap_y):
        if None in (
                left_x, left_y,
                right_x, right_y):
            return None
        if any(isinstance(value, bool) for value in (
                left_x, left_y, right_x, right_y)):
            return None
        try:
            left_x = int(left_x)
            left_y = int(left_y)
            right_x = int(right_x)
            right_y = int(right_y)
        except (TypeError, ValueError, OverflowError):
            return None
        dx = abs(left_x - right_x)
        dy = abs(left_y - right_y)
        if wrap_x is True:
            if (
                    isinstance(width, bool)
                    or not isinstance(width, int)
                    or width <= 0):
                return None
            dx = min(dx, width - dx)
        if wrap_y is True:
            if (
                    isinstance(height, bool)
                    or not isinstance(height, int)
                    or height <= 0):
                return None
            dy = min(dy, height - dy)
        return max(dx, dy)

    def production_persistence_guard(
            self, writer, snapshot,
            maximum_remaining_turns=12,
            threat_radius=3,
            caused_by=()):
        """Protect safe active products from a competing queue switch.

        This is a bounded veto, not a replacement action.  It returns only
        byte-identical currently advertised city-production actions that may
        be excluded from this planner readout.  Incomplete economy, food,
        threat, ETA, lifecycle, or target identity fails closed.
        """
        if snapshot is None:
            return frozenset(), ()
        for value, name in (
                (maximum_remaining_turns,
                 "maximum remaining turns"),
                (threat_radius,
                 "threat radius")):
            if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError(
                    "production persistence {} must be non-negative"
                    .format(name))
        from .production_operations import (
            ProductionEnablingOperationAssembler,
        )

        legal_rows = []
        for action_key in tuple(
                getattr(
                    snapshot,
                    "legal_action_json", ())):
            try:
                action = json.loads(action_key)
            except (TypeError, ValueError):
                continue
            if isinstance(action, dict):
                legal_rows.append((
                    str(action_key), action))
        lifecycle = self._production_lifecycle_for(
            writer)
        eligible_by_city = {}
        for record in lifecycle.store.nonterminal_records():
            assembly = lifecycle.assembly(
                record.spec.operation_id)
            if (
                    assembly is None
                    or record.progress.state
                    != OperationState.ACTIVE
                    or record.progress.current_step_index != 1
                    or record.spec.expiry_turn
                    < int(snapshot.turn)):
                continue
            readout = (
                ProductionEnablingOperationAssembler
                .readout(
                    assembly, snapshot, 1))
            if readout.disposition != "waiting":
                continue
            city = snapshot.city(
                assembly.intent.city_id)
            if city is None:
                continue
            if (
                    getattr(city, "disorder", None) is not False
                    or getattr(city, "had_famine", None) is not False):
                continue
            surplus = tuple(
                getattr(city, "surplus", ()))
            if (
                    len(surplus) < 2
                    or isinstance(surplus[0], bool)
                    or not isinstance(
                        surplus[0], (int, float))
                    or surplus[0] < 0
                    or isinstance(surplus[1], bool)
                    or not isinstance(
                        surplus[1], (int, float))
                    or surplus[1] <= 0):
                continue
            stock = getattr(
                city, "shield_stock", None)
            build_cost = assembly.target_profile.get(
                "build_cost")
            if any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in (stock, build_cost)):
                continue
            remaining_turns = max(
                1,
                int(math.ceil(
                    max(0, build_cost - stock)
                    / float(surplus[1]))))
            projected_completion_turn = (
                int(snapshot.turn)
                + remaining_turns)
            if (
                    remaining_turns
                    > maximum_remaining_turns
                    or projected_completion_turn
                    > record.spec.expiry_turn):
                continue
            profile = assembly.target_profile
            future_gold_upkeep = sum(
                int(profile.get(name, 0) or 0)
                for name in (
                    "building_upkeep",
                    "gold_upkeep"))
            if future_gold_upkeep > 0:
                economy = getattr(
                    snapshot, "economy", None)
                gold = getattr(
                    economy, "gold", None)
                operating = getattr(
                    economy,
                    "operating_gold_per_turn",
                    None)
                if (
                        getattr(
                            economy,
                            "available", False)
                        is not True
                        or isinstance(gold, bool)
                        or not isinstance(gold, int)
                        or gold < future_gold_upkeep
                        or isinstance(operating, bool)
                        or not isinstance(operating, int)
                        or operating < 0):
                    continue
            visible_enemies = getattr(
                snapshot, "visible_enemy_units", None)
            if not isinstance(visible_enemies, (tuple, list)):
                continue
            threats = []
            threat_geometry_unknown = False
            if visible_enemies and (
                    not isinstance(
                        getattr(snapshot, "map_width", None), int)
                    or isinstance(
                        getattr(snapshot, "map_width", None), bool)
                    or getattr(snapshot, "map_width", 0) <= 0
                    or not isinstance(
                        getattr(snapshot, "map_height", None), int)
                    or isinstance(
                        getattr(snapshot, "map_height", None), bool)
                    or getattr(snapshot, "map_height", 0) <= 0
                    or not isinstance(
                        getattr(snapshot, "map_wrap_x", None), bool)
                    or not isinstance(
                        getattr(snapshot, "map_wrap_y", None), bool)):
                continue
            for unit in tuple(visible_enemies):
                distance = self._production_guard_distance(
                    city.x, city.y,
                    getattr(unit, "x", None),
                    getattr(unit, "y", None),
                    getattr(snapshot, "map_width", 0),
                    getattr(snapshot, "map_height", 0),
                    getattr(snapshot, "map_wrap_x", None),
                    getattr(snapshot, "map_wrap_y", None))
                if distance is None:
                    threat_geometry_unknown = True
                elif distance <= threat_radius:
                    threats.append(unit)
            if threats or threat_geometry_unknown:
                continue
            city_id = int(
                assembly.intent.city_id)
            eligible_by_city.setdefault(
                city_id, []).append((
                    record,
                    assembly,
                    projected_completion_turn,
                    {
                        "city_disorder": bool(
                            getattr(city, "disorder", False)),
                        "city_had_famine": bool(
                            getattr(city, "had_famine", False)),
                        "competing_active_operation_count": 1,
                        "build_cost": build_cost,
                        "current_production_kind": getattr(
                            city, "production_kind", None),
                        "current_production_value": getattr(
                            city, "production_value", None),
                        "food_surplus": float(surplus[0]),
                        "future_gold_upkeep": future_gold_upkeep,
                        "gold": getattr(
                            getattr(snapshot, "economy", None),
                            "gold", None),
                        "operating_gold_per_turn": getattr(
                            getattr(snapshot, "economy", None),
                            "operating_gold_per_turn", None),
                        "remaining_turns": remaining_turns,
                        "shield_stock": stock,
                        "shield_surplus": float(surplus[1]),
                        "visible_threat_count": 0,
                    }))
        excluded = set()
        emitted = []
        parents = tuple(caused_by)
        for city_id, rows in sorted(
                eligible_by_city.items()):
            # Competing active intents for one identity-bearing production
            # slot are ambiguous.  Do not choose between them here.
            if len(rows) != 1:
                continue
            record, assembly, completion_turn, safety = rows[0]
            protected_key = canonical_json_bytes(
                assembly.queue_action()).decode("utf-8")
            competing = tuple(sorted(
                action_key
                for action_key, action in legal_rows
                if (
                    action.get("action_type")
                    == "city_production"
                    and action.get("city_id") == city_id
                    and action_key != protected_key)))
            if not competing:
                continue
            excluded.update(competing)
            guard_key = (
                str(writer.game_id),
                str(snapshot.snapshot_id),
                record.spec.operation_id)
            if guard_key in (
                    self
                    ._emitted_production_persistence_guards):
                continue
            self._emitted_production_persistence_guards.add(
                guard_key)
            payload = self._operation_payloads.get(
                record.spec.operation_id)
            if not isinstance(payload, dict):
                continue
            payload["policy_authority"] = True
            payload["shadow_only"] = False
            payload["provenance"] = list(dict.fromkeys(
                tuple(payload.get("provenance") or ())
                + (
                    "bounded-production-persistence-authority/1.0",
                )))
            selected = dict(payload)
            selected.update({
                "authority_effect": (
                    "exclude-competing-city-production-switches"),
                "excluded_action_ids": [
                    structural_hash(json.loads(action_key))
                    for action_key in competing
                ],
                "excluded_actions": [
                    json.loads(action_key)
                    for action_key in competing
                ],
                "next_action": assembly.queue_action(),
                "persistence_maximum_remaining_turns": (
                    maximum_remaining_turns),
                "persistence_threat_radius": threat_radius,
                "policy_authority": True,
                "production_persistence_safety": dict(safety),
                "projected_completion_turn": completion_turn,
                "protected_city_id": city_id,
                "reason_code": (
                    "bounded-production-persistence-authority"),
                "selected": True,
                "shadow_only": False,
                "snapshot_id": snapshot.snapshot_id,
                "state": "step_selected",
                "visible_threat_count": 0,
            })
            event = writer.emit(
                "operation_step_selected",
                int(snapshot.turn), selected,
                caused_by=list(parents))
            emitted.append(event)
            metric = writer.emit(
                "metric_sample",
                int(snapshot.turn), {
                    "labels": {
                        "authority_kind": (
                            "production_persistence"),
                        "component": (
                            "bounded-operation-authority"),
                        "operation_type": (
                            record.spec.operation_type),
                    },
                    "name": (
                        "production_persistence_authority_application"),
                    "unit": "count",
                    "value": 1.0,
                },
                caused_by=[event["event_id"]])
            emitted.append(metric)
            parents = (metric["event_id"],)
        return frozenset(excluded), tuple(emitted)

    def emit_combat_operation_shadow(
            self, writer, snapshot,
            ruleset_digest, ruleset_ir=None,
            caused_by=(),
            maximum_operations=32,
            action_budget=None):
        """Emit one exact, shadow-only GDO-5 readout per snapshot."""
        from ..pressure.resource_capacity import (
            ResourceCapacityExtractor,
        )
        from ..pressure.resource_scheduler import (
            BoundedExactScheduler,
        )
        from .combat_operations import (
            CombatOperationAssembler,
            combat_target_capacities,
        )

        snapshot_id = str(
            getattr(snapshot, "snapshot_id", ""))
        if (
            not snapshot_id
            or snapshot_id
                in self._emitted_combat_snapshot_ids
        ):
            return ()
        self._emitted_combat_snapshot_ids.add(
            snapshot_id)
        parents = tuple(caused_by)
        emitted = []
        assembler = CombatOperationAssembler()
        assemblies = assembler.assemble(
            snapshot,
            str(ruleset_digest),
            ruleset_ir=ruleset_ir,
            maximum_operations=(
                maximum_operations))
        schedule = None
        entries = {}
        if assemblies:
            capacity_snapshot = (
                ResourceCapacityExtractor()
                .extract(
                    snapshot,
                    action_budget=(
                        action_budget)))
            capacities = (
                capacity_snapshot.capacities
                + combat_target_capacities(
                    assemblies, snapshot))
            premise_packets = {
                premise_id: value
                for assembly in assemblies
                for premise_id, value in
                assembly.initial_premise_packets
            }
            schedule = (
                BoundedExactScheduler(
                    node_budget=4096,
                    time_budget_ms=20.0)
                .schedule(
                    tuple(
                        assembly.resource_request
                        for assembly
                        in assemblies),
                    capacities,
                    requirement_sets=tuple(
                        assembly.requirement_set
                        for assembly
                        in assemblies),
                    premise_packets=(
                        premise_packets)))
            entries = {
                row.operation_id: row
                for row in schedule.entries
            }

        lifecycle_eligible_ids = set()
        for assembly in assemblies:
            operation_id = (
                assembly.spec.operation_id)
            entry = entries.get(
                operation_id)
            selected = bool(
                entry is not None
                and entry.selected)
            reason = (
                "shadow-schedule-selected-no-policy-authority"
                if selected
                else (
                    entry.reason
                    if entry is not None
                    else
                    "shadow-scheduler-unavailable"))
            readout = assembler.readout(
                assembly, snapshot, 0)
            if readout.disposition != (
                    "reservable"):
                selected = False
                reason = readout.reason
            payload = {
                "actor_id": (
                    assembly.spec
                    .participants[0]
                    .actor_id),
                "assignment_digest": (
                    schedule.decision_digest
                    if schedule is not None
                    else None),
                "bid": float(
                    assembly.resource_request
                    .bid),
                "claims": [
                    claim.to_dict()
                    for claim in
                    assembly.resource_request
                    .claims],
                "deadline_turn": (
                    assembly.spec.expiry_turn),
                "event_schema_version":
                    CONTROL_EVENT_SCHEMA_VERSION,
                "expected_prevented_loss":
                    float(
                        assembly
                        .step_material_estimates[0]
                        .expected_enemy_terminal_loss
                        .lower),
                "next_action":
                    readout.next_action,
                "operation_digest":
                    structural_hash(
                        assembly.spec.to_dict()),
                "operation_id":
                    operation_id,
                "operation_type":
                    assembly.spec.operation_type,
                "opportunity_cost": float(
                    assembly
                    .step_material_estimates[0]
                    .expected_friendly_terminal_loss
                    .upper),
                "material_estimate": (
                    assembly
                    .step_material_estimates[0]
                    .to_dict()),
                "participants": [
                    participant.to_dict()
                    for participant in
                    assembly.spec.participants],
                "policy_authority": False,
                "probability_interval": (
                    assembly
                    .operation_probability_interval
                    .to_dict()),
                "provenance": list(
                    assembly.spec.provenance),
                "reason_code": str(reason),
                "requirement_id": (
                    assembly.requirement_set
                    .requirement_set_id),
                "requirement_set": (
                    assembly.requirement_set
                    .to_dict()),
                "selected": selected,
                "shadow_only": True,
                "snapshot_id": snapshot_id,
                "state": "proposed",
                "step_probability_intervals": [
                    interval.to_dict()
                    for interval in
                    assembly
                    .step_probability_intervals],
                "step_material_estimates": [
                    estimate.to_dict()
                    for estimate in
                    assembly
                    .step_material_estimates],
                "target_id":
                    assembly.spec.target_ref,
            }
            event = writer.emit(
                "operation_proposed",
                int(snapshot.turn),
                payload,
                caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
            if selected:
                lifecycle_eligible_ids.add(
                    operation_id)
                if operation_id not in (
                        self
                        ._operation_payloads):
                    self._operation_payloads[
                        operation_id] = dict(
                            payload)
                    self._operation_event_ids[
                        operation_id] = (
                            event["event_id"])

        if schedule is not None:
            schedule_dict = schedule.to_dict()
            batch_id = structural_hash({
                "component":
                    "gdo5-combat-operation-shadow",
                "ruleset_digest":
                    str(ruleset_digest),
                "snapshot_id": snapshot_id,
            })
            artifact = {
                "batch_id": batch_id,
                "exact": schedule_dict,
                "packet_committed_operation_ids":
                    list(
                        schedule
                        .selected_operation_ids),
                "packet_exact_selection_equal":
                    True,
                "request_count":
                    len(assemblies),
            }
            artifact["artifact_hash"] = (
                structural_hash(artifact))
            schedule_events = (
                self.emit_resource_schedule_results(
                    writer,
                    int(snapshot.turn),
                    (artifact,),
                    caused_by=parents))
            emitted.extend(
                schedule_events)
            if schedule_events:
                parents = (
                    schedule_events[-1][
                        "event_id"],)

            lifecycle = (
                self._combat_lifecycle_for(
                    writer))
            try:
                lifecycle_updates = (
                    lifecycle
                    .register_schedule(
                        tuple(
                            assembly
                            for assembly in
                            assemblies
                            if assembly.spec
                            .operation_id
                            in lifecycle_eligible_ids),
                        schedule,
                        snapshot))
            except (
                    KeyError,
                    TypeError,
                    ValueError):
                lifecycle_updates = ()
                for operation_id in (
                        schedule
                        .selected_operation_ids):
                    if operation_id not in (
                            lifecycle_eligible_ids):
                        continue
                    if lifecycle.store.get(
                            operation_id
                    ) is not None:
                        continue
                    blocked = (
                        self
                        ._emit_operation_state(
                            writer,
                            int(snapshot.turn),
                            operation_id,
                            "operation_blocked",
                            "blocked",
                            "combat-lifecycle-registration-failed",
                            snapshot_id,
                            parents))
                    emitted.append(
                        blocked)
                    parents = (
                        blocked[
                            "event_id"],)
            for update in (
                    lifecycle_updates):
                self._apply_combat_lifecycle_update(
                    lifecycle, update)
                reserved = (
                    self._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        update.operation_id,
                        "operation_reserved",
                        "reserved", None,
                        snapshot_id,
                        parents))
                emitted.append(
                    reserved)
                selected = (
                    self._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        update.operation_id,
                        "operation_step_selected",
                        "step_selected",
                        None,
                        snapshot_id,
                        (reserved[
                            "event_id"],)))
                emitted.append(
                    selected)
                parents = (
                    selected[
                        "event_id"],)
            registered_ids = {
                update.operation_id
                for update in
                lifecycle_updates}
            for operation_id in sorted(
                    lifecycle_eligible_ids
                    & set(
                        schedule
                        .selected_operation_ids)
                    - registered_ids):
                if lifecycle.store.get(
                        operation_id
                ) is not None:
                    continue
                blocked = (
                    self
                    ._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        operation_id,
                        "operation_blocked",
                        "blocked",
                        "active-reservation-conflict",
                        snapshot_id,
                        parents))
                emitted.append(
                    blocked)
                parents = (
                    blocked[
                        "event_id"],)

        metrics = (
            (
                "native_combat_probability_rows",
                len(getattr(
                    snapshot,
                    "combat_probabilities", ()))),
            (
                "combat_operation_candidate_count",
                len(assemblies)),
            (
                "combat_operation_selected_count",
                0 if schedule is None else
                len(schedule
                    .selected_operation_ids)),
            (
                "combat_operation_scheduler_latency_ms",
                0.0 if schedule is None
                else schedule.latency_ms),
        )
        for name, value in metrics:
            event = writer.emit(
                "metric_sample",
                int(snapshot.turn), {
                    "labels": {
                        "component": "gdo5",
                        "mode": "shadow",
                    },
                    "name": name,
                    "unit": (
                        "milliseconds"
                        if name.endswith(
                            "_latency_ms")
                        else "count"),
                    "value": float(value),
                },
                caused_by=list(parents))
            emitted.append(event)
            parents = (
                event["event_id"],)
        return tuple(emitted)

    def emit_combat_action_outcome(
            self, writer, snapshot,
            action, outcome,
            caused_by=()):
        """Attribute a real action to a reserved shadow combat step."""
        if (
            snapshot is None
            or not isinstance(
                action, dict)
            or outcome is None
        ):
            return ()
        lifecycle = (
            self._combat_lifecycle_for(
                writer))
        accepted = bool(
            getattr(
                outcome,
                "submitted", False)
            and getattr(
                outcome,
                "status", None)
            == "accepted")
        updates = (
            lifecycle
            .commit_matching_action(
                snapshot, action,
                accepted=accepted,
                reason=getattr(
                    outcome,
                    "reason", None)))
        if not updates:
            return ()
        parents = tuple(caused_by)
        emitted = []
        action_id = getattr(
            outcome, "action_id", None)
        for update in updates:
            self._apply_combat_lifecycle_update(
                lifecycle, update)
            if update.disposition == (
                    "failed"):
                event = (
                    self._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        update.operation_id,
                        "operation_failed",
                        "failed",
                        update.reason,
                        snapshot.snapshot_id,
                        parents,
                        action_id=action_id,
                        resolution_status=(
                            "resolved_failure")))
                emitted.append(event)
                parents = (
                    event["event_id"],)
            else:
                if update.previous_state == (
                        OperationState
                        .RESERVED.value):
                    activated = (
                        self._emit_operation_state(
                            writer,
                            int(snapshot.turn),
                            update.operation_id,
                            "operation_activated",
                            "activated", None,
                            snapshot.snapshot_id,
                            parents,
                            action_id=(
                                action_id)))
                    emitted.append(
                        activated)
                    parents = (
                        activated[
                            "event_id"],)
                revalidated = (
                    self._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        update.operation_id,
                        "operation_step_revalidated",
                        "step_revalidated",
                        None,
                        snapshot.snapshot_id,
                        parents,
                        action_id=action_id))
                emitted.append(
                    revalidated)
                committed = (
                    self._emit_operation_state(
                        writer,
                        int(snapshot.turn),
                        update.operation_id,
                        "operation_step_committed",
                        "step_committed",
                        None,
                        snapshot.snapshot_id,
                        (revalidated[
                            "event_id"],),
                        action_id=action_id))
                emitted.append(
                    committed)
                parents = (
                    committed[
                        "event_id"],)
            if update.released_reservation is not None:
                releases = (
                    self.emit_resource_releases(
                        writer,
                        int(snapshot.turn),
                        (
                            update
                            .released_reservation,),
                        lifecycle.ledger
                        .ledger_digest,
                        lifecycle.ledger
                        .LEDGER_IDENTITY,
                        caused_by=parents))
                emitted.extend(
                    releases)
                if releases:
                    parents = (
                        releases[-1][
                            "event_id"],)
        return tuple(emitted)

    def _emit_combat_lifecycle_schedule(
            self, writer, snapshot,
            update, caused_by):
        if update.schedule is None:
            return ()
        schedule = update.schedule
        batch_id = structural_hash({
            "component":
                "gdo5-combat-lifecycle-step",
            "operation_id":
                update.operation_id,
            "snapshot_id":
                snapshot.snapshot_id,
            "step_index":
                update.step_index,
        })
        artifact = {
            "batch_id": batch_id,
            "exact": schedule.to_dict(),
            "packet_committed_operation_ids":
                list(
                    schedule
                    .selected_operation_ids),
            "packet_exact_selection_equal":
                True,
            "request_count":
                len(schedule.requests),
        }
        artifact["artifact_hash"] = (
            structural_hash(artifact))
        return self.emit_resource_schedule_results(
            writer,
            int(snapshot.turn),
            (artifact,),
            caused_by=caused_by)

    def resolve_combat_operations(
            self, writer, snapshot,
            caused_by=()):
        """Re-estimate committed or blocked combat steps on a new snapshot."""
        if snapshot is None:
            return ()
        lifecycle = (
            self._combat_lifecycle_for(
                writer))
        updates = lifecycle.observe(
            snapshot)
        parents = tuple(caused_by)
        emitted = []
        for update in updates:
            self._apply_combat_lifecycle_update(
                lifecycle, update)
            if update.released_reservation is not None:
                releases = (
                    self.emit_resource_releases(
                        writer,
                        int(snapshot.turn),
                        (
                            update
                            .released_reservation,),
                        lifecycle.ledger
                        .ledger_digest,
                        lifecycle.ledger
                        .LEDGER_IDENTITY,
                        caused_by=parents))
                emitted.extend(
                    releases)
                if releases:
                    parents = (
                        releases[-1][
                            "event_id"],)
            schedule_events = (
                self
                ._emit_combat_lifecycle_schedule(
                    writer, snapshot,
                    update, parents))
            emitted.extend(
                schedule_events)
            if schedule_events:
                parents = (
                    schedule_events[-1][
                        "event_id"],)
            common = (
                writer,
                int(snapshot.turn),
                update.operation_id)
            if update.disposition == (
                    "completed"):
                event = self._emit_operation_state(
                    *common,
                    "operation_completed",
                    "completed",
                    update.reason,
                    snapshot.snapshot_id,
                    parents,
                    resolution_status=(
                        "resolved_success"))
                emitted.append(event)
                parents = (
                    event["event_id"],)
            elif update.disposition == (
                    "failed"):
                event = self._emit_operation_state(
                    *common,
                    "operation_failed",
                    "failed",
                    update.reason,
                    snapshot.snapshot_id,
                    parents,
                    resolution_status=(
                        "resolved_no_effect"))
                emitted.append(event)
                parents = (
                    event["event_id"],)
            elif update.disposition in (
                    "abandoned",
                    "expired"):
                event_type = (
                    "operation_abandoned"
                    if update.disposition
                    == "abandoned"
                    else "operation_expired")
                event = self._emit_operation_state(
                    *common,
                    event_type,
                    update.disposition,
                    update.reason,
                    snapshot.snapshot_id,
                    parents,
                    resolution_status=(
                        "censored_operation_abort"))
                emitted.append(event)
                parents = (
                    event["event_id"],)
            elif update.disposition == (
                    "blocked"):
                event = self._emit_operation_state(
                    *common,
                    "operation_blocked",
                    "blocked",
                    update.reason,
                    snapshot.snapshot_id,
                    parents)
                emitted.append(event)
                parents = (
                    event["event_id"],)
            elif update.disposition == (
                    "repaired"):
                repaired = self._emit_operation_state(
                    *common,
                    "operation_repaired",
                    "repaired",
                    update.reason,
                    snapshot.snapshot_id,
                    parents)
                emitted.append(
                    repaired)
                reserved = self._emit_operation_state(
                    *common,
                    "operation_reserved",
                    "reserved", None,
                    snapshot.snapshot_id,
                    (repaired[
                        "event_id"],))
                emitted.append(
                    reserved)
                selected = self._emit_operation_state(
                    *common,
                    "operation_step_selected",
                    "step_selected", None,
                    snapshot.snapshot_id,
                    (reserved[
                        "event_id"],))
                emitted.append(
                    selected)
                parents = (
                    selected[
                        "event_id"],)
            elif update.disposition in (
                    "step_reestimated",
                    "step_revalidated"):
                revalidated = (
                    self._emit_operation_state(
                        *common,
                        "operation_step_revalidated",
                        "step_revalidated",
                        update.reason,
                        snapshot.snapshot_id,
                        parents))
                emitted.append(
                    revalidated)
                parents = (
                    revalidated[
                        "event_id"],)
                if update.disposition == (
                        "step_reestimated"):
                    selected = (
                        self._emit_operation_state(
                            *common,
                            "operation_step_selected",
                            "step_selected",
                            None,
                            snapshot.snapshot_id,
                            parents))
                    emitted.append(
                        selected)
                    parents = (
                        selected[
                            "event_id"],)
        return tuple(emitted)

    @staticmethod
    def emit_resource_releases(
            writer, turn, reservations,
            ledger_digest, scheduler_identity,
            caused_by=()):
        """Emit release/expiry rows returned by a reservation ledger."""
        parents = tuple(caused_by)
        emitted = []
        for reservation in reservations:
            state = getattr(
                getattr(
                    reservation,
                    "state", None),
                "value", None)
            if state not in (
                    "released", "expired"):
                continue
            for claim in getattr(
                    reservation, "claims", ()):
                claim_payload = (
                    claim.to_dict())
                payload = {
                    "claim_id":
                        claim.claim_id,
                    "conflict_resource_ids":
                        [],
                    "conflicting_operation_ids":
                        [],
                    "disposition": state,
                    "event_schema_version":
                        CONTROL_EVENT_SCHEMA_VERSION,
                    "exclusive":
                        claim.exclusive,
                    "hardness":
                        claim.hardness.value,
                    "operation_id":
                        reservation
                        .operation_id,
                    "quantity":
                        claim.quantity,
                    "reason":
                        reservation.reason,
                    "resource":
                        claim_payload[
                            "resource"],
                    "schedule_digest":
                        ledger_digest,
                    "scheduler_identity":
                        scheduler_identity,
                    "shadow_only": True,
                    "snapshot_id":
                        reservation
                        .snapshot_id,
                    "source_step_id":
                        claim.source_step_id,
                    "window":
                        claim_payload[
                            "window"],
                }
                event = writer.emit(
                    "resource_claim_released",
                    turn, payload,
                    caused_by=list(parents))
                emitted.append(event)
                parents = (
                    event["event_id"],)
        return tuple(emitted)

    def emit_domain_estimate_artifacts(
            self, writer, turn, artifacts,
            caused_by=()):
        """Emit completed shadow rows once, including final drained batches."""
        parents = tuple(caused_by)
        emitted = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            for row in artifact.get(
                    "estimates", ()):
                if not isinstance(row, dict):
                    continue
                event_type = row.get(
                    "event_type")
                payload = row.get(
                    "event_payload")
                if (event_type not in (
                        "domain_estimate_emitted",
                        "domain_estimate_abstained")
                        or not isinstance(payload, dict)):
                    continue
                request_id = payload.get(
                    "request_id",
                    row.get("request_id"))
                if (not isinstance(request_id, str)
                        or not request_id
                        or request_id in
                        self._emitted_domain_request_ids):
                    continue
                event = writer.emit(
                    event_type, turn, payload,
                    caused_by=list(parents))
                self._emitted_domain_request_ids.add(
                    request_id)
                emitted.append(event)
                parents = (event["event_id"],)
        return tuple(emitted)

    @staticmethod
    def _emit(
            writer, event_type, turn, query,
            decision, parents, summary,
            flow_artifact=None,
            decision_hash=None):
        parents = tuple(str(value) for value in parents)
        summary = json.loads(
            canonical_json_bytes(
                dict(summary)).decode("utf-8"))
        payload = {
            "artifact_hash": structural_hash(
                summary),
            "config_digest": query.config_digest,
            "controller_decision_hash":
                (decision_hash
                 if decision_hash is not None
                 else decision.decision_hash),
            "event_schema_version":
                CONTROL_EVENT_SCHEMA_VERSION,
            "parent_event_ids": list(parents),
            "query_id": query.query_id,
            "semantic_epoch":
                query.semantic_epoch,
            "summary": summary,
            "topology_generation":
                _topology_generation(
                    query, flow_artifact),
        }
        return writer.emit(
            event_type, turn, payload,
            caused_by=list(parents))

    def emit_decision(
            self, writer, turn, query,
            decision, caused_by=()):
        if not isinstance(query, ControlQuery):
            raise TypeError(
                "control events require ControlQuery")
        if not isinstance(decision, ControlDecision):
            raise TypeError(
                "control events require ControlDecision")
        parents = tuple(caused_by)
        emitted = []
        flow_artifact = _flow_artifact(
            decision)
        # A unified artifact contains probe, projection, transport, and packet
        # blocks. Its semantic hash is intentionally comprehensive, but
        # recomputing it for every event in the same causal chain made
        # observability more expensive than the controller itself.
        decision_hash = decision.decision_hash
        direct_ranker = (
            decision.artifact.get(
                "ranker_artifact")
            if isinstance(
                decision.artifact, dict)
            else None)
        pressure = (
            flow_artifact.get(
                "pressure_artifact", {})
            if flow_artifact is not None
            else direct_ranker
            if isinstance(direct_ranker, dict)
            else {})
        direct_bridge = (
            direct_ranker.get("bridge")
            if (
                flow_artifact is None
                and isinstance(direct_ranker, dict)
                and isinstance(
                    direct_ranker.get("bridge"),
                    dict))
            else None)
        domain_estimates = (
            pressure.get("domain_estimates")
            if isinstance(pressure, dict)
            else None)
        if isinstance(domain_estimates, dict):
            domain_events = (
                self.emit_domain_estimate_artifacts(
                    writer, turn,
                    (domain_estimates,),
                    caused_by=parents))
            emitted.extend(domain_events)
            if domain_events:
                parents = (
                    domain_events[-1][
                        "event_id"],)
        resource_artifacts = (
            self._resource_schedule_artifact(
                pressure))
        if resource_artifacts is not None:
            resource_events = (
                self.emit_resource_schedule_results(
                    writer, turn,
                    (resource_artifacts[0],),
                    caused_by=parents))
            emitted.extend(
                resource_events)
            if resource_events:
                parents = (
                    resource_events[-1][
                        "event_id"],)
        teleology = (
            pressure.get("teleology", {})
            if isinstance(pressure, dict)
            else {})
        if isinstance(teleology, dict) and teleology:
            event = self._emit(
                writer, "teleology_estimated",
                turn, query, decision, parents, {
                    "artifact_hash":
                        teleology.get(
                            "artifact_hash"),
                    "calibration":
                        teleology.get(
                            "calibration"),
                    "estimator_hierarchy":
                        teleology.get(
                            "estimator_hierarchy",
                            ()),
                    "goal_count": len(
                        teleology.get(
                            "goal_losses", ())),
                    "operation_count": len(
                        teleology.get(
                            "operation_estimates",
                            ())),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
            calibration = teleology.get(
                "calibration", {})
            if (isinstance(calibration, dict)
                    and calibration.get(
                        "model") is not None):
                estimates = tuple(
                    row.get("transition_value")
                    for row in teleology.get(
                        "operation_estimates", ())
                    if isinstance(row, dict)
                    and isinstance(
                        row.get(
                            "transition_value"),
                        dict))
                event = self._emit(
                    writer,
                    "transition_value_estimated",
                    turn, query, decision, parents, {
                        "abstained_operation_count":
                            sum(
                                not row.get(
                                    "calibrated",
                                    False)
                                for row in estimates),
                        "all_candidate_support":
                            calibration.get(
                                "all_candidate_support",
                                False),
                        "authority_active":
                            calibration.get(
                                "authority_active",
                                False),
                        "authority_requested":
                            calibration.get(
                                "authority_requested",
                                False),
                        "gate_reason":
                            calibration.get(
                                "gate_reason"),
                        "model":
                            calibration.get("model"),
                        "operation_count":
                            len(estimates),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
        path_persistence = (
            pressure.get("path_persistence")
            if isinstance(pressure, dict)
            else None)
        if isinstance(path_persistence, dict):
            event = self._emit(
                writer,
                "path_persistence_applied",
                turn, query, decision, parents, {
                    "artifact_hash":
                        path_persistence.get(
                            "artifact_hash"),
                    "authority_active":
                        path_persistence.get(
                            "authority_active",
                            False),
                    "decision":
                        path_persistence.get(
                            "decision"),
                    "fallback_reason":
                        path_persistence.get(
                            "fallback_reason"),
                    "maximum_priority_regret":
                        path_persistence.get(
                            "maximum_priority_regret"),
                    "priority_regret":
                        path_persistence.get(
                            "priority_regret"),
                    "reordered":
                        path_persistence.get(
                            "reordered", False),
                    "scalar_corridor":
                        path_persistence.get(
                            "scalar_corridor"),
                    "selected_corridor":
                        path_persistence.get(
                            "selected_corridor"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        if direct_bridge is not None:
            potential_summary = direct_bridge.get(
                "potential_summary")
            potential_rows = (
                (potential_summary,)
                if isinstance(
                    potential_summary, dict)
                else potential_summary
                if isinstance(
                    potential_summary, (list, tuple))
                else None)
            if potential_rows is not None:
                event = self._emit(
                    writer, "bridge_estimated",
                    turn, query, decision, parents, {
                        "controller_mode":
                            decision.controller_mode,
                        "goal_summaries":
                            potential_rows,
                        "normalization_contract":
                            query
                            .normalization_contract_hash,
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            probe_batches = []
            goal_readouts = []
            for goal_row in direct_bridge.get(
                    "goal_selections", ()):
                if not isinstance(goal_row, dict):
                    continue
                goal_id = goal_row.get(
                    "goal_id")
                for side in (
                        "forward", "backward"):
                    probe = goal_row.get(
                        "{}_probe".format(side))
                    if not isinstance(probe, dict):
                        continue
                    probe_batches.append({
                        "artifact_hash":
                            probe.get(
                                "artifact_hash"),
                        "goal_id": goal_id,
                        "health":
                            probe.get("health"),
                        "meet_count":
                            probe.get(
                                "meet_count"),
                        "path_count":
                            probe.get(
                                "path_count"),
                        "side": side,
                    })
                selection = goal_row.get(
                    "selection")
                if isinstance(selection, dict):
                    goal_readouts.append({
                        "fallback_reason":
                            selection.get(
                                "fallback_reason"),
                        "fallback_required":
                            selection.get(
                                "fallback_required",
                                False),
                        "goal_id": goal_id,
                        "selected_operation_count":
                            len(selection.get(
                                "selected_operation_node_ids",
                                ())),
                    })
            if probe_batches:
                event = self._emit(
                    writer,
                    "probe_block_completed",
                    turn, query, decision, parents, {
                        "batches": probe_batches,
                        "controller_mode":
                            decision.controller_mode,
                        "goal_readouts":
                            goal_readouts,
                        "readout_source":
                            "protected-bridge-scalar",
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            if direct_bridge.get(
                    "fallback_required") is True:
                event = self._emit(
                    writer,
                    "controller_fallback",
                    turn, query, decision, parents, {
                        "controller_identity":
                            direct_bridge.get(
                                "controller_identity"),
                        "controller_mode":
                            decision.controller_mode,
                        "effective_candidate_key":
                            decision
                            .selected_candidate_key,
                        "fallback_chain": list(
                            decision.fallback_chain),
                        "reason":
                            direct_bridge.get(
                                "fallback_reason"),
                        "readout_source":
                            "protected-bridge-scalar",
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            candidate_union = (
                _protected_bridge_union(
                    direct_bridge))
            if candidate_union is not None:
                scalar = direct_bridge.get(
                    "scalar_decision", {})
                scalar_id = (
                    scalar.get(
                        "selected_route_id")
                    if isinstance(scalar, dict)
                    else None)
                selected_id = direct_bridge.get(
                    "selected_operation_id")
                calibration = (
                    teleology.get(
                        "calibration", {})
                    if isinstance(
                        teleology, dict)
                    else {})
                event = self._emit(
                    writer,
                    "flow_candidate_selected",
                    turn, query, decision, parents, {
                        "calibrated": bool(
                            calibration.get(
                                "authority_active",
                                False)),
                        "confidence": 0.0,
                        "effective_candidate_key":
                            decision
                            .selected_candidate_key,
                        "readout_source":
                            "protected-bridge-scalar",
                        "selected_candidate_key":
                            decision
                            .selected_candidate_key,
                        "selection_disposition":
                            _flow_selection_disposition(
                                decision),
                        "transport_readout": {
                            "candidate_regions": [],
                            "candidate_readouts": [],
                            "candidate_union":
                                candidate_union,
                            "disagrees_with_scalar":
                                selected_id != scalar_id,
                            "maximum_overlap": None,
                            "scalar_selected_operation_id":
                                scalar_id,
                            "selected_node_id": None,
                            "selected_operation_id":
                                selected_id,
                            "selected_overlap": None,
                        },
                        "typed_advantage": None,
                    }, None, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
        if flow_artifact is not None:
            flow = flow_artifact.get("flow", {})
            potential_summary = flow.get(
                "potential_summary")
            if isinstance(potential_summary, list):
                event = self._emit(
                    writer, "bridge_estimated",
                    turn, query, decision, parents, {
                        "goal_summaries":
                            potential_summary,
                        "normalization_contract":
                            query
                            .normalization_contract_hash,
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            probe_batches = flow.get(
                "probe_batches", ())
            if isinstance(probe_batches, list):
                event = self._emit(
                    writer,
                    "probe_block_completed",
                    turn, query, decision, parents, {
                        "batches": [
                            {
                                "artifact_hash":
                                    row.get(
                                        "artifact_hash"),
                                "health": row.get(
                                    "health"),
                                "path_count": len(
                                    row.get(
                                        "paths", ())),
                                "side": row.get(
                                    "side"),
                            }
                            for row in probe_batches
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            currents = flow.get(
                "requested_currents", ())
            if isinstance(currents, list):
                event = self._emit(
                    writer,
                    "path_current_deposited",
                    turn, query, decision, parents, {
                        "currents": [
                            {
                                "commodity_id":
                                    row.get(
                                        "commodity_id"),
                                "current_hash":
                                    structural_hash(row),
                                "probe_effective_sample_size":
                                    row.get(
                                        "probe_effective_sample_size"),
                                "successful_probe_count":
                                    row.get(
                                        "successful_probe_count"),
                            }
                            for row in currents
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            projections = flow.get(
                "projection_results", ())
            if isinstance(projections, list):
                event = self._emit(
                    writer, "flow_projected",
                    turn, query, decision, parents, {
                        "projections": [
                            {
                                "balance_residual":
                                    row.get(
                                        "balance_residual"),
                                "component_count":
                                    row.get(
                                        "component_count"),
                                "health": row.get(
                                    "health"),
                                "iterations": row.get(
                                    "iterations"),
                                "requested_current_hash":
                                    row.get(
                                        "requested_current_hash"),
                                "solver": row.get(
                                    "solver"),
                            }
                            for row in projections
                            if isinstance(row, dict)
                        ],
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            transport = flow.get(
                "transport")
            if isinstance(transport, dict):
                final_state = transport.get(
                    "final_state", {})
                event = self._emit(
                    writer, "attention_advected",
                    turn, query, decision, parents, {
                        "backward_total":
                            final_state.get(
                                "backward_total"),
                        "edge_updates":
                            transport.get(
                                "edge_updates"),
                        "forward_total":
                            final_state.get(
                                "forward_total"),
                        "microsteps":
                            transport.get(
                                "microsteps"),
                        "readout":
                            _compact_transport_readout(
                                flow.get(
                                    "transport_readout")),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            packet = flow.get(
                "packet_decision")
            if isinstance(packet, dict):
                event = self._emit(
                    writer, "packet_reserved",
                    turn, query, decision, parents, {
                        "candidate_authority":
                            packet.get(
                                "candidate_authority"),
                        "packet_schedule":
                            packet.get(
                                "packet_schedule"),
                        "revalidation":
                            packet.get(
                                "revalidation"),
                    }, flow_artifact, decision_hash)
                emitted.append(event)
                parents = (event["event_id"],)
            event = self._emit(
                writer, "flow_candidate_selected",
                turn, query, decision, parents, {
                    "admissible_candidate_keys":
                        flow_artifact.get(
                            "admissible_candidate_keys",
                            ()),
                    "calibrated":
                        flow_artifact.get(
                            "calibrated", False),
                    "confidence":
                        flow_artifact.get(
                            "confidence", 0.0),
                    "effective_candidate_key":
                        decision
                        .selected_candidate_key,
                    "selected_candidate_key":
                        _flow_candidate_key(
                            decision,
                            flow_artifact),
                    "selection_disposition":
                        _flow_selection_disposition(
                            decision),
                    "transport_readout":
                        _compact_transport_readout(
                            flow.get(
                                "transport_readout")),
                    "typed_advantage":
                        flow_artifact.get(
                            "typed_advantage"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        validation = decision.artifact.get(
            "validation")
        if isinstance(validation, dict):
            event = self._emit(
                writer, "candidate_revalidated",
                turn, query, decision, parents,
                validation, flow_artifact,
                decision_hash)
            emitted.append(event)
            parents = (event["event_id"],)
        if (decision.health in (
                "fallback", "unhealthy")
                or decision.fallback_chain):
            event = self._emit(
                writer, "controller_fallback",
                turn, query, decision, parents, {
                    "fallback_chain": list(
                        decision.fallback_chain),
                    "gate_reasons":
                        decision.artifact.get(
                            "gate_reasons", ()),
                    "health": decision.health,
                    "advisory_candidate_key":
                        decision.artifact.get(
                            "advisory_candidate_key"),
                    "advisory_candidate_terminal":
                        decision.artifact.get(
                            "advisory_candidate_terminal"),
                    "fallback_candidate_key":
                        decision.artifact.get(
                            "fallback_candidate_key"),
                    "fallback_candidate_terminal":
                        decision.artifact.get(
                            "fallback_candidate_terminal"),
                }, flow_artifact, decision_hash)
            emitted.append(event)
        return tuple(emitted)

    def emit_outcome(
            self, writer, turn, query,
            decision, outcome, caused_by=()):
        if not isinstance(outcome, ControlOutcomeRecord):
            raise TypeError(
                "control outcome event has wrong type")
        return self._emit(
            writer, "control_outcome_recorded",
            turn, query, decision, caused_by,
            outcome.to_dict(),
            _flow_artifact(decision),
            outcome.decision_hash)

    def emit_transition_value_update(
            self, writer, turn, query,
            decision, update, caused_by=()):
        from ..pressure.transition_value import (
            ContextualTransitionValueUpdate,
            TransitionValueUpdate,
        )
        if not isinstance(
                update, (
                    TransitionValueUpdate,
                    ContextualTransitionValueUpdate)):
            raise TypeError(
                "transition value event has wrong type")
        return self._emit(
            writer, "transition_value_updated",
            turn, query, decision, caused_by,
            update.to_dict(),
            _flow_artifact(decision),
            decision.decision_hash)
