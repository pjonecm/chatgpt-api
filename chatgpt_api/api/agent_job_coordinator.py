"""Phase 1C.3 in-process Agent Job coordinator lifecycle.

Owns startup recovery, bounded polling, durable retry promotion, non-running
cancellation finalization, and the single-active-job execution boundary.

Production servers install a real executor callback for eligible queued chat
and deep_research jobs. The coordinator still owns only lifecycle concerns:
startup recovery, bounded polling, retry promotion, cancellation
finalization, and the single active execution boundary.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chatgpt_api.api.agent_jobs import AgentJob, AgentJobRepository
from chatgpt_api.api.admin_store import utc_now

LOGGER = logging.getLogger(__name__)

DEFAULT_LEASE_DURATION_SECONDS = 60
DEFAULT_LEASE_RENEWAL_INTERVAL_SECONDS = 15
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class CoordinatorCycleResult:
    promoted_retry_ids: tuple[str, ...] = ()
    cancelled_job_ids: tuple[str, ...] = ()
    selected_job_id: str | None = None
    executor_invoked: bool = False


class AgentJobCoordinator:
    def __init__(
        self,
        repo: AgentJobRepository,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
        lease_renewal_interval_seconds: int = DEFAULT_LEASE_RENEWAL_INTERVAL_SECONDS,
        now_fn: Callable[[], str] = utc_now,
        executor: Callable[[AgentJob], Any] | None = None,
    ) -> None:
        self._repo = repo
        self._poll_interval_seconds = max(0.01, float(poll_interval_seconds))
        self._lease_duration_seconds = int(lease_duration_seconds)
        self._lease_renewal_interval_seconds = int(lease_renewal_interval_seconds)
        self._now_fn = now_fn
        self._executor = executor

        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._executor_active = False

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    @property
    def lease_duration_seconds(self) -> int:
        return self._lease_duration_seconds

    @property
    def lease_renewal_interval_seconds(self) -> int:
        return self._lease_renewal_interval_seconds

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            self._wake_event.clear()
            self._run_startup_recovery()
            thread = threading.Thread(
                target=self._run_loop,
                name="agent-job-coordinator",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            LOGGER.info(
                "agent job coordinator started poll_interval=%.2fs lease_duration=%ss lease_renewal=%ss",
                self._poll_interval_seconds,
                self._lease_duration_seconds,
                self._lease_renewal_interval_seconds,
            )

    def stop(self) -> None:
        thread: threading.Thread | None
        with self._lock:
            if not self._started:
                return
            self._started = False
            self._stop_event.set()
            self._wake_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=max(1.0, self._poll_interval_seconds * 4))
        LOGGER.info("agent job coordinator stopped")

    def wake(self) -> None:
        self._wake_event.set()

    def run_once(self) -> CoordinatorCycleResult:
        now = self._now_fn()
        promoted = tuple(self._repo.promote_due_retries(now=now))
        if promoted:
            LOGGER.info("agent job coordinator promoted %d due retries", len(promoted))

        cancelled = tuple(self._repo.finalize_pending_cancellations(now=now).cancelled)
        if cancelled:
            LOGGER.info("agent job coordinator finalized %d cancellations", len(cancelled))

        selected_job_id: str | None = None
        executor_invoked = False
        if self._executor is not None and not self._executor_active:
            next_job = self._repo.get_next_queued_job(request_types=("chat", "deep_research"))
            if next_job is not None:
                selected_job_id = next_job.job_id
                LOGGER.info(
                    "agent job coordinator selected queued job_id=%s type=%s",
                    next_job.job_id,
                    next_job.request_type,
                )
                self._executor_active = True
                try:
                    self._executor(next_job)
                    executor_invoked = True
                finally:
                    self._executor_active = False
        return CoordinatorCycleResult(
            promoted_retry_ids=promoted,
            cancelled_job_ids=cancelled,
            selected_job_id=selected_job_id,
            executor_invoked=executor_invoked,
        )

    def _run_startup_recovery(self) -> None:
        summary = self._repo.recover_stale_jobs(now=self._now_fn())
        LOGGER.info(
            "agent job coordinator recovery requeued=%d failed=%d",
            len(summary.requeued),
            len(summary.failed),
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=self._poll_interval_seconds)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                LOGGER.exception("agent job coordinator loop failed; continuing")
