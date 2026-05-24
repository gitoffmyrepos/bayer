"""
LLM-driven GitHub issue body generator for K8s events.

Pulls a small bundle of observed data (event details + recent pod logs +
related events for the same resource) and asks the LLM to write a concise
Markdown issue body in a format that downstream LLM agents (Openclaw,
Hermes, Goose) can act on autonomously.

Deterministic fallback: if the LLM call fails, we still emit a structured
Markdown body with all observed data — so issue creation is never blocked
on LLM availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger("nightwatch.k8s.issue_body")

__all__ = ["IssueBodyContext", "IssueBodyBuilder"]


_PROMPT_TEMPLATE = """You are a Kubernetes SRE assistant working inside the Nightwatch \
monitoring platform. Generate a concise GitHub issue body in Markdown for an \
LLM agent (Openclaw / Hermes / Goose) to investigate and fix autonomously.

The body MUST contain these sections, in this exact order:
### Summary
### Symptoms
### Recent Events
### Recent Logs
### Suggested Investigation
### Related Resources

Strict rules:
- Be terse and factual. Use only the observed data below.
- Do NOT invent root causes. Phrase hypotheses with "may", "could", "suggests".
- Wrap log/event text in ```fenced code blocks```.
- Keep the whole body under ~80 lines.

OBSERVED DATA:
{data_block}
"""


@dataclass
class IssueBodyContext:
    """All observed data passed to the LLM (and used for the deterministic fallback)."""

    namespace: str
    kind: str
    name: str
    reason: str
    message: str
    count: int
    first_seen: Optional[str]
    last_seen: Optional[str]
    source_component: Optional[str] = None
    recent_logs: list[str] = None  # tail of pod logs (max ~80 lines)
    related_events: list[dict] = None  # last few events for same resource
    repo_slug: Optional[str] = None  # "owner/name" for context
    fingerprint: Optional[str] = None

    def __post_init__(self):
        if self.recent_logs is None:
            self.recent_logs = []
        if self.related_events is None:
            self.related_events = []

    def to_data_block(self) -> str:
        """Format observed data for the prompt — kept compact."""
        lines: list[str] = []
        lines.append(f"- namespace: {self.namespace}")
        lines.append(f"- kind: {self.kind}")
        lines.append(f"- name: {self.name}")
        lines.append(f"- reason: {self.reason}")
        lines.append(f"- event_count: {self.count}")
        lines.append(f"- first_seen: {self.first_seen or 'unknown'}")
        lines.append(f"- last_seen: {self.last_seen or 'unknown'}")
        if self.source_component:
            lines.append(f"- source: {self.source_component}")
        if self.repo_slug:
            lines.append(f"- routed_to_repo: {self.repo_slug}")
        if self.fingerprint:
            lines.append(f"- fingerprint: {self.fingerprint}")
        lines.append(f"- message: {self.message[:500]}")

        if self.related_events:
            lines.append("")
            lines.append("RELATED EVENTS (last 10):")
            for ev in self.related_events[-10:]:
                lines.append(
                    f"  - [{ev.get('last_seen', '?')}] "
                    f"{ev.get('reason', '?')}: {str(ev.get('message', ''))[:200]}"
                )
        if self.recent_logs:
            lines.append("")
            lines.append("RECENT LOGS (last lines):")
            for ln in self.recent_logs[-80:]:
                lines.append(f"  {ln.rstrip()}")
        return "\n".join(lines)


class IssueBodyBuilder:
    """
    Build a Markdown issue body from an IssueBodyContext.

    Tries the LLM first; falls back to a deterministic template if the
    call raises. Either way the operator gets the raw observed data.
    """

    def __init__(self, llm_client=None, max_tokens: int = 1200):
        self.llm = llm_client
        self.max_tokens = int(max_tokens)

    def build(self, ctx: IssueBodyContext) -> str:
        if self.llm is None:
            return self._fallback(ctx, reason="no_llm_client")
        prompt = _PROMPT_TEMPLATE.format(data_block=ctx.to_data_block())
        try:
            body = self.llm.complete(prompt, max_tokens=self.max_tokens)
            body = (body or "").strip()
            if not body:
                return self._fallback(ctx, reason="empty_llm_response")
            return self._append_meta(body, ctx)
        except Exception as e:  # noqa: BLE001 — LLM client surfaces many error types
            log.warning(
                "issue_body_llm_failed_using_fallback",
                error=str(e),
                fingerprint=ctx.fingerprint,
            )
            return self._fallback(ctx, reason=f"llm_error: {type(e).__name__}")

    # ─── internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _append_meta(body: str, ctx: IssueBodyContext) -> str:
        """Append a hidden meta block consumed by the dedup updater."""
        meta = build_meta_footer(ctx)
        return f"{body}\n\n{meta}"

    @staticmethod
    def _fallback(ctx: IssueBodyContext, reason: str) -> str:
        log.info("issue_body_fallback", reason=reason, fingerprint=ctx.fingerprint)
        logs_block = (
            "```\n" + "\n".join(ctx.recent_logs[-80:]) + "\n```"
            if ctx.recent_logs
            else "_no logs captured_"
        )
        events_block = "_no related events captured_"
        if ctx.related_events:
            events_lines = [
                f"- `{ev.get('last_seen', '?')}` **{ev.get('reason', '?')}** — "
                f"{str(ev.get('message', ''))[:200]}"
                for ev in ctx.related_events[-10:]
            ]
            events_block = "\n".join(events_lines)

        body = f"""### Summary
