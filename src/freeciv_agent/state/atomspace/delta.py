"""Canonical field-level deltas for immutable FreeCiv snapshots."""

from dataclasses import dataclass
from functools import lru_cache

from ...events.schema import structural_hash
from .model import DependencyKey, DependencyRef, joined_identity_hash


_SCALAR_FIELDS = (
    "player_id",
    "player_alive",
    "phase",
    "ruleset_ready",
    "ruleset_diagnostic",
    "game_over",
    "own_score",
    "map_width",
    "map_height",
    "map_wrap_x",
    "map_wrap_y",
    "map_topology_id",
    "legal_actions_digest",
)
_OBJECT_FIELDS = ("research", "economy", "government")
_COLLECTIONS = (
    ("cities", "city_id"),
    ("units", "unit_id"),
    ("visible_enemy_units", "unit_id"),
    ("map_tiles", "index"),
    ("opponent_scores", "player_id"),
    ("movement_routes", ("unit_id", "destination_tile")),
    ("combat_probabilities", ("actor_unit_id", "target_tile_id")),
    ("research_options", "tech_name"),
)


def _canonical(value):
    if hasattr(value, "grounded_dict"):
        return _canonical(value.grounded_dict())
    if hasattr(value, "to_dict"):
        return _canonical(value.to_dict())
    if isinstance(value, dict):
        return dict((str(key), _canonical(item))
                    for key, item in sorted(value.items(), key=lambda row: str(row[0])))
    if isinstance(value, (tuple, list, set, frozenset)):
        values = [_canonical(item) for item in value]
        if isinstance(value, (set, frozenset)):
            values.sort(key=structural_hash)
        return values
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return _canonical(vars(value))
    return str(value)


def _owner(snapshot):
    return "game:{}:player:{}".format(
        snapshot.identity.game_id, snapshot.player_id)


def _entity_id(value, id_spec, index):
    if isinstance(id_spec, tuple):
        parts = [getattr(value, name, None) for name in id_spec]
        if any(part is None for part in parts) and isinstance(value, dict):
            parts = [value.get(name) for name in id_spec]
        if any(part is None for part in parts):
            return "index:{}".format(index)
        return ":".join(str(part) for part in parts)
    result = getattr(value, id_spec, None)
    if result is None and isinstance(value, dict):
        result = value.get(id_spec)
    return str(result) if result is not None else "index:{}".format(index)


def _collection(snapshot, name, id_spec):
    result = {}
    for index, value in enumerate(tuple(getattr(snapshot, name, ()) or ())):
        entity_id = _entity_id(value, id_spec, index)
        if entity_id in result:
            raise ValueError(
                "snapshot collection {} has duplicate entity {}".format(
                    name, entity_id))
        result[entity_id] = _canonical(value)
    return result


def snapshot_document(snapshot):
    """Return stable semantic fields without revision-only identity material."""
    document = dict((name, _canonical(getattr(snapshot, name, None)))
                    for name in _SCALAR_FIELDS)
    document["turn"] = int(snapshot.turn)
    document["source_seq"] = int(snapshot.identity.source_seq)
    for name in _OBJECT_FIELDS:
        document[name] = _canonical(getattr(snapshot, name, None))
    for name, id_spec in _COLLECTIONS:
        document[name] = _collection(snapshot, name, id_spec)
    document["visible_tile_ids"] = dict(
        (str(value), True)
        for value in sorted(set(getattr(snapshot, "visible_tile_ids", ()) or ())))
    document["known_hut_tile_ids"] = dict(
        (str(value), True)
        for value in sorted(set(getattr(snapshot, "known_hut_tile_ids", ()) or ())))
    known_techs = getattr(getattr(snapshot, "research", None), "known_techs", ())
    document["known_techs"] = dict(
        (str(value), True) for value in sorted(set(known_techs or ())))
    document["legal_actions"] = dict(
        (structural_hash(value), str(value))
        for value in tuple(getattr(snapshot, "legal_action_json", ()) or ()))
    return document


