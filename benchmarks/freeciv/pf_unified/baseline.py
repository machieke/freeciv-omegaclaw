"""Strict baseline identity, verification, and comparison guards."""

import copy
import hashlib
import os
import subprocess

import yaml

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.paths import REPO_ROOT


DEFAULT_MANIFEST = os.path.join(
    REPO_ROOT, "benchmarks", "freeciv", "pf_unified",
    "baseline_manifest.yaml")
_SOURCE_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".metta", ".c")
_SOURCE_ROOTS = ("src/freeciv_agent", "benchmarks/freeciv", "schemas")
_TOP_LEVEL_FIELDS = {
    "baseline_id", "branch", "fixtures", "golden", "platform_profile",
    "random_seed", "repository", "ruleset", "runtime", "schema_version",
    "solvers", "source",
}


class BaselineIdentityError(ValueError):
    """Raised when benchmark identities are not scientifically comparable."""


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_mapping(value, name):
    if not isinstance(value, dict):
        raise BaselineIdentityError("{} must be an object".format(name))
    return value


def load_baseline_manifest(path=None):
    path = os.path.abspath(path or DEFAULT_MANIFEST)
    with open(path, encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    _require_mapping(value, "baseline manifest")
    if set(value) != _TOP_LEVEL_FIELDS:
        raise BaselineIdentityError(
            "baseline fields mismatch: missing={} extra={}".format(
                sorted(_TOP_LEVEL_FIELDS - set(value)),
                sorted(set(value) - _TOP_LEVEL_FIELDS)))
    if value.get("schema_version") != "1.0":
        raise BaselineIdentityError("baseline schema_version must be 1.0")
    for name in (
            "fixtures", "golden", "ruleset", "runtime", "solvers", "source"):
        _require_mapping(value.get(name), name)
    if not isinstance(value["fixtures"].get("files"), list):
        raise BaselineIdentityError("fixtures.files must be a list")
    if not isinstance(value["golden"].get("artifacts"), list):
        raise BaselineIdentityError("golden.artifacts must be a list")
    return copy.deepcopy(value)


def comparison_identity(manifest):
    """Return fields that must match for a direct result comparison."""
    manifest = copy.deepcopy(manifest)
    return {
        "fixtures_sha256": manifest["fixtures"]["fixture_set_sha256"],
        "ruleset": manifest["ruleset"],
        "runtime": manifest["runtime"],
        "solvers": manifest["solvers"],
        "source": manifest["source"],
    }


def baseline_identity(manifest):
    return structural_hash(comparison_identity(manifest))


def assert_comparable(left, right, allow_cross_version=False):
    """Refuse mismatched comparisons unless explicitly authorized."""
    left_identity = comparison_identity(left)
    right_identity = comparison_identity(right)
    mismatches = tuple(
        name for name in sorted(left_identity)
        if left_identity[name] != right_identity[name])
    if mismatches and not allow_cross_version:
        raise BaselineIdentityError(
            "benchmark identity mismatch in {}; pass the explicit "
            "cross-version flag to compare descriptively".format(
                ", ".join(mismatches)))
    return {
        "allow_cross_version": bool(allow_cross_version),
        "comparable": not mismatches,
        "mismatches": list(mismatches),
    }


def _git_source_identity(commit):
    command = [
        "git", "ls-tree", "-r", "--name-only", str(commit), "--",
    ] + list(_SOURCE_ROOTS)
    try:
        output = subprocess.check_output(
            command, cwd=REPO_ROOT, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BaselineIdentityError(
            "cannot read archived source identity: {}".format(exc))
    paths = sorted(
        line.decode("utf-8") for line in output.splitlines()
        if line.decode("utf-8").endswith(_SOURCE_SUFFIXES)
        and "__pycache__" not in line.decode("utf-8").split("/"))
    digest = hashlib.sha256()
    for relative in paths:
        try:
            data = subprocess.check_output(
                ["git", "show", "{}:{}".format(commit, relative)],
                cwd=REPO_ROOT, stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BaselineIdentityError(
                "cannot read archived source {}: {}".format(relative, exc))
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(data)
        digest.update(b"\0")
    return {
        "commit": str(commit),
        "implementation_sha256": digest.hexdigest(),
        "source_files": len(paths),
    }


def _verify_rows(rows):
    mismatches = []
    actual_rows = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise BaselineIdentityError(
                "artifact rows must contain only path and sha256")
        relative = str(row["path"])
        path = os.path.join(REPO_ROOT, relative)
        actual = None if not os.path.isfile(path) else _file_sha256(path)
        actual_rows.append({"path": relative, "sha256": actual})
        if actual != row["sha256"]:
            mismatches.append({
                "actual": actual, "expected": row["sha256"],
                "path": relative,
            })
    return actual_rows, mismatches


def verify_baseline(manifest=None):
    """Verify archived source, fixtures, and committed golden bytes."""
    manifest = load_baseline_manifest() if manifest is None else copy.deepcopy(
        manifest)
    archived_source = _git_source_identity(manifest["source"]["commit"])
    expected_source = dict(manifest["source"])
    source_matches = archived_source == expected_source
    fixture_rows, fixture_mismatches = _verify_rows(
        manifest["fixtures"]["files"])
    fixture_set_sha256 = structural_hash(fixture_rows)
    golden_rows, golden_mismatches = _verify_rows(
        manifest["golden"]["artifacts"])
    golden_set_sha256 = structural_hash(golden_rows)
    expected_golden_set = manifest["golden"]["artifact_set_sha256"]
    report = {
        "archived_source": archived_source,
        "baseline_id": manifest["baseline_id"],
        "baseline_identity": baseline_identity(manifest),
        "fixture_mismatches": fixture_mismatches,
        "fixture_set_sha256": fixture_set_sha256,
        "fixture_set_matches": (
            not fixture_mismatches
            and fixture_set_sha256
            == manifest["fixtures"]["fixture_set_sha256"]),
        "golden_mismatches": golden_mismatches,
        "golden_set_sha256": golden_set_sha256,
        "golden_set_matches": (
            not golden_mismatches
            and golden_set_sha256 == expected_golden_set),
        "schema_version": "1.0",
        "source_matches": source_matches,
    }
    report["valid"] = bool(
        source_matches and report["fixture_set_matches"]
        and report["golden_set_matches"])
    report["verification_hash"] = structural_hash(report)
    return report
