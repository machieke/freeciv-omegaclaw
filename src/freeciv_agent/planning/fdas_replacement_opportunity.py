"""Revision-bound why-not funnel for coordinated defender replacement."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from ..state.atomspace import AtomNamespace
from .fdas_replacement_readout import FdasCoordinatedReplacementReadout


REPLACEMENT_OPPORTUNITY_FUNNEL_IDENTITY = (
    "fdas-coordinated-replacement-opportunity-funnel/1.0")
REPLACEMENT_OPPORTUNITY_BLOCKER_TAXONOMY = (
    "coordinated-replacement-opportunity-blockers/1.0")

_STAGES = frozenset((
    "grounded-pair-available",
    "no-deficit-target-city",
    "no-critical-source-garrison",
    "no-safe-replacement-relation",
    "no-reinforcement-route",
    "no-structural-source-target-join",
    "structural-join-not-current-candidate",
    "no-protected-direct-control",
    "current-candidate-not-grounded",
))


@dataclass(frozen=True)
class FdasReplacementOpportunityFunnel:
    snapshot_id: str
    revision_id: str
    deficit_target_city_count: int
    critical_source_garrison_count: int
    safe_replacement_relation_count: int
    reinforcement_route_count: int
    structural_source_target_join_count: int
    current_replacement_candidate_count: int
    protected_direct_control_count: int
    grounded_pair_count: int
    readout_rejection_count: int
    blocker_stage: str
    result_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.revision_id, "revision ID"),
                (self.blocker_stage, "blocker stage"),
                (self.result_hash, "result hash")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "replacement opportunity {} is required".format(name))
        for name in (
                "deficit_target_city_count",
                "critical_source_garrison_count",
                "safe_replacement_relation_count",
                "reinforcement_route_count",
                "structural_source_target_join_count",
                "current_replacement_candidate_count",
                "protected_direct_control_count",
                "grounded_pair_count",
                "readout_rejection_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    "replacement opportunity {} is invalid".format(name))
        if self.blocker_stage not in _STAGES:
            raise ValueError("replacement opportunity blocker stage differs")
        expected_stage = self._stage_from_counts()
        if self.blocker_stage != expected_stage:
            raise ValueError("replacement opportunity first blocker differs")
        if self.result_hash != structural_hash(self._semantic()):
            raise ValueError("replacement opportunity funnel hash differs")

    def _stage_from_counts(self):
        if self.grounded_pair_count:
            return "grounded-pair-available"
        if not self.deficit_target_city_count:
            return "no-deficit-target-city"
        if not self.critical_source_garrison_count:
            return "no-critical-source-garrison"
        if not self.safe_replacement_relation_count:
            return "no-safe-replacement-relation"
        if not self.reinforcement_route_count:
            return "no-reinforcement-route"
        if not self.structural_source_target_join_count:
            return "no-structural-source-target-join"
        if not self.current_replacement_candidate_count:
            return "structural-join-not-current-candidate"
        if not self.protected_direct_control_count:
            return "no-protected-direct-control"
        return "current-candidate-not-grounded"

    def _semantic(self):
        return {
            "action_selection_changed": False,
            "blocker_stage": self.blocker_stage,
            "blocker_taxonomy": REPLACEMENT_OPPORTUNITY_BLOCKER_TAXONOMY,
            "critical_source_garrison_count": (
                self.critical_source_garrison_count),
            "current_replacement_candidate_count": (
                self.current_replacement_candidate_count),
            "deficit_target_city_count": self.deficit_target_city_count,
            "grounded_pair_count": self.grounded_pair_count,
            "identity": REPLACEMENT_OPPORTUNITY_FUNNEL_IDENTITY,
            "policy_authority": False,
            "protected_direct_control_count": (
                self.protected_direct_control_count),
            "readout_authority": False,
            "readout_rejection_count": self.readout_rejection_count,
            "reinforcement_route_count": self.reinforcement_route_count,
            "revision_id": self.revision_id,
            "safe_replacement_relation_count": (
                self.safe_replacement_relation_count),
            "snapshot_id": self.snapshot_id,
            "structural_source_target_join_count": (
                self.structural_source_target_join_count),
            "transition_value_estimated": False,
            "truth_mutated": False,
        }

    def to_dict(self):
        return {**self._semantic(), "result_hash": self.result_hash}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise TypeError("replacement opportunity funnel must be an object")
        expected = {
            "action_selection_changed", "blocker_stage", "blocker_taxonomy",
            "critical_source_garrison_count",
            "current_replacement_candidate_count",
            "deficit_target_city_count", "grounded_pair_count", "identity",
            "policy_authority", "protected_direct_control_count",
            "readout_authority", "readout_rejection_count",
            "reinforcement_route_count", "result_hash", "revision_id",
            "safe_replacement_relation_count", "snapshot_id",
            "structural_source_target_join_count",
            "transition_value_estimated", "truth_mutated",
        }
        if set(value) != expected:
            raise ValueError("replacement opportunity funnel keys differ")
        if (value["identity"] != REPLACEMENT_OPPORTUNITY_FUNNEL_IDENTITY
                or value["blocker_taxonomy"]
                != REPLACEMENT_OPPORTUNITY_BLOCKER_TAXONOMY
                or any(value[name] is not False for name in (
                    "action_selection_changed", "policy_authority",
                    "readout_authority", "transition_value_estimated",
                    "truth_mutated"))):
            raise ValueError("replacement opportunity funnel semantics differ")
        return cls(
            value["snapshot_id"], value["revision_id"],
            value["deficit_target_city_count"],
            value["critical_source_garrison_count"],
            value["safe_replacement_relation_count"],
            value["reinforcement_route_count"],
            value["structural_source_target_join_count"],
            value["current_replacement_candidate_count"],
            value["protected_direct_control_count"],
            value["grounded_pair_count"], value["readout_rejection_count"],
            value["blocker_stage"], value["result_hash"])


class FdasReplacementOpportunityFunnelEvaluator:
    """Explain the first exact stage that prevents a grounded safe chain."""

    @staticmethod
    def _relations(revision, predicate, arity):
        rows = set()
        for record in revision.records:
            if (record.key.namespace != AtomNamespace.DERIVED
                    or record.key.predicate != predicate
                    or len(record.key.arguments) != arity):
                continue
            rows.add(tuple(record.key.arguments))
        return rows

    @staticmethod
    def _stage(deficits, critical, safe, routes, joins, readout):
        if readout.pairs:
            return "grounded-pair-available"
        if not deficits:
            return "no-deficit-target-city"
        if not critical:
            return "no-critical-source-garrison"
        if not safe:
            return "no-safe-replacement-relation"
        if not routes:
            return "no-reinforcement-route"
        if not joins:
            return "no-structural-source-target-join"
        if not readout.replacement_candidate_count:
            return "structural-join-not-current-candidate"
        if not readout.direct_candidate_count:
            return "no-protected-direct-control"
        return "current-candidate-not-grounded"

    def evaluate(self, revision, readout):
        if not isinstance(readout, FdasCoordinatedReplacementReadout):
            raise TypeError(
                "replacement opportunity funnel requires typed readout")
        if (revision is None
                or revision.snapshot_id != readout.snapshot_id
                or revision.revision_id != readout.revision_id):
            raise ValueError(
                "replacement opportunity funnel requires current revision")
        deficits = self._relations(
            revision, "city-garrison-deficit", 2)
        critical = self._relations(
            revision, "unit-critical-garrison", 2)
        safe = self._relations(
            revision, "unit-coordinated-replacement-for", 3)
        routes = self._relations(
            revision, "unit-reinforcement-route", 2)
        deficit_cities = frozenset(value[0] for value in deficits)
        route_pairs = frozenset((value[0], value[1]) for value in routes)
        joins = frozenset(
            (replacement, protected, source, target)
            for replacement, protected, source in safe
            for route_actor, target in route_pairs
            if (protected == route_actor
                and target in deficit_cities
                and source != target))
        stage = self._stage(
            deficits, critical, safe, routes, joins, readout)
        semantic = {
            "action_selection_changed": False,
            "blocker_stage": stage,
            "blocker_taxonomy": REPLACEMENT_OPPORTUNITY_BLOCKER_TAXONOMY,
            "critical_source_garrison_count": len(critical),
            "current_replacement_candidate_count": (
                readout.replacement_candidate_count),
            "deficit_target_city_count": len(deficits),
            "grounded_pair_count": len(readout.pairs),
            "identity": REPLACEMENT_OPPORTUNITY_FUNNEL_IDENTITY,
            "policy_authority": False,
            "protected_direct_control_count": readout.direct_candidate_count,
            "readout_authority": False,
            "readout_rejection_count": len(readout.rejected),
            "reinforcement_route_count": len(routes),
            "revision_id": revision.revision_id,
            "safe_replacement_relation_count": len(safe),
            "snapshot_id": revision.snapshot_id,
            "structural_source_target_join_count": len(joins),
            "transition_value_estimated": False,
            "truth_mutated": False,
        }
        return FdasReplacementOpportunityFunnel(
            revision.snapshot_id,
            revision.revision_id,
            len(deficits),
            len(critical),
            len(safe),
            len(routes),
            len(joins),
            readout.replacement_candidate_count,
            readout.direct_candidate_count,
            len(readout.pairs),
            len(readout.rejected),
            stage,
            structural_hash(semantic),
        )
