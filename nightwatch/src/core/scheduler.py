"""
Nightwatch Scheduler
=====================
Cron-based check scheduling. Supports:
  - Interval-based polling (every N seconds)
  - Cron expressions (e.g., "*/5 * * * *")
  - One-shot immediate checks

Author: Nova ⚡ | Nightwatch Platform
"""

import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional

import structlog

log = structlog.get_logger("nightwatch.scheduler")


class ScheduledTask:
    """A named, recurring async task."""

    def __init__(
        self,
        name: str,
        coro_fn: Callable,
        interval_seconds: int,
        run_immediately: bool = True,
    ):
        self.name = name
        self.coro_fn = coro_fn
        self.interval_seconds = interval_seconds
        self.run_immediately = run_immediately
        self.last_run: Optional[datetime] = None
        self.run_count: int = 0
        self.error_count: int = 0
        self._task: Optional[asyncio.Task] = None

    async def _loop(self):
        """Internal loop: run the task on schedule."""
        if not self.run_immediately:
            await asyncio.sleep(self.interval_seconds)

        while True:
            start = asyncio.get_event_loop().time()
            try:
                log.debug("task_running", task=self.name)
                await self.coro_fn()
                self.last_run = datetime.now(timezone.utc)
                self.run_count += 1
                log.debug("task_complete", task=self.name, run_count=self.run_count)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error_count += 1
                log.error("task_failed", task=self.name, error=str(e), error_count=self.error_count)

            # Sleep for remaining interval time (accounting for task execution time)
            elapsed = asyncio.get_event_loop().time() - start
            sleep_time = max(0, self.interval_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    def start(self) -> asyncio.Task:
        """Start the scheduled task. Returns the asyncio Task."""
        self._task = asyncio.create_task(self._loop(), name=f"nightwatch-{self.name}")
        return self._task

    def cancel(self):
        """Cancel the scheduled task."""
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
        }


class NightwatchScheduler:
    """
    Manages multiple scheduled tasks for Nightwatch.

    Usage:
        scheduler = NightwatchScheduler()
        scheduler.add_task("health_check", engine.run_check_cycle, interval_seconds=60)
        scheduler.add_task("deep_scan", engine.run_deep_scan, interval_seconds=300)
        await scheduler.start()
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}

    def add_task(
        self,
        name: str,
        coro_fn: Callable,
        interval_seconds: int,
        run_immediately: bool = True,
    ) -> None:
        """Register a new scheduled task."""
        if name in self._tasks:
            log.warning("task_already_registered", name=name)
            return
        self._tasks[name] = ScheduledTask(name, coro_fn, interval_seconds, run_immediately)
        log.info("task_registered", name=name, interval_seconds=interval_seconds)

    async def start(self) -> None:
        """Start all registered tasks. Blocks until cancelled."""
        if not self._tasks:
            log.warning("no_tasks_registered")
            return

        log.info("scheduler_starting", task_count=len(self._tasks))
        task_handles = [t.start() for t in self._tasks.values()]

        try:
            await asyncio.gather(*task_handles)
        except asyncio.CancelledError:
            log.info("scheduler_cancelled")
            for t in self._tasks.values():
                t.cancel()

    def stop(self) -> None:
        """Cancel all running tasks."""
        for task in self._tasks.values():
            task.cancel()
        log.info("scheduler_stopped")

    def get_status(self) -> list[dict]:
        """Return status of all scheduled tasks."""
        return [t.status() for t in self._tasks.values()]

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        return self._tasks.get(name)
