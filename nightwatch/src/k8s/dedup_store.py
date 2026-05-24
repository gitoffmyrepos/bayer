"""
Durable fingerprint → issue-number cache.

Implementation: JSON file on disk, atomic write-through on every mutation.
No Redis/Postgres dependency — the nightwatch pod doesn't have either.

Concurrency:
  - In-process: protected by a threading.Lock (FastAPI may run handlers
    concurrently in a thread pool).
  - Multi-process: fcntl.flock advisory lock around read/write blocks.
    (We only run 1 replica today, but the CronJob escalation pod may
    open the same file briefly.)

State format (JSON):
{
  "<fingerprint>": {
    "issue_number": 1234,
    "repo": "gitoffmyrepos/FX",
    "first_seen": "2026-05-24T12:34:56+00:00",
    "last_seen":  "2026-05-24T13:45:00+00:00",
    "occurrence_count": 42
  },
  ...
}
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger("nightwatch.k8s.dedup_store")

__all__ = ["DedupRecord", "DedupStore"]


@dataclass
class DedupRecord:
    """One row in the dedup store."""

    issue_number: int
    repo: str  # "owner/name"
    first_seen: str  # ISO 8601 UTC
    last_seen: str  # ISO 8601 UTC
    occurrence_count: int = 1

    @classmethod
    def new(cls, issue_number: int, repo: str) -> "DedupRecord":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            issue_number=issue_number,
            repo=repo,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DedupRecord":
        return cls(
            issue_number=int(d["issue_number"]),
            repo=str(d["repo"]),
            first_seen=str(d.get("first_seen") or datetime.now(timezone.utc).isoformat()),
            last_seen=str(d.get("last_seen") or datetime.now(timezone.utc).isoformat()),
            occurrence_count=int(d.get("occurrence_count", 1)),
        )


class DedupStore:
    """
    Durable fingerprint -> DedupRecord map with atomic write-through.

    Usage:
        store = DedupStore("/var/lib/nightwatch/issue_fingerprints.json")
        rec = store.lookup(fingerprint)
        if rec:
            count = store.bump_occurrence(fingerprint)
        else:
            store.record_new(fingerprint, issue_number=123, repo="o/r")
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, DedupRecord] = {}
        self._loaded = False
        self._ensure_dir()
        self._load()

    # ─── public API ─────────────────────────────────────────────────────────

    def lookup(self, fingerprint: str) -> Optional[DedupRecord]:
        with self._lock:
            rec = self._data.get(fingerprint)
            # return a defensive copy so callers can't mutate in-place
            return DedupRecord(**asdict(rec)) if rec else None

    def record_new(self, fingerprint: str, issue_number: int, repo: str) -> DedupRecord:
        with self._lock:
            rec = DedupRecord.new(issue_number=issue_number, repo=repo)
            self._data[fingerprint] = rec
            self._flush_locked()
            log.info(
                "dedup_record_new",
                fingerprint=fingerprint,
                issue_number=issue_number,
                repo=repo,
            )
            return DedupRecord(**asdict(rec))

    def bump_occurrence(self, fingerprint: str) -> int:
        """Increment occurrence_count and refresh last_seen; returns new count."""
        with self._lock:
            rec = self._data.get(fingerprint)
            if rec is None:
                raise KeyError(f"fingerprint not in store: {fingerprint}")
            rec.occurrence_count += 1
            rec.last_seen = datetime.now(timezone.utc).isoformat()
            self._flush_locked()
            log.debug(
                "dedup_bump",
                fingerprint=fingerprint,
                occurrence_count=rec.occurrence_count,
                issue_number=rec.issue_number,
            )
            return rec.occurrence_count

    def forget(self, fingerprint: str) -> bool:
        """Drop a record (e.g. when the GH issue is observed closed)."""
        with self._lock:
            existed = fingerprint in self._data
            if existed:
                self._data.pop(fingerprint, None)
                self._flush_locked()
            return existed

    def all_records(self) -> dict[str, DedupRecord]:
        with self._lock:
            # defensive copy
            return {k: DedupRecord(**asdict(v)) for k, v in self._data.items()}

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    # ─── disk I/O ──────────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning("dedup_store_mkdir_failed", path=str(self.path.parent), error=str(e))

    def _load(self) -> None:
        if self._loaded:
            return
        if not self.path.exists():
            self._loaded = True
            log.info("dedup_store_empty_init", path=str(self.path))
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    raw = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("dedup_store_load_failed", path=str(self.path), error=str(e))
            raw = {}

        self._data = {}
        for fp, rec_d in (raw or {}).items():
            try:
                self._data[fp] = DedupRecord.from_dict(rec_d)
            except (KeyError, TypeError, ValueError) as e:
                log.warning("dedup_record_skipped", fingerprint=fp, error=str(e))
        self._loaded = True
        log.info("dedup_store_loaded", path=str(self.path), records=len(self._data))

    def _flush_locked(self) -> None:
        """Caller must hold self._lock. Atomically rewrite the JSON file."""
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=".dedup-", suffix=".tmp"
            )
            payload = {fp: rec.to_dict() for fp, rec in self._data.items()}
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(payload, f, indent=2, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.replace(tmp_path, self.path)
        except OSError as e:
            log.error("dedup_store_flush_failed", path=str(self.path), error=str(e))
