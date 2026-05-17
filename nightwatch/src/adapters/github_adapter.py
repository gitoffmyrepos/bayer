"""
GitHub Issues Adapter for Nightwatch
=====================================
Integrates Nightwatch with GitHub Issues for automated issue tracking and priority escalation.

Features:
  - Auto-creates GitHub issues from Nightwatch incidents
  - Deduplicates: checks for existing open issues with same title before creating
  - Priority escalation: bumps priority label every 6 hours if issue is unresolved
  - Priority labels: priority/p0 (critical) → p1 → p2 → p3 (low)
  - Adds `nightwatch` label to all auto-created issues

Usage:
  adapter = GitHubIssuesAdapter({
      "repo_owner": "gitoffmyrepos",
      "repo_name": "FX",
      "api_token": os.getenv("GITHUB_API_TOKEN"),
  })
  await adapter.create_issue(incident, priority="p3")
  existing = await adapter.find_duplicate_issue(title)

Author: Nova ⚡ | Nightwatch Platform
"""

import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import structlog

log = structlog.get_logger("nightwatch.adapter.github")

GITHUB_API = "https://api.github.com"

# Priority → label mapping
PRIORITY_LABELS = {
    "p0": "priority/p0",
    "p1": "priority/p1",
    "p2": "priority/p2",
    "p3": "priority/p3",
}

# All Nightwatch-created issues get these labels
DEFAULT_LABELS = ["nightwatch", "automated"]

# Auto-escalation schedule (seconds)
ESCALATION_INTERVAL = 6 * 3600  # 6 hours per priority level


