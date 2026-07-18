"""Subtree-local proof/plan repair with immutable structural reuse."""

import time
from dataclasses import replace

from .model import RepairResult


class LocalRepairer(object):
    def __init__(self, rederive, timeout_ms=2000.0):
        self.rederive = rederive
        self.timeout_ms = float(timeout_ms)

    def repair(self, invalidation, proof_subtrees):
        """Re-derive only affected hashes; reuse every other immutable subtree."""
        started = time.perf_counter()
        all_hashes = frozenset(str(value) for value in proof_subtrees)
        affected = tuple(sorted(set(invalidation.affected_subtree_hashes)))
        reused = tuple(sorted(all_hashes - set(affected)))
        if not affected:
            return RepairResult(
                "NO_PLAN", invalidation.invalidation_id, None, reused, (),
                (time.perf_counter() - started) * 1000.0,
                "BROKEN_ASSUMPTION_HAS_NO_SUBTREE")
        derived = []
        replacement_plan = None
        for subtree_hash in affected:
            if (time.perf_counter() - started) * 1000.0 > self.timeout_ms:
                return RepairResult(
                    "NO_PLAN", invalidation.invalidation_id, None, reused,
                    tuple(derived), (time.perf_counter() - started) * 1000.0,
                    "REPAIR_TIMEOUT")
            result = self.rederive(subtree_hash, invalidation)
            if result is None:
                return RepairResult(
                    "NO_PLAN", invalidation.invalidation_id, None, reused,
                    tuple(derived), (time.perf_counter() - started) * 1000.0,
                    "NO_REPLACEMENT_FOR_SUBTREE")
            derived_hash, candidate_plan = result
            derived.append(str(derived_hash))
            replacement_plan = candidate_plan or replacement_plan
        latency = (time.perf_counter() - started) * 1000.0
        if replacement_plan is None:
            return RepairResult("NO_PLAN", invalidation.invalidation_id, None, reused,
                                tuple(derived), latency, "PLANNER_RETURNED_NO_PLAN")
        try:
            replacement_plan = replace(
                replacement_plan, reused_subtree_hashes=reused,
                rederived_subtree_hashes=tuple(derived))
        except (TypeError, ValueError):
            pass
        return RepairResult("REPAIRED", invalidation.invalidation_id,
                            replacement_plan, reused, tuple(derived), latency)
