"""Reproducible run manifests for every FreeCiv condition.

The manifest identity intentionally excludes timestamps, output paths, and host
details.  It includes the repository commit plus a hash of the dirty worktree,
so two runs only share an identity when their behavior-defining inputs match.
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid

from . import __version__
from .config import condition as load_condition
from .paths import REPO_ROOT


SCHEMA_VERSION = "1.0"
DEFAULT_EVENTS_SCHEMA_VERSION = "1.0"


class ManifestError(ValueError):
    """A required reproducibility field is absent or invalid."""


def _run_git(args, cwd=REPO_ROOT):
    try:
        return subprocess.check_output(
            ["git"] + list(args), cwd=cwd, stderr=subprocess.DEVNULL).decode("utf-8", "replace").strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def repository_identity(repo_root=REPO_ROOT):
    """Return commit and dirty-patch identity for ``repo_root``."""
    commit = _run_git(["rev-parse", "HEAD"], cwd=repo_root)
    if not commit:
        raise ManifestError("repository is not a readable Git checkout: {}".format(repo_root))
    status = _run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_root) or ""
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--binary", "HEAD", "--"], cwd=repo_root, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestError("cannot hash repository diff: {}".format(exc))
    dirty_material = status.encode("utf-8") + b"\0" + diff
    return {
        "commit": commit,
        "dirty": bool(status),
        "dirty_sha256": _sha256_bytes(dirty_material),
    }


def external_git_commit(path):
    """Return an external dependency commit, or ``None`` when not configured."""
    if not path:
        return None
    path = os.path.abspath(path)
    return _run_git(["rev-parse", "HEAD"], cwd=path)


def stable_manifest_content(manifest):
    """Behavior-defining subset used to calculate ``manifest_identity``."""
    keys = ("condition", "source", "engine", "rulebase", "llm", "game", "beliefs", "events")
    return {key: manifest[key] for key in keys}


def calculate_identity(manifest):
    return _sha256_bytes(_canonical_bytes(stable_manifest_content(manifest)))


def validate_manifest(manifest):
    required = (
        "schema_version", "run_id", "manifest_identity", "created_at", "condition", "source",
        "engine", "rulebase", "llm", "game", "beliefs", "events", "runtime",
    )
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ManifestError("manifest missing fields: {}".format(missing))
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ManifestError("unsupported manifest schema_version: {}".format(manifest["schema_version"]))
    if not isinstance(manifest["game"].get("seed"), int):
        raise ManifestError("game.seed must be an integer")
    if manifest["condition"].get("id") not in (
            "a_stock_llm", "b_state_oracle", "c_dependency_scheduler",
            "d_uncertain_monitor", "e_full_loop"):
        raise ManifestError("unknown condition id")
    expected = calculate_identity(manifest)
    if manifest["manifest_identity"] != expected:
        raise ManifestError("manifest_identity mismatch: expected {}".format(expected))
    return manifest


def build_manifest(
        condition_id, game_id, seed, ruleset, turn_limit, provider, model,
        base_url=None, temperature=None, max_tokens=None, opponent="builtin-ai",
        difficulty="normal", freeciv_commit=None, proxy_commit=None,
        engine_image_digest=None, ruleset_source_sha256=None,
        compiler_version="legacy-uncompiled", rulebase_sha256=None,
        events_schema_version=DEFAULT_EVENTS_SCHEMA_VERSION,
        beliefs=None, run_id=None, repo_root=REPO_ROOT):
    """Build and validate a complete run manifest."""
    cond = load_condition(condition_id)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or uuid.uuid4().hex,
        "manifest_identity": "",
        "created_at": _utc_now(),
        "condition": cond,
        "source": dict(repository_identity(repo_root), agent_package_version=__version__),
        "engine": {
            "freeciv_commit": freeciv_commit,
            "proxy_commit": proxy_commit,
            "image_digest": engine_image_digest,
            "ruleset": ruleset,
            "ruleset_source_sha256": ruleset_source_sha256,
        },
        "rulebase": {
            "compiler_version": compiler_version,
            "artifact_sha256": rulebase_sha256,
        },
        "llm": {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "sampling": {"temperature": temperature, "max_tokens": max_tokens},
        },
        "game": {
            "game_id": game_id,
            "seed": int(seed),
            "opponent": opponent,
            "difficulty": difficulty,
            "turn_limit": int(turn_limit),
        },
        "beliefs": beliefs or {
            "decay_schedule": None,
            "dampening_lambda": None,
            "actionable_threshold": None,
        },
        "events": {"schema_version": events_schema_version},
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    manifest["manifest_identity"] = calculate_identity(manifest)
    return validate_manifest(manifest)


def write_manifest(path, manifest):
    validate_manifest(manifest)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp.{}".format(os.getpid())
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")
    os.replace(tmp, path)
    return path


def _provider_defaults(name):
    try:
        import provider_config
        row = provider_config.provider_entry(name)
        return row.get("model"), row.get("base_url")
    except Exception:
        return None, None


def main(argv=None):
    parser = argparse.ArgumentParser(description="write a reproducible FreeCiv run manifest")
    parser.add_argument("--out", required=True)
    parser.add_argument("--condition", choices=(
        "a_stock_llm", "b_state_oracle", "c_dependency_scheduler",
        "d_uncertain_monitor", "e_full_loop"), default="a_stock_llm")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ruleset", default="civ2civ3")
    parser.add_argument("--turn-limit", type=int, default=200)
    parser.add_argument("--provider", default=os.environ.get("FREECIV_PROVIDER", "Ollama-local"))
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--opponent", default="builtin-ai")
    parser.add_argument("--difficulty", default="normal")
    parser.add_argument("--freeciv-commit")
    parser.add_argument("--proxy-commit")
    parser.add_argument("--engine-image-digest")
    parser.add_argument("--freeciv-llm-root", default=os.environ.get("FREECIV_LLM_ROOT"))
    args = parser.parse_args(argv)
    default_model, default_url = _provider_defaults(args.provider)
    external = external_git_commit(args.freeciv_llm_root)
    manifest = build_manifest(
        condition_id=args.condition, game_id=args.game_id, seed=args.seed,
        ruleset=args.ruleset, turn_limit=args.turn_limit, provider=args.provider,
        model=args.model or default_model or "unknown", base_url=args.base_url or default_url,
        temperature=args.temperature, max_tokens=args.max_tokens, opponent=args.opponent,
        difficulty=args.difficulty, freeciv_commit=args.freeciv_commit or external,
        proxy_commit=args.proxy_commit or external, engine_image_digest=args.engine_image_digest,
    )
    write_manifest(args.out, manifest)
    print(json.dumps({
        "manifest": os.path.abspath(args.out),
        "run_id": manifest["run_id"],
        "manifest_identity": manifest["manifest_identity"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