A Kubernetes Warning event was repeatedly observed on **{ctx.kind}/{ctx.name}** \
in namespace `{ctx.namespace}` with reason `{ctx.reason}`.

### Symptoms
- Reason: `{ctx.reason}`
- Event count: {ctx.count}
- Message: {ctx.message[:400]}
- First seen: `{ctx.first_seen or 'unknown'}`
- Last seen: `{ctx.last_seen or 'unknown'}`

### Recent Events
{events_block}

### Recent Logs
{logs_block}

### Suggested Investigation
- `kubectl -n {ctx.namespace} describe {ctx.kind.lower()} {ctx.name}`
- `kubectl -n {ctx.namespace} get events --field-selector involvedObject.name={ctx.name}`
- `kubectl -n {ctx.namespace} logs {ctx.name} --tail=200 --previous` (if Pod)
- Inspect recent changes in the owning Deployment / StatefulSet / DaemonSet.

### Related Resources
- Namespace: `{ctx.namespace}`
- Resource: `{ctx.kind}/{ctx.name}`
"""
        return f"{body}\n{build_meta_footer(ctx, fallback_reason=reason)}"


def build_meta_footer(ctx: IssueBodyContext, fallback_reason: Optional[str] = None) -> str:
    """
    Generate the hidden HTML-comment meta block used for body refresh on re-observation.

    Kept stable so dedup updater can swap the block atomically.
    """
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "<!-- nightwatch-meta -->",
        f"<!-- fingerprint: {ctx.fingerprint or 'unknown'} -->",
        f"<!-- namespace: {ctx.namespace} -->",
        f"<!-- kind: {ctx.kind} -->",
        f"<!-- name: {ctx.name} -->",
        f"<!-- reason: {ctx.reason} -->",
        f"<!-- last_seen: {ctx.last_seen or now} -->",
        f"<!-- event_count: {ctx.count} -->",
    ]
    if fallback_reason:
        lines.append(f"<!-- body_source: deterministic_fallback ({fallback_reason}) -->")
    else:
        lines.append("<!-- body_source: llm -->")
    lines.append("<!-- /nightwatch-meta -->")
    return "\n".join(lines)


def replace_meta_footer(body: str, new_footer: str) -> str:
    """
    Swap an existing `<!-- nightwatch-meta -->` block in `body` with `new_footer`.

    If the body has no footer (older issues), the new footer is appended.
    """
    import re

    pattern = re.compile(
        r"<!-- nightwatch-meta -->.*?<!-- /nightwatch-meta -->", re.DOTALL
    )
    if pattern.search(body or ""):
        return pattern.sub(new_footer, body)
    return f"{(body or '').rstrip()}\n\n{new_footer}"
