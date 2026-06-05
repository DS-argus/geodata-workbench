from __future__ import annotations

from threading import Event

from app.jobs.runner import BackgroundJobRunner


def test_background_job_runner_runs_job() -> None:
    ran = Event()

    def target(job_id: int, request: str, cancel_event: Event) -> None:
        assert job_id == 10
        assert request == "payload"
        assert not cancel_event.is_set()
        ran.set()

    runner = BackgroundJobRunner[str](max_workers=1, thread_name_prefix="test-runner")
    runner.start(10, target, "payload")

    assert ran.wait(timeout=2)


def test_background_job_runner_cancel_sets_event() -> None:
    started = Event()
    release = Event()
    observed_cancel = Event()

    def target(_job_id: int, _request: None, cancel_event: Event) -> None:
        started.set()
        assert release.wait(timeout=2)
        if cancel_event.is_set():
            observed_cancel.set()

    runner = BackgroundJobRunner[None](max_workers=1, thread_name_prefix="test-cancel-runner")
    runner.start(20, target, None)

    assert started.wait(timeout=2)
    assert runner.cancel(20)
    release.set()
    assert observed_cancel.wait(timeout=2)
