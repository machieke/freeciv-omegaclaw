"""Logical scope contracts and deterministic focused activation for FDAS."""

from dataclasses import dataclass

from ...events.schema import structural_hash

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


@dataclass(frozen=True)
class ScopeActivationSignal:
    scope_id: str
    reason: str
    funded_by: str
    priority: float
    causal_parent_ids: tuple = ()

    def __post_init__(self):
        for value, name in (
                (self.scope_id, "scope ID"), (self.reason, "reason"),
                (self.funded_by, "funding identity")):
            if not isinstance(value, str) or not value:
                raise ValueError("scope activation {} is required".format(name))
        priority = float(self.priority)
        if not 0.0 <= priority <= 1.0:
            raise ValueError("scope activation priority must be in 0..1")
        parents = tuple(sorted(str(value) for value in self.causal_parent_ids))
        if (any(not value for value in parents)
                or len(parents) != len(set(parents))):
            raise ValueError("scope activation parents must be unique strings")
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "causal_parent_ids", parents)


@dataclass(frozen=True)
class ScopeActivationRequest:
    scope_id: str
    scope_kind: str
    reason: str
    funded_by: str
    priority: float
    activated_turn: int
    expires_turn: int
    retained: bool
    causal_parent_ids: tuple

    def to_dict(self):
        return {
            "activated_turn": self.activated_turn,
            "causal_parent_ids": list(self.causal_parent_ids),
            "expires_turn": self.expires_turn,
            "funded_by": self.funded_by,
            "priority": self.priority,
            "reason": self.reason,
            "retained": self.retained,
            "scope_id": self.scope_id,
            "scope_kind": self.scope_kind,
        }


@dataclass(frozen=True)
class ScopeActivationState:
    turn: int
    requests: tuple
    rejected: tuple
    state_hash: str

    @property
    def active_scope_ids(self):
        return tuple(value.scope_id for value in self.requests)

    def to_dict(self):
        return {
            "active_scope_ids": list(self.active_scope_ids),
            "rejected": [dict(value) for value in self.rejected],
            "requests": [value.to_dict() for value in self.requests],
            "state_hash": self.state_hash,
            "turn": self.turn,
        }


@dataclass(frozen=True)
class ScopeActivationPolicy:
    maximum_active_scopes: int = 512
    maximum_by_kind: tuple = (
        ("combat-engagement", 64),
        ("opponent-belief", 8),
        ("population-recovery", 32),
        ("region", 16),
        ("route-corridor", 64),
        ("settlement-site", 64),
        ("task-force", 32),
        ("transport", 32),
    )
    focused_scope_ttl_turns: int = 3
    always_active_kinds: tuple = (
        "city-facts", "empire", "episode", "operation", "ruleset",
        "unit-facts", "world",
    )

    def __post_init__(self):
        if (isinstance(self.maximum_active_scopes, bool)
                or not isinstance(self.maximum_active_scopes, int)
                or self.maximum_active_scopes < 1):
            raise ValueError("maximum active scopes must be positive")
        if (isinstance(self.focused_scope_ttl_turns, bool)
                or not isinstance(self.focused_scope_ttl_turns, int)
                or self.focused_scope_ttl_turns < 0):
            raise ValueError("focused scope TTL must be non-negative")
        limits = tuple(sorted(
            (str(kind), int(limit)) for kind, limit in self.maximum_by_kind))
        if (any(not kind or limit < 1 for kind, limit in limits)
                or len({kind for kind, _limit in limits}) != len(limits)):
            raise ValueError("scope kind limits must be unique and positive")
        always = tuple(sorted(str(value) for value in self.always_active_kinds))
        if (any(not value for value in always)
                or len(always) != len(set(always))):
            raise ValueError("always-active scope kinds must be unique")
        object.__setattr__(self, "maximum_by_kind", limits)
        object.__setattr__(self, "always_active_kinds", always)


