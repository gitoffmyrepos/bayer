"""
K8s event → GitHub issue orchestrator.

Glues together:
  - K8sEventWatcher  (input stream)
  - RepoRouter       (event → destination repo)
  - DedupStore       (fingerprint → existing issue)
  - IssueBodyBuilder (LLM-driven Markdown body)
  - GitHubIssuesAdapter (per-repo HTTP client)

Behavior per event (see `handle_event`):

  1. Drop if reason not in allow-list (defense-in-depth — watcher also filters).
  2. Route to (owner, name) repo via RepoRouter.
  3. Compute fingerprint.
  4. Lookup dedup store:
       a) Hit + GH issue still open → bump occurrence, post a comment,
          refresh the hidden meta footer in the issue body.
       b) Hit + GH issue closed     → forget the cached record so the next
          observation creates a fresh issue.
       c) Miss                      → build LLM body, create issue, record.
  5. dry_run=True   → log everything that WOULD happen but skip mutating
                       GitHub calls. Read-only API calls (look-up, get-issue)
                       still run so dedup logic is exercised end-to-end.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import structlog

from src.adapters.github_adapter import GitHubIssuesAdapter
from src.k8s.dedup_store import DedupRecord, DedupStore
from src.k8s.event_watcher import K8sEventRecord
from src.k8s.fingerprint import compute_fingerprint
from src.k8s.issue_body import (
    IssueBodyBuilder,
    IssueBodyContext,
    build_meta_footer,
    replace_meta_footer,
)
from src.k8s.priority import priority_for
from src.k8s.routing import RepoRouter, RoutingDecision

log = structlog.get_logger("nightwatch.k8s.issue_creator")

__all__ = ["K8sIssueCreator", "ProcessResult"]


@dataclass
class ProcessResult:
    """What the creator decided to do for one event (useful for tests)."""

    action: str  # "filtered" | "created" | "would_create" | "updated" | "would_update" | "skipped"
    fingerprint: Optional[str] = None
    repo: Optional[str] = None
    issue_number: Optional[int] = None
    occurrence_count: Optional[int] = None
    detail: Optional[str] = None


AdapterFactory = Callable[[str, str], GitHubIssuesAdapter]


def default_adapter_factory(api_token: str) -> AdapterFactory:
    """Returns a factory that builds GitHubIssuesAdapter instances per (owner, name)."""

    def _factory(owner: str, name: str) -> GitHubIssuesAdapter:
        return GitHubIssuesAdapter(
            {
                "repo_owner": owner,
                "repo_name": name,
                "api_token": api_token,
            }
        )

    return _factory


class K8sIssueCreator:
    """Routes filtered K8s events to GitHub issues with dedup + escalation hooks."""

    def __init__(
        self,
        *,
        router: RepoRouter,
        dedup_store: DedupStore,
        body_builder: IssueBodyBuilder,
        adapter_factory: AdapterFactory,
        allowed_reasons: Optional[set[str]] = None,
        dry_run: bool = True,
        issue_kind: str = "k8s-event",
        k8s_log_fetcher: Optional[Callable[[str, str, int], list[str]]] = None,
        related_events_fetcher: Optional[Callable[[str, str], list[dict]]] = None,
    ):
        self.router = router
        self.dedup_store = dedup_store
        self.body_builder = body_builder
        self.adapter_factory = adapter_factory
        self.allowed_reasons = set(allowed_reasons or [])
        self.dry_run = bool(dry_run)
        self.issue_kind = issue_kind
        self.k8s_log_fetcher = k8s_log_fetcher
        self.related_events_fetcher = related_events_fetcher

        self._adapters: dict[tuple[str, str], GitHubIssuesAdapter] = {}
        self._lock = asyncio.Lock()  # per-event serialization to avoid race-on-same-fp
        self._created = 0
        self._updated = 0
        self._filtered = 0
        self._errors = 0

    # ─── public API ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "created": self._created,
            "updated": self._updated,
            "filtered": self._filtered,
            "errors": self._errors,
            "dedup_size": self.dedup_store.size(),
            "repos_cached": [f"{o}/{n}" for (o, n) in self._adapters.keys()],
        }

    async def close(self) -> None:
        for adapter in self._adapters.values():
            try:
                await adapter.close()
            except Exception as e:  # noqa: BLE001
                log.warning("adapter_close_failed", error=str(e))

    async def handle_event(self, record: K8sEventRecord) -> ProcessResult:
        # 1. allow-list filter (defense-in-depth)
        if self.allowed_reasons and record.reason not in self.allowed_reasons:
            self._filtered += 1
            return ProcessResult(action="filtered", detail=f"reason {record.reason} not allowed")

        # 2. route
        decision = self.router.route(
            namespace=record.namespace,
            kind=record.kind,
            name=record.name,
            reason=record.reason,
        )
        repo_slug = decision.slug

        # 3. fingerprint
        fp = compute_fingerprint(
            repo=repo_slug,
            issue_kind=self.issue_kind,
            namespace=record.namespace,
            resource_name=record.name,
            reason=record.reason,
        )

        # Serialize per-event so two near-simultaneous identical events don't
        # both create new issues.
        async with self._lock:
            existing = self.dedup_store.lookup(fp)
            if existing is not None:
                return await self._handle_existing(record, decision, fp, existing)
            return await self._handle_new(record, decision, fp)

    # ─── existing-issue path ───────────────────────────────────────────────

    async def _handle_existing(
        self,
        record: K8sEventRecord,
        decision: RoutingDecision,
        fp: str,
        existing: DedupRecord,
    ) -> ProcessResult:
        adapter = self._get_adapter(decision.owner, decision.name)
        # Confirm the issue is still open. (Read API — always runs even in dry-run.)
        try:
            issue = await adapter.get_issue(existing.issue_number)
        except Exception as e:  # noqa: BLE001
            self._errors += 1
            log.warning(
                "existing_issue_fetch_failed",
                fingerprint=fp,
                issue_number=existing.issue_number,
                error=str(e),
            )
            # Don't drop the cache — transient errors shouldn't trigger duplicate creates.
            return ProcessResult(
                action="skipped",
                fingerprint=fp,
                repo=decision.slug,
                issue_number=existing.issue_number,
                detail=f"get_issue failed: {e}",
            )

        if (issue or {}).get("state") == "closed":
            # GH issue was resolved — drop the cache so future occurrences create fresh.
            self.dedup_store.forget(fp)
            log.info(
                "existing_issue_closed_forgetting",
                fingerprint=fp,
                issue_number=existing.issue_number,
            )
            # Fall through to creating a new one.
            return await self._handle_new(record, decision, fp)

        new_count = self.dedup_store.bump_occurrence(fp)
        comment_body = (
            f"⚡ Re-observed at `{record.last_seen or datetime.now(timezone.utc).isoformat()}`. "
            f"Occurrence count: **{new_count}**.\n\n"
            f"_(message: `{(record.message or '')[:300]}`)_"
        )

        # Refresh the meta footer in the body
        ctx = self._build_ctx(record, decision, fp)
        ctx.count = new_count
        new_footer = build_meta_footer(ctx)
        original_body = (issue or {}).get("body") or ""
        updated_body = replace_meta_footer(original_body, new_footer)

        if self.dry_run:
            log.info(
                "dry_run_would_update",
                fingerprint=fp,
                issue_number=existing.issue_number,
                repo=decision.slug,
                occurrence_count=new_count,
            )
            return ProcessResult(
                action="would_update",
                fingerprint=fp,
                repo=decision.slug,
                issue_number=existing.issue_number,
                occurrence_count=new_count,
                detail="dry-run: comment + body footer refresh skipped",
            )

        try:
            await adapter.add_issue_comment(existing.issue_number, comment_body)
            if updated_body != original_body:
                await adapter.update_issue(existing.issue_number, body=updated_body)
            self._updated += 1
            log.info(
                "issue_updated",
                fingerprint=fp,
                issue_number=existing.issue_number,
                repo=decision.slug,
                occurrence_count=new_count,
            )
            return ProcessResult(
                action="updated",
                fingerprint=fp,
                repo=decision.slug,
                issue_number=existing.issue_number,
                occurrence_count=new_count,
            )
        except Exception as e:  # noqa: BLE001
            self._errors += 1
            log.error(
                "issue_update_failed",
                fingerprint=fp,
                issue_number=existing.issue_number,
                error=str(e),
            )
            return ProcessResult(
                action="skipped",
                fingerprint=fp,
                repo=decision.slug,
                issue_number=existing.issue_number,
                detail=f"update failed: {e}",
            )

    # ─── new-issue path ────────────────────────────────────────────────────

    async def _handle_new(
        self,
        record: K8sEventRecord,
        decision: RoutingDecision,
        fp: str,
    ) -> ProcessResult:
        adapter = self._get_adapter(decision.owner, decision.name)

        ctx = self._build_ctx(record, decision, fp)
        # Best-effort fetch logs / related events (sync fetchers).
        if record.kind == "Pod" and self.k8s_log_fetcher is not None:
            try:
                ctx.recent_logs = self.k8s_log_fetcher(record.namespace, record.name, 80) or []
            except Exception as e:  # noqa: BLE001
                log.debug("k8s_log_fetch_failed", error=str(e))
        if self.related_events_fetcher is not None:
            try:
                ctx.related_events = (
                    self.related_events_fetcher(record.namespace, record.name) or []
                )
            except Exception as e:  # noqa: BLE001
                log.debug("related_events_fetch_failed", error=str(e))

        body = self.body_builder.build(ctx)
        title = self._build_title(record)
        priority = priority_for(record.reason)
        labels = ["k8s-event", f"reason/{record.reason.lower()}"] + list(decision.extra_labels)

        if self.dry_run:
            log.info(
                "dry_run_would_create",
                fingerprint=fp,
                repo=decision.slug,
                title=title[:80],
                priority=priority,
                labels=labels,
            )
            return ProcessResult(
                action="would_create",
                fingerprint=fp,
                repo=decision.slug,
                detail=f"dry-run: title='{title[:80]}' priority={priority}",
            )

        try:
            created = await adapter.create_issue(
                title=title,
                body=body,
                labels=labels,
                priority=priority,
            )
            issue_number = int(created["number"])
            self.dedup_store.record_new(fp, issue_number=issue_number, repo=decision.slug)
            self._created += 1
            log.info(
                "issue_created",
                fingerprint=fp,
                issue_number=issue_number,
                repo=decision.slug,
                priority=priority,
            )
            return ProcessResult(
                action="created",
                fingerprint=fp,
                repo=decision.slug,
                issue_number=issue_number,
                occurrence_count=1,
            )
        except Exception as e:  # noqa: BLE001
            self._errors += 1
            log.error(
                "issue_create_failed",
                fingerprint=fp,
                repo=decision.slug,
                error=str(e),
            )
            return ProcessResult(
                action="skipped",
                fingerprint=fp,
                repo=decision.slug,
                detail=f"create failed: {e}",
            )

    # ─── helpers ───────────────────────────────────────────────────────────

    def _get_adapter(self, owner: str, name: str) -> GitHubIssuesAdapter:
        key = (owner, name)
        adapter = self._adapters.get(key)
        if adapter is None:
            adapter = self.adapter_factory(owner, name)
            self._adapters[key] = adapter
            log.info("adapter_cached", owner=owner, name=name)
        return adapter

    def _build_title(self, record: K8sEventRecord) -> str:
        ns_part = f"{record.namespace}/" if record.namespace else ""
        return f"[Nightwatch] {record.reason}: {record.kind}/{ns_part}{record.name}"

    def _build_ctx(
        self,
        record: K8sEventRecord,
        decision: RoutingDecision,
        fp: str,
    ) -> IssueBodyContext:
        return IssueBodyContext(
            namespace=record.namespace,
            kind=record.kind,
            name=record.name,
            reason=record.reason,
            message=record.message,
            count=record.count,
            first_seen=record.first_seen,
            last_seen=record.last_seen,
            source_component=record.source,
            repo_slug=decision.slug,
            fingerprint=fp,
        )
