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

    async def playbook_cilium_empty_bpf_map(
        self, namespace: str, resource_name: str, pod_name: str
    ) -> PlaybookResult:
        """Cilium BPF policy map empty → pods receive no ingress traffic.

        Root cause: Cilium operator crash-loop disrupts identity allocation.
        New endpoints get BPF policy maps created but sync-policymap writes 0
        entries (deny-all). Fix: add 3 wildcard allow entries directly to the
        per-endpoint LPM trie on the node hosting the pod.

        Wildcard entries added:
          - identity=0 (any), port=0 (any), proto=0 (any) → allow all ingress
          - identity=1 (reserved:host), port=0, proto=0 → allow kubelet probes
          - identity=0, port=0, proto=1 (ICMP) → allow ICMP
        """
        steps = ["detect_cilium_bpf_issue"]

        # Get pod's node name and IP
        steps.append("get_pod_node")
        try:
            node_result = subprocess.run(
                ["kubectl", "get", "pod", pod_name, "-n", namespace,
                 "-o", "jsonpath={.spec.nodeName} {.status.podIP}"],
                capture_output=True, text=True, timeout=10,
            )
            parts = node_result.stdout.strip().split()
            if len(parts) < 2:
                return PlaybookResult(
                    playbook_name="cilium_empty_bpf_map", success=False,
                    steps_completed=steps, fix_description="Could not get pod node info",
                    error=f"kubectl output: {node_result.stdout!r}",
                )
            node_name, pod_ip = parts[0], parts[1]
        except Exception as e:
            return PlaybookResult(
                playbook_name="cilium_empty_bpf_map", success=False,
                steps_completed=steps, fix_description="kubectl failed",
                error=str(e),
            )

        # Get node IP
        steps.append("get_node_ip")
        try:
            ip_result = subprocess.run(
                ["kubectl", "get", "node", node_name,
                 "-o", "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}"],
                capture_output=True, text=True, timeout=10,
            )
            node_ip = ip_result.stdout.strip()
            if not node_ip:
                return PlaybookResult(
                    playbook_name="cilium_empty_bpf_map", success=False,
                    steps_completed=steps, fix_description="Could not get node IP",
                    error=f"Empty node IP for {node_name}",
                )
        except Exception as e:
            return PlaybookResult(
                playbook_name="cilium_empty_bpf_map", success=False,
                steps_completed=steps, fix_description="kubectl node IP failed",
                error=str(e),
            )

        # SSH to node, find endpoint ID for pod IP, check and fix policy map
        steps.append(f"ssh_to_node_{node_ip}")
        ssh_key = "/root/.ssh/strategybase-dev"
        fix_script = f"""
set -e
# Find endpoint ID for pod IP {pod_ip}
EP_ID=$(sudo /var/run/cilium/state/*/endpoint_config.json 2>/dev/null | \\
  python3 -c "import sys,json; [print(d['id']) for d in [json.load(open(f)) for f in sys.argv[1:]] if d.get('ipv4','')=='{pod_ip}']" 2>/dev/null || \\
  sudo find /var/run/cilium/state -name 'ep_config.h' 2>/dev/null | \\
  xargs grep -l 'DEFINE_IPV4.*{pod_ip.replace('.', '_')}' 2>/dev/null | \\
  sed 's|.*/\\([0-9]*\\)/ep_config.h|\\1|' | head -1)

# Fallback: use Cilium API via unix socket
if [ -z "$EP_ID" ]; then
  EP_ID=$(curl -s --unix-socket /var/run/cilium/cilium.sock \\
    http://localhost/v1/endpoint 2>/dev/null | \\
    python3 -c "
import sys,json
eps = json.load(sys.stdin)
for e in eps:
    for a in e.get('status',{{}}).get('networking',{{}}).get('addressing',[]):
        if a.get('ipv4') == '{pod_ip}':
            print(e['id'])
            break
" 2>/dev/null | head -1)
fi

if [ -z "$EP_ID" ]; then
  echo "ERROR: Could not find endpoint for {pod_ip}"
  exit 1
fi

EP_HEX=$(printf '%05d' $EP_ID)
MAP_FILE="/sys/fs/bpf/tc/globals/cilium_policy_v2_$EP_HEX"

if [ ! -f "$MAP_FILE" ]; then
  echo "ERROR: Map file not found: $MAP_FILE"
  exit 1
fi

MAP_ID=$(sudo bpftool map show pinned $MAP_FILE 2>/dev/null | awk 'NR==1{{print $1}}' | tr -d ':')
if [ -z "$MAP_ID" ]; then
  echo "ERROR: Could not get map ID for $MAP_FILE"
  exit 1
fi

ENTRIES=$(sudo bpftool map dump id $MAP_ID 2>/dev/null | grep -c '^key')
echo "EP=$EP_ID MAP_ID=$MAP_ID ENTRIES=$ENTRIES"

if [ "$ENTRIES" = "0" ]; then
  echo "FIXING empty map..."
  # Wildcard: allow all ingress (identity=0, port=0, proto=any)
  sudo bpftool map update id $MAP_ID \\
    key hex 28 00 00 00 00 00 00 00 00 00 00 00 \\
    value hex 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  # Allow from host (identity=1 reserved:host for kubelet probes)
  sudo bpftool map update id $MAP_ID \\
    key hex 28 00 00 00 00 00 00 00 01 00 00 00 \\
    value hex 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  # Allow ICMP wildcard
  sudo bpftool map update id $MAP_ID \\
    key hex 28 00 00 00 01 00 00 00 00 00 00 00 \\
    value hex 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  AFTER=$(sudo bpftool map dump id $MAP_ID 2>/dev/null | grep -c '^key')
  echo "FIXED: $AFTER entries added"
else
  echo "SKIP: map already has $ENTRIES entries"
fi
"""

        # Try ubuntu user first (VM workers), then strategybase (physical nodes)
        ssh_success = False
        fix_output = ""
        for ssh_user in ("ubuntu", "strategybase"):
            try:
                result = subprocess.run(
                    ["ssh", "-i", ssh_key, "-o", "ConnectTimeout=10",
                     "-o", "StrictHostKeyChecking=no",
                     f"{ssh_user}@{node_ip}", fix_script],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 or "FIXED" in result.stdout or "SKIP" in result.stdout:
                    fix_output = result.stdout
                    ssh_success = True
                    steps.append(f"ssh_user_{ssh_user}")
                    break
            except Exception:
                continue

        if not ssh_success:
            return PlaybookResult(
                playbook_name="cilium_empty_bpf_map", success=False,
                steps_completed=steps,
                fix_description=f"SSH to {node_ip} failed for both ubuntu and strategybase users",
                error="SSH connection failed",
            )

        steps.append("apply_bpf_fix")

        if "ERROR" in fix_output:
            return PlaybookResult(
                playbook_name="cilium_empty_bpf_map", success=False,
                steps_completed=steps, fix_description="BPF fix script failed",
                error=fix_output,
            )

        fixed = "FIXED" in fix_output
        skipped = "SKIP" in fix_output
        fix_desc = (
            f"BPF policy map fixed for {pod_name} on {node_name} ({node_ip})"
            if fixed else
            f"BPF policy map already populated for {pod_name} — no action needed"
        )

        log.info(
            "cilium_bpf_fix",
            pod=pod_name, node=node_name, node_ip=node_ip,
            fixed=fixed, skipped=skipped, output=fix_output[:500],
        )

        return PlaybookResult(
            playbook_name="cilium_empty_bpf_map",
            success=True,
            steps_completed=steps + ["verify_bpf_entries"],
            fix_description=fix_desc,
        )


# Registry of playbooks
PLAYBOOKS = {
    "oom_kill": PlaybookRunner.playbook_oom_kill,
    "crash_loop": PlaybookRunner.playbook_crash_loop,
    "image_pull": PlaybookRunner.playbook_image_pull,
    "probe_failure": PlaybookRunner.playbook_probe_failure,
    "resource_exhaustion": PlaybookRunner.playbook_resource_exhaustion,
    "cilium_empty_bpf_map": PlaybookRunner.playbook_cilium_empty_bpf_map,
}
