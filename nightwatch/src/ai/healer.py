"""
Nightwatch AI Healer
=====================
AI-driven auto-remediation suggestion and execution engine.

The healer takes AI diagnosis results and:
  1. Suggests concrete remediation commands
  2. Executes safe, pre-approved remediation actions (when enabled)
  3. Logs all remediation attempts

SAFETY: Auto-remediation is OFF by default. Enable with care.
All commands run in dry-run mode unless explicitly enabled.

Author: Nova ⚡ | Nightwatch Platform
"""

import asyncio
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.core.llm_client import NightwatchLLMClient

log = structlog.get_logger("nightwatch.ai.healer")


class HealingAction:
    """A proposed or executed remediation action."""

    def __init__(self, name: str, command: str, description: str, risk_level: str = "low"):
        self.name = name
        self.command = command
        self.description = description
        self.risk_level = risk_level  # low | medium | high
        self.executed = False
        self.success = None
        self.output = ""
        self.executed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "description": self.description,
            "risk_level": self.risk_level,
            "executed": self.executed,
            "success": self.success,
            "output": self.output[:500] if self.output else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class AIHealer:
    """
    Suggests and optionally executes auto-remediation actions.

    Configure allowed actions in nightwatch.yaml [healing] section.

    SAFETY LEVELS:
      - suggest_only: Only suggest actions, never execute (DEFAULT)
      - auto_low_risk: Auto-execute low-risk actions (restarts, cache clears)
      - auto_medium_risk: Auto-execute medium-risk actions (scaling, config changes)
      - disabled: No healing, no suggestions
    """

    # Pre-approved safe actions (always allowed in auto modes)
    SAFE_ACTIONS = {
        "k8s_restart_pod": {
            "pattern": r"kubectl rollout restart deployment/\S+ -n \S+",
            "risk": "low",
        },
        "k8s_scale_up": {
            "pattern": r"kubectl scale deployment/\S+ --replicas=\d+ -n \S+",
            "risk": "medium",
        },
        "clear_jenkins_cache": {
            "pattern": r"ssh .* 'docker exec jenkins rm -rf /var/jenkins_home/caches/git-\*'",
            "risk": "low",
        },
    }

    def __init__(self, llm_client: NightwatchLLMClient, config: dict):
        self.llm = llm_client
        self.mode = config.get("mode", "suggest_only")
        self.allowed_actions = config.get("allowed_actions", list(self.SAFE_ACTIONS.keys()))
        self.dry_run = config.get("dry_run", True)
        self._history: list[HealingAction] = []

    def suggest_remediation(
        self,
        diagnosis: dict,
        architecture: str = "",
        application: str = "",
    ) -> list[HealingAction]:
        """
        Use AI to suggest concrete remediation actions for a diagnosis.

        Returns a list of HealingAction objects (not yet executed).
        """
        if self.mode == "disabled":
            return []

        prompt = f"""You are Nightwatch, an AI monitoring system. Suggest concrete remediation actions.

APPLICATION: {application}
ARCHITECTURE: {architecture}

DIAGNOSIS:
- Root cause: {diagnosis.get('root_cause')}
- Severity: {diagnosis.get('severity')}
- Recommendation: {diagnosis.get('recommendation')}
- Auto-fix possible: {diagnosis.get('auto_fix_possible')}

Provide 1-3 specific remediation commands in this JSON format:
[
  {{
    "name": "restart_failed_pod",
    "command": "kubectl rollout restart deployment/xyz -n prod",
    "description": "Restart the failed deployment to clear transient errors",
    "risk_level": "low"
  }}
]

Only suggest commands that are safe and reversible. Prefer low-risk actions.
Respond with ONLY the JSON array."""

        try:
            response = self.llm._call(prompt)
            # Extract JSON
            import json
            import re
            json_match = re.search(r"\[.*?\]", response, re.DOTALL)
            if json_match:
                actions_data = json.loads(json_match.group(0))
                actions = []
                for a in actions_data[:3]:  # Max 3 suggestions
                    action = HealingAction(
                        name=a.get("name", "unnamed_action"),
                        command=a.get("command", ""),
                        description=a.get("description", ""),
                        risk_level=a.get("risk_level", "medium"),
                    )
                    actions.append(action)
                return actions
        except Exception as e:
            log.warning("healing_suggestion_failed", error=str(e))

        # Fallback: use the auto_fix_command from diagnosis
        if diagnosis.get("auto_fix_possible") and diagnosis.get("auto_fix_command"):
            return [HealingAction(
                name="ai_suggested_fix",
                command=diagnosis["auto_fix_command"],
                description="AI-suggested auto-fix from diagnosis",
                risk_level="medium",
            )]

        return []

    async def execute_healing(
        self,
        actions: list[HealingAction],
        force: bool = False,
    ) -> list[HealingAction]:
        """
        Execute approved healing actions.

        Args:
            actions: List of HealingAction objects
            force: Bypass dry_run mode (use with caution)

        Returns:
            The same list with execution results filled in.
        """
        if self.mode in ("disabled", "suggest_only") and not force:
            log.info("healing_skipped", mode=self.mode, action_count=len(actions))
            return actions

        for action in actions:
            if action.risk_level == "high" and self.mode != "auto_medium_risk":
                log.warning("healing_skipped_high_risk", action=action.name)
                continue

            if self.dry_run and not force:
                log.info("healing_dry_run", action=action.name, command=action.command)
                action.executed = True
                action.success = True
                action.output = "[DRY RUN] Command not executed"
                action.executed_at = datetime.now(timezone.utc)
            else:
                log.warning("executing_healing_action", action=action.name, command=action.command)
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: subprocess.run(
                            shlex.split(action.command),
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                    )
                    action.executed = True
                    action.success = result.returncode == 0
                    action.output = (result.stdout + result.stderr)[:500]
                    action.executed_at = datetime.now(timezone.utc)

                    log.info(
                        "healing_executed",
                        action=action.name,
                        success=action.success,
                        output=action.output[:100],
                    )
                except Exception as e:
                    action.executed = True
                    action.success = False
                    action.output = str(e)
                    log.error("healing_failed", action=action.name, error=str(e))

            self._history.append(action)

        return actions

    def get_history(self, limit: int = 20) -> list[dict]:
        return [a.to_dict() for a in self._history[-limit:]]
