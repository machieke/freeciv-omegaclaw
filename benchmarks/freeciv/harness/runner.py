"""Resumable, isolated, deterministically assigned harness controller."""

import concurrent.futures
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import threading

from freeciv_agent.events.schema import structural_hash
from freeciv_agent.events.validator import validate_file
from freeciv_agent.paths import REPO_ROOT

from .config import CapabilityContext, load
from .representative import run_game as representative_game
from .engine_live import run_game as engine_live_game


def _atomic_json(path, value):
    temporary = path + ".tmp.{}".format(os.getpid())
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _source_identity():
    """Hash every target-agent/runtime source used by an engine harness game."""
    roots = (
        os.path.join(REPO_ROOT, "src", "freeciv_agent"),
        os.path.join(REPO_ROOT, "benchmarks", "freeciv"),
        os.path.join(REPO_ROOT, "schemas"),
    )
    files = []
    for root in roots:
        for directory, names, filenames in os.walk(root):
            names[:] = sorted(name for name in names if name != "__pycache__")
            for name in sorted(filenames):
                if name.endswith((".py", ".json", ".yaml", ".yml", ".metta", ".c")):
                    files.append(os.path.join(directory, name))
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
        digest.update(relative.encode("utf-8") + b"\0")
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", True
    return {"commit": commit, "dirty": dirty,
            "implementation_sha256": digest.hexdigest(), "source_files": len(files)}


