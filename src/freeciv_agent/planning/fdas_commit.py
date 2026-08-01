"""Exact fail-closed commit binding for FDAS-selected operations."""

from dataclasses import dataclass

from ..events.schema import structural_hash
from .commit_validator import ValidationDisposition


@dataclass(frozen=True)
class FDASCommitBinding:
    snapshot_id: str
    legal_actions_digest: str
    revision_id: str
    revision_build_hash: str
    operation_id: str
    operation_spec_digest: str
    candidate_hash: str
    action_key: str
    source_support_ids: tuple
    binding_hash: str

    def __post_init__(self):
        for value, name in (
                (self.snapshot_id, "snapshot ID"),
                (self.legal_actions_digest, "legal-action digest"),
                (self.revision_id, "revision ID"),
                (self.revision_build_hash, "revision build hash"),
                (self.operation_id, "operation ID"),
                (self.operation_spec_digest, "operation spec digest"),
                (self.candidate_hash, "candidate hash"),
                (self.action_key, "action key"),
                (self.binding_hash, "binding hash")):
            if not isinstance(value, str) or not value:
                raise ValueError("FDAS {} is required".format(name))
        object.__setattr__(
            self, "source_support_ids",
            tuple(sorted(set(self.source_support_ids))))
        if not self.source_support_ids:
            raise ValueError("FDAS commit binding requires source supports")
        semantic = {
            "action_key": self.action_key,
            "candidate_hash": self.candidate_hash,
            "legal_actions_digest": self.legal_actions_digest,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "revision_build_hash": self.revision_build_hash,
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "source_support_ids": list(self.source_support_ids),
        }
        if self.binding_hash != structural_hash(semantic):
            raise ValueError("FDAS commit binding hash mismatch")

    @classmethod
    def create(cls, revision, snapshot, candidate, goal_contexts):
        if revision.snapshot_id != snapshot.snapshot_id:
            raise ValueError("FDAS revision and snapshot differ")
        goal_by_id = dict(
            (value.goal.goal_id, value) for value in goal_contexts)
        goal_ids = tuple(candidate.operation.goal_ids)
        if not goal_ids or any(value not in goal_by_id for value in goal_ids):
            raise ValueError("FDAS candidate goals are unavailable")
        supports = []
        for goal_id in goal_ids:
            record = revision.record(goal_by_id[goal_id].deficit_atom_id)
            if record is None:
                raise ValueError("FDAS candidate deficit support is absent")
            supports.extend(value.support_id for value in record.supports)
        semantic = {
            "action_key": candidate.action_key,
            "candidate_hash": candidate.candidate_hash,
            "legal_actions_digest": snapshot.legal_actions_digest,
            "operation_id": candidate.operation.operation_id,
            "operation_spec_digest": candidate.operation.spec_digest,
            "revision_build_hash": revision.build_hash,
            "revision_id": revision.revision_id,
            "snapshot_id": snapshot.snapshot_id,
            "source_support_ids": sorted(set(supports)),
        }
        return cls(
            snapshot.snapshot_id,
            snapshot.legal_actions_digest,
            revision.revision_id,
            revision.build_hash,
            candidate.operation.operation_id,
            candidate.operation.spec_digest,
            candidate.candidate_hash,
            candidate.action_key,
            tuple(supports),
            structural_hash(semantic),
        )

    def to_dict(self):
        return {
            "action_key": self.action_key,
            "binding_hash": self.binding_hash,
            "candidate_hash": self.candidate_hash,
            "legal_actions_digest": self.legal_actions_digest,
            "operation_id": self.operation_id,
            "operation_spec_digest": self.operation_spec_digest,
            "revision_build_hash": self.revision_build_hash,
            "revision_id": self.revision_id,
            "snapshot_id": self.snapshot_id,
            "source_support_ids": list(self.source_support_ids),
        }


@dataclass(frozen=True)
class FDASCommitValidation:
    disposition: ValidationDisposition
    reason: object
    checks: tuple
    binding_hash: str
    current_revision_id: str
    current_snapshot_id: str
    plan_materialization_authorized: bool
    execution_authority: bool
    result_hash: str

    def __post_init__(self):
        if self.execution_authority:
            raise ValueError("ExecutionGate remains final authority")
        if self.plan_materialization_authorized:
            if self.disposition != ValidationDisposition.COMMIT:
                raise ValueError("authorized FDAS validation must commit")
        elif self.disposition == ValidationDisposition.COMMIT:
            raise ValueError("commit disposition must authorize materialization")

    def to_dict(self):
        return {
            "binding_hash": self.binding_hash,
            "checks": list(self.checks),
            "current_revision_id": self.current_revision_id,
            "current_snapshot_id": self.current_snapshot_id,
            "disposition": self.disposition.value,
            "execution_authority": False,
            "plan_materialization_authorized": (
                self.plan_materialization_authorized),
            "reason": self.reason,
            "result_hash": self.result_hash,
            "validator_identity": "fdas-commit-validator/1.0",
        }


