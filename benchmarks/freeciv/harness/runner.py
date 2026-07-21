"""Resumable, isolated, deterministically assigned harness controller."""

import concurrent.futures
import copy
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


_IMPACT_COHORT_TOKENS = {
    "development": "dev", "pilot": "pilot",
    "pilot_horizon_60": "p60",
    "pilot_horizon_60_v2": "p60v2",
    "pilot_horizon_60_v3": "p60v3",
    "confirmatory_score": "cscore",
    "confirmatory_score_horizon_60_v1": "cs60v1",
    "confirmatory_joint": "cjoint",
}


def _impact_cohort_token(name):
    """Keep declared IDs stable and safely identify arbitrary valid cohorts."""
    return _IMPACT_COHORT_TOKENS.get(
        name, "x" + structural_hash(["impact-cohort", name])[:10])


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
                 workers=1, base_port=6100, seed_limit=None, conditions=None,
                 impact_cohort=None):
        self.out = os.path.abspath(out)
        self.config = load(config_path)
        self.backend = backend
        self.workers = max(1, int(workers))
        self.base_port = int(base_port)
        self.seed_limit = None if seed_limit is None else max(1, int(seed_limit))
        self.conditions = tuple(conditions or self.config["conditions"])
        self.source_identity = _source_identity()
        paired = self.config.get("paired_impact", {})
        self.impact_cohort = impact_cohort or paired.get("default_cohort")
        if paired and self.impact_cohort not in paired.get("cohorts", {}):
            raise ValueError("unknown paired impact cohort {}".format(self.impact_cohort))
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

    def _impact_jobs(self):
        paired = self.config.get("paired_impact")
        if paired is None:
            raise ValueError("configuration does not declare paired_impact")
        cohort = paired["cohorts"][self.impact_cohort]
        seeds = cohort["seeds"][:self.seed_limit]
        jobs = []
        for pair_index, seed in enumerate(seeds):
            order = (("baseline", "treatment") if pair_index % 2 == 0
                     else ("treatment", "baseline"))
            for within_pair_order, arm in enumerate(order):
                jobs.append({
                    "cohort": self.impact_cohort,
                    "condition": paired["condition"], "pair_index": pair_index,
                    "policy_arm": arm, "seed": seed, "sequence": 0,
                    "track": "impact_pair", "within_pair_order": within_pair_order,
                })
        return jobs

    def _manifest(self, job, worker):
        arm = job.get("policy_arm")
        game_id = ("m7-ip-{}-{}-{}-{:02d}-{}".format(
            _impact_cohort_token(job["cohort"]), arm[0], job["seed"],
            job["sequence"],
            structural_hash([
                job["track"], job["cohort"], arm, job["condition"]])[:8])
                   if arm is not None else "m7-{}-{}-{}-{:02d}".format(
            job["track"], job["condition"], job["seed"], job["sequence"]))
        run_parts = [self.out, "games", job["track"]]
        if arm is not None:
            run_parts.append(job["cohort"])
            run_parts.append(arm)
        run_parts.extend((job["condition"],
                          "{}-{:02d}".format(job["seed"], job["sequence"])))
        run_dir = os.path.join(*run_parts)
        impact_policy = copy.deepcopy(self.config["impact_policy"])
        horizon_turn = self.config["turn_limit"]
        if arm is not None:
            cohort_design = self.config["paired_impact"]["cohorts"][job["cohort"]]
            horizon_turn = cohort_design.get(
                "horizon_turn", self.config["paired_impact"]["outcomes"]["horizon_turn"])
            impact_policy.update(self.config["paired_impact"]["arms"][arm])
            impact_policy["horizon_turn"] = horizon_turn
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
            "impact_policy": impact_policy,
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
            "turn_limit": horizon_turn,
            "engine_max_turns": max(
                horizon_turn, self.config.get("engine_max_turns", horizon_turn)),
            "worker": worker,
        }
        if arm is not None:
            material["impact_pair"] = {
                "arm": arm, "experimental_unit": "seed_pair",
                "cohort": job["cohort"],
                "cohort_purpose": cohort_design["purpose"],
                "claim_eligible": cohort_design["claim_eligible"],
                "pair_index": job["pair_index"],
                "planned_pairs": cohort_design["planned_pairs"],
                "require_clean_source": cohort_design["require_clean_source"],
                "seed_derivation": cohort_design.get("seed_derivation"),
                "score_design": cohort_design.get("score_design"),
                "horizon_turn": horizon_turn,
                "within_pair_order": job["within_pair_order"],
            }
            material["impact_outcomes"] = copy.deepcopy(
                self.config["paired_impact"]["outcomes"])
            material["impact_outcomes"]["horizon_turn"] = horizon_turn
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
        # Preserve every superseded attempt outside ``games`` so aggregation
        # sees only the active arm while paired failure reporting can retain
        # the full operational history.
        persisted_path = os.path.join(run_dir, "manifest.json")
        if os.path.isfile(status_path) and os.path.isfile(persisted_path):
            persisted = json.load(open(persisted_path, encoding="utf-8"))
            attempt_id = persisted.get("attempt_id") or structural_hash([
                persisted.get("manifest_identity"), persisted.get("runtime")])[:16]
            relative = os.path.relpath(run_dir, os.path.join(self.out, "games"))
            archive = os.path.join(
                self.out, "attempt-history", relative, str(attempt_id))
            os.makedirs(archive, exist_ok=True)
            for name in ("manifest.json", "status.json", "events.jsonl"):
                source = os.path.join(run_dir, name)
                if os.path.isfile(source):
                    shutil.copy2(source, os.path.join(archive, name))
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

    def run_impact_pairs(self, resume=True):
        """Run paired policy arms serially in predeclared alternating order."""
        if self.workers != 1:
            raise ValueError("paired impact evaluation requires workers=1")
        cohort = self.config["paired_impact"]["cohorts"][self.impact_cohort]
        if cohort["claim_eligible"] and self.seed_limit is not None:
            raise ValueError(
                "confirmatory cohort {} cannot use a pair limit".format(
                    self.impact_cohort))
        if cohort["require_clean_source"]:
            # Refresh immediately before the first arm so a runner constructed
            # before later edits cannot retain a stale clean identity.
            self.source_identity = _source_identity()
            if self.source_identity.get("commit") in (None, "", "unavailable"):
                raise RuntimeError(
                    "{} cohort requires a readable committed source identity".format(
                        self.impact_cohort))
            if self.source_identity.get("dirty"):
                raise RuntimeError(
                    "{} cohort requires a clean source tree; commit all changes first".format(
                        self.impact_cohort))
        os.makedirs(self.out, exist_ok=True)
        jobs = list(enumerate(self._impact_jobs()))
        results = [self._run_one(job, resume) for job in jobs]
        summary = {
            "backend": self.backend,
            "completed": sum(row["status"].get("status") == "completed"
                             for row in results),
            "configuration_hash": self.config["configuration_hash"],
            "infrastructure_failures": sum(
                row["status"].get("status") == "infrastructure_failure"
                for row in results),
            "jobs": len(results), "machine": platform.platform(),
            "paired_impact": True,
            "cohort": self.impact_cohort,
            "cohort_purpose": cohort["purpose"],
            "claim_eligible": cohort["claim_eligible"],
            "pairs": len(self._impact_jobs()) // 2,
            "resumed": sum(row["resumed"] for row in results),
        }
        if cohort["require_clean_source"]:
            ending_source = _source_identity()
            summary["source_stable"] = ending_source == self.source_identity
        else:
            summary["source_stable"] = None
        _atomic_json(os.path.join(self.out, "impact-run-summary.json"), summary)
        if summary["source_stable"] is False:
            raise RuntimeError(
                "{} cohort source changed during execution; artifacts are not claim eligible"
                .format(self.impact_cohort))
        return summary