class HarnessRunner(object):
    def __init__(self, out, config_path=None, backend="representative",
                 workers=1, base_port=6100, seed_limit=None, conditions=None):
        self.out = os.path.abspath(out)
        self.config = load(config_path)
        self.backend = backend
        self.workers = max(1, int(workers))
        self.base_port = int(base_port)
        self.seed_limit = None if seed_limit is None else max(1, int(seed_limit))
        self.conditions = tuple(conditions or self.config["conditions"])
        self.source_identity = _source_identity()
        unknown = sorted(set(self.conditions) - set(self.config["conditions"]))
        if unknown:
            raise ValueError("unknown harness conditions {}".format(unknown))
        self._lock = threading.Lock()
        if backend not in ("representative", "engine-live"):
            raise ValueError("unknown harness backend {}".format(backend))
        if backend == "engine-live":
            self.base_port = int(self.config.get("live", {}).get("civserver_port", base_port))
            if self.workers > 9 or self.base_port < 6001 or self.base_port + self.workers - 1 > 6009:
                raise ValueError("engine-live workers require dedicated ports within 6001-6009")

    def _jobs(self, include_induction=True, include_grading=True):
        jobs = []
        seeds = self.config["seeds"][:self.seed_limit]
        for condition in self.conditions:
            for seed in seeds:
                jobs.append({"condition": condition, "seed": seed, "track": "main", "sequence": 0})
        if include_induction:
            # Consecutive same-opponent sequence for both memory-capable conditions.
            for condition in ("d_uncertain_monitor", "e_full_loop"):
                if condition not in self.conditions:
                    continue
                for sequence in range(1, self.config["induction"]["games"] + 1):
                    jobs.append({
                        "condition": condition, "seed": self.config["seeds"][(sequence - 1) % 30],
                        "track": "induction", "sequence": sequence})
        if include_grading:
            # Same full-loop implementation, selection policy as the only A/B toggle.
            for mode in ("ungraded", "graded"):
                if "e_full_loop" not in self.conditions:
                    continue
                for seed in seeds:
                    jobs.append({
                        "condition": "e_full_loop", "seed": seed,
                        "track": "grading_{}".format(mode), "sequence": 0})
        return jobs

    def _manifest(self, job, worker):
        game_id = "m7-{}-{}-{}-{:02d}".format(
            job["track"], job["condition"], job["seed"], job["sequence"])
        run_dir = os.path.join(self.out, "games", job["track"], job["condition"],
                               "{}-{:02d}".format(job["seed"], job["sequence"]))
        material = {
            "backend": self.backend, "beliefs": self.config["beliefs"],
            "capabilities": self.config["capabilities"][job["condition"]],
            "condition_id": job["condition"], "configuration_hash": self.config["configuration_hash"],
            # Total concurrency changes local-model queueing and can therefore
            # change bounded-timeout/fallback behavior. Keep it in behavioral
            # identity even though the individual worker slot and port remain
            # operational details.
            "controller_workers": self.workers,
            "engine": self.config["engine"], "game_id": game_id,
            "machine_profile": self.config["machine_profile"],
            "model": self.config["model"]["name"], "model_config": self.config["model"],
            "opponent": (self.config["induction"] if job["track"] == "induction"
                         else self.config["opponent"]),
            "rulebase": self.config["rulebase"],
            "ruleset": self.config["ruleset"], "seed": job["seed"],
            "sequence": job["sequence"], "track": job["track"],
            "source": self.source_identity,
            "events_schema_version": "1.0",
            "runtime": {
                "ended_at": None, "platform": platform.platform(),
                "python": platform.python_version(), "started_at": None,
            },
            "turn_limit": self.config["turn_limit"],
            "engine_max_turns": self.config.get(
                "engine_max_turns", self.config["turn_limit"]),
            "worker": worker,
        }
        identity_material = {key: value for key, value in material.items()
                             if key not in ("runtime", "worker")}
        material["manifest_identity"] = structural_hash(identity_material)
        # Each retry needs a fresh proxy authentication identity even though its
        # behavioral manifest identity remains stable. Filled immediately before
        # execution and retained as operational evidence.
        material["attempt_id"] = None
        material["events_path"] = "events.jsonl"
        material["_run_dir"] = run_dir
        material["port"] = self.base_port + worker
        return material

    def _run_one(self, indexed_job, resume):
        index, job = indexed_job
        worker = index % self.workers
        manifest = self._manifest(job, worker)
        run_dir = manifest["_run_dir"]
        events_path = os.path.join(run_dir, manifest["events_path"])
        status_path = os.path.join(run_dir, "status.json")
        if resume and os.path.isfile(status_path):
            status = json.load(open(status_path, encoding="utf-8"))
            persisted_path = os.path.join(run_dir, "manifest.json")
            persisted = (json.load(open(persisted_path, encoding="utf-8"))
                         if os.path.isfile(persisted_path) else {})
            if (status.get("status") == "completed"
                    and persisted.get("manifest_identity") == manifest["manifest_identity"]
                    and persisted.get("configuration_hash") == manifest["configuration_hash"]):
                report = validate_file(events_path)
                if report.valid:
                    return dict(manifest=manifest, status=status, resumed=True)
        os.makedirs(run_dir, exist_ok=True)
        if os.path.exists(events_path):
            os.remove(events_path)
        started_at = _utc_now()
        manifest["runtime"]["started_at"] = started_at
        manifest["attempt_id"] = structural_hash([
            manifest["manifest_identity"], started_at])[:16]
        persisted_manifest = {key: value for key, value in manifest.items()
                              if not key.startswith("_")}
        _atomic_json(os.path.join(run_dir, "manifest.json"), persisted_manifest)
        _atomic_json(status_path, {
            "status": "running", "completed": False,
            "infrastructure_failure": False,
            "manifest_identity": manifest["manifest_identity"],
        })
        try:
            context = CapabilityContext(
                job["condition"], self.config["capabilities"][job["condition"]])
            backend = engine_live_game if self.backend == "engine-live" else representative_game
            result = backend(run_dir, manifest, context)
            validation = validate_file(events_path)
            if not validation.valid:
                raise RuntimeError("event validation failed: {}".format(validation.to_dict()))
            status = dict(result, status="completed", event_count=validation.event_count)
        except Exception as exc:
            status = {"status": "infrastructure_failure", "completed": False,
                      "infrastructure_failure": True,
                      "error": "{}: {}".format(type(exc).__name__, str(exc)[:1000])}
        manifest["runtime"]["ended_at"] = _utc_now()
        persisted_manifest["runtime"]["ended_at"] = manifest["runtime"]["ended_at"]
        _atomic_json(os.path.join(run_dir, "manifest.json"), persisted_manifest)
        _atomic_json(status_path, status)
        return dict(manifest=manifest, status=status, resumed=False)

    def run(self, resume=True, include_induction=True, include_grading=True):
        os.makedirs(self.out, exist_ok=True)
        jobs = list(enumerate(self._jobs(include_induction, include_grading)))
        if self.workers == 1:
            results = [self._run_one(job, resume) for job in jobs]
        else:
            # Bind each deterministic worker number to one serial bucket so two
            # executor threads can never recycle or connect to the same server
            # port. Opponent-memory games remain globally sequential.
            induction = [job for job in jobs if job[1]["track"] == "induction"]
            parallel = [job for job in jobs if job[1]["track"] != "induction"]
            buckets = [[] for _ in range(self.workers)]
            for job in parallel:
                buckets[job[0] % self.workers].append(job)

            def run_bucket(bucket):
                return [self._run_one(job, resume) for job in bucket]

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
                grouped = list(pool.map(run_bucket, buckets))
            results = [row for group in grouped for row in group]
            results.extend(self._run_one(job, resume) for job in induction)
        summary = {
            "backend": self.backend, "completed": sum(
                row["status"].get("status") == "completed" for row in results),
            "configuration_hash": self.config["configuration_hash"],
            "infrastructure_failures": sum(
                row["status"].get("status") == "infrastructure_failure" for row in results),
            "jobs": len(results), "machine": platform.platform(),
            "resumed": sum(row["resumed"] for row in results),
        }
        _atomic_json(os.path.join(self.out, "run-summary.json"), summary)
        return summary
