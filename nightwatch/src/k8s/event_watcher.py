"""
Async wrapper around the Kubernetes Events watch stream.

Design:
  - Uses the official `kubernetes` Python client (blocking).
  - Wraps the blocking `watch.Watch().stream(...)` in run_in_executor so the
    asyncio FastAPI process is not blocked.
  - Filters: only forward type=Warning events whose `reason` is in the
    operator-configured allow-list.
  - On disconnect (Gone / timeout), reconnects from the last observed
    resourceVersion.
  - Graceful shutdown via an asyncio.Event.

The watcher hands each filtered event to an async `handler` callback. The
handler is expected to be fast — heavy work (LLM, GitHub API) should be
scheduled by the handler itself.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Optional

import structlog

log = structlog.get_logger("nightwatch.k8s.event_watcher")

__all__ = ["K8sEventRecord", "K8sEventWatcher", "DEFAULT_ALLOWED_REASONS"]


DEFAULT_ALLOWED_REASONS: tuple[str, ...] = (
    "CrashLoopBackOff",
    "BackOff",
    "Failed",
    "FailedCreatePodSandBox",
    "FailedScheduling",
    "ImagePullBackOff",
    "ErrImagePull",
    "OOMKilled",
    "Unhealthy",
    "FailedMount",
    "NodeNotReady",
    "Evicted",
    "FailedSync",
    "DeadlineExceeded",
)


@dataclass
class K8sEventRecord:
    """Normalized representation of a Kubernetes Warning event."""

    namespace: str
    kind: str
    name: str
    reason: str
    message: str
    count: int
    first_seen: Optional[str]
    last_seen: Optional[str]
    source: Optional[str] = None  # event.source.component
    type: str = "Warning"
    uid: Optional[str] = None  # involvedObject.uid
    api_version: Optional[str] = None  # involvedObject.apiVersion
    resource_version: Optional[str] = None  # event.metadata.resourceVersion
    raw_event_name: Optional[str] = None  # event.metadata.name

    @classmethod
    def from_v1_event(cls, ev) -> "K8sEventRecord":
        """Build from a kubernetes.client.V1Event."""
        involved = getattr(ev, "involved_object", None)
        source = getattr(ev, "source", None)
        meta = getattr(ev, "metadata", None)

        def _iso(t):
            if t is None:
                return None
            if isinstance(t, str):
                return t
            try:
                return t.isoformat()
            except AttributeError:
                return str(t)

        return cls(
            namespace=(getattr(involved, "namespace", None) or getattr(meta, "namespace", "") or ""),
            kind=getattr(involved, "kind", "") or "",
            name=getattr(involved, "name", "") or "",
            reason=ev.reason or "",
            message=(ev.message or "")[:2000],
            count=int(getattr(ev, "count", 1) or 1),
            first_seen=_iso(getattr(ev, "first_timestamp", None)) or _iso(getattr(ev, "event_time", None)),
            last_seen=_iso(getattr(ev, "last_timestamp", None)) or _iso(getattr(ev, "event_time", None)) or datetime.now(timezone.utc).isoformat(),
            source=getattr(source, "component", None) if source else None,
            type=ev.type or "Warning",
            uid=getattr(involved, "uid", None),
            api_version=getattr(involved, "api_version", None),
            resource_version=getattr(meta, "resource_version", None) if meta else None,
            raw_event_name=getattr(meta, "name", None) if meta else None,
        )


EventHandler = Callable[[K8sEventRecord], Awaitable[None]]


class K8sEventWatcher:
    """
    Watches all-namespaces V1 Events and dispatches Warning events to a handler.

    Usage:
        watcher = K8sEventWatcher(
            handler=creator.handle_event,
            allowed_reasons=("CrashLoopBackOff", ...),
        )
        await watcher.start()   # returns immediately; loops in a background task
        ...
        await watcher.stop()
    """

    def __init__(
        self,
        handler: EventHandler,
        allowed_reasons: Optional[Iterable[str]] = None,
        timeout_seconds: int = 300,
        reconnect_backoff_seconds: float = 5.0,
    ):
        self.handler = handler
        self.allowed_reasons: set[str] = set(allowed_reasons or DEFAULT_ALLOWED_REASONS)
        self.timeout_seconds = int(timeout_seconds)
        self.reconnect_backoff = float(reconnect_backoff_seconds)

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._last_resource_version: Optional[str] = None
        self._api = None
        self._watch_cls = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._initialized = False
        self._events_seen = 0
        self._events_forwarded = 0
        self._last_event_iso: Optional[str] = None

    # ─── public lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task and not self._task.done():
            log.warning("event_watcher_already_running")
            return
        if not self._init_k8s_client():
            log.error("event_watcher_init_failed")
            return
        self._loop = asyncio.get_running_loop()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_forever(), name="k8s-event-watcher")
        log.info(
            "event_watcher_started",
            allowed_reasons=sorted(self.allowed_reasons),
            timeout_seconds=self.timeout_seconds,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                log.warning("event_watcher_stop_timeout_cancelling")
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
        log.info(
            "event_watcher_stopped",
            events_seen=self._events_seen,
            events_forwarded=self._events_forwarded,
        )

    def stats(self) -> dict:
        return {
            "events_seen": self._events_seen,
            "events_forwarded": self._events_forwarded,
            "last_event": self._last_event_iso,
            "last_resource_version": self._last_resource_version,
            "running": bool(self._task and not self._task.done()),
        }

    # ─── internals ─────────────────────────────────────────────────────────

    def _init_k8s_client(self) -> bool:
        if self._initialized:
            return True
        try:
            from kubernetes import client, config, watch  # type: ignore
        except ImportError as e:
            log.error("kubernetes_client_unavailable", error=str(e))
            return False
        try:
            config.load_incluster_config()
            log.info("k8s_in_cluster_config_loaded")
        except Exception:  # noqa: BLE001
            try:
                config.load_kube_config()
                log.info("k8s_kubeconfig_loaded")
            except Exception as e:  # noqa: BLE001
                log.error("k8s_config_load_failed", error=str(e))
                return False
        self._api = client.CoreV1Api()
        self._watch_cls = watch.Watch
        self._initialized = True
        return True

    async def _run_forever(self) -> None:
        """Outer loop — reconnects on disconnect / timeout / 410 Gone."""
        while not self._stop_event.is_set():
            try:
                await self._loop.run_in_executor(None, self._stream_once)
            except Exception as e:  # noqa: BLE001
                # Inspect lazily so we don't import api_exceptions unconditionally.
                msg = str(e)
                is_gone = "410" in msg or "Gone" in msg or "Expired" in msg
                if is_gone:
                    log.info("event_watcher_resource_gone_resyncing")
                    self._last_resource_version = None
                else:
                    log.warning("event_watcher_stream_error", error=msg)
            if self._stop_event.is_set():
                break
            # backoff before reconnect
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.reconnect_backoff
                )
            except asyncio.TimeoutError:
                pass

    def _stream_once(self) -> None:
        """One pass over the watch stream — runs in executor (blocking)."""
        assert self._api is not None and self._watch_cls is not None
        w = self._watch_cls()
        kwargs = {
            "watch": True,
            "timeout_seconds": self.timeout_seconds,
        }
        if self._last_resource_version:
            kwargs["resource_version"] = self._last_resource_version

        try:
            for raw in w.stream(self._api.list_event_for_all_namespaces, **kwargs):
                if self._stop_event.is_set():
                    w.stop()
                    return
                obj = raw.get("object")
                if obj is None:
                    continue
                # Track resource version for resume on reconnect
                rv = getattr(getattr(obj, "metadata", None), "resource_version", None)
                if rv:
                    self._last_resource_version = rv

                self._events_seen += 1

                if (obj.type or "") != "Warning":
                    continue
                reason = obj.reason or ""
                if reason not in self.allowed_reasons:
                    continue

                try:
                    record = K8sEventRecord.from_v1_event(obj)
                except Exception as e:  # noqa: BLE001
                    log.warning("event_record_build_failed", error=str(e))
                    continue

                self._events_forwarded += 1
                self._last_event_iso = record.last_seen or datetime.now(timezone.utc).isoformat()
                # Hand off to the asyncio handler on the main loop.
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._safe_handle(record), self._loop
                    )
        finally:
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass

    async def _safe_handle(self, record: K8sEventRecord) -> None:
        try:
            await self.handler(record)
        except Exception as e:  # noqa: BLE001
            log.error(
                "event_handler_failed",
                error=str(e),
                namespace=record.namespace,
                kind=record.kind,
                name=record.name,
                reason=record.reason,
            )
