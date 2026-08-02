"""Fail-closed conversion from FDAS decision episodes to induction rows."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.induction import (
    InductionEpisode,
    InductionLedger,
    InductionPromotionApproval,
    PatternMiner,
    ReplayValidator,
)
from .fdas_episodes import DecisionEpisodeStore, INDUCTION_FEATURE_SCHEMA
from .fdas_induction_labels import (
    EpisodeInductionOutcomeLabelStore,
    delayed_outcome_episode_eligible,
)


IMMEDIATE_GOAL_RELIEF_TARGET = "immediate-goal-relief/1.0"


def combine_episode_stores(stores, persistence_identity):
    """Combine verified source stores without weakening their identities."""
    stores = tuple(stores)
    if not stores:
        raise ValueError("episode cohort requires at least one source store")
    if not isinstance(persistence_identity, str) or not persistence_identity:
        raise ValueError("episode cohort persistence identity is required")
    if any(not isinstance(value, DecisionEpisodeStore) for value in stores):
        raise TypeError("episode cohort accepts DecisionEpisodeStore values")
    if any(value.quarantined for value in stores):
        raise ValueError("quarantined source store cannot enter episode cohort")
    source_identities = [value.persistence_identity for value in stores]
    source_digests = [value.store_digest for value in stores]
    if len(source_identities) != len(set(source_identities)):
        raise ValueError("episode cohort source identities overlap")
    if len(source_digests) != len(set(source_digests)):
        raise ValueError("episode cohort source artifacts overlap")
    episodes = tuple(
        episode for store in stores for episode in store.episodes())
    episode_ids = [value.episode_id for value in episodes]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("episode cohort IDs overlap")
    return DecisionEpisodeStore(persistence_identity, episodes)


@dataclass(frozen=True)
class EpisodeInductionSpec:
    """Explicit, evidence-linked feature declaration for one episode."""

    episode_id: str
    context_keys: tuple
    feature_context_keys: tuple
    linked_features: tuple = ()
    outcome_target: str = IMMEDIATE_GOAL_RELIEF_TARGET

    def __post_init__(self):
        if not isinstance(self.episode_id, str) or not self.episode_id:
            raise ValueError("episode induction spec requires an episode ID")
        if not isinstance(self.outcome_target, str) or not self.outcome_target:
            raise ValueError("episode induction spec requires outcome target")
        for name in ("context_keys", "feature_context_keys"):
            values = tuple(sorted(str(value) for value in getattr(self, name)))
            if any(not value for value in values) or len(values) != len(
                    set(values)):
                raise ValueError(
                    "episode induction {} must be unique strings".format(name))
            object.__setattr__(self, name, values)
        linked = tuple(sorted(
            (str(feature_id), str(evidence_id))
            for feature_id, evidence_id in self.linked_features))
        if any(not feature_id or not evidence_id
               for feature_id, evidence_id in linked):
            raise ValueError("linked induction features must be non-empty")
        feature_ids = [feature_id for feature_id, _evidence_id in linked]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("linked induction feature IDs must be unique")
        if not self.feature_context_keys and not linked:
            raise ValueError("episode induction requires at least one feature")
        object.__setattr__(self, "linked_features", linked)

    def to_dict(self):
        return {
            "context_keys": list(self.context_keys),
            "episode_id": self.episode_id,
            "feature_context_keys": list(self.feature_context_keys),
            "linked_features": [
                {"evidence_id": evidence_id, "feature_id": feature_id}
                for feature_id, evidence_id in self.linked_features
            ],
            "outcome_target": self.outcome_target,
        }


@dataclass(frozen=True)
class EpisodeInductionResult:
    episode_id: str
    accepted: bool
    reason: str
    induction_episode: object
    truth_mutated: bool
    policy_authority: bool
    result_hash: str

    def to_dict(self):
        return {
            "accepted": bool(self.accepted),
            "episode_id": self.episode_id,
            "induction_episode": (
                None if self.induction_episode is None
                else self.induction_episode.to_dict()),
            "policy_authority": bool(self.policy_authority),
            "reason": self.reason,
            "result_hash": self.result_hash,
            "truth_mutated": bool(self.truth_mutated),
        }


class FdasEpisodeInductionAdapter(object):
    """Encode attributable FDAS outcomes without granting rule authority."""

    ADAPTER_IDENTITY = "fdas-episode-induction/1.0"
    _ELIGIBLE = frozenset((
        "goal-relief-observed",
        "effect-without-goal-relief",
        "no-effect-observed",
    ))

    def __init__(self, episode_store, outcome_label_store=None):
        if not isinstance(episode_store, DecisionEpisodeStore):
            raise TypeError("episode induction requires DecisionEpisodeStore")
        if (outcome_label_store is not None
                and not isinstance(
                    outcome_label_store, EpisodeInductionOutcomeLabelStore)):
            raise TypeError(
                "episode induction labels require typed outcome-label store")
        self.episode_store = episode_store
        self.outcome_label_store = outcome_label_store

    @staticmethod
    def _result(episode_id, accepted, reason, induction_episode=None):
        semantic = {
            "accepted": bool(accepted),
            "adapter_identity": FdasEpisodeInductionAdapter.ADAPTER_IDENTITY,
            "episode_id": str(episode_id),
            "induction_episode": (
                None if induction_episode is None
                else induction_episode.to_dict()),
            "policy_authority": False,
            "reason": str(reason),
            "truth_mutated": False,
        }
        return EpisodeInductionResult(
            str(episode_id), bool(accepted), str(reason), induction_episode,
            False, False, structural_hash(semantic))

    @staticmethod
    def _linked_evidence(episode):
        return frozenset(
            episode.source_atom_ids
            + episode.source_support_ids
            + episode.grounding_result_ids
            + episode.prediction_ids
            + episode.resource_claim_ids
            + episode.provenance_ids
            + tuple(value for value in (
                episode.execution_event_id,
                episode.before_revision_id,
                episode.after_revision_id,
            ) if value is not None))

    def encode(self, spec):
        if self.episode_store.quarantined:
            raise ValueError("quarantined episode store cannot feed induction")
        if not isinstance(spec, EpisodeInductionSpec):
            raise TypeError("episode induction requires EpisodeInductionSpec")
        episode = self.episode_store.get(spec.episode_id)
        if episode is None:
            raise KeyError("unknown decision episode")
        label = None
        if spec.outcome_target == IMMEDIATE_GOAL_RELIEF_TARGET:
            if episode.outcome_status not in self._ELIGIBLE:
                return self._result(
                    episode.episode_id, False,
                    "episode-outcome-not-attributable-for-induction")
            outcome = episode.outcome_status == "goal-relief-observed"
            accepted_reason = (
                "attributable-episode-encoded-for-quarantined-induction")
        else:
            if not delayed_outcome_episode_eligible(
                    episode, spec.outcome_target):
                return self._result(
                    episode.episode_id, False,
                    "episode-not-eligible-for-outcome-target")
            if self.outcome_label_store is None:
                return self._result(
                    episode.episode_id, False,
                    "episode-outcome-label-store-not-configured")
            if self.outcome_label_store.quarantined:
                raise ValueError(
                    "quarantined outcome-label store cannot feed induction")
            label = self.outcome_label_store.for_episode(
                episode.episode_id, spec.outcome_target)
            if label is None:
                return self._result(
                    episode.episode_id, False,
                    "episode-outcome-label-missing")
            if label.episode_digest != episode.immutable_digest:
                raise ValueError("episode outcome-label digest mismatch")
            if label.status != "observed":
                return self._result(
                    episode.episode_id, False,
                    "episode-outcome-label-not-observed:{}".format(
                        label.status))
            outcome = label.outcome
            accepted_reason = (
                "revision-bound-delayed-outcome-encoded-for-"
                "quarantined-induction")
        context = dict(episode.context_signature)
        requested = set(spec.context_keys + spec.feature_context_keys)
        missing = sorted(requested.difference(context))
        if missing:
            return self._result(
                episode.episode_id, False,
                "episode-context-keys-missing:{}".format(",".join(missing)))
        linked_evidence = self._linked_evidence(episode)
        unlinked = sorted(
            evidence_id for _feature_id, evidence_id in spec.linked_features
            if evidence_id not in linked_evidence)
        if unlinked:
            return self._result(
                episode.episode_id, False,
                "episode-feature-evidence-unlinked:{}".format(
                    ",".join(unlinked)))
        induction_context = tuple(
            (key, context[key]) for key in spec.context_keys)
        if spec.outcome_target != IMMEDIATE_GOAL_RELIEF_TARGET:
            induction_context += (("outcome_target", spec.outcome_target),)
            induction_context = tuple(sorted(induction_context))
        features = tuple(sorted(
            tuple("context:{}={}".format(key, context[key])
                  for key in spec.feature_context_keys)
            + tuple(feature_id for feature_id, _evidence_id
                    in spec.linked_features)))
        provenance = tuple(sorted(set(
            ("fdas-episode:" + episode.immutable_digest,)
            + (() if episode.execution_event_id is None else (
                "execution-event:" + episode.execution_event_id,))
            + (() if label is None else (
                "outcome-label:" + label.state_digest,)))))
        induction_episode = InductionEpisode(
            episode.episode_id,
            induction_context,
            features,
            outcome,
            provenance,
        )
        return self._result(
            episode.episode_id, True, accepted_reason, induction_episode)


@dataclass(frozen=True)
class EpisodeInductionShadowResult:
    """One idempotent, non-authorizing evaluation of durable episodes."""

    encoding_results: tuple
    proposals: tuple
    newly_quarantined_proposal_ids: tuple
    duplicate_proposal_ids: tuple
    mining_reason: str
    ledger_hash: str
    truth_mutated: bool
    policy_authority: bool
    result_hash: str

    def to_dict(self):
        return {
            "duplicate_proposal_ids": list(self.duplicate_proposal_ids),
            "encoding_results": [
                value.to_dict() for value in self.encoding_results],
            "ledger_hash": self.ledger_hash,
            "mining_reason": self.mining_reason,
            "newly_quarantined_proposal_ids": list(
                self.newly_quarantined_proposal_ids),
            "policy_authority": bool(self.policy_authority),
            "proposals": [value.to_dict() for value in self.proposals],
            "result_hash": self.result_hash,
            "truth_mutated": bool(self.truth_mutated),
        }


class FdasEpisodeInductionShadow(object):
    """Mine only quarantined rules from live durable episode evidence."""

    SHADOW_IDENTITY = "fdas-episode-induction-shadow/1.0"

    def __init__(self, episode_store, ledger, miner=None):
        if not isinstance(episode_store, DecisionEpisodeStore):
            raise TypeError("episode induction shadow requires episode store")
        if not isinstance(ledger, InductionLedger):
            raise TypeError("episode induction shadow requires induction ledger")
        if miner is not None and not isinstance(miner, PatternMiner):
            raise TypeError("episode induction shadow requires PatternMiner")
        self.episode_store = episode_store
        self.adapter = FdasEpisodeInductionAdapter(episode_store)
        self.ledger = ledger
        self.miner = miner or PatternMiner(
            minimum_support=4,
            maximum_antecedents=2,
            minimum_residual=0.05,
            maximum_candidates=32)

    @staticmethod
    def _spec(episode):
        context = dict(episode.context_signature)
        if context.get("induction_feature_schema") == INDUCTION_FEATURE_SCHEMA:
            return EpisodeInductionSpec(
                episode.episode_id,
                ("induction_feature_schema", "operation_type"),
                (
                    "actor_moves_band",
                    "actor_unit_type",
                    "actor_veteran_band",
                    "city_disorder",
                    "city_size_band",
                    "other_own_units_at_target_band",
                    "own_units_at_target_band",
                ))
        return EpisodeInductionSpec(
            episode.episode_id,
            ("operation_type",),
            ("actor_tile_before", "target_tile"))

    def evaluate(self):
        if self.episode_store.quarantined:
            raise ValueError("quarantined episode store cannot feed induction")
        if self.ledger.promoted_rules():
            raise ValueError(
                "shadow induction ledger cannot contain promoted rules")
        encodings = tuple(
            self.adapter.encode(self._spec(episode))
            for episode in self.episode_store.episodes())
        rows = tuple(
            value.induction_episode for value in encodings
            if value.accepted)
        proposals = ()
        if len(rows) < self.miner.minimum_support:
            mining_reason = "insufficient-attributable-episode-support"
        else:
            try:
                proposals = self.miner.mine(
                    rows, "defense-operation-relieves-goal")
                mining_reason = (
                    "quarantined-proposals-mined"
                    if proposals else
                    "no-pattern-cleared-residual-gate")
            except ValueError as error:
                if "not independent" not in str(error):
                    raise
                proposals = ()
                mining_reason = "training-provenance-not-independent"
        new_ids = []
        duplicate_ids = []
        for proposal in proposals:
            target = new_ids if self.ledger.propose(proposal) else duplicate_ids
            target.append(proposal.proposal_id)
        if self.ledger.promoted_rules():
            raise RuntimeError("live shadow induction escaped quarantine")
        semantic = {
            "adapter_identity": self.adapter.ADAPTER_IDENTITY,
            "duplicate_proposal_ids": sorted(duplicate_ids),
            "encoding_results": [value.to_dict() for value in encodings],
            "ledger_hash": self.ledger.state_hash,
            "mining_reason": mining_reason,
            "newly_quarantined_proposal_ids": sorted(new_ids),
            "policy_authority": False,
            "proposals": [value.to_dict() for value in proposals],
            "shadow_identity": self.SHADOW_IDENTITY,
            "truth_mutated": False,
        }
        return EpisodeInductionShadowResult(
            encodings,
            proposals,
            tuple(sorted(new_ids)),
            tuple(sorted(duplicate_ids)),
            mining_reason,
            self.ledger.state_hash,
            False,
            False,
            structural_hash(semantic))


@dataclass(frozen=True)
class EpisodeInductionHeldoutResult:
    """Deterministic train/holdout lifecycle with no readout authority."""

    training_encoding_results: tuple
    holdout_encoding_results: tuple
    proposals: tuple
    validations: tuple
    approvals: tuple
    newly_quarantined_proposal_ids: tuple
    newly_validated_ids: tuple
    duplicate_proposal_ids: tuple
    duplicate_validation_ids: tuple
    promoted_rule_ids: tuple
    demoted_rule_ids: tuple
    mining_reason: str
    ledger_hash: str
    truth_mutated: bool
    policy_authority: bool
    readout_authority: bool
    result_hash: str

    def to_dict(self):
        return {
            "approvals": [value.to_dict() for value in self.approvals],
            "demoted_rule_ids": list(self.demoted_rule_ids),
            "duplicate_proposal_ids": list(self.duplicate_proposal_ids),
            "duplicate_validation_ids": list(self.duplicate_validation_ids),
            "holdout_encoding_results": [
                value.to_dict() for value in self.holdout_encoding_results],
            "ledger_hash": self.ledger_hash,
            "mining_reason": self.mining_reason,
            "newly_quarantined_proposal_ids": list(
                self.newly_quarantined_proposal_ids),
            "newly_validated_ids": list(self.newly_validated_ids),
            "policy_authority": bool(self.policy_authority),
            "promoted_rule_ids": list(self.promoted_rule_ids),
            "proposals": [value.to_dict() for value in self.proposals],
            "readout_authority": bool(self.readout_authority),
            "result_hash": self.result_hash,
            "training_encoding_results": [
                value.to_dict() for value in self.training_encoding_results],
            "truth_mutated": bool(self.truth_mutated),
            "validations": [value.to_dict() for value in self.validations],
        }


class FdasEpisodeInductionHeldoutGate(object):
    """Validate quarantined episode rules on an independent episode store."""

    GATE_IDENTITY = "fdas-episode-induction-heldout/1.0"

    def __init__(
            self, training_store, holdout_store, ledger, miner=None,
            validator=None, outcome_target=IMMEDIATE_GOAL_RELIEF_TARGET,
            training_outcome_label_store=None,
            holdout_outcome_label_store=None):
        for value, name in (
                (training_store, "training"), (holdout_store, "holdout")):
            if not isinstance(value, DecisionEpisodeStore):
                raise TypeError(
                    "{} induction partition requires episode store".format(
                        name))
            if value.quarantined:
                raise ValueError(
                    "quarantined {} episode store cannot feed induction".format(
                        name))
        if not isinstance(ledger, InductionLedger):
            raise TypeError("held-out induction requires induction ledger")
        if miner is not None and not isinstance(miner, PatternMiner):
            raise TypeError("held-out induction requires PatternMiner")
        if validator is not None and not isinstance(validator, ReplayValidator):
            raise TypeError("held-out induction requires ReplayValidator")
        if (training_store.persistence_identity
                == holdout_store.persistence_identity):
            raise ValueError("training and holdout store identities overlap")
        if training_store.store_digest == holdout_store.store_digest:
            raise ValueError("training and holdout store artifacts overlap")
        if not isinstance(outcome_target, str) or not outcome_target:
            raise ValueError("held-out induction requires outcome target")
        if outcome_target != IMMEDIATE_GOAL_RELIEF_TARGET:
            for value, name in (
                    (training_outcome_label_store, "training"),
                    (holdout_outcome_label_store, "holdout")):
                if not isinstance(value, EpisodeInductionOutcomeLabelStore):
                    raise TypeError(
                        "{} delayed induction requires outcome-label store".format(
                            name))
                if value.quarantined:
                    raise ValueError(
                        "quarantined {} outcome-label store".format(name))
            if (training_outcome_label_store.persistence_identity
                    == holdout_outcome_label_store.persistence_identity
                    or training_outcome_label_store.store_digest
                    == holdout_outcome_label_store.store_digest):
                raise ValueError(
                    "training and holdout outcome-label artifacts overlap")
        self.training_store = training_store
        self.holdout_store = holdout_store
        self.outcome_target = outcome_target
        self.training_outcome_label_store = training_outcome_label_store
        self.holdout_outcome_label_store = holdout_outcome_label_store
        self.training_adapter = FdasEpisodeInductionAdapter(
            training_store, training_outcome_label_store)
        self.holdout_adapter = FdasEpisodeInductionAdapter(
            holdout_store, holdout_outcome_label_store)
        self.ledger = ledger
        self.miner = miner or PatternMiner(
            minimum_support=4,
            maximum_antecedents=2,
            minimum_residual=0.05,
            maximum_candidates=32)
        self.validator = validator or ReplayValidator()

    def _spec(self, episode):
        value = FdasEpisodeInductionShadow._spec(episode)
        return EpisodeInductionSpec(
            value.episode_id,
            value.context_keys,
            value.feature_context_keys,
            value.linked_features,
            self.outcome_target)

    def _artifact_hash(self, partition):
        episode_store = (
            self.training_store if partition == "training"
            else self.holdout_store)
        label_store = (
            self.training_outcome_label_store if partition == "training"
            else self.holdout_outcome_label_store)
        if label_store is None:
            return episode_store.store_digest
        return structural_hash({
            "episode_store_digest": episode_store.store_digest,
            "outcome_label_store_digest": label_store.store_digest,
            "outcome_target": self.outcome_target,
        })

    @staticmethod
    def _assert_partition_independence(training_rows, holdout_rows):
        training_ids = {value.episode_id for value in training_rows}
        holdout_ids = {value.episode_id for value in holdout_rows}
        if training_ids & holdout_ids:
            raise ValueError("training/holdout episode overlap")
        seen = set()
        for partition, rows in (
                ("training", training_rows), ("holdout", holdout_rows)):
            for row in rows:
                overlap = seen & set(row.provenance_ids)
                if overlap:
                    raise ValueError(
                        "{} induction provenance is not independent: {}".format(
                            partition, sorted(overlap)))
                seen.update(row.provenance_ids)

    def evaluate(self):
        training_encodings = tuple(
            self.training_adapter.encode(self._spec(episode))
            for episode in self.training_store.episodes())
        holdout_encodings = tuple(
            self.holdout_adapter.encode(self._spec(episode))
            for episode in self.holdout_store.episodes())
        training_rows = tuple(
            value.induction_episode for value in training_encodings
            if value.accepted)
        holdout_rows = tuple(
            value.induction_episode for value in holdout_encodings
            if value.accepted)
        self._assert_partition_independence(training_rows, holdout_rows)
        if len(training_rows) < self.miner.minimum_support:
            proposals = ()
            mining_reason = "insufficient-attributable-training-support"
        else:
            proposals = self.miner.mine(
                training_rows,
                "defense-operation-relieves-goal"
                if self.outcome_target == IMMEDIATE_GOAL_RELIEF_TARGET
                else self.outcome_target)
            mining_reason = (
                "heldout-candidates-mined" if proposals
                else "no-pattern-cleared-residual-gate")
        new_proposals = []
        duplicate_proposals = []
        validations = []
        approvals = []
        new_validations = []
        duplicate_validations = []
        promoted = []
        demoted = []
        for proposal in proposals:
            target = (
                new_proposals
                if self.ledger.propose(proposal) else duplicate_proposals)
            target.append(proposal.proposal_id)
            validation = self.validator.validate(proposal, holdout_rows)
            approval = (
                InductionPromotionApproval.issue(
                    proposal, validation,
                    self._artifact_hash("training"),
                    self._artifact_hash("holdout"))
                if validation.verdict == "promoted" else None)
            inserted = self.ledger.record_validation(
                validation, approval=approval)
            validations.append(validation)
            if approval is not None:
                approvals.append(approval)
            target = new_validations if inserted else duplicate_validations
            target.append(validation.validation_id)
            target = promoted if validation.verdict == "promoted" else demoted
            target.append(proposal.proposal_id)
        semantic = {
            "approvals": [value.to_dict() for value in approvals],
            "demoted_rule_ids": sorted(demoted),
            "duplicate_proposal_ids": sorted(duplicate_proposals),
            "duplicate_validation_ids": sorted(duplicate_validations),
            "gate_identity": self.GATE_IDENTITY,
            "holdout_encoding_results": [
                value.to_dict() for value in holdout_encodings],
            "holdout_store_digest": self.holdout_store.store_digest,
            "ledger_hash": self.ledger.state_hash,
            "mining_reason": mining_reason,
            "newly_quarantined_proposal_ids": sorted(new_proposals),
            "newly_validated_ids": sorted(new_validations),
            "outcome_target": self.outcome_target,
            "policy_authority": False,
            "promoted_rule_ids": sorted(promoted),
            "proposals": [value.to_dict() for value in proposals],
            "readout_authority": False,
            "training_encoding_results": [
                value.to_dict() for value in training_encodings],
            "training_store_digest": self.training_store.store_digest,
            "truth_mutated": False,
            "validations": [value.to_dict() for value in validations],
        }
        return EpisodeInductionHeldoutResult(
            training_encodings,
            holdout_encodings,
            proposals,
            tuple(validations),
            tuple(approvals),
            tuple(sorted(new_proposals)),
            tuple(sorted(new_validations)),
            tuple(sorted(duplicate_proposals)),
            tuple(sorted(duplicate_validations)),
            tuple(sorted(promoted)),
            tuple(sorted(demoted)),
            mining_reason,
            self.ledger.state_hash,
            False,
            False,
            False,
            structural_hash(semantic))
