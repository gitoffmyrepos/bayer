"""
Unit tests for the K8s event → GitHub issue pipeline.

Covers:
  - compute_fingerprint determinism + repo-awareness
  - RepoRouter rule matching (default + explicit + regex)
  - DedupStore round-trip + bump occurrence + atomic persistence
  - priority_for mapping
  - K8sIssueCreator.handle_event in dry-run mode
       * new event → would_create + dedup record stored
       * duplicate event → would_update + occurrence bumped

The GitHubIssuesAdapter is mocked (no network calls).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.k8s.dedup_store import DedupRecord, DedupStore
from src.k8s.event_watcher import K8sEventRecord
from src.k8s.fingerprint import FINGERPRINT_LEN, compute_fingerprint
from src.k8s.issue_body import IssueBodyBuilder
from src.k8s.issue_creator import K8sIssueCreator, ProcessResult
from src.k8s.priority import REASON_TO_PRIORITY, priority_for
from src.k8s.routing import DEFAULT_ROUTING_CONFIG, RepoRouter


# ─── fingerprint ───────────────────────────────────────────────────────────


def test_fingerprint_is_deterministic():
    fp1 = compute_fingerprint("o/r", "k8s-event", "ns", "pod-a", "CrashLoopBackOff")
    fp2 = compute_fingerprint("o/r", "k8s-event", "ns", "pod-a", "CrashLoopBackOff")
    assert fp1 == fp2
    assert len(fp1) == FINGERPRINT_LEN
    assert all(c in "0123456789abcdef" for c in fp1)


def test_fingerprint_changes_with_repo():
    fp_fx = compute_fingerprint("o/FX", "k8s-event", "ns", "pod-a", "CrashLoopBackOff")
    fp_gitops = compute_fingerprint(
        "o/sb-gitops", "k8s-event", "ns", "pod-a", "CrashLoopBackOff"
    )
    assert fp_fx != fp_gitops


def test_fingerprint_changes_with_reason():
    fp1 = compute_fingerprint("o/r", "k8s-event", "ns", "pod-a", "CrashLoopBackOff")
    fp2 = compute_fingerprint("o/r", "k8s-event", "ns", "pod-a", "OOMKilled")
    assert fp1 != fp2


def test_fingerprint_handles_empty_namespace():
    # Cluster-scoped resources have no namespace.
    fp = compute_fingerprint("o/r", "k8s-event", "", "node-1", "NodeNotReady")
    assert len(fp) == FINGERPRINT_LEN


# ─── priority ──────────────────────────────────────────────────────────────


def test_priority_mapping_known_reasons():
    assert priority_for("CrashLoopBackOff") == "p0"
    assert priority_for("OOMKilled") == "p0"
    assert priority_for("NodeNotReady") == "p0"
    assert priority_for("BackOff") == "p1"
    assert priority_for("ImagePullBackOff") == "p1"
    assert priority_for("FailedScheduling") == "p1"
    assert priority_for("Failed") == "p2"
    assert priority_for("Unhealthy") == "p3"
    assert priority_for("FailedSync") == "p3"


def test_priority_unknown_reason_returns_default():
    assert priority_for("SomethingNew") == "p3"
    assert priority_for("", default="p2") == "p2"


def test_priority_table_keys_all_strings():
    # Sanity: no typo-keys
    for k, v in REASON_TO_PRIORITY.items():
        assert isinstance(k, str) and k
        assert v in ("p0", "p1", "p2", "p3")


# ─── routing ───────────────────────────────────────────────────────────────


def test_router_routes_forextrader_pod_to_fx():
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    decision = router.route(
        namespace="prod-forex",
        kind="Pod",
        name="forextrader-trade-executor-abc",
        reason="CrashLoopBackOff",
    )
    assert decision.owner == "gitoffmyrepos"
    assert decision.name == "FX"
    assert "microservice" in decision.extra_labels


def test_router_routes_argocd_to_gitops():
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    decision = router.route(
        namespace="argocd",
        kind="Application",
        name="some-app",
        reason="Failed",
    )
    assert decision.name == "sb-gitops"
    assert "gitops" in decision.extra_labels
    assert "argocd" in decision.extra_labels


def test_router_routes_kube_system_to_infra_via_regex():
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    decision = router.route(
        namespace="kube-system",
        kind="Pod",
        name="coredns-abc",
        reason="CrashLoopBackOff",
    )
    assert decision.name == "sb-dev-infra"
    assert "infra" in decision.extra_labels


def test_router_default_repo_for_unmatched():
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    decision = router.route(
        namespace="some-random-ns",
        kind="Pod",
        name="unknown",
        reason="Unhealthy",
    )
    # Default falls through to FX with needs-routing label
    assert decision.name == "FX"
    assert "needs-routing" in decision.extra_labels


def test_router_all_repos_includes_default():
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    repos = router.all_repos()
    assert ("gitoffmyrepos", "FX") in repos
    assert ("gitoffmyrepos", "sb-gitops") in repos
    assert ("gitoffmyrepos", "sb-dev-infra") in repos


def test_router_custom_config_rules_first_match_wins():
    cfg = {
        "routing_rules": [
            {
                "match": {"reason": "CrashLoopBackOff"},
                "repo": {"owner": "o", "name": "high-priority"},
                "labels": ["crash"],
            },
            {
                "match": {"namespace": "prod-forex"},
                "repo": {"owner": "o", "name": "FX"},
                "labels": ["fx"],
            },
        ],
        "default": {"repo": {"owner": "o", "name": "default-repo"}, "labels": []},
    }
    router = RepoRouter(cfg)
    d = router.route("prod-forex", "Pod", "x", "CrashLoopBackOff")
    assert d.name == "high-priority"
    d2 = router.route("prod-forex", "Pod", "x", "Unhealthy")
    assert d2.name == "FX"
    d3 = router.route("other", "Pod", "x", "Unhealthy")
    assert d3.name == "default-repo"


# ─── dedup store ───────────────────────────────────────────────────────────


def test_dedup_store_roundtrip(tmp_path):
    p = tmp_path / "fp.json"
    store = DedupStore(str(p))
    assert store.lookup("abc") is None
    rec = store.record_new("abc", issue_number=42, repo="o/r")
    assert rec.issue_number == 42
    assert rec.occurrence_count == 1

    got = store.lookup("abc")
    assert got is not None
    assert got.issue_number == 42
    assert got.occurrence_count == 1

    new_count = store.bump_occurrence("abc")
    assert new_count == 2
    assert store.lookup("abc").occurrence_count == 2

    # Verify durability — new instance reads same file.
    store2 = DedupStore(str(p))
    persisted = store2.lookup("abc")
    assert persisted is not None
    assert persisted.occurrence_count == 2
    assert persisted.repo == "o/r"


def test_dedup_store_bump_missing_raises(tmp_path):
    p = tmp_path / "fp.json"
    store = DedupStore(str(p))
    with pytest.raises(KeyError):
        store.bump_occurrence("missing-fp")


def test_dedup_store_forget(tmp_path):
    store = DedupStore(str(tmp_path / "fp.json"))
    store.record_new("xyz", issue_number=7, repo="o/r")
    assert store.forget("xyz") is True
    assert store.lookup("xyz") is None
    assert store.forget("xyz") is False


def test_dedup_store_handles_corrupt_file(tmp_path):
    p = tmp_path / "fp.json"
    p.write_text("not valid json {{{")
    # Should not raise — corrupt file falls back to empty.
    store = DedupStore(str(p))
    assert store.size() == 0


# ─── issue creator (dry-run) ───────────────────────────────────────────────


class FakeIssue:
    def __init__(self, number, state="open", body=""):
        self.number = number
        self.state = state
        self.body = body


class FakeGitHubAdapter:
    """Stand-in for GitHubIssuesAdapter — records calls, no HTTP."""

    def __init__(self, owner, name):
        self.owner = owner
        self.name = name
        self._issues: dict[int, dict] = {}
        self._next = 100
        self.created: list[dict] = []
        self.commented: list[tuple[int, str]] = []
        self.updated: list[tuple[int, dict]] = []
        self.gets: list[int] = []
        self.close_called = False

    async def get_issue(self, number):
        self.gets.append(number)
        if number not in self._issues:
            raise RuntimeError(f"no issue {number}")
        return dict(self._issues[number])

    async def create_issue(self, title, body, labels=None, priority="p3"):
        n = self._next
        self._next += 1
        issue = {
            "number": n,
            "title": title,
            "body": body,
            "state": "open",
            "labels": [{"name": l} for l in (labels or [])],
            "html_url": f"https://github.com/{self.owner}/{self.name}/issues/{n}",
        }
        self._issues[n] = issue
        self.created.append({"title": title, "labels": labels, "priority": priority})
        return issue

    async def add_issue_comment(self, number, body):
        self.commented.append((number, body))
        return {"id": 1}

    async def update_issue(self, number, body=None, state=None, labels=None):
        payload = {}
        if body is not None:
            payload["body"] = body
            self._issues[number]["body"] = body
        if state is not None:
            payload["state"] = state
            self._issues[number]["state"] = state
        if labels is not None:
            payload["labels"] = [{"name": l} for l in labels]
            self._issues[number]["labels"] = payload["labels"]
        self.updated.append((number, payload))
        return self._issues[number]

    async def close(self):
        self.close_called = True

    def seed(self, number, state="open", body=""):
        self._issues[number] = {
            "number": number,
            "state": state,
            "body": body,
            "title": f"seeded-{number}",
            "labels": [],
            "html_url": "https://example/x",
        }


def _make_record(**overrides):
    base = dict(
        namespace="prod-forex",
        kind="Pod",
        name="forextrader-trade-executor-7d-abc",
        reason="CrashLoopBackOff",
        message="Back-off restarting failed container",
        count=5,
        first_seen="2026-05-24T12:00:00+00:00",
        last_seen="2026-05-24T12:05:00+00:00",
        source="kubelet",
    )
    base.update(overrides)
    return K8sEventRecord(**base)


def _build_creator(tmp_path, dry_run=True, adapters_out=None):
    store = DedupStore(str(tmp_path / "fp.json"))
    router = RepoRouter(DEFAULT_ROUTING_CONFIG)
    builder = IssueBodyBuilder(llm_client=None)

    factory_cache: dict = {}

    def factory(owner, name):
        a = FakeGitHubAdapter(owner, name)
        factory_cache[(owner, name)] = a
        if adapters_out is not None:
            adapters_out.append(a)
        return a

    creator = K8sIssueCreator(
        router=router,
        dedup_store=store,
        body_builder=builder,
        adapter_factory=factory,
        allowed_reasons={"CrashLoopBackOff", "OOMKilled", "Failed"},
        dry_run=dry_run,
    )
    return creator, store, factory_cache


@pytest.mark.asyncio
async def test_new_event_dry_run_would_create(tmp_path):
    creator, store, _ = _build_creator(tmp_path, dry_run=True)
    rec = _make_record()
    result = await creator.handle_event(rec)
    assert isinstance(result, ProcessResult)
    assert result.action == "would_create"
    assert result.repo == "gitoffmyrepos/FX"
    # In dry-run we DO NOT record a real issue number (no creation happened).
    assert store.lookup(result.fingerprint) is None


@pytest.mark.asyncio
async def test_filtered_event_not_processed(tmp_path):
    creator, _, _ = _build_creator(tmp_path, dry_run=True)
    rec = _make_record(reason="SomeOtherReason")
    result = await creator.handle_event(rec)
    assert result.action == "filtered"


@pytest.mark.asyncio
async def test_new_event_live_creates_and_records(tmp_path):
    adapters_out: list = []
    creator, store, _ = _build_creator(tmp_path, dry_run=False, adapters_out=adapters_out)
    rec = _make_record()
    result = await creator.handle_event(rec)
    assert result.action == "created"
    assert result.issue_number is not None
    # dedup record now persisted
    rec_db = store.lookup(result.fingerprint)
    assert rec_db is not None
    assert rec_db.issue_number == result.issue_number
    assert rec_db.occurrence_count == 1
    # exactly one create call on the FX adapter
    assert len(adapters_out) == 1
    assert len(adapters_out[0].created) == 1


@pytest.mark.asyncio
async def test_duplicate_event_live_bumps_and_comments(tmp_path):
    adapters_out: list = []
    creator, store, _ = _build_creator(tmp_path, dry_run=False, adapters_out=adapters_out)
    rec = _make_record()
    r1 = await creator.handle_event(rec)
    assert r1.action == "created"
    # second occurrence — same fingerprint
    r2 = await creator.handle_event(rec)
    assert r2.action == "updated"
    assert r2.occurrence_count == 2
    assert store.lookup(r1.fingerprint).occurrence_count == 2

    # Adapter cached across calls — only one created, one comment.
    adapter = adapters_out[0]
    assert len(adapter.created) == 1
    assert len(adapter.commented) == 1
    assert adapter.commented[0][0] == r1.issue_number


@pytest.mark.asyncio
async def test_duplicate_event_dry_run_does_not_mutate(tmp_path):
    """Dry-run with a *pre-existing* dedup record should still talk to GitHub
    (read-only) but never comment/update — and should NOT bump occurrence."""
    adapters_out: list = []
    creator, store, factory_cache = _build_creator(
        tmp_path, dry_run=True, adapters_out=adapters_out
    )
    # Pre-seed the dedup store + a fake "open" issue on the routed adapter.
    rec = _make_record()
    fp = compute_fingerprint(
        repo="gitoffmyrepos/FX",
        issue_kind="k8s-event",
        namespace=rec.namespace,
        resource_name=rec.name,
        reason=rec.reason,
    )
    store.record_new(fp, issue_number=999, repo="gitoffmyrepos/FX")

    # Force the adapter for this repo to be built ahead of time, then seed.
    adapter = creator._get_adapter("gitoffmyrepos", "FX")  # noqa: SLF001 — test introspection
    adapter.seed(999, state="open", body="placeholder body")

    result = await creator.handle_event(rec)
    assert result.action == "would_update"
    assert result.issue_number == 999
    # Read API DID run (get_issue called).
    assert 999 in adapter.gets
    # Mutations did NOT run.
    assert adapter.commented == []
    assert adapter.updated == []


@pytest.mark.asyncio
async def test_existing_closed_issue_creates_fresh(tmp_path):
    adapters_out: list = []
    creator, store, _ = _build_creator(tmp_path, dry_run=False, adapters_out=adapters_out)
    rec = _make_record()
    fp = compute_fingerprint(
        repo="gitoffmyrepos/FX",
        issue_kind="k8s-event",
        namespace=rec.namespace,
        resource_name=rec.name,
        reason=rec.reason,
    )
    store.record_new(fp, issue_number=42, repo="gitoffmyrepos/FX")
    adapter = creator._get_adapter("gitoffmyrepos", "FX")  # noqa: SLF001
    adapter.seed(42, state="closed", body="old body")

    result = await creator.handle_event(rec)
    # Closed issue → forget + create new
    assert result.action == "created"
    assert result.issue_number != 42
    # Dedup updated to the new issue number
    new_rec = store.lookup(fp)
    assert new_rec is not None
    assert new_rec.issue_number == result.issue_number


@pytest.mark.asyncio
async def test_two_simultaneous_events_serialize_to_one_create(tmp_path):
    adapters_out: list = []
    creator, _, _ = _build_creator(tmp_path, dry_run=False, adapters_out=adapters_out)
    rec = _make_record()
    r1, r2 = await asyncio.gather(
        creator.handle_event(rec),
        creator.handle_event(rec),
    )
    actions = sorted([r1.action, r2.action])
    # Exactly one created + one updated (or one created and one filtered, but
    # they don't filter on reason here).
    assert actions == ["created", "updated"], actions
    adapter = adapters_out[0]
    assert len(adapter.created) == 1
