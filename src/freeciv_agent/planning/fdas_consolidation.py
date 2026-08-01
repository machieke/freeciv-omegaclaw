"""Evidence-gated FDAS legacy consolidation and rollback audit."""

from dataclasses import dataclass

from ..events.schema import structural_hash


_LEVELS = {
    "not-built": 0,
    "component-only": 1,
    "shadow-live": 2,
    "bounded-authority": 3,
    "engine-live": 4,
}


def _strings(values, name):
    result = tuple(sorted(str(value) for value in values))
    if not result or any(not value for value in result):
        raise ValueError("{} must contain non-empty strings".format(name))
    if len(result) != len(set(result)):
        raise ValueError("{} values must be unique".format(name))
    return result


@dataclass(frozen=True)
class LegacyReplacementSpec:
    branch_id: str
    legacy_owner: str
    replacement_capabilities: tuple
    replacement_test_ids: tuple
    policy_defaults: tuple
    rollback_id: str
    requested_action: str
    minimum_activation: str = "engine-live"

    def __post_init__(self):
        for value, name in (
                (self.branch_id, "branch ID"),
                (self.legacy_owner, "legacy owner"),
                (self.rollback_id, "rollback ID")):
            if not isinstance(value, str) or not value:
                raise ValueError("replacement {} is required".format(name))
        for name in (
                "replacement_capabilities", "replacement_test_ids",
                "policy_defaults"):
            object.__setattr__(
                self, name, _strings(getattr(self, name), name))
        if self.requested_action not in ("retain", "remove"):
            raise ValueError("replacement action must be retain or remove")
        if self.minimum_activation not in _LEVELS:
            raise ValueError("unknown replacement activation level")

    @classmethod
    def from_dict(cls, value):
        expected = {
            "branch_id", "legacy_owner", "minimum_activation",
            "policy_defaults", "replacement_capabilities",
            "replacement_test_ids", "requested_action", "rollback_id",
        }
        if set(value) != expected:
            raise ValueError("replacement specification keys differ")
        return cls(**value)

    def to_dict(self):
        return {
            "branch_id": self.branch_id,
            "legacy_owner": self.legacy_owner,
            "minimum_activation": self.minimum_activation,
            "policy_defaults": list(self.policy_defaults),
            "replacement_capabilities": list(
                self.replacement_capabilities),
            "replacement_test_ids": list(self.replacement_test_ids),
            "requested_action": self.requested_action,
            "rollback_id": self.rollback_id,
        }


@dataclass(frozen=True)
class LegacyReplacementDecision:
    branch_id: str
    requested_action: str
    disposition: str
    blockers: tuple
    replacement_capabilities: tuple
    verified_test_ids: tuple
    rollback_id: str

    def to_dict(self):
        return {
            "blockers": list(self.blockers),
            "branch_id": self.branch_id,
            "disposition": self.disposition,
            "replacement_capabilities": list(
                self.replacement_capabilities),
            "requested_action": self.requested_action,
            "rollback_id": self.rollback_id,
            "verified_test_ids": list(self.verified_test_ids),
        }


@dataclass(frozen=True)
class LegacyConsolidationReport:
    schema_version: str
    decisions: tuple
    removal_authorized: bool
    retained_count: int
    removable_count: int
    report_hash: str

    def to_dict(self):
        return {
            "decisions": [value.to_dict() for value in self.decisions],
            "removable_count": self.removable_count,
            "removal_authorized": self.removal_authorized,
            "report_hash": self.report_hash,
            "retained_count": self.retained_count,
            "schema_version": self.schema_version,
        }


class LegacyConsolidationAudit(object):
    """Authorize removal only with live replacement, tests, and rollback."""

    AUDIT_IDENTITY = "fdas-legacy-consolidation-audit/1.0"

    @classmethod
    def evaluate(cls, fdas_manifest, replacement_manifest,
                 passing_test_ids=(), available_rollback_ids=()):
        if not isinstance(fdas_manifest, dict):
            raise TypeError("FDAS manifest must be an object")
        capabilities = fdas_manifest.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError("FDAS manifest lacks capabilities")
        if replacement_manifest.get("schema_version") != "1.0":
            raise ValueError("unsupported replacement manifest schema")
        if replacement_manifest.get("audit_identity") != cls.AUDIT_IDENTITY:
            raise ValueError("replacement audit identity mismatch")
        rows = tuple(
            LegacyReplacementSpec.from_dict(value)
            for value in replacement_manifest.get("branches", ()))
        if not rows:
            raise ValueError("replacement manifest requires branches")
        if len({value.branch_id for value in rows}) != len(rows):
            raise ValueError("replacement branch IDs must be unique")
        passing = frozenset(str(value) for value in passing_test_ids)
        rollbacks = frozenset(str(value) for value in available_rollback_ids)
        decisions = []
        for spec in sorted(rows, key=lambda value: value.branch_id):
            blockers = []
            required_level = _LEVELS[spec.minimum_activation]
            for capability in spec.replacement_capabilities:
                actual = capabilities.get(capability, "not-built")
                if actual not in _LEVELS:
                    raise ValueError("unknown FDAS activation status")
                if _LEVELS[actual] < required_level:
                    blockers.append(
                        "capability:{}:{}<{}".format(
                            capability, actual, spec.minimum_activation))
            missing_tests = sorted(
                set(spec.replacement_test_ids).difference(passing))
            blockers.extend("replacement-test-not-passing:" + value
                            for value in missing_tests)
            if spec.rollback_id not in rollbacks:
                blockers.append("rollback-unavailable:" + spec.rollback_id)
            if spec.requested_action == "retain":
                disposition = "retained-by-manifest"
            elif blockers:
                disposition = "removal-blocked"
            else:
                disposition = "removal-authorized"
            decisions.append(LegacyReplacementDecision(
                spec.branch_id, spec.requested_action, disposition,
                tuple(sorted(blockers)), spec.replacement_capabilities,
                tuple(sorted(set(spec.replacement_test_ids).intersection(
                    passing))), spec.rollback_id))
        decisions = tuple(decisions)
        removable = sum(
            value.disposition == "removal-authorized" for value in decisions)
        retained = len(decisions) - removable
        semantic = {
            "audit_identity": cls.AUDIT_IDENTITY,
            "decisions": [value.to_dict() for value in decisions],
            "removable_count": removable,
            "removal_authorized": removable > 0,
            "retained_count": retained,
            "schema_version": "1.0",
        }
        return LegacyConsolidationReport(
            "1.0", decisions, removable > 0, retained, removable,
            structural_hash(semantic))
