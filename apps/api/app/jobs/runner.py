from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Event, Lock, Thread
from typing import Generic, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")
JobTarget = Callable[[int, T, Event], None]


@dataclass
class RunningJob(Generic[T]):
    cancel_event: Event


@dataclass
class QueuedJob(Generic[T]):
    job_id: int
    target: JobTarget[T]
    request: T
    cancel_event: Event


class BackgroundJobRunner(Generic[T]):
    def __init__(self, *, max_workers: int = 2, thread_name_prefix: str = "background-job") -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1.")
        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix
        self._queue: Queue[QueuedJob[T]] = Queue()
        self._lock = Lock()
        self._jobs: dict[int, RunningJob[T]] = {}
        self._workers: list[Thread] = []

    def start(self, job_id: int, target: JobTarget[T], request: T) -> None:
        cancel_event = Event()
        queued_job = QueuedJob(job_id=job_id, target=target, request=request, cancel_event=cancel_event)
        with self._lock:
            if job_id in self._jobs:
                raise ValueError(f"Job {job_id} is already running.")
            self._ensure_workers_started()
            self._jobs[job_id] = RunningJob(cancel_event=cancel_event)
            self._queue.put(queued_job)

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            running_job = self._jobs.get(job_id)
            if running_job is None:
                return False
            running_job.cancel_event.set()
            return True

    def _ensure_workers_started(self) -> None:
        if self._workers:
            return
        for worker_index in range(1, self._max_workers + 1):
            worker = Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"{self._thread_name_prefix}-worker-{worker_index}",
            )
            worker.start()
            self._workers.append(worker)

    def _worker_loop(self) -> None:
        while True:
            queued_job = self._queue.get()
            try:
                queued_job.target(queued_job.job_id, queued_job.request, queued_job.cancel_event)
            except Exception:
                logger.exception("Unhandled background job error: job_id=%s", queued_job.job_id)
            finally:
                with self._lock:
                    self._jobs.pop(queued_job.job_id, None)
                self._queue.task_done()