class ScopeActivator(object):
    """Fund scopes deterministically; absence of a signal is not a fact."""

    ACTIVATOR_IDENTITY = "fdas-scope-activator/1.0"

    def __init__(self, policy=None):
        self.policy = policy or ScopeActivationPolicy()

    def activate(self, scopes, signals, turn, previous_state=None):
        scopes = tuple(scopes)
        if any(not isinstance(value, ScopeSpec) for value in scopes):
            raise TypeError("scope activator requires ScopeSpec values")
        by_id = dict((value.scope_id, value) for value in scopes)
        if len(by_id) != len(scopes):
            raise ValueError("scope activation IDs must be unique")
        turn = int(turn)
        if turn < 0:
            raise ValueError("scope activation turn must be non-negative")
        signals = tuple(signals)
        if any(not isinstance(value, ScopeActivationSignal)
               for value in signals):
            raise TypeError("scope activator requires typed signals")
        if any(value.scope_id not in by_id for value in signals):
            raise ValueError("scope activation signal references unknown scope")
        strongest = {}
        for signal in signals:
            prior = strongest.get(signal.scope_id)
            if (prior is None
                    or (-signal.priority, signal.reason, signal.funded_by)
                    < (-prior.priority, prior.reason, prior.funded_by)):
                strongest[signal.scope_id] = signal
        candidates = []
        for scope in scopes:
            if scope.scope_kind in self.policy.always_active_kinds:
                candidates.append((
                    0, -1.0, scope.scope_id, scope,
                    "always-materialized", "base-scope", (), False,
                    turn + self.policy.focused_scope_ttl_turns))
        for scope_id, signal in strongest.items():
            scope = by_id[scope_id]
            if scope.scope_kind in self.policy.always_active_kinds:
                continue
            candidates.append((
                1, -signal.priority, scope.scope_id, scope,
                signal.reason, signal.funded_by, signal.causal_parent_ids,
                False, turn + self.policy.focused_scope_ttl_turns))
        if previous_state is not None:
            if not isinstance(previous_state, ScopeActivationState):
                raise TypeError("previous activation must be ScopeActivationState")
            if previous_state.turn > turn:
                raise ValueError("scope activation turn regressed")
            for previous in previous_state.requests:
                scope = by_id.get(previous.scope_id)
                if (scope is None or previous.expires_turn < turn
                        or scope.scope_kind in self.policy.always_active_kinds
                        or previous.scope_id in strongest):
                    continue
                candidates.append((
                    2, -previous.priority, scope.scope_id, scope,
                    "retained-scope-momentum", previous.funded_by,
                    previous.causal_parent_ids, True, previous.expires_turn))
        candidates.sort(key=lambda value: value[:3])
        limits = dict(self.policy.maximum_by_kind)
        by_kind_count = {}
        requests = []
        rejected = []
        for (_tier, negative_priority, _scope_id, scope, reason, funded_by,
             parents, retained, expires_turn) in candidates:
            if len(requests) >= self.policy.maximum_active_scopes:
                rejected.append({
                    "reason": "global-scope-budget-exhausted",
                    "scope_id": scope.scope_id,
                    "scope_kind": scope.scope_kind,
                })
                continue
            kind_limit = limits.get(scope.scope_kind)
            if (kind_limit is not None
                    and by_kind_count.get(scope.scope_kind, 0) >= kind_limit):
                rejected.append({
                    "reason": "scope-kind-budget-exhausted",
                    "scope_id": scope.scope_id,
                    "scope_kind": scope.scope_kind,
                })
                continue
            requests.append(ScopeActivationRequest(
                scope.scope_id, scope.scope_kind, reason, funded_by,
                -negative_priority, turn, expires_turn, retained, parents))
            by_kind_count[scope.scope_kind] = (
                by_kind_count.get(scope.scope_kind, 0) + 1)
        requests = tuple(sorted(requests, key=lambda value: value.scope_id))
        rejected = tuple(sorted(
            rejected, key=lambda value: (value["scope_id"], value["reason"])))
        semantic = {
            "activator_identity": self.ACTIVATOR_IDENTITY,
            "rejected": list(rejected),
            "requests": [value.to_dict() for value in requests],
            "turn": turn,
        }
        return ScopeActivationState(
            turn, requests, rejected, structural_hash(semantic))
