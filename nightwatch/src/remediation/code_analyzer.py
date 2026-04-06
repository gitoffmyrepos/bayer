"""
Application Code Analyzer — reads pod error logs, traces to source code,
and generates fix recommendations for Nova.

Does NOT auto-fix application code. Instead:
  1. Reads error from pod logs (kubectl logs)
  2. Parses the traceback to find file + line number
  3. Reads the actual source code from the FX repo
  4. Uses LLM to generate a fix recommendation
  5. Sends to Discord @Nova with: error, source code context, recommended fix

Author: Nova ⚡ | Nightwatch Platform
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger("nightwatch.remediation.code_analyzer")

NOVA_MENTION_ID = os.getenv("NOVA_MENTION_ID", "1319042937081593857")


@dataclass(frozen=True)
class CodeAnalysis:
    """Immutable result of application code analysis."""
    service_name: str
    pod_name: str
    error_summary: str
    traceback: str
    root_cause: str
    source_file: Optional[str] = None
    source_context: Optional[str] = None
    line_number: Optional[int] = None
    recommended_fix: Optional[str] = None
    code_diff: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical
    escalated: bool = False


class ApplicationCodeAnalyzer:
    """Analyzes application errors and generates fix recommendations for Nova."""

    # Map container paths to repo paths
    CONTAINER_TO_REPO = {
        "/app/app/": "app/",
        "/app/": "",
    }

    def __init__(self, fx_repo_path: str, llm_client, alert_manager=None):
        self.fx_repo = Path(fx_repo_path)
        self.llm = llm_client
        self.alert_manager = alert_manager
        self._analysis_history: list[CodeAnalysis] = []

    def _get_pod_logs(self, namespace: str, pod_name: str, lines: int = 100) -> str:
        """Get pod logs via kubectl."""
        try:
            result = subprocess.run(
                ["kubectl", "logs", "-n", namespace, pod_name, "--tail", str(lines)],
                capture_output=True, text=True, timeout=15,
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"Error: {e}"

    def _extract_service_name(self, pod_name: str) -> str:
        """Extract service name from pod name (e.g., forextrader-ml-trainer-xxx → ml-trainer)."""
        # Remove hash suffixes
        name = re.sub(r"-[a-f0-9]{8,10}-[a-z0-9]{5}$", "", pod_name)
        # Remove forextrader- prefix
        name = re.sub(r"^forextrader-", "", name)
        return name

    def _parse_python_traceback(self, logs: str) -> list[dict]:
        """Parse Python tracebacks for file paths and line numbers."""
        frames = []
        # Match: File "/app/app/main.py", line 123, in some_function
        pattern = r'File "([^"]+)", line (\d+), in (\w+)'
        for match in re.finditer(pattern, logs):
            filepath, lineno, funcname = match.groups()
            frames.append({
                "file": filepath,
                "line": int(lineno),
                "function": funcname,
            })
        return frames

    def _container_path_to_repo(self, container_path: str, service_name: str) -> Optional[str]:
        """Map a container file path to the FX repo path."""
        for container_prefix, repo_suffix in self.CONTAINER_TO_REPO.items():
            if container_path.startswith(container_prefix):
                relative = container_path[len(container_prefix):]
                repo_path = self.fx_repo / "microservices" / service_name / repo_suffix / relative
                if repo_path.exists():
                    return str(repo_path)

        # Try direct search
        filename = os.path.basename(container_path)
        for match in self.fx_repo.glob(f"microservices/{service_name}/**/{filename}"):
            return str(match)

        return None

    def _get_source_context(self, repo_path: str, line_number: int, context: int = 10) -> str:
        """Read source code around the error line."""
        try:
            lines = Path(repo_path).read_text().split("\n")
            start = max(0, line_number - context - 1)
            end = min(len(lines), line_number + context)

            result = []
            for i in range(start, end):
                marker = " >>> " if i == line_number - 1 else "     "
                result.append(f"{i + 1:4d}{marker}{lines[i]}")
            return "\n".join(result)
        except Exception as e:
            return f"Error reading source: {e}"

    def _extract_error_message(self, logs: str) -> str:
        """Extract the main error message from logs."""
        # Look for common Python error patterns
        patterns = [
            r"((?:Error|Exception|Traceback).*?)(?:\n(?!\s)|\Z)",
            r"(ERROR:.*?)(?:\n(?!ERROR)|\Z)",
            r"(CRITICAL:.*?)(?:\n|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, logs, re.DOTALL)
            if match:
                return match.group(1).strip()[:500]
        # Fallback: last 5 non-empty lines
        lines = [l for l in logs.strip().split("\n") if l.strip()]
        return "\n".join(lines[-5:])

    def _classify_severity(self, error: str, restart_count: int = 0) -> str:
        """Classify error severity."""
        if restart_count > 10:
            return "critical"
        critical_kw = ["OOMKilled", "FATAL", "panic", "segfault", "killed"]
        if any(kw in error for kw in critical_kw):
            return "critical"
        high_kw = ["ConnectionRefused", "TimeoutError", "DatabaseError", "AuthenticationError"]
        if any(kw in error for kw in high_kw):
            return "high"
        return "medium"

    def generate_fix_recommendation(
        self, error: str, source_context: str, service_name: str
    ) -> dict:
        """Use LLM to analyze the error and suggest a fix."""
        prompt = f"""You are a senior Python developer debugging a FastAPI microservice in a Kubernetes forex trading platform.

