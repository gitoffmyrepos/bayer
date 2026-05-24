"""
K8s event reason → Nightwatch priority mapping (p0..p3).

Used to seed the GitHub issue's initial `priority/pN` label.
Subsequent hourly escalation (via GitHubIssuesAdapter.escalate_if_needed)
will bump the priority every 6h until p0 if the issue stays open.

Mapping rationale:
  - p0 reserved for impacts that block the whole cluster (NodeNotReady)
    or repeatedly-killed workloads (OOMKilled, CrashLoopBackOff).
  - p1 for symptoms that escalate without intervention (BackOff,
    ImagePullBackOff, FailedScheduling).
  - p2 for "soft" failures with retry potential (Failed, FailedMount,
    Evicted, FailedCreatePodSandBox, DeadlineExceeded, ErrImagePull).
  - p3 for low-noise / informational warnings (Unhealthy, FailedSync).

Unknown reasons → `default` (p3).
"""

from __future__ import annotations

__all__ = ["REASON_TO_PRIORITY", "priority_for"]


REASON_TO_PRIORITY: dict[str, str] = {
    # p0 — page-now
    "CrashLoopBackOff": "p0",
    "OOMKilled": "p0",
    "NodeNotReady": "p0",
    # p1 — escalating without intervention
    "BackOff": "p1",
    "ImagePullBackOff": "p1",
    "FailedScheduling": "p1",
    # p2 — soft / retryable
    "Failed": "p2",
    "FailedMount": "p2",
    "Evicted": "p2",
    "FailedCreatePodSandBox": "p2",
    "DeadlineExceeded": "p2",
    "ErrImagePull": "p2",
    # p3 — noisy / informational
    "Unhealthy": "p3",
    "FailedSync": "p3",
}


def priority_for(reason: str, default: str = "p3") -> str:
    """Return the priority bucket for a K8s event reason."""
    if not reason:
        return default
    return REASON_TO_PRIORITY.get(reason, default)