@lru_cache(maxsize=16384)
def _scalar_fingerprint(value_type, value):
    return structural_hash(value)


def _fingerprint(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return _scalar_fingerprint(type(value).__name__, value)
    return structural_hash(value)


def _flatten(prefix, value, output):
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten("{}.{}".format(prefix, key), value[key], output)
        return
    output[prefix] = _fingerprint(value)
    if isinstance(value, list):
        for index, item in enumerate(value):
            _flatten("{}.{}".format(prefix, index), item, output)


def snapshot_dependency_fingerprints(snapshot, document=None):
    """Map stable dependency keys to canonical field/entity fingerprints."""
    owner_id = _owner(snapshot)
    flattened = {}
    document = document or snapshot_document(snapshot)
    for key, value in sorted(document.items()):
        _flatten(key, value, flattened)
    collection_names = set(name for name, _ in _COLLECTIONS)
    for name in collection_names:
        for entity_id in document[name]:
            flattened["{}.{}.__exists__".format(name, entity_id)] = (
                structural_hash(True))
    return dict(
        (DependencyKey("snapshot-field", owner_id, path), fingerprint)
        for path, fingerprint in flattened.items())


def snapshot_dependency_ref(snapshot, path, fingerprints=None):
    fingerprints = fingerprints or snapshot_dependency_fingerprints(snapshot)
    key = DependencyKey("snapshot-field", _owner(snapshot), str(path))
    try:
        return DependencyRef(key, fingerprints[key])
    except KeyError:
        raise KeyError("snapshot dependency path is absent: {}".format(path))


@dataclass(frozen=True, order=True)
class CollectionChange:
    collection: str
    entity_id: str
    prior_fingerprint: object
    current_fingerprint: object
    changed_keys: tuple

    def __post_init__(self):
        object.__setattr__(self, "changed_keys", tuple(sorted(self.changed_keys)))

    def to_dict(self):
        return {
            "changed_keys": [value.to_dict() for value in self.changed_keys],
            "collection": self.collection,
            "current_fingerprint": self.current_fingerprint,
            "entity_id": self.entity_id,
            "prior_fingerprint": self.prior_fingerprint,
        }


@dataclass(frozen=True)
class SnapshotDelta:
    prior_snapshot_id: object
    current_snapshot_id: str
    changed_scalar_keys: tuple
    collection_additions: tuple
    collection_removals: tuple
    collection_updates: tuple
    legal_actions_changed: bool
    visibility_changed: bool
    map_changed: bool
    turn_advanced: bool
    source_seq_advanced: bool
    delta_hash: str

    @property
    def changed_dependency_keys(self):
        values = set(self.changed_scalar_keys)
        for change in (
                self.collection_additions
                + self.collection_removals
                + self.collection_updates):
            values.update(change.changed_keys)
        return tuple(sorted(values))

    @classmethod
    def between(cls, prior, current, prior_document=None,
                current_document=None):
        prior_document = (
            prior_document
            if prior_document is not None
            else snapshot_document(prior) if prior is not None else {})
        current_document = (
            current_document
            if current_document is not None
            else snapshot_document(current))
        if prior is None:
            semantic = {
                "changed_scalar_keys": [],
                "collection_additions": [],
                "collection_removals": [],
                "collection_updates": [],
                "current_snapshot_id": current.snapshot_id,
                "legal_actions_changed": True,
                "map_changed": True,
                "prior_snapshot_id": None,
                "source_seq_advanced": False,
                "turn_advanced": False,
                "visibility_changed": True,
            }
            return cls(
                None,
                current.snapshot_id,
                (),
                (),
                (),
                (),
                True,
                True,
                True,
                False,
                False,
                "snapshot-delta-" + joined_identity_hash((
                    structural_hash(semantic),))[:32],
            )
        owner_id = _owner(current)
        changed_scalars = []
        additions = []
        removals = []
        updates = []
        collection_names = set(name for name, _ in _COLLECTIONS).union((
            "visible_tile_ids",
            "known_hut_tile_ids",
            "known_techs",
            "legal_actions",
        ))

        def dependency(path):
            return DependencyKey("snapshot-field", owner_id, path)

        def changed_paths(prefix, before, after):
            old = {}
            new = {}
            _flatten(prefix, before, old)
            _flatten(prefix, after, new)
            return tuple(sorted(
                dependency(path)
                for path in set(old).union(new)
                if old.get(path) != new.get(path)))

        for name in sorted(set(prior_document).union(current_document)):
            before = prior_document.get(name)
            after = current_document.get(name)
            if name not in collection_names:
                for key in changed_paths(name, before, after):
                    changed_scalars.append(key)
                continue
            before = before or {}
            after = after or {}
            for entity_id in sorted(set(before).union(after)):
                prefix = "{}.{}".format(name, entity_id)
                keys = changed_paths(
                    prefix, before.get(entity_id), after.get(entity_id))
                if (entity_id not in before) != (entity_id not in after):
                    keys = tuple(sorted(set(keys).union((
                        dependency(prefix + ".__exists__"),))))
                if not keys:
                    continue
                change = CollectionChange(
                    name,
                    entity_id,
                    structural_hash(before[entity_id])
                    if entity_id in before else None,
                    structural_hash(after[entity_id])
                    if entity_id in after else None,
                    keys,
                )
                if entity_id not in before:
                    additions.append(change)
                elif entity_id not in after:
                    removals.append(change)
                else:
                    updates.append(change)

        turn_advanced = bool(
            prior is not None and current.turn > prior.turn)
        source_seq_advanced = bool(
            prior is not None
            and current.identity.source_seq > prior.identity.source_seq)
        semantic = {
            "changed_scalar_keys": [value.to_dict()
                                    for value in sorted(set(changed_scalars))],
            "collection_additions": [value.to_dict() for value in additions],
            "collection_removals": [value.to_dict() for value in removals],
            "collection_updates": [value.to_dict() for value in updates],
            "current_snapshot_id": current.snapshot_id,
            "legal_actions_changed": (
                prior is None
                or prior_document.get("legal_actions")
                != current_document.get("legal_actions")),
            "map_changed": any(
                name.startswith("map_") or name == "known_hut_tile_ids"
                for name in set(prior_document).union(current_document)
                if prior_document.get(name) != current_document.get(name)),
            "prior_snapshot_id": (
                prior.snapshot_id if prior is not None else None),
            "source_seq_advanced": source_seq_advanced,
            "turn_advanced": turn_advanced,
            "visibility_changed": (
                prior is None
                or prior_document.get("visible_tile_ids")
                != current_document.get("visible_tile_ids")),
        }
        delta_hash = "snapshot-delta-" + joined_identity_hash((
            structural_hash(semantic),))[:32]
        return cls(
            semantic["prior_snapshot_id"],
            current.snapshot_id,
            tuple(sorted(set(changed_scalars))),
            tuple(additions),
            tuple(removals),
            tuple(updates),
            semantic["legal_actions_changed"],
            semantic["visibility_changed"],
            semantic["map_changed"],
            turn_advanced,
            source_seq_advanced,
            delta_hash,
        )

    def to_dict(self):
        return {
            "changed_scalar_keys": [value.to_dict()
                                    for value in self.changed_scalar_keys],
            "collection_additions": [value.to_dict()
                                     for value in self.collection_additions],
            "collection_removals": [value.to_dict()
                                    for value in self.collection_removals],
            "collection_updates": [value.to_dict()
                                   for value in self.collection_updates],
            "current_snapshot_id": self.current_snapshot_id,
            "delta_hash": self.delta_hash,
            "legal_actions_changed": self.legal_actions_changed,
            "map_changed": self.map_changed,
            "prior_snapshot_id": self.prior_snapshot_id,
            "source_seq_advanced": self.source_seq_advanced,
            "turn_advanced": self.turn_advanced,
            "visibility_changed": self.visibility_changed,
        }
