"""
Nightwatch AI Analyzer
=======================
AI-powered root cause analysis and anomaly detection.

Works on top of the LLM client to provide structured analysis
with severity scoring and confidence levels.

Author: Nova ⚡ | Nightwatch Platform
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.core.llm_client import NightwatchLLMClient

log = structlog.get_logger("nightwatch.ai.analyzer")


class AIAnalyzer:
    """
    Performs AI-powered root cause analysis on monitoring data.

    Used by the engine when health checks fail. The analyzer:
      1. Synthesizes metrics, logs, and failing checks
      2. Asks the LLM to identify the root cause
      3. Returns structured analysis with severity and recommendations
    """

    def __init__(self, llm_client: NightwatchLLMClient, adapter_name: str = ""):
        self.llm = llm_client
        self.adapter_name = adapter_name
        self._analysis_count = 0

    def analyze_failure(
        self,
        failing_checks: list,
        metrics: dict,
        logs: list[str],
        architecture: str = "",
    ) -> dict:
        """
        Perform root cause analysis on a set of failing checks.

        Returns:
            {
                "root_cause": str,
                "severity": "critical"|"high"|"medium"|"low",
                "recommendation": str,
                "auto_fix_possible": bool,
                "auto_fix_command": str | None,
                "confidence": float,
                "affected_components": list[str],
                "estimated_impact": str,
            }
        """
        self._analysis_count += 1

        error_summary = "\n".join(
            f"- {c.name}: [{c.status.value.upper()}] {c.message}"
            for c in failing_checks
        )
        affected_components = list({c.component for c in failing_checks if c.component})

        diagnosis = self.llm.diagnose(
            metrics=metrics,
            logs=logs,
            error=error_summary,
            architecture=architecture,
        )

        # Enrich with affected components
        diagnosis["affected_components"] = affected_components
        diagnosis["analysis_id"] = f"analysis-{self._analysis_count}"
        diagnosis["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        log.info(
            "analysis_complete",
            severity=diagnosis.get("severity"),
            confidence=diagnosis.get("confidence"),
            components=affected_components,
        )

        return diagnosis

    def analyze_trend(
        self,
        metric_history: list[dict],
        metric_name: str,
        context: str = "",
    ) -> dict:
        """
        Analyze a metric time series for trends and anomalies.

        Args:
            metric_history: List of {"timestamp": str, "value": float}
            metric_name: Name of the metric
            context: Application context

        Returns:
            {"trend": str, "anomaly_detected": bool, "analysis": str}
        """
        history_text = json.dumps(metric_history[-20:], default=str, indent=2)

        analysis_text = self.llm.analyze(
            context=f"{context}\n\nMetric history for '{metric_name}':\n{history_text}",
            question=f"Is there a concerning trend or anomaly in this '{metric_name}' metric data? "
                     f"What pattern do you see and should we be concerned?",
        )

        return {
            "metric": metric_name,
            "analysis": analysis_text,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    def correlate_incidents(
        self,
        current_incident: dict,
        past_incidents: list[dict],
    ) -> dict:
        """
        Check if the current incident matches patterns from past incidents.
        Useful for identifying recurring issues.
        """
        if not past_incidents:
            return {"similar_found": False}

        past_text = json.dumps(past_incidents[-5:], default=str, indent=2)
        current_text = json.dumps(current_incident, default=str, indent=2)

        analysis = self.llm.analyze(
            context=f"Past incidents:\n{past_text}",
            question=f"Does this new incident match any past incidents? New incident:\n{current_text}\n\n"
                     f"If yes, what is the pattern and is there a known fix?",
        )

        return {
            "analysis": analysis,
            "similar_found": "yes" in analysis.lower() or "similar" in analysis.lower(),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
