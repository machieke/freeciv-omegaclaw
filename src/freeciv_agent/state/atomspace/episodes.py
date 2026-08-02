"""Materialized FDAS view of durable compact decision episodes."""

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
from .operations import operation_predicate_registry
from .predicates import PredicateSpec
from .scopes import ScopeSpec, snapshot_scopes


_STRUCTURAL = {"structural": True}
_STRUCTURAL_HASH = structural_hash(_STRUCTURAL)


def _spec(predicate, arguments):
    return PredicateSpec(
        predicate,
        len(arguments),
        tuple(tuple(value) for value in arguments),
        frozenset((AtomNamespace.EPISODE,)),
        "structural",
        frozenset(("episode",)),
        "explicit-witness",
        "parent-summary",
        "1.0",
    )


def episode_predicate_registry():
    return operation_predicate_registry().extended((
        _spec("episode-operation", (("episode",), ("operation",))),
        _spec("episode-action", (("episode",), ("action",))),
        _spec("episode-before-revision", (("episode",), ("revision",))),
        _spec("episode-after-revision", (("episode",), ("revision",))),
        _spec("episode-outcome-status", (
            ("episode",), ("episode-outcome",))),
        _spec("episode-context", (("episode",), ("context-signature",))),
        _spec("episode-source-atom", (("episode",), ("atom",))),
        _spec("episode-source-support", (("episode",), ("support",))),
        _spec("episode-grounding-result", (
            ("episode",), ("grounding-result",))),
        _spec("episode-prediction", (("episode",), ("prediction",))),
        _spec("episode-resource-claim", (
            ("episode",), ("resource-claim",))),
        _spec("episode-validation", (
            ("episode",), ("validation-result",))),
        _spec("episode-execution-event", (("episode",), ("event",))),
        _spec("episode-attributed-effect", (("episode",), ("effect",))),
        _spec("episode-goal-relief", (("episode",), ("goal",))),
    ))