class GitHubIssuesAdapter:
    """
    GitHub Issues integration for Nightwatch.

    Handles:
      - Creating issues from incidents
      - Deduplicating by title
      - Priority management and escalation
      - Linking incidents to GitHub issues
    """

    def __init__(self, config: dict):
        self.repo_owner = config["repo_owner"]
        self.repo_name = config["repo_name"]
        self.api_token = config.get("api_token") or os.getenv("GITHUB_API_TOKEN", "")
        self.base_url = f"{GITHUB_API}/repos/{self.repo_owner}/{self.repo_name}"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._http = httpx.AsyncClient(timeout=30)
        # Track last-escalation time per issue to avoid re-escalating within window
        self._last_escalation: dict[int, float] = {}

    async def close(self):
        await self._http.aclose()

    # ─── Issue CRUD ─────────────────────────────────────────────────────────

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[list[str]] = None,
        priority: str = "p3",
    ) -> dict:
        """
        Create a new GitHub issue.

        Returns:
            Created issue dict with id, number, html_url
        """
        all_labels = list(DEFAULT_LABELS)
        if priority and priority in PRIORITY_LABELS:
            all_labels.append(PRIORITY_LABELS[priority])
        if labels:
            all_labels.extend(labels)

        payload = {
            "title": title,
            "body": body,
            "labels": list(set(all_labels)),  # dedupe
        }

        log.info("github_create_issue", title=title[:60], labels=all_labels, repo=f"{self.repo_owner}/{self.repo_name}")
        resp = await self._http.post(
            f"{self.base_url}/issues",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        issue = resp.json()
        log.info("github_issue_created", number=issue["number"], html_url=issue["html_url"])
        return issue

    async def get_issue(self, issue_number: int) -> dict:
        """Get a single issue by number."""
        resp = await self._http.get(
            f"{self.base_url}/issues/{issue_number}",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def update_issue(
        self,
        issue_number: int,
        body: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> dict:
        """Update an existing issue (body, state, labels)."""
        payload = {}
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels

        if not payload:
            return {}

        resp = await self._http.patch(
            f"{self.base_url}/issues/{issue_number}",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def add_issue_comment(self, issue_number: int, body: str) -> dict:
        """Add a comment to an issue."""
        payload = {"body": body}
        resp = await self._http.post(
            f"{self.base_url}/issues/{issue_number}/comments",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_labels(self) -> list[dict]:
        """Get all labels in the repo."""
        resp = await self._http.get(
            f"{self.base_url}/labels",
            headers=self.headers,
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()

    async def ensure_label(self, label_name: str, color: str = "ffffff") -> dict:
        """Ensure a label exists, creating it if needed."""
        # Check if it exists
        existing = await self._http.get(
            f"{self.base_url}/labels/{label_name}",
            headers=self.headers,
        )
        if existing.status_code == 200:
            return existing.json()

        # Create it
        resp = await self._http.post(
            f"{self.base_url}/labels",
            headers=self.headers,
            json={"name": label_name, "color": color},
        )
        resp.raise_for_status()
        return resp.json()

    # ─── Deduplication ─────────────────────────────────────────────────────────

    async def find_duplicate_issue(self, title: str, state: str = "open") -> Optional[dict]:
        """
        Search for an open issue with the same title (case-insensitive).

        Returns:
            The matching issue dict, or None if no duplicate found.
        """
        search_title = title.lower().strip()
        page = 1
        while True:
            resp = await self._http.get(
                f"{self.base_url}/issues",
                headers=self.headers,
                params={
                    "state": state,
                    "labels": "nightwatch",
                    "per_page": 100,
                    "page": page,
                },
            )
            resp.raise_for_status()
            issues = resp.json()
            if not issues:
                break

            for issue in issues:
                if issue["title"].lower().strip() == search_title:
                    log.info("github_duplicate_found", number=issue["number"], title=title[:60])
                    return issue

            # If we got fewer than per_page, we're done
            if len(issues) < 100:
                break
            page += 1

        log.info("github_no_duplicate", title=title[:60])
        return None

    async def find_issues_by_label(self, label: str, state: str = "open") -> list[dict]:
        """Get all open issues with a specific label."""
        resp = await self._http.get(
            f"{self.base_url}/issues",
            headers=self.headers,
            params={"state": state, "labels": label, "per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()

    # ─── Priority Escalation ──────────────────────────────────────────────────

    async def get_priority_level(self, issue_number: int) -> Optional[str]:
        """Get current priority level of an issue (p0-p3)."""
        issue = await self.get_issue(issue_number)
        label_names = [l["name"] for l in issue.get("labels", [])]
        for p in ["p0", "p1", "p2", "p3"]:
            if PRIORITY_LABELS[p] in label_names:
                return p
        return None

    async def set_priority(self, issue_number: int, priority: str) -> dict:
        """Set or update the priority label on an issue."""
        issue = await self.get_issue(issue_number)
        current_labels = {l["name"] for l in issue.get("labels", [])}

        # Remove old priority labels
        for p in PRIORITY_LABELS.values():
            current_labels.discard(p)

        # Add new priority label
        if priority in PRIORITY_LABELS:
            current_labels.add(PRIORITY_LABELS[priority])

        return await self.update_issue(issue_number, labels=list(current_labels))

    async def bump_priority(self, issue_number: int) -> dict:
        """
        Bump priority by one level (p3 → p2 → p1 → p0).

        p0 is the ceiling — cannot go higher.
        Returns the new priority level.
        """
        current = await self.get_priority_level(issue_number) or "p3"
        priority_order = ["p3", "p2", "p1", "p0"]
        idx = priority_order.index(current)
        if idx > 0:
            new_priority = priority_order[idx - 1]
        else:
            new_priority = "p0"  # Already at max

        await self.set_priority(issue_number, new_priority)
        log.info("github_priority_bumped", issue=issue_number, from_p=current, to_p=new_priority)
        return {"issue_number": issue_number, "old_priority": current, "new_priority": new_priority}

    async def escalate_if_needed(self, issue_number: int, incident_id: str = "") -> Optional[dict]:
        """
        Escalate an issue to the next priority level if:
          1. It's been >6 hours since last escalation
          2. It's still open
          3. Priority is not yet p0

        Returns bump info dict if escalated, None otherwise.
        """
        now = time.time()
        last = self._last_escalation.get(issue_number, 0)

        if now - last < ESCALATION_INTERVAL:
            log.debug("github_escalation_cooldown", issue=issue_number, elapsed=int(now - last))
            return None

        current = await self.get_priority_level(issue_number) or "p3"
        if current == "p0":
            log.debug("github_already_p0", issue=issue_number)
            return None

        issue = await self.get_issue(issue_number)
        if issue.get("state") == "closed":
            log.debug("github_issue_closed_skip_escalation", issue=issue_number)
            return None

        # Perform the escalation
        self._last_escalation[issue_number] = now
        result = await self.bump_priority(issue_number)

        # Add a comment noting the escalation
        escalation_comment = (
            f"**⏰ Auto-escalation** (Nightwatch)\n\n"
            f"This issue has been open for over {ESCALATION_INTERVAL // 3600} hours "
            f"without resolution and has been escalated to **{result['new_priority']}**.\n\n"
            f"Incident reference: `{incident_id}`"
        )
        await self.add_issue_comment(issue_number, escalation_comment)

        log.info("github_issue_escalated", issue=issue_number, new_priority=result["new_priority"])
        return result

    # ─── Incident → Issue Pipeline ─────────────────────────────────────────────

    async def process_incident(
        self,
        title: str,
        body: str,
        incident_id: str = "",
        severity: str = "medium",
        existing_issue_number: int = 0,
    ) -> dict:
        """
        Main entry point for Nightwatch.

        1. Check for duplicate (by title)
        2. If duplicate found: attach comment, link incident
        3. If new: create issue at appropriate priority
        4. Return issue info with action taken
        """
        # Map severity to priority
        sev_to_priority = {
            "critical": "p0",
            "high": "p1",
            "medium": "p2",
            "low": "p3",
            "info": "p3",
        }
        initial_priority = sev_to_priority.get(severity, "p3")

        # Normalize title for deduplication
        normalized_title = title.strip()

        # Check for existing open issue
        if existing_issue_number:
            # Link to a specific known issue number
            issue = await self.get_issue(existing_issue_number)
            action = "linked"
        else:
            issue = await self.find_duplicate_issue(normalized_title)
            action = "duplicate_found" if issue else "created"

        if issue:
            # Attach incident details as a comment
            comment = (
                f"**🔄 Nightwatch Incident Update**\n\n"
                f"**Incident ID:** `{incident_id}`\n"
                f"**Severity:** {severity.upper()}\n"
                f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n"
                f"**Details:**\n{body[:1500]}"
            )
            await self.add_issue_comment(issue["number"], comment)
            log.info("github_incident_attached", issue=issue["number"], action="comment_added")
            return {
                "action": "attached",
                "issue_number": issue["number"],
                "html_url": issue["html_url"],
                "title": issue["title"],
                "duplicate": True,
            }

        # Create new issue with [Nightwatch] prefix for easy filtering
        issue_title = f"[Nightwatch] {normalized_title}"
        result = await self.create_issue(
            title=issue_title,
            body=body,
            priority=initial_priority,
        )

        log.info(
            "github_incident_processed",
            issue=result["number"],
            action="created",
            priority=initial_priority,
        )
        return {
            "action": "created",
            "issue_number": result["number"],
            "html_url": result["html_url"],
            "title": result["title"],
            "priority": initial_priority,
            "duplicate": False,
        }

    # ─── Batch Operations ─────────────────────────────────────────────────────

    async def run_escalation_cycle(self) -> list[dict]:
        """
        Run one escalation cycle on all open nightwatch issues.

        Called by the engine or a scheduled task every hour.
        Returns list of escalation results.
        """
        log.info("github_escalation_cycle_start")
        results = []

        # Get all open p1-p3 issues with nightwatch label
        for priority in ["p3", "p2", "p1"]:
            label = PRIORITY_LABELS[priority]
            issues = await self.find_issues_by_label(label, state="open")

            for issue in issues:
                issue_num = issue["number"]
                incident_id = f"nightwatch-{issue_num}"
                result = await self.escalate_if_needed(issue_num, incident_id)
                if result:
                    results.append(result)

        log.info("github_escalation_cycle_done", escalated=len(results))
        return results