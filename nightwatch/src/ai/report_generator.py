"""
Nightwatch AI Report Generator
================================
Generates human-readable incident reports and health summaries using AI.

Reports are generated in Markdown format and can be:
  - Sent to Slack/Discord
  - Stored as incident artifacts
  - Emailed to stakeholders

Author: Nova ⚡ | Nightwatch Platform
"""

import json
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.core.llm_client import NightwatchLLMClient

log = structlog.get_logger("nightwatch.ai.report_generator")


class ReportGenerator:
    """
    Generates AI-powered reports from monitoring data.
    """

    def __init__(self, llm_client: NightwatchLLMClient):
        self.llm = llm_client

    def generate_incident_report(
        self,
        incident: dict,
        diagnosis: dict,
        healing_actions: Optional[list] = None,
    ) -> str:
        """
        Generate a full incident report from incident data + AI diagnosis.

        Returns Markdown-formatted report string.
        """
        incident_data = {
            **incident,
            "diagnosis": diagnosis,
            "remediation_actions": [a if isinstance(a, dict) else a.to_dict()
                                    for a in (healing_actions or [])],
        }

        report = self.llm.generate_incident_report(incident_data)
        log.info("incident_report_generated", incident_id=incident.get("id"))
        return report

    def generate_daily_summary(
        self,
        application: str,
        incidents_24h: list[dict],
        current_status: dict,
        metrics_snapshot: dict,
    ) -> str:
        """
        Generate a daily health summary report.
        """
        summary_data = {
            "application": application,
            "report_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "current_status": current_status,
            "incidents_24h": incidents_24h,
            "incident_count": len(incidents_24h),
            "metrics_snapshot": metrics_snapshot,
        }

        prompt = f"""You are Nightwatch, an AI monitoring system. Generate a concise daily health summary.

DATA:
{json.dumps(summary_data, indent=2, default=str)}

Write a daily health summary with:
1. **Overall Health** (1 sentence + emoji: ✅ 🟡 🔴)
2. **Incidents Today** ({len(incidents_24h)} total)
3. **Key Metrics** (3-5 bullet points)
4. **Recommendations** (if any)

Keep it brief. Use markdown."""

        return self.llm._call(prompt)

    def generate_postmortem(
        self,
        incident: dict,
        timeline: list[dict],
        root_cause: str,
        resolution: str,
    ) -> str:
        """
        Generate a post-mortem document for a resolved incident.
        """
        prompt = f"""You are Nightwatch, an AI monitoring system. Write a post-mortem for this resolved incident.

INCIDENT: {json.dumps(incident, indent=2, default=str)}
ROOT CAUSE: {root_cause}
RESOLUTION: {resolution}
TIMELINE: {json.dumps(timeline, indent=2, default=str)}

Write a professional post-mortem with:
1. **Incident Summary**
2. **Impact** (duration, services affected, users/processes impacted)
3. **Root Cause Analysis**
4. **Timeline of Events**
5. **Resolution**
6. **Prevention Measures** (3-5 action items to prevent recurrence)
7. **Lessons Learned**

Use markdown. Be specific and actionable."""

        return self.llm._call(prompt)
