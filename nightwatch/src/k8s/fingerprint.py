"""
Fingerprint generator for K8s Event → GitHub Issue dedup.

A fingerprint is a short, deterministic hash over the canonical tuple:
    (repo, issue_kind, namespace, resource_name, reason)

Same tuple → same fingerprint → same GitHub issue.

Why include `repo`? The same resource (e.g. `prod-forex/Pod/foo` with reason
`CrashLoopBackOff`) may be routed to different repos depending on operator
config — we want the fingerprint to be scoped to the destination repo so a
routing-rule change does not silently merge into a stale issue.
"""

from __future__ import annotations

import hashlib

__all__ = ["compute_fingerprint", "FINGERPRINT_LEN"]

FINGERPRINT_LEN = 16  # hex chars (64 bits) — collision-resistant for our volume


def compute_fingerprint(
    repo: str,
    issue_kind: str,
    namespace: str,
    resource_name: str,
    reason: str,
) -> str:
    """
    Compute a deterministic 16-char hex fingerprint.

    Args:
        repo:          "owner/name", e.g. "gitoffmyrepos/FX".
        issue_kind:    Logical issue class — e.g. "k8s-event".
                       Reserved for future expansion (e.g. "metric-anomaly").
        namespace:     K8s namespace, or "" for cluster-scoped resources.
        resource_name: K8s resource name (involvedObject.name).
        reason:        K8s event reason (e.g. "CrashLoopBackOff").

    Returns:
        16-char lowercase hex prefix of a SHA-256 digest.
    """
    parts = [repo or "", issue_kind or "", namespace or "", resource_name or "", reason or ""]
    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_LEN]
