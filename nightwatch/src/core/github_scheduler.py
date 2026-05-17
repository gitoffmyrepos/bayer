"""
GitHub Issue Escalation Scheduler
==================================
Runs the priority escalation cycle for Nightwatch-created GitHub issues.

Escalation rules:
  - Every 6 hours: if an open nightwatch issue is still unresolved,
    bump its priority one level (p3 → p2 → p1 → p0)
  - p0 is the ceiling — Nightwatch issues at p0 require immediate attention
  - Closed issues are never escalated

Usage:
  scheduler = GitHubEscalationScheduler(github_adapter)
  await scheduler.run_once()          # Run one cycle
  scheduler.start()                    # Start background loop
  scheduler.stop()                      # Stop background loop

Author: Nova ⚡ | Nightwatch Platform
"""

import asyncio
import threading
from datetime import datetime, timezone

import structlog

log = structlog.get_logger("nightwatch.github_scheduler")

ESCALATION_CYCLE_INTERVAL = 1 * 3600  # Run escalation check every 1 hour


class GitHubEscalationScheduler:
    """
    Background scheduler that periodically checks GitHub issues and escalates
    any Nightwatch-created issues that have been open for >6 hours.
    """

    def __init__(self, github_adapter, cycle_interval: int = ESCALATION_CYCLE_INTERVAL):
        self.github = github_adapter
        self.cycle_interval = cycle_interval
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._running = False
        self._last_run: datetime | None = None
        self._last_results: list[dict] = []

    async def run_once(self) -> list[dict]:
        """Execute one escalation cycle. Returns results of any escalations performed."""
        log.info("github_escalation_run_start", ts=datetime.now(timezone.utc).isoformat())
        try:
            results = await self.github.run_escalation_cycle()
            self._last_results = results
            self._last_run = datetime.now(timezone.utc)
            if results:
                log.info(
                    "github_escalation_run_complete",
                    escalated=len(results),
                    results=[
                        f"#{r['issue_number']} → {r['new_priority']}" for r in results
                    ],
                )
            else:
                log.debug("github_escalation_run_complete", escalated=0)
            return results
        except Exception as e:
            log.error("github_escalation_run_failed", error=str(e))
            return []

    async def _loop(self):
        """Background escalation loop."""
        log.info(
            "github_escalation_loop_started",
            interval_seconds=self.cycle_interval,
        )
        while not self._stop_event.wait(self.cycle_interval):
            await self.run_once()

        self._running = False
        log.info("github_escalation_loop_stopped")

    def start(self):
        """Start the background escalation scheduler."""
        if self._running:
            log.warning("github_escalation_already_running")
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        self._running = True
        log.info("github_escalation_scheduler_started")

    async def stop(self):
        """Stop the background escalation scheduler."""
        if self._task:
            self._stop_event.set()
            await self._task
            self._task = None
        self._running = False
        log.info("github_escalation_scheduler_stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    @property
    def last_results(self) -> list[dict]:
        return self._last_results
