"""Strict configuration and activation gates for dependent AtomSpace."""

from dataclasses import dataclass


_ACTIVATION_LEVELS = {
    "not-built": 0,
    "component-only": 1,
    "shadow-live": 2,
    "bounded-authority": 3,
    "engine-live": 4,
}


def _exact_keys(value, expected, name):
    if not isinstance(value, dict):
        raise TypeError("{} must be an object".format(name))
    unknown = sorted(set(value).difference(expected))
    missing = sorted(set(expected).difference(value))
    if unknown or missing:
        raise ValueError(
            "{} keys differ; unknown={}, missing={}".format(
                name, unknown, missing))


def _booleans(value, name):
    invalid = sorted(key for key, row in value.items()
                     if not isinstance(row, bool))
    if invalid:
        raise TypeError("{} flags must be boolean: {}".format(name, invalid))


@dataclass(frozen=True)
class DependentAtomSpaceConfig:
    enabled: bool
    shadow_enabled: bool
    authority_enabled: bool
    schema_version: str
    store_backend: str
    cold_verify_sample_rate: float
    revision_retention: int
    projection: tuple
    materialization: tuple
    inference: tuple
    domain_authority: tuple
    events: tuple

    ROOT_KEYS = frozenset((
        "authority_enabled", "cold_verify_sample_rate", "domain_authority",
        "enabled", "events", "inference", "materialization", "projection",
        "revision_retention", "schema_version", "shadow_enabled",
        "store_backend"))
    PROJECTION_KEYS = frozenset((
        "beliefs", "city", "economy", "empire", "operations", "region",
        "research", "ruleset", "unit", "world"))
    MATERIALIZATION_KEYS = frozenset((
        "focused_scope_ttl_turns", "maximum_atoms_global",
        "maximum_atoms_per_city_scope", "maximum_atoms_per_region_scope",
        "maximum_atoms_per_unit_scope", "maximum_expansion_depth",
        "maximum_groundings_per_scope", "maximum_rule_fires_per_scope"))
    INFERENCE_KEYS = frozenset((
        "deterministic_forward_enabled", "generic_rule_engine_enabled",
        "goal_regression_enabled", "technology_compatibility_path_enabled",
        "uncertain_assessment_enabled"))
    DOMAIN_KEYS = frozenset((
        "city_defense", "city_production", "city_stability", "combat",
        "expansion", "local_movement", "research", "transport"))
    EVENT_KEYS = frozenset((
        "explanation_capture", "shadow_divergence_capture", "support_level"))

    @classmethod
    def from_dict(cls, value, manifest=None):
        _exact_keys(value, cls.ROOT_KEYS, "dependent_atomspace")
        for name in ("enabled", "shadow_enabled", "authority_enabled"):
            if not isinstance(value[name], bool):
                raise TypeError("{} must be boolean".format(name))
        if value["schema_version"] != "1.0":
            raise ValueError("unsupported dependent AtomSpace schema")
        if value["store_backend"] != "memory":
            raise ValueError("unsupported dependent AtomSpace store backend")
        sample_rate = float(value["cold_verify_sample_rate"])
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError("cold verification sample rate must be in 0..1")
        retention = value["revision_retention"]
        if (isinstance(retention, bool) or not isinstance(retention, int)
                or retention < 1):
            raise ValueError("revision retention must be positive")
        projection = value["projection"]
        inference = value["inference"]
        authority = value["domain_authority"]
        events = value["events"]
        materialization = value["materialization"]
        _exact_keys(projection, cls.PROJECTION_KEYS, "projection")
        _exact_keys(inference, cls.INFERENCE_KEYS, "inference")
        _exact_keys(authority, cls.DOMAIN_KEYS, "domain_authority")
        _exact_keys(events, cls.EVENT_KEYS, "events")
        _exact_keys(
            materialization, cls.MATERIALIZATION_KEYS, "materialization")
        _booleans(projection, "projection")
        _booleans(inference, "inference")
        _booleans(authority, "domain_authority")
        _booleans({
            key: events[key] for key in (
                "explanation_capture", "shadow_divergence_capture")},
            "events")
        if events["support_level"] not in ("none", "selected", "all"):
            raise ValueError("unknown FDAS support event level")
        for key, row in materialization.items():
            if (isinstance(row, bool) or not isinstance(row, int) or row < 1):
                raise ValueError(
                    "materialization budget {} must be positive".format(key))
        if value["authority_enabled"] and not value["enabled"]:
            raise ValueError("FDAS authority requires the core to be enabled")
        if any(authority.values()) and not value["authority_enabled"]:
            raise ValueError("domain authority requires the authority gate")
        if authority["research"] and not inference[
                "technology_compatibility_path_enabled"]:
            raise ValueError(
                "research authority requires technology compatibility parity")
        if projection["region"] and materialization[
                "maximum_atoms_per_region_scope"] < 1:
            raise ValueError("region projection requires a region atom budget")
        if manifest is not None:
            cls._validate_manifest(value, manifest)
        return cls(
            value["enabled"],
            value["shadow_enabled"],
            value["authority_enabled"],
            value["schema_version"],
            value["store_backend"],
            sample_rate,
            retention,
            tuple(sorted(projection.items())),
            tuple(sorted(materialization.items())),
            tuple(sorted(inference.items())),
            tuple(sorted(authority.items())),
            tuple(sorted(events.items())),
        )

    @staticmethod
    def _validate_manifest(config, manifest):
        if not isinstance(manifest, dict):
            raise TypeError("FDAS activation manifest must be an object")
        capabilities = manifest.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError("FDAS activation manifest lacks capabilities")
        unknown_levels = sorted(
            value for value in capabilities.values()
            if value not in _ACTIVATION_LEVELS)
        if unknown_levels:
            raise ValueError("unknown FDAS activation status")

        def require(name, level):
            actual = capabilities.get(name, "not-built")
            if _ACTIVATION_LEVELS[actual] < _ACTIVATION_LEVELS[level]:
                raise ValueError(
                    "FDAS capability {} is {}, requires {}".format(
                        name, actual, level))

        if config["enabled"]:
            require("dependent_atomspace_core", "component-only")
        if config["shadow_enabled"]:
            require("dependent_atom_pressure_adapter", "component-only")
        if config["projection"]["operations"]:
            require("operation_atom_projection", "component-only")
        if any(config["domain_authority"].values()):
            require("dependent_atom_pressure_adapter", "bounded-authority")
            require("fdas_resource_packet_bridge", "bounded-authority")
            require("fdas_exact_commit_validation", "bounded-authority")
        if (config["domain_authority"]["city_stability"]
                or config["domain_authority"]["city_production"]):
            require("city_domain_projection", "bounded-authority")
        if (config["domain_authority"]["city_defense"]
                or config["domain_authority"]["local_movement"]):
            require("unit_domain_projection", "bounded-authority")
        domain_capabilities = {
            "expansion": (
                "route_corridor_projection",
                "settlement_site_projection",
                "population_recovery_projection",
                "expansion_operation_projection",
            ),
            "transport": (
                "transport_capability_projection",
                "transport_operation_projection",
            ),
            "combat": (
                "combat_task_force_projection",
                "combat_operation_projection",
            ),
        }
        for domain, names in domain_capabilities.items():
            if not config["domain_authority"][domain]:
                continue
            for name in names:
                require(name, "bounded-authority")

    def section(self, name):
        return dict(getattr(self, name))

    def to_dict(self):
        return {
            "authority_enabled": self.authority_enabled,
            "cold_verify_sample_rate": self.cold_verify_sample_rate,
            "domain_authority": dict(self.domain_authority),
            "enabled": self.enabled,
            "events": dict(self.events),
            "inference": dict(self.inference),
            "materialization": dict(self.materialization),
            "projection": dict(self.projection),
            "revision_retention": self.revision_retention,
            "schema_version": self.schema_version,
            "shadow_enabled": self.shadow_enabled,
            "store_backend": self.store_backend,
        }
