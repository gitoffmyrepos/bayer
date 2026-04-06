"""
Pre-built Remediation Playbooks for Common K8s Issues.

Each playbook defines: detection → diagnosis → fix → verify pipeline.
Playbooks are executed by the GitOpsRemediator.

Author: Nova ⚡ | Nightwatch Platform
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger("nightwatch.remediation.playbooks")


@dataclass(frozen=True)
class PlaybookResult:
    """Immutable result of a playbook execution."""
    playbook_name: str
    success: bool
    steps_completed: list
    fix_description: str
    error: Optional[str] = None


def _get_pod_logs(namespace: str, pod_name: str, lines: int = 100) -> str:
    """Get last N lines of pod logs."""
    try:
        result = subprocess.run(
            ["kubectl", "logs", "-n", namespace, pod_name, "--tail", str(lines)],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return f"Error getting logs: {e}"


def _get_pod_events(namespace: str, pod_name: str) -> str:
    """Get recent events for a pod."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace,
             "--field-selector", f"involvedObject.name={pod_name}",
             "--sort-by=.lastTimestamp"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout
    except Exception as e:
        return f"Error getting events: {e}"


def _get_resource_limits(namespace: str, deployment_name: str) -> dict:
    """Get current resource limits for a deployment."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "deployment", deployment_name, "-n", namespace,
             "-o", "jsonpath={.spec.template.spec.containers[0].resources}"],
            capture_output=True, text=True, timeout=10,
        )
        import json
        return json.loads(result.stdout) if result.stdout else {}
    except Exception:
        return {}


def _parse_memory(mem_str: str) -> int:
    """Parse K8s memory string to bytes."""
    mem_str = str(mem_str).strip()
    multipliers = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    for suffix, mult in multipliers.items():
        if mem_str.endswith(suffix):
            return int(float(mem_str[:-len(suffix)]) * mult)
    return int(mem_str)


def _format_memory(bytes_val: int) -> str:
    """Format bytes to K8s memory string."""
    if bytes_val >= 1024**3:
        return f"{bytes_val // (1024**3)}Gi"
    if bytes_val >= 1024**2:
        return f"{bytes_val // (1024**2)}Mi"
    return f"{bytes_val // 1024}Ki"


# ─── Playbook Definitions ──────────────────────────────────────────────────────


class PlaybookRunner:
    """Runs pre-built remediation playbooks."""

    def __init__(self, remediator):
        self.remediator = remediator

    async def run(self, playbook_name: str, namespace: str,
                  resource_name: str, pod_name: str = "") -> PlaybookResult:
        """Execute a named playbook."""
        playbook_fn = PLAYBOOKS.get(playbook_name)
        if not playbook_fn:
            return PlaybookResult(
                playbook_name=playbook_name, success=False,
                steps_completed=[], fix_description="Unknown playbook",
                error=f"No playbook named '{playbook_name}'",
            )
        return await playbook_fn(self, namespace, resource_name, pod_name)

    async def playbook_oom_kill(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """OOMKilled → increase memory limit by 50%."""
        steps = ["detect_oom"]

        # Get current limits
        steps.append("read_current_limits")
        limits = _get_resource_limits(namespace, resource_name)
        current_mem = limits.get("limits", {}).get("memory", "256Mi")
        current_bytes = _parse_memory(current_mem)
        new_bytes = int(current_bytes * 1.5)
        new_mem = _format_memory(new_bytes)

        steps.append(f"increase_memory_{current_mem}_to_{new_mem}")

        # Get error context
        logs = _get_pod_logs(namespace, pod_name, lines=50)
        events = _get_pod_events(namespace, pod_name)
        error_context = f"OOMKilled. Current memory limit: {current_mem}\nEvents:\n{events}\nLogs:\n{logs}"

        # Run remediation
        result = await self.remediator.remediate(
            "oom_kill", namespace, resource_name, error_context
        )
        steps.extend(result.steps_taken)

        return PlaybookResult(
            playbook_name="oom_kill",
            success=result.success,
            steps_completed=steps,
            fix_description=f"Memory limit increased: {current_mem} → {new_mem}",
            error=result.error,
        )

    async def playbook_crash_loop(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """CrashLoopBackOff → check logs → add/increase startupProbe."""
        steps = ["detect_crash_loop"]

        # Read logs to understand the crash
        steps.append("read_pod_logs")
        logs = _get_pod_logs(namespace, pod_name, lines=100)
        events = _get_pod_events(namespace, pod_name)

        # Classify crash type
        steps.append("classify_crash")
        if "Startup probe failed" in events or "startup" in logs.lower():
            crash_type = "startup_timeout"
        elif "Liveness probe failed" in events:
            crash_type = "liveness_failure"
        elif "OOMKilled" in events:
            crash_type = "oom"  # Redirect to OOM playbook
        else:
            crash_type = "application_error"

        error_context = (
            f"CrashLoopBackOff (classified as {crash_type})\n"
            f"Events:\n{events}\nLast logs:\n{logs}"
        )

        if crash_type == "application_error":
            # Can't auto-fix application code — escalate
            return PlaybookResult(
                playbook_name="crash_loop",
                success=False,
                steps_completed=steps + ["escalate_application_error"],
                fix_description="Application code error — escalated to Nova",
                error="Application-level crash, not a K8s config issue",
            )

        # For startup/liveness issues, fix the probe
        issue_type = "crash_loop_backoff" if crash_type == "startup_timeout" else "liveness_probe_failure"
        result = await self.remediator.remediate(
            issue_type, namespace, resource_name, error_context
        )
        steps.extend(result.steps_taken)

        return PlaybookResult(
            playbook_name="crash_loop",
            success=result.success,
            steps_completed=steps,
            fix_description=result.fix_description,
            error=result.error,
        )

    async def playbook_image_pull(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """ImagePullBackOff → check registry → fix tag."""
        steps = ["detect_image_pull_error"]
        events = _get_pod_events(namespace, pod_name)
        error_context = f"ImagePullBackOff\nEvents:\n{events}"

        result = await self.remediator.remediate(
            "image_pull_error", namespace, resource_name, error_context
        )
        steps.extend(result.steps_taken)

        return PlaybookResult(
            playbook_name="image_pull",
            success=result.success,
            steps_completed=steps,
            fix_description=result.fix_description,
            error=result.error,
        )

    async def playbook_probe_failure(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """Probe failure → increase timeout/period."""
        steps = ["detect_probe_failure"]
        events = _get_pod_events(namespace, pod_name)
        logs = _get_pod_logs(namespace, pod_name, lines=30)

        # Determine which probe
        if "Liveness" in events:
            issue_type = "liveness_probe_failure"
        elif "Readiness" in events:
            issue_type = "readiness_probe_failure"
        else:
            issue_type = "startup_probe_failure"

        error_context = f"{issue_type}\nEvents:\n{events}\nLogs:\n{logs}"

        result = await self.remediator.remediate(
            issue_type, namespace, resource_name, error_context
        )
        steps.extend(result.steps_taken)

        return PlaybookResult(
            playbook_name="probe_failure",
            success=result.success,
            steps_completed=steps,
            fix_description=result.fix_description,
            error=result.error,
        )

    async def playbook_resource_exhaustion(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """Pending with insufficient resources → reduce requests or adjust scheduling."""
        steps = ["detect_resource_exhaustion"]
        events = _get_pod_events(namespace, pod_name)
        error_context = f"Pending pod - resource exhaustion\nEvents:\n{events}"

        result = await self.remediator.remediate(
            "resource_quota_exceeded", namespace, resource_name, error_context
        )
        steps.extend(result.steps_taken)

        return PlaybookResult(
            playbook_name="resource_exhaustion",
            success=result.success,
            steps_completed=steps,
            fix_description=result.fix_description,
            error=result.error,
        )


# Registry of playbooks
PLAYBOOKS = {
    "oom_kill": PlaybookRunner.playbook_oom_kill,
    "crash_loop": PlaybookRunner.playbook_crash_loop,
    "image_pull": PlaybookRunner.playbook_image_pull,
    "probe_failure": PlaybookRunner.playbook_probe_failure,
    "resource_exhaustion": PlaybookRunner.playbook_resource_exhaustion,
}
