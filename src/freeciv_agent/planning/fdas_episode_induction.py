"""Fail-closed conversion from FDAS decision episodes to induction rows."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from ..pressure.induction import InductionEpisode
from .fdas_episodes import DecisionEpisodeStore


@dataclass(frozen=True)
class EpisodeInductionSpec:
    """Explicit, evidence-linked feature declaration for one episode."""

    episode_id: str
    context_keys: tuple
    feature_context_keys: tuple
    linked_features: tuple = ()

    def __post_init__(self):
        if not isinstance(self.episode_id, str) or not self.episode_id:
            raise ValueError("episode induction spec requires an episode ID")
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

    def __init__(self, episode_store):
        if not isinstance(episode_store, DecisionEpisodeStore):
            raise TypeError("episode induction requires DecisionEpisodeStore")
        self.episode_store = episode_store

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
        if episode.outcome_status not in self._ELIGIBLE:
            return self._result(
                episode.episode_id, False,
                "episode-outcome-not-attributable-for-induction")
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
        features = tuple(sorted(
            tuple("context:{}={}".format(key, context[key])
                  for key in spec.feature_context_keys)
            + tuple(feature_id for feature_id, _evidence_id
                    in spec.linked_features)))
        provenance = tuple(sorted(set(
            ("fdas-episode:" + episode.immutable_digest,)
            + (() if episode.execution_event_id is None else (
                "execution-event:" + episode.execution_event_id,)))))
        induction_episode = InductionEpisode(
            episode.episode_id,
            induction_context,
            features,
            episode.outcome_status == "goal-relief-observed",
            provenance,
        )
        return self._result(
            episode.episode_id, True,
            "attributable-episode-encoded-for-quarantined-induction",
            induction_episode)
