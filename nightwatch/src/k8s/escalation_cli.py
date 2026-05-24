"""
CronJob entrypoint: hourly priority escalation across all routed repos.

Runs:
  python -m src.k8s.escalation_cli

For each repo discovered via the routing rules, instantiates a
GitHubIssuesAdapter and runs its `run_escalation_cycle()`. The adapter
already enforces the 6h-since-last-escalation cooldown (in-memory per
process — which is fine for a once-per-hour CronJob because escalations
that didn't fire this run will fire next run).

Environment:
  GITHUB_TOKEN              required (from forextrader-research-secrets)
  NIGHTWATCH_GH_DRY_RUN     "true" (default) → log only, no GitHub mutation
  NIGHTWATCH_ROUTING_RULES  path to routing rules YAML (default: /app/config/routing-rules.yaml)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import structlog

from src.adapters.github_adapter import GitHubIssuesAdapter
from src.k8s.routing import RepoRouter

log = structlog.get_logger("nightwatch.k8s.escalation_cli")


def _is_dry_run() -> bool:
    val = os.environ.get("NIGHTWATCH_GH_DRY_RUN", "true").strip().lower()
    return val in ("1", "true", "yes", "on")


async def escalate_repo(owner: str, name: str, token: str, dry_run: bool) -> dict:
    adapter = GitHubIssuesAdapter(
        {"repo_owner": owner, "repo_name": name, "api_token": token}
    )
    try:
        if dry_run:
            log.info("dry_run_escalation_would_run", repo=f"{owner}/{name}")
            # Read-only — list issues so we report what WOULD have been escalated.
            from src.adapters.github_adapter import PRIORITY_LABELS

            candidates: list[dict] = []
            for p in ("p3", "p2", "p1"):
                try:
                    issues = await adapter.find_issues_by_label(
                        PRIORITY_LABELS[p], state="open"
                    )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "dry_run_list_failed", repo=f"{owner}/{name}", priority=p, error=str(e)
                    )
                    continue
                for iss in issues:
                    candidates.append({"number": iss["number"], "priority": p})
            log.info(
                "dry_run_escalation_candidates",
                repo=f"{owner}/{name}",
                count=len(candidates),
            )
            return {"repo": f"{owner}/{name}", "dry_run": True, "candidates": candidates}

        results = await adapter.run_escalation_cycle()
        return {"repo": f"{owner}/{name}", "dry_run": False, "escalated": results}
    finally:
        await adapter.close()


async def main_async() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        log.error("github_token_missing_exiting")
        return 2

    dry_run = _is_dry_run()
    rules_path = os.environ.get(
        "NIGHTWATCH_ROUTING_RULES", "/app/config/routing-rules.yaml"
    )
    router = RepoRouter.from_yaml(rules_path)
    repos = sorted(router.all_repos())
    log.info(
        "escalation_cli_start",
        dry_run=dry_run,
        repos=[f"{o}/{n}" for (o, n) in repos],
        rules_path=rules_path,
    )

    summaries: list[dict] = []
    for owner, name in repos:
        try:
            summary = await escalate_repo(owner, name, token, dry_run)
            summaries.append(summary)
        except Exception as e:  # noqa: BLE001
            log.error("escalation_cli_repo_failed", repo=f"{owner}/{name}", error=str(e))
            summaries.append({"repo": f"{owner}/{name}", "error": str(e)})

    print(json.dumps({"summaries": summaries}, indent=2, default=str))
    log.info("escalation_cli_done", repos=len(summaries))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