class FDASCommitValidator(object):
    """Revalidate every FDAS support and identity immediately before commit."""

    VALIDATOR_IDENTITY = "fdas-commit-validator/1.0"

    @staticmethod
    def _result(disposition, reason, checks, binding, revision, snapshot,
                authorized=False):
        semantic = {
            "binding_hash": binding.binding_hash,
            "checks": list(checks),
            "current_revision_id": revision.revision_id,
            "current_snapshot_id": snapshot.snapshot_id,
            "disposition": disposition.value,
            "plan_materialization_authorized": bool(authorized),
            "reason": reason,
            "validator_identity": FDASCommitValidator.VALIDATOR_IDENTITY,
        }
        return FDASCommitValidation(
            disposition,
            reason,
            tuple(checks),
            binding.binding_hash,
            revision.revision_id,
            snapshot.snapshot_id,
            bool(authorized),
            False,
            structural_hash(semantic),
        )

    def validate(self, binding, current_revision, current_snapshot,
                 current_candidate, authority_enabled=False):
        if not isinstance(binding, FDASCommitBinding):
            raise TypeError("FDAS commit requires FDASCommitBinding")
        if not isinstance(authority_enabled, bool):
            raise TypeError("FDAS authority switch must be boolean")
        checks = []
        if (current_snapshot.snapshot_id != binding.snapshot_id
                or current_snapshot.legal_actions_digest
                != binding.legal_actions_digest):
            return self._result(
                ValidationDisposition.REGENERATE,
                "stale-snapshot-or-legal-actions",
                ("snapshot-and-legal-action-refresh",),
                binding, current_revision, current_snapshot)
        checks.append("snapshot-and-legal-action-refresh")
        if (current_revision.snapshot_id != current_snapshot.snapshot_id
                or current_revision.revision_id != binding.revision_id
                or current_revision.build_hash != binding.revision_build_hash):
            return self._result(
                ValidationDisposition.REGENERATE,
                "fdas-revision-changed",
                checks + ["fdas-revision-identity"],
                binding, current_revision, current_snapshot)
        checks.append("fdas-revision-identity")
        support_ids = current_revision.dependency_index.support_by_id
        if any(value not in support_ids for value in binding.source_support_ids):
            return self._result(
                ValidationDisposition.REGENERATE,
                "fdas-source-support-retracted",
                checks + ["fdas-source-supports"],
                binding, current_revision, current_snapshot)
        checks.append("fdas-source-supports")
        if (current_candidate.operation.operation_id != binding.operation_id
                or current_candidate.operation.spec_digest
                != binding.operation_spec_digest
                or current_candidate.candidate_hash != binding.candidate_hash
                or current_candidate.action_key != binding.action_key):
            return self._result(
                ValidationDisposition.REGENERATE,
                "fdas-candidate-changed",
                checks + ["fdas-candidate-identity"],
                binding, current_revision, current_snapshot)
        checks.append("fdas-candidate-identity")
        if (not current_candidate.legal_bound
                or binding.action_key not in current_snapshot.legal_action_json):
            return self._result(
                ValidationDisposition.REJECT,
                "action-not-in-server-legal-set",
                checks + ["server-legal-action-membership"],
                binding, current_revision, current_snapshot)
        checks.append("server-legal-action-membership")
        if current_candidate.blockers:
            return self._result(
                ValidationDisposition.REJECT,
                "fdas-candidate-has-causal-blockers",
                checks + ["causal-effect-and-requirement-firewall"],
                binding, current_revision, current_snapshot)
        checks.append("causal-effect-and-requirement-firewall")
        if not authority_enabled or not current_candidate.authority_eligible:
            return self._result(
                ValidationDisposition.REJECT,
                "fdas-domain-authority-disabled",
                checks + ["domain-authority-gate"],
                binding, current_revision, current_snapshot)
        checks.append("domain-authority-gate")
        return self._result(
            ValidationDisposition.COMMIT,
            None,
            checks,
            binding, current_revision, current_snapshot,
            authorized=True)
