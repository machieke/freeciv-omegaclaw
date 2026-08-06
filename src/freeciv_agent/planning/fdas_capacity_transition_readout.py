"""Protected decision-safe readout for retained replacement capacity.

The readout is deliberately shadow-only.  It makes selection role explicit
and refuses to transport the PR99 selected-candidate model to nonselected
candidates until a separate outcome population has confirmed that use.
"""

from dataclasses import dataclass
import math

from ..events.schema import structural_hash
from ..pressure.scheduler import OperationScore
from ..state.atomspace.model import AtomNamespace, EntityRef
from .fdas import ShadowOperationCandidate
from .fdas_capacity_transition_model import (
    FdasRetainedCapacityTransitionModel,
    FdasRetainedCapacityTransitionPrediction,
)
from .fdas_capacity_transition_queries import (
    FdasRetainedCapacityTransitionQuery,
    RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
    retained_capacity_transition_features,
)


RETAINED_CAPACITY_DECISION_SAFE_READOUT_IDENTITY = (
    "fdas-retained-capacity-decision-safe-readout/1.0")
RETAINED_CAPACITY_CANDIDATE_QUERY_IDENTITY = (
    "fdas-retained-capacity-candidate-query/1.0")
PR100_RETAINED_CAPACITY_CONFIRMATION_HASH = (
    "4f977bc166836202fe70273fbb7ded843f2500bfc39992e22ddd52654264d829")
PR100_RETAINED_CAPACITY_CONFIRMATION_SHA256 = (
    "5587d5a9fd14c87b690a627d56886768b43decee9ca092da8546782c47b8b2a3")

_OPERATION_TYPE = (
    "fdas-shadow:city-replacement-capacity-deficit:city_production")
_DOWNSTREAM_PREFIX = "fdas-replacement-capacity:"
_QUERY_REASON = "insufficient-independent-calibration-evidence"


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError("{} is required".format(name))
    return value


def _finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("{} must be finite".format(name))
    return value


@dataclass(frozen=True)
class FdasRetainedCapacityScalarScore:
    operation_id: str
    admissible: bool
    priority: float

    def __post_init__(self):
        _text(self.operation_id, "retained capacity score operation")
        if not isinstance(self.admissible, bool):
            raise TypeError("retained capacity score admissibility is invalid")
        object.__setattr__(
            self, "priority", _finite(
                self.priority, "retained capacity score priority"))

    @classmethod
    def from_operation_score(cls, value):
        if not isinstance(value, OperationScore):
            raise TypeError("retained capacity readout requires typed scores")
        return cls(value.operation_id, value.admissible, value.priority)

    def to_dict(self):
        return {
            "admissible": self.admissible,
            "operation_id": self.operation_id,
            "priority": self.priority,
        }


