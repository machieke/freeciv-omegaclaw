"""Bounded asynchronous execution for non-authoritative domain estimates."""

import concurrent.futures
import threading
import time
from collections import OrderedDict, deque


class DomainEstimateShadowExecutor:
    """Run immutable shadow batches without delaying live action selection.

    The executor is deliberately single-worker and bounded.  Results are
    observational artifacts only: worker failure, queue saturation, or result
    timing can never authorize or alter a live decision.
    """

    def __init__(
            self, maximum_pending=2, maximum_cached=8,
            thread_name_prefix="freeciv-domain-shadow",
            count_field="estimate_count",
            collection_field="estimates",
            completed_count_key="completed_estimate_count"):
        maximum_pending = int(maximum_pending)
        maximum_cached = int(maximum_cached)
        if maximum_pending < 1:
            raise ValueError(
                "shadow executor pending capacity must be positive")
        if maximum_cached < maximum_pending:
            raise ValueError(
                "shadow executor cache must cover pending capacity")
        for value, name in (
                (thread_name_prefix,
                 "shadow thread prefix"),
                (count_field,
                 "shadow count field"),
                (collection_field,
                 "shadow collection field"),
                (completed_count_key,
                 "shadow completed-count key")):
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "{} must be non-empty".format(name))
        self.maximum_pending = maximum_pending
        self.maximum_cached = maximum_cached
        self.count_field = count_field
        self.collection_field = collection_field
        self.completed_count_key = (
            completed_count_key)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=thread_name_prefix)
        self._lock = threading.RLock()
        self._pending = {}
        self._completed = OrderedDict()
        self._ready = deque()
        self._closed = False
        self._submitted_count = 0
        self._completed_count = 0
        self._failed_count = 0
        self._capacity_rejection_count = 0
        self._completed_item_count = 0

    @staticmethod
    def _run(submitted_at, function, arguments):
        started_at = time.perf_counter()
        payload = function(*arguments)
        finished_at = time.perf_counter()
        if not isinstance(payload, dict):
            raise TypeError(
                "shadow domain batch must return an artifact dictionary")
        return {
            "payload": payload,
            "queue_delay_ms": (
                started_at - submitted_at) * 1000.0,
            "worker_latency_ms": (
                finished_at - started_at) * 1000.0,
            "end_to_end_latency_ms": (
                finished_at - submitted_at) * 1000.0,
        }

    def _store_completed_locked(self, batch_id, artifact):
        self._completed[batch_id] = artifact
        self._completed.move_to_end(batch_id)
        self._ready.append(batch_id)
        while len(self._completed) > self.maximum_cached:
            evicted_id, _ = self._completed.popitem(last=False)
            self._ready = deque(
                value for value in self._ready
                if value != evicted_id)

    def _harvest_locked(self):
        for batch_id, pending in tuple(self._pending.items()):
            future, failure_artifact = pending
            if not future.done():
                continue
            del self._pending[batch_id]
            try:
                result = future.result()
            except Exception as error:
                artifact = dict(failure_artifact)
                artifact.update({
                    "error_type": type(error).__name__,
                    self.count_field: 0,
                    self.collection_field: [],
                    "status": "failed",
                })
                self._failed_count += 1
            else:
                artifact = dict(result["payload"])
                artifact.update({
                    "end_to_end_latency_ms":
                        float(result["end_to_end_latency_ms"]),
                    "queue_delay_ms":
                        float(result["queue_delay_ms"]),
                    "status": "completed",
                    "worker_latency_ms":
                        float(result["worker_latency_ms"]),
                })
                self._completed_item_count += int(
                    artifact.get(
                        self.count_field, 0))
            self._completed_count += 1
            self._store_completed_locked(
                batch_id, artifact)

    def submit(
            self, batch_id, function, arguments=(),
            failure_artifact=None):
        if not isinstance(batch_id, str) or not batch_id:
            raise ValueError(
                "shadow estimate batch requires a batch ID")
        if not callable(function):
            raise TypeError(
                "shadow estimate batch requires a callable")
        arguments = tuple(arguments)
        with self._lock:
            if self._closed:
                return "closed"
            self._harvest_locked()
            if batch_id in self._completed:
                return "cached"
            if batch_id in self._pending:
                return "pending"
            if len(self._pending) >= self.maximum_pending:
                self._capacity_rejection_count += 1
                return "capacity"
            submitted_at = time.perf_counter()
            future = self._executor.submit(
                self._run, submitted_at,
                function, arguments)
            self._pending[batch_id] = (
                future, dict(failure_artifact or {
                    "batch_id": batch_id,
                    "shadow_only": True,
                }))
            self._submitted_count += 1
            return "submitted"

    def poll(self, preferred_batch_id=None):
        """Return one completed artifact without waiting."""
        with self._lock:
            self._harvest_locked()
            if preferred_batch_id in self._completed:
                self._ready = deque(
                    value for value in self._ready
                    if value != preferred_batch_id)
                return self._completed[preferred_batch_id]
            while self._ready:
                batch_id = self._ready.popleft()
                if batch_id in self._completed:
                    return self._completed[batch_id]
            return None

    def wait(self, batch_id, timeout=None):
        """Wait for one known batch, primarily for replay and shutdown."""
        with self._lock:
            self._harvest_locked()
            if batch_id in self._completed:
                return self._completed[batch_id]
            pending = self._pending.get(batch_id)
        if pending is None:
            return None
        done, _ = concurrent.futures.wait(
            (pending[0],), timeout=timeout)
        if not done:
            raise concurrent.futures.TimeoutError()
        with self._lock:
            self._harvest_locked()
            return self._completed.get(batch_id)

    def flush(self, timeout=None):
        """Wait for pending work and return the currently retained results."""
        with self._lock:
            self._harvest_locked()
            futures = tuple(
                pending[0]
                for pending in self._pending.values())
        if futures:
            concurrent.futures.wait(
                futures, timeout=timeout)
        with self._lock:
            self._harvest_locked()
            return tuple(self._completed.values())

    def statistics(self):
        with self._lock:
            self._harvest_locked()
            result = {
                "cache_size": len(self._completed),
                "capacity_rejection_count":
                    self._capacity_rejection_count,
                "completed_batch_count":
                    self._completed_count,
                "failed_batch_count":
                    self._failed_count,
                "maximum_cached": self.maximum_cached,
                "maximum_pending": self.maximum_pending,
                "pending_batch_count":
                    len(self._pending),
                "submitted_batch_count":
                    self._submitted_count,
            }
            result[self.completed_count_key] = (
                self._completed_item_count)
            return result

    def close(self, wait=True):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=bool(wait))