class EpisodeProjector(object):
    projector_id = "fdas-episode-projector"
    version = "1.0"
    incremental_dependency_roots = frozenset(("player_id",))
    incremental_dependency_kinds = frozenset(("episode-revision",))

    def __init__(self, episodes_source):
        self.episodes_source = episodes_source
        self.predicate_registry = episode_predicate_registry()

    def _episodes(self):
        from ...planning.fdas_episodes import DecisionEpisode, DecisionEpisodeStore

        source = self.episodes_source
        if callable(source):
            source = source()
        if isinstance(source, DecisionEpisodeStore):
            if source.quarantined:
                raise ValueError("quarantined episode store cannot project")
            source = source.episodes()
        episodes = tuple(source)
        if any(not isinstance(value, DecisionEpisode) for value in episodes):
            raise TypeError("episode projection requires DecisionEpisode values")
        ids = [value.episode_id for value in episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("episode projection IDs must be unique")
        return tuple(sorted(episodes, key=lambda value: value.episode_id))

    def scopes(self, snapshot):
        world, empire = snapshot_scopes(snapshot)
        scopes = [world, empire]
        prefix = empire.scope_id.rsplit(":empire", 1)[0]
        predicates = tuple(sorted(
            value for value in self.predicate_registry.predicates
            if value.startswith("episode-")))
        episodes = self._episodes()
        if any(
                episode.game_id != snapshot.identity.game_id
                or episode.player_id != snapshot.player_id
                for episode in episodes):
            raise ValueError("episode projection crosses game/player scope")
        for episode in episodes:
            scopes.append(ScopeSpec(
                "{}:episode:{}".format(prefix, episode.episode_id),
                "episode",
                snapshot.player_id,
                (EntityRef("episode", episode.episode_id),),
                (empire.scope_id,),
                (),
                predicates,
                frozenset((AtomNamespace.EPISODE,)),
                500,
                250,
                100,
                2,
                "durable-compact",
                empire.validity,
            ))
        return tuple(scopes)

    @staticmethod
    def _dependency(episode):
        return DependencyRef(
            DependencyKey("episode-revision", episode.episode_id, "record"),
            structural_hash(episode.to_dict()))

    def extend_fingerprints(self, fingerprints):
        result = dict(fingerprints)
        for episode in self._episodes():
            dependency = self._dependency(episode)
            result[dependency.key] = dependency.fingerprint
        return result

    def _record(self, scope, predicate, arguments, dependency, witness,
                lifecycle="recorded"):
        key = AtomKey(
            AtomNamespace.EPISODE, predicate, tuple(arguments), scope.scope_id)
        support = SupportRecord.create(
            self.projector_id, self.version, key.to_dict(), (dependency,),
            witness, (self.projector_id,))
        return AtomRecord.create(
            key, AuthorityClass.CONTROL_MODEL, _STRUCTURAL, scope.validity,
            (support,), (self.projector_id,), lifecycle=lifecycle,
            tags=(("domain", "decision-episode"),),
            truth_hash=_STRUCTURAL_HASH)

    def project(self, snapshot, scopes, fingerprints):
        scope_by_episode = dict(
            (value.root_entities[0].entity_id, value)
            for value in scopes if value.scope_kind == "episode")
        records = []
        episodes = self._episodes()
        if any(
                episode.game_id != snapshot.identity.game_id
                or episode.player_id != snapshot.player_id
                for episode in episodes):
            raise ValueError("episode projection crosses game/player scope")
        for episode in episodes:
            scope = scope_by_episode[episode.episode_id]
            episode_ref = EntityRef("episode", episode.episode_id)
            dependency = self._dependency(episode)
            if fingerprints.get(dependency.key) != dependency.fingerprint:
                raise ValueError("episode changed during projection")

            def add(predicate, argument, witness=None):
                records.append(self._record(
                    scope, predicate, (episode_ref, argument), dependency,
                    episode.to_dict() if witness is None else witness,
                    lifecycle=episode.outcome_status))

            add("episode-operation", EntityRef(
                "operation", episode.operation_id))
            add("episode-action", EntityRef(
                "action", "historical-" + structural_hash(
                    episode.action_key)[:24]))
            add("episode-before-revision", EntityRef(
                "revision", episode.before_revision_id))
            if episode.after_revision_id is not None:
                add("episode-after-revision", EntityRef(
                    "revision", episode.after_revision_id))
            add("episode-outcome-status", SymbolRef(
                "episode-outcome", episode.outcome_status))
            add("episode-context", SymbolRef(
                "context-signature", structural_hash(
                    dict(episode.context_signature))),
                {"context_signature": dict(episode.context_signature)})
            for atom_id in episode.source_atom_ids:
                add("episode-source-atom", EntityRef("atom", atom_id))
            for support_id in episode.source_support_ids:
                add("episode-source-support", EntityRef(
                    "support", support_id))
            for grounding_id in episode.grounding_result_ids:
                add("episode-grounding-result", EntityRef(
                    "grounding-result", grounding_id))
            for prediction_id in episode.prediction_ids:
                add("episode-prediction", EntityRef(
                    "prediction", prediction_id))
            for claim_id in episode.resource_claim_ids:
                add("episode-resource-claim", EntityRef(
                    "resource-claim", claim_id))
            add("episode-validation", EntityRef(
                "validation-result", episode.validation_result_hash))
            if episode.execution_event_id is not None:
                add("episode-execution-event", EntityRef(
                    "event", episode.execution_event_id))
            for effect in episode.attributed_effects:
                add("episode-attributed-effect", SymbolRef(
                    "effect", structural_hash(effect)), effect)
            for goal_id, relief in episode.realized_goal_relief:
                add("episode-goal-relief", EntityRef("goal", goal_id), {
                    "goal_id": goal_id,
                    "realized_relief": relief,
                })
        return tuple(sorted(records, key=lambda value: value.atom_id))