class FdasRetainedCapacityCandidateQueryBuilder(object):
    """Build the frozen feature vocabulary for an exact current queue."""

    BUILDER_IDENTITY = RETAINED_CAPACITY_CANDIDATE_QUERY_IDENTITY

    @staticmethod
    def build(candidate, snapshot, revision):
        if not isinstance(candidate, ShadowOperationCandidate):
            raise TypeError("retained capacity query requires a candidate")
        assembly = candidate.production_assembly
        if (assembly is None or assembly.initial_step_index != 1
                or candidate.operation.operation_type != _OPERATION_TYPE
                or assembly.spec != candidate.operation
                or candidate.authority_eligible
                or not candidate.legal_bound
                or candidate.action_key not in snapshot.legal_action_json
                or candidate.action != assembly.queue_action()
                or candidate.blockers != (
                    "delayed-production-completion-unobserved",)):
            raise ValueError(
                "retained capacity candidate is not an exact current queue")
        if (getattr(revision, "snapshot_id", None) != snapshot.snapshot_id
                or not isinstance(
                    getattr(revision, "revision_id", None), str)
                or not revision.revision_id):
            raise ValueError("retained capacity candidate revision is stale")
        intent = assembly.intent
        downstream = intent.downstream_operation_id
        if (not isinstance(downstream, str)
                or not downstream.startswith(_DOWNSTREAM_PREFIX)):
            raise ValueError("retained capacity candidate downstream differs")
        deficit_atom_id = downstream[len(_DOWNSTREAM_PREFIX):]
        deficit = revision.record(deficit_atom_id)
        if (deficit is None
                or deficit.key.namespace != AtomNamespace.DERIVED
                or deficit.key.predicate != (
                    "city-replacement-capacity-deficit")
                or len(deficit.key.arguments) != 2
                or any(not isinstance(value, EntityRef)
                       or value.kind != "city"
                       for value in deficit.key.arguments)):
            raise ValueError("retained capacity candidate deficit differs")
        source_city_id, target_city_id = tuple(
            int(value.entity_id) for value in deficit.key.arguments)
        if source_city_id != intent.city_id:
            raise ValueError("retained capacity candidate source differs")
        features = retained_capacity_transition_features(
            snapshot, source_city_id, target_city_id, intent.target_name,
            int(snapshot.turn), int(intent.completion_deadline_turn))
        identity = structural_hash({
            "candidate_hash": candidate.candidate_hash,
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
        })
        label_id = "retained-capacity-candidate-label-" + identity[:24]
        proposal_id = "retained-capacity-candidate-proposal-" + identity[:24]
        provenance = tuple(sorted((
            FdasRetainedCapacityCandidateQueryBuilder.BUILDER_IDENTITY,
            "candidate-hash:" + candidate.candidate_hash,
            "deficit-atom:" + deficit_atom_id,
            "revision-id:" + revision.revision_id,
            "snapshot-id:" + snapshot.snapshot_id,
        )))
        semantic = {
            "deficit_atom_id": deficit_atom_id,
            "estimate": None,
            "feature_schema": RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
            "features": dict(features),
            "game_id": snapshot.identity.game_id,
            "interval_lower": None,
            "interval_upper": None,
            "label_id": label_id,
            "model_id": None,
            "operation_id": candidate.operation.operation_id,
            "player_id": snapshot.player_id,
            "proposal_event_id": proposal_id,
            "proposed_turn": int(snapshot.turn),
            "provenance_ids": list(provenance),
            "reason": _QUERY_REASON,
            "revision_id": revision.revision_id,
            "schema_version": 1,
            "snapshot_id": snapshot.snapshot_id,
            "status": "abstained",
        }
        result_hash = structural_hash(semantic)
        return FdasRetainedCapacityTransitionQuery(
            1, "retained-capacity-transition-query-" + result_hash[:24],
            snapshot.identity.game_id, snapshot.player_id,
            candidate.operation.operation_id, label_id, proposal_id,
            int(snapshot.turn), snapshot.snapshot_id, revision.revision_id,
            deficit_atom_id, RETAINED_CAPACITY_TRANSITION_FEATURE_SCHEMA,
            features, "abstained", _QUERY_REASON, None, None, None, None,
            provenance, result_hash)


@dataclass(frozen=True)
class FdasRetainedCapacityCandidateValue:
    operation_id: str
    action_key: str
    candidate_hash: str
    selection_role: str
    scalar_rank: int
    scalar_priority: float
    query: FdasRetainedCapacityTransitionQuery
    prediction: FdasRetainedCapacityTransitionPrediction

    def __post_init__(self):
        for value, name in (
                (self.operation_id, "candidate operation"),
                (self.action_key, "candidate action key"),
                (self.candidate_hash, "candidate hash")):
            _text(value, "retained capacity " + name)
        if self.selection_role not in (
                "scalar-selected", "nonselected-unvalidated"):
            raise ValueError("retained capacity selection role differs")
        if (isinstance(self.scalar_rank, bool)
                or not isinstance(self.scalar_rank, int)
                or self.scalar_rank < 1):
            raise ValueError("retained capacity scalar rank differs")
        object.__setattr__(
            self, "scalar_priority", _finite(
                self.scalar_priority, "retained capacity scalar priority"))
        if (not isinstance(
                self.query, FdasRetainedCapacityTransitionQuery)
                or not isinstance(
                    self.prediction,
                    FdasRetainedCapacityTransitionPrediction)
                or self.query.operation_id != self.operation_id
                or self.prediction.query_id != self.query.query_id):
            raise ValueError("retained capacity candidate value binding differs")

    @property
    def numerically_supported(self):
        return bool(
            self.prediction.goal_relief.status == "estimated"
            and self.prediction.product_effect.status == "estimated")

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "candidate_hash": self.candidate_hash,
            "numerically_supported": self.numerically_supported,
            "operation_id": self.operation_id,
            "prediction": self.prediction.to_dict(),
            "query": self.query.to_dict(),
            "scalar_priority": self.scalar_priority,
            "scalar_rank": self.scalar_rank,
            "selection_role": self.selection_role,
        }