SERVICE: {service_name}
ERROR:
{error[:1500]}

SOURCE CODE (around the error line, marked with >>>):
{source_context[:2000]}

Analyze this error and provide:
1. ROOT CAUSE: One sentence explaining why this error occurs
2. RECOMMENDED FIX: The exact code change needed (as a diff)
3. FILE TO EDIT: The file path that needs changing
4. SEVERITY: low/medium/high/critical

Format your response as:
ROOT_CAUSE: <one sentence>
SEVERITY: <low|medium|high|critical>
FILE: <path>
FIX:
```python
# The corrected code
```
EXPLANATION: <2-3 sentences on why this fix works>"""

        try:
            response = self.llm._call(prompt)
            # Parse structured response
            root_cause = ""
            fix_code = ""
            explanation = ""

            rc_match = re.search(r"ROOT_CAUSE:\s*(.+)", response)
            if rc_match:
                root_cause = rc_match.group(1).strip()

            fix_match = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
            if fix_match:
                fix_code = fix_match.group(1).strip()

            exp_match = re.search(r"EXPLANATION:\s*(.+?)(?:\n\n|\Z)", response, re.DOTALL)
            if exp_match:
                explanation = exp_match.group(1).strip()

            return {
                "root_cause": root_cause or "Could not determine root cause",
                "recommended_fix": fix_code,
                "explanation": explanation,
            }
        except Exception as e:
            log.error(f"llm_analysis_failed: {e}")
            return {
                "root_cause": f"LLM analysis failed: {e}",
                "recommended_fix": "",
                "explanation": "",
            }

    async def analyze_pod_error(
        self, namespace: str, pod_name: str, restart_count: int = 0
    ) -> CodeAnalysis:
        """Full analysis pipeline: logs → traceback → source → LLM → recommendation."""
        service_name = self._extract_service_name(pod_name)

        # Step 1: Get logs
        logs = self._get_pod_logs(namespace, pod_name)
        error_msg = self._extract_error_message(logs)

        # Step 2: Parse traceback
        frames = self._parse_python_traceback(logs)
        severity = self._classify_severity(error_msg, restart_count)

        source_file = None
        source_context = None
        line_number = None

        if frames:
            # Use the last frame (most specific)
            last_frame = frames[-1]
            line_number = last_frame["line"]
            repo_path = self._container_path_to_repo(last_frame["file"], service_name)
            if repo_path:
                source_file = repo_path
                source_context = self._get_source_context(repo_path, line_number)

        # Step 3: Generate fix recommendation
        fix_rec = {"root_cause": "Unknown", "recommended_fix": "", "explanation": ""}
        if source_context:
            fix_rec = self.generate_fix_recommendation(error_msg, source_context, service_name)

        analysis = CodeAnalysis(
            service_name=service_name,
            pod_name=pod_name,
            error_summary=error_msg[:200],
            traceback="\n".join(logs.split("\n")[-30:]),
            root_cause=fix_rec["root_cause"],
            source_file=source_file,
            source_context=source_context,
            line_number=line_number,
            recommended_fix=fix_rec["recommended_fix"],
            code_diff=fix_rec.get("explanation", ""),
            severity=severity,
            escalated=True,
        )

        self._analysis_history.append(analysis)
        return analysis

    def format_discord_message(self, analysis: CodeAnalysis) -> dict:
        """Format analysis as a Discord embed for Nova."""
        severity_colors = {
            "critical": 0xFF0000,
            "high": 0xFF6600,
            "medium": 0xFFAA00,
            "low": 0x00AAFF,
        }

        # Truncate fields for Discord embed limits
        description = (
            f"**Service:** `{analysis.service_name}`\n"
            f"**Pod:** `{analysis.pod_name}`\n"
            f"**Severity:** {analysis.severity.upper()}\n\n"
            f"**Error:** {analysis.error_summary[:200]}\n\n"
            f"**Root Cause:** {analysis.root_cause[:300]}"
        )

        fields = []

        if analysis.source_file:
            fields.append({
                "name": "📁 Source File",
                "value": f"`{analysis.source_file}`" + (f" (line {analysis.line_number})" if analysis.line_number else ""),
                "inline": False,
            })

        if analysis.source_context:
            context_truncated = analysis.source_context[:800]
            fields.append({
                "name": "📝 Source Context",
                "value": f"```python\n{context_truncated}\n```",
                "inline": False,
            })

        if analysis.recommended_fix:
            fix_truncated = analysis.recommended_fix[:800]
            fields.append({
                "name": "🔧 Recommended Fix",
                "value": f"```python\n{fix_truncated}\n```",
                "inline": False,
            })

        if analysis.code_diff:
            fields.append({
                "name": "💡 Explanation",
                "value": analysis.code_diff[:500],
                "inline": False,
            })

        return {
            "content": f"<@{NOVA_MENTION_ID}> Application error detected — fix recommendation below",
            "embeds": [{
                "title": f"🚨 Application Error: {analysis.service_name}",
                "description": description,
                "color": severity_colors.get(analysis.severity, 0xFFAA00),
                "fields": fields,
                "footer": {"text": "Nightwatch Agent | Auto-analyzed from pod logs + source code"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    def format_escalation_message(
        self, analysis: CodeAnalysis, debug_context: str = ""
    ) -> dict:
        """Format escalation message when Nightwatch can't fix the issue."""
        description = (
            f"**Service:** `{analysis.service_name}`\n"
            f"**Severity:** {analysis.severity.upper()}\n\n"
            f"**Error:** {analysis.error_summary}\n\n"
            f"**What Nightwatch tried:**\n{debug_context[:500]}\n\n"
            f"**Root Cause Analysis:** {analysis.root_cause}\n\n"
            f"**Recommended Action:** {analysis.recommended_fix[:300] if analysis.recommended_fix else 'Manual investigation needed'}"
        )

        return {
            "content": f"<@{NOVA_MENTION_ID}> ⚠️ ESCALATION — Nightwatch needs your help. Debug context below so you don't have to redo the investigation.",
            "embeds": [{
                "title": f"⬆️ Escalated: {analysis.service_name}",
                "description": description,
                "color": 0xFF6600,
                "footer": {"text": "Nightwatch Agent | Escalated after auto-remediation failed"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    def get_history(self, limit: int = 20) -> list[dict]:
        """Return recent analysis history."""
        return [
            {
                "service": a.service_name,
                "pod": a.pod_name,
                "error": a.error_summary,
                "severity": a.severity,
                "root_cause": a.root_cause,
                "has_fix": bool(a.recommended_fix),
                "file": a.source_file,
                "line": a.line_number,
            }
            for a in self._analysis_history[-limit:]
        ]
