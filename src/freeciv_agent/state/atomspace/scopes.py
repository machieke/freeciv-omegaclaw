"""Logical scope contracts for the FDAS full-build compatibility layer."""

from dataclasses import dataclass

from .model import AtomNamespace, EntityRef, ValidityInterval


@dataclass(frozen=True)
class ScopeSpec:
    scope_id: str
    scope_kind: str
    owner_player_id: int
    root_entities: tuple
    parent_scope_ids: tuple
    imported_predicates: tuple
    exported_predicates: tuple
    namespaces: frozenset
    maximum_atoms: int
    maximum_rule_fires: int
    maximum_groundings: int
    maximum_expansion_depth: int
    retention_policy: str
    validity: ValidityInterval

    def __post_init__(self):
        for value, name in (
                (self.scope_id, "scope ID"),
                (self.scope_kind, "scope kind"),
                (self.retention_policy, "scope retention policy")):
            if not isinstance(value, str) or not value:
                raise ValueError("{} is required".format(name))
        if (isinstance(self.owner_player_id, bool)
                or not isinstance(self.owner_player_id, int)
                or self.owner_player_id < 0):
            raise ValueError("scope owner player ID must be non-negative")
        for field_name in (
                "root_entities", "parent_scope_ids", "imported_predicates",
                "exported_predicates"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(self, "namespaces", frozenset(
            AtomNamespace(value) for value in self.namespaces))
        if any(not isinstance(value, EntityRef) for value in self.root_entities):
            raise TypeError("scope roots must be EntityRef values")
        for values, name in (
                (self.parent_scope_ids, "parent scope IDs"),
                (self.imported_predicates, "imported predicates"),
                (self.exported_predicates, "exported predicates")):
            if any(not isinstance(value, str) or not value for value in values):
                raise ValueError("{} must be non-empty strings".format(name))
            if len(values) != len(set(values)):
                raise ValueError("{} must be unique".format(name))
        if not self.namespaces:
            raise ValueError("scope requires at least one namespace")
        for value, name in (
                (self.maximum_atoms, "maximum atoms"),
                (self.maximum_rule_fires, "maximum rule fires"),
                (self.maximum_groundings, "maximum groundings"),
                (self.maximum_expansion_depth, "maximum expansion depth")):
            if (isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0):
                raise ValueError("{} must be non-negative".format(name))
        if self.maximum_atoms < 1:
            raise ValueError("scope maximum atoms must be positive")
        if not isinstance(self.validity, ValidityInterval):
            raise TypeError("scope requires ValidityInterval")

    def to_dict(self):
        return {
            "exported_predicates": list(self.exported_predicates),
            "imported_predicates": list(self.imported_predicates),
            "maximum_atoms": self.maximum_atoms,
            "maximum_expansion_depth": self.maximum_expansion_depth,
            "maximum_groundings": self.maximum_groundings,
            "maximum_rule_fires": self.maximum_rule_fires,
            "namespaces": sorted(value.value for value in self.namespaces),
            "owner_player_id": self.owner_player_id,
            "parent_scope_ids": list(self.parent_scope_ids),
            "retention_policy": self.retention_policy,
            "root_entities": [value.to_dict() for value in self.root_entities],
            "scope_id": self.scope_id,
            "scope_kind": self.scope_kind,
            "validity": self.validity.to_dict(),
        }


def _scope_prefix(snapshot):
    return "scope:game:{}:player:{}".format(
        snapshot.identity.game_id, snapshot.player_id)


def snapshot_scopes(snapshot):
    """Return the two Phase-1 logical scopes for the legacy projection."""
    prefix = _scope_prefix(snapshot)
    validity = ValidityInterval(
        snapshot_id=snapshot.snapshot_id,
        valid_from_turn=snapshot.turn,
        valid_through_turn=snapshot.turn,
        source_seq=snapshot.identity.source_seq,
    )
    player = EntityRef("player", str(snapshot.player_id))
    world = ScopeSpec(
        scope_id=prefix + ":world",
        scope_kind="world",
        owner_player_id=snapshot.player_id,
        root_entities=(player,),
        parent_scope_ids=(),
        imported_predicates=(),
        exported_predicates=("tile-visible",),
        namespaces=frozenset((AtomNamespace.OBSERVATION,)),
        maximum_atoms=25000,
        maximum_rule_fires=0,
        maximum_groundings=0,
        maximum_expansion_depth=0,
        retention_policy="snapshot-revision",
        validity=validity,
    )
    empire = ScopeSpec(
        scope_id=prefix + ":empire",
        scope_kind="empire",
        owner_player_id=snapshot.player_id,
        root_entities=(player,),
        parent_scope_ids=(world.scope_id,),
        imported_predicates=("tile-visible",),
        exported_predicates=(),
        namespaces=frozenset((AtomNamespace.AUTHORITATIVE,)),
        maximum_atoms=25000,
        maximum_rule_fires=0,
        maximum_groundings=0,
        maximum_expansion_depth=0,
        retention_policy="snapshot-revision",
        validity=validity,
    )
    return world, empire