@dataclass(frozen=True)
class FdasRetainedCapacityDecisionSafeReadout:
    status: str
    reason: str
    snapshot_id: str
    revision_id: str
    model_result_hash: str
    confirmation_hash: str
    nonselected_outcomes_confirmed: bool
    baseline_operation_id: object
    proposed_operation_id: object
    candidates: tuple
    rejected: tuple
    result_hash: str

    def __post_init__(self):
        if self.status not in ("eligible-shadow", "abstained"):
            raise ValueError("retained capacity readout status differs")
        for value, name in (
                (self.reason, "readout reason"),
                (self.snapshot_id, "readout snapshot"),
                (self.revision_id, "readout revision"),
                (self.model_result_hash, "readout model"),
                (self.confirmation_hash, "readout confirmation"),
                (self.result_hash, "readout hash")):
            _text(value, "retained capacity " + name)
        if self.confirmation_hash != PR100_RETAINED_CAPACITY_CONFIRMATION_HASH:
            raise ValueError("retained capacity confirmation hash differs")
        if not isinstance(self.nonselected_outcomes_confirmed, bool):
            raise TypeError("nonselected outcome confirmation is invalid")
        candidates = tuple(self.candidates)
        rejected = tuple(sorted(set(str(value) for value in self.rejected)))
        if (any(not isinstance(
                value, FdasRetainedCapacityCandidateValue)
                for value in candidates)
                or any(not value for value in rejected)):
            raise TypeError("retained capacity readout diagnostics differ")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "rejected", rejected)
        eligible = self.status == "eligible-shadow"
        if (eligible != (self.proposed_operation_id is not None)
                or (eligible and not self.nonselected_outcomes_confirmed)
                or (eligible and self.baseline_operation_id is None)
                or (eligible
                    and self.proposed_operation_id
                    == self.baseline_operation_id)):
            raise ValueError("retained capacity preference semantics differ")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("retained capacity readout hash differs")

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "baseline_operation_id": self.baseline_operation_id,
            "candidate_surface_changed": False,
            "candidates": [value.to_dict() for value in self.candidates],
            "confirmation_hash": self.confirmation_hash,
            "counterfactual_preference": self.status == "eligible-shadow",
            "identity": RETAINED_CAPACITY_DECISION_SAFE_READOUT_IDENTITY,
            "model_result_hash": self.model_result_hash,
            "nonselected_outcomes_confirmed": (
                self.nonselected_outcomes_confirmed),
            "policy_authority": False,
            "pressure_selection_changed": False,
            "proposed_operation_id": self.proposed_operation_id,
            "readout_authority": False,
            "reason": self.reason,
            "rejected": list(self.rejected),
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "truth_mutated": False,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}


class FdasRetainedCapacityDecisionSafeReadoutEvaluator(object):
    """Compare confirmed intervals while preserving scalar PF authority."""

    def __init__(self, model, *, nonselected_outcomes_confirmed=False,
                 confirmation_hash=PR100_RETAINED_CAPACITY_CONFIRMATION_HASH):
        if not isinstance(model, FdasRetainedCapacityTransitionModel):
            raise TypeError("retained capacity readout requires frozen model")
        if not isinstance(nonselected_outcomes_confirmed, bool):
            raise TypeError("nonselected outcome confirmation is invalid")
        if confirmation_hash != PR100_RETAINED_CAPACITY_CONFIRMATION_HASH:
            raise ValueError("retained capacity readout confirmation differs")
        self.model = model
        self.nonselected_outcomes_confirmed = (
            nonselected_outcomes_confirmed)
        self.confirmation_hash = confirmation_hash

    def _readout(self, status, reason, snapshot, revision, baseline=None,
                 proposed=None, candidates=(), rejected=()):
        semantic = {
            "action_selection_changed": False,
            "baseline_operation_id": baseline,
            "candidate_surface_changed": False,
            "candidates": [value.to_dict() for value in candidates],
            "confirmation_hash": self.confirmation_hash,
            "counterfactual_preference": status == "eligible-shadow",
            "identity": RETAINED_CAPACITY_DECISION_SAFE_READOUT_IDENTITY,
            "model_result_hash": self.model.result_hash,
            "nonselected_outcomes_confirmed": (
                self.nonselected_outcomes_confirmed),
            "policy_authority": False,
            "pressure_selection_changed": False,
            "proposed_operation_id": proposed,
            "readout_authority": False,
            "reason": reason,
            "rejected": sorted(set(str(value) for value in rejected)),
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
            "truth_mutated": False,
        }
        return FdasRetainedCapacityDecisionSafeReadout(
            status, reason, snapshot.snapshot_id, revision.revision_id,
            self.model.result_hash, self.confirmation_hash,
            self.nonselected_outcomes_confirmed, baseline, proposed,
            tuple(candidates), tuple(semantic["rejected"]),
            structural_hash(semantic))

    def evaluate(self, snapshot, revision, candidates, scores,
                 selected_operation_id):
        if (getattr(revision, "snapshot_id", None) != snapshot.snapshot_id
                or not isinstance(
                    getattr(revision, "revision_id", None), str)):
            raise ValueError("retained capacity readout revision is stale")
        candidates = tuple(candidates)
        scores = tuple(
            value if isinstance(value, FdasRetainedCapacityScalarScore)
            else FdasRetainedCapacityScalarScore.from_operation_score(value)
            for value in scores)
        if any(not isinstance(value, ShadowOperationCandidate)
               for value in candidates):
            raise TypeError("retained capacity readout candidates are untyped")
        candidate_ids = tuple(
            value.operation.operation_id for value in candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("retained capacity readout candidates overlap")
        score_by_id = dict((value.operation_id, value) for value in scores)
        if len(score_by_id) != len(scores):
            raise ValueError("retained capacity readout scores overlap")
        retained = tuple(
            value for value in candidates
            if value.operation.operation_type == _OPERATION_TYPE
            and value.operation.operation_id in score_by_id
            and score_by_id[value.operation.operation_id].admissible)
        ranked = tuple(sorted(retained, key=lambda value: (
            -score_by_id[value.operation.operation_id].priority,
            value.operation.operation_id)))
        values = []
        rejected = []
        for rank, candidate in enumerate(ranked, 1):
            try:
                query = FdasRetainedCapacityCandidateQueryBuilder.build(
                    candidate, snapshot, revision)
                prediction = self.model.predict(query)
            except (TypeError, ValueError) as error:
                rejected.append(
                    candidate.operation.operation_id + ":" + str(error))
                continue
            operation_id = candidate.operation.operation_id
            values.append(FdasRetainedCapacityCandidateValue(
                operation_id, candidate.action_key,
                candidate.candidate_hash,
                ("scalar-selected" if operation_id == selected_operation_id
                 else "nonselected-unvalidated"),
                rank, score_by_id[operation_id].priority, query, prediction))
        values = tuple(values)
        baseline = next((
            value for value in values
            if value.operation_id == selected_operation_id), None)
        if baseline is None:
            return self._readout(
                "abstained", "scalar-selected-operation-outside-confirmed-domain",
                snapshot, revision, candidates=values, rejected=rejected)
        if len(values) < 2:
            return self._readout(
                "abstained", "fewer-than-two-current-retained-candidates",
                snapshot, revision, baseline=baseline.operation_id,
                candidates=values, rejected=rejected)
        if not all(value.numerically_supported for value in values):
            return self._readout(
                "abstained", "candidate-transition-estimate-abstained",
                snapshot, revision, baseline=baseline.operation_id,
                candidates=values, rejected=rejected)
        if not self.nonselected_outcomes_confirmed:
            return self._readout(
                "abstained", "nonselected-candidate-outcomes-unconfirmed",
                snapshot, revision, baseline=baseline.operation_id,
                candidates=values, rejected=rejected)
        alternatives = []
        for value in values:
            if value.operation_id == baseline.operation_id:
                continue
            if (value.prediction.goal_relief.interval_lower
                    <= baseline.prediction.goal_relief.interval_upper):
                rejected.append(value.operation_id + ":relief-interval-overlap")
                continue
            if (value.prediction.product_effect.interval_lower
                    < baseline.prediction.product_effect.interval_lower):
                rejected.append(
                    value.operation_id + ":product-lower-bound-inferior")
                continue
            alternatives.append(value)
        if not alternatives:
            return self._readout(
                "abstained", "no-decision-safe-separated-alternative",
                snapshot, revision, baseline=baseline.operation_id,
                candidates=values, rejected=rejected)
        selected = sorted(alternatives, key=lambda value: (
            -value.prediction.goal_relief.interval_lower,
            -value.prediction.goal_relief.estimate,
            -value.prediction.product_effect.interval_lower,
            -value.scalar_priority,
            value.operation_id))[0]
        return self._readout(
            "eligible-shadow", "confirmed-interval-dominance",
            snapshot, revision, baseline=baseline.operation_id,
            proposed=selected.operation_id, candidates=values,
            rejected=rejected)
