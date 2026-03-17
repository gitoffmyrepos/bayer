"""
Nightwatch Alert Manager
=========================
Universal alerting layer — sends alerts to any configured channel.

Supported channels:
  - Slack webhook
  - Discord webhook
  - PagerDuty Events API v2
  - Email (SMTP)

All channels are optional. Configure what you need in nightwatch.yaml [alerting].

Author: Nova ⚡ | Nightwatch Platform
"""

import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
import structlog

log = structlog.get_logger("nightwatch.alerting")


SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}

SEVERITY_COLOR = {
    "critical": 0xFF0000,   # Red
    "high": 0xFF8C00,       # Orange
    "medium": 0xFFD700,     # Yellow
    "low": 0x1E90FF,        # Blue
    "info": 0x808080,       # Gray
}

# Slack attachment colors
SLACK_COLOR = {
    "critical": "danger",
    "high": "warning",
    "medium": "warning",
    "low": "good",
    "info": "#439FE0",
}


class AlertManager:
    """
    Routes alerts to all configured notification channels.

    Usage:
        am = AlertManager(config.alerting)
        await am.send_alert(
            title="Step Function FAILED",
            body="bay-modeln-jobs-workflow failed after 3 retries",
            severity="critical",
            application="Bayer ModelN",
            metadata={"execution_arn": "...", "error": "States.TaskFailed"}
        )
    """

    def __init__(self, alerting_config: dict):
        self.config = alerting_config
        self.slack_config = alerting_config.get("slack", {})
        self.discord_config = alerting_config.get("discord", {})
        self.pagerduty_config = alerting_config.get("pagerduty", {})
        self.email_config = alerting_config.get("email", {})

        # Track recently sent alerts to avoid spam (alert deduplication)
        self._recent_alerts: dict[str, datetime] = {}
        self._dedup_window_seconds = alerting_config.get("dedup_window_seconds", 300)

    async def send_alert(
        self,
        title: str,
        body: str,
        severity: str = "medium",
        application: str = "Unknown",
        metadata: Optional[dict] = None,
        incident_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> dict:
        """
        Send alert to all configured channels.

        Returns:
            {"slack": bool, "discord": bool, "pagerduty": bool, "email": bool}
        """
        severity = severity.lower()
        emoji = SEVERITY_EMOJI.get(severity, "⚠️")
        metadata = metadata or {}

        # Deduplication
        if dedup_key:
            now = datetime.now(timezone.utc)
            last_sent = self._recent_alerts.get(dedup_key)
            if last_sent:
                elapsed = (now - last_sent).total_seconds()
                if elapsed < self._dedup_window_seconds:
                    log.debug("alert_deduplicated", key=dedup_key, elapsed_seconds=elapsed)
                    return {"deduplicated": True}
            self._recent_alerts[dedup_key] = now

        log.info("sending_alert", title=title, severity=severity, application=application)

        results = {}

        # Send to all channels concurrently
        import asyncio
        tasks = []

        if self.slack_config.get("webhook_url"):
            tasks.append(("slack", self._send_slack(title, body, severity, application, metadata, emoji)))

        if self.discord_config.get("webhook_url"):
            tasks.append(("discord", self._send_discord(title, body, severity, application, metadata, emoji)))

        if self.pagerduty_config.get("routing_key"):
            tasks.append(("pagerduty", self._send_pagerduty(title, body, severity, application, metadata, incident_id)))

        if self.email_config.get("smtp_host") and self.email_config.get("to"):
            tasks.append(("email", self._send_email(title, body, severity, application, metadata, emoji)))

        if not tasks:
            log.warning("no_alert_channels_configured")
            return {"warning": "no channels configured"}

        gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        for (channel, _), result in zip(tasks, gathered):
            if isinstance(result, Exception):
                log.error("alert_channel_failed", channel=channel, error=str(result))
                results[channel] = False
            else:
                results[channel] = result

        return results

    # ─── Slack ────────────────────────────────────────────────────────────────

    async def _send_slack(
        self,
        title: str,
        body: str,
        severity: str,
        application: str,
        metadata: dict,
        emoji: str,
    ) -> bool:
        webhook_url = self.slack_config["webhook_url"]
        channel = self.slack_config.get("channel", "#nightwatch-incidents")

        fields = [
            {"title": "Application", "value": application, "short": True},
            {"title": "Severity", "value": f"{emoji} {severity.upper()}", "short": True},
        ]

        # Add metadata as fields (first 5 items)
        for k, v in list(metadata.items())[:5]:
            fields.append({"title": k.replace("_", " ").title(), "value": str(v)[:200], "short": False})

        payload = {
            "channel": channel,
            "username": "Nightwatch ⚡",
            "icon_emoji": ":eye:",
            "attachments": [{
                "color": SLACK_COLOR.get(severity, "warning"),
                "title": f"{emoji} {title}",
                "text": body,
                "fields": fields,
                "footer": "Nightwatch AI Monitor",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }],
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        log.info("slack_alert_sent", title=title)
        return True

    # ─── Discord ─────────────────────────────────────────────────────────────

    async def _send_discord(
        self,
        title: str,
        body: str,
        severity: str,
        application: str,
        metadata: dict,
        emoji: str,
    ) -> bool:
        webhook_url = self.discord_config["webhook_url"]
        color = SEVERITY_COLOR.get(severity, 0xFFD700)

        fields = [
            {"name": "Application", "value": application, "inline": True},
            {"name": "Severity", "value": f"{emoji} {severity.upper()}", "inline": True},
        ]

        for k, v in list(metadata.items())[:5]:
            fields.append({"name": k.replace("_", " ").title(), "value": f"```{str(v)[:100]}```", "inline": False})

        payload = {
            "username": "Nightwatch ⚡",
            "avatar_url": "https://em-content.zobj.net/source/openmoji/338/eye_1f441.png",
            "embeds": [{
                "title": f"{emoji} {title}",
                "description": body[:2000],
                "color": color,
                "fields": fields,
                "footer": {"text": "Nightwatch AI Monitor"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        log.info("discord_alert_sent", title=title)
        return True

    # ─── PagerDuty ───────────────────────────────────────────────────────────

    async def _send_pagerduty(
        self,
        title: str,
        body: str,
        severity: str,
        application: str,
        metadata: dict,
        incident_id: Optional[str],
    ) -> bool:
        routing_key = self.pagerduty_config["routing_key"]

        # PagerDuty severity mapping
        pd_severity = {
            "critical": "critical",
            "high": "error",
            "medium": "warning",
            "low": "info",
            "info": "info",
        }.get(severity, "warning")

        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": incident_id or f"nightwatch-{application}-{title}",
            "payload": {
                "summary": title,
                "source": f"Nightwatch/{application}",
                "severity": pd_severity,
                "custom_details": {
                    "body": body,
                    **metadata,
                },
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

        log.info("pagerduty_alert_sent", title=title)
        return True

    # ─── Email ───────────────────────────────────────────────────────────────

    async def _send_email(
        self,
        title: str,
        body: str,
        severity: str,
        application: str,
        metadata: dict,
        emoji: str,
    ) -> bool:
        import asyncio
        # Run synchronous SMTP in thread pool
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._send_email_sync(title, body, severity, application, metadata, emoji)
        )
        return True

    def _send_email_sync(
        self,
        title: str,
        body: str,
        severity: str,
        application: str,
        metadata: dict,
        emoji: str,
    ) -> None:
        cfg = self.email_config
        smtp_host = cfg["smtp_host"]
        smtp_port = int(cfg.get("smtp_port", 587))
        from_addr = cfg.get("from", "nightwatch@monitoring.local")
        to_addrs = cfg["to"] if isinstance(cfg["to"], list) else [cfg["to"]]
        username = cfg.get("username", "")
        password = cfg.get("password", "")

        subject = f"[Nightwatch] {emoji} [{severity.upper()}] {title}"

        # HTML body
        metadata_rows = "".join(
            f"<tr><td style='font-weight:bold;padding:4px 8px;'>{k.replace('_',' ').title()}</td>"
            f"<td style='padding:4px 8px;'>{v}</td></tr>"
            for k, v in metadata.items()
        )
        html_body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:700px;">
  <h2 style="color:#c0392b;">{emoji} {title}</h2>
  <p><strong>Application:</strong> {application}<br>
  <strong>Severity:</strong> {severity.upper()}<br>
  <strong>Time:</strong> {datetime.now(timezone.utc).isoformat()}</p>
  <h3>Details</h3>
  <p>{body}</p>
  {"<h3>Context</h3><table border='1' cellpadding='4' style='border-collapse:collapse;'>" + metadata_rows + "</table>" if metadata_rows else ""}
  <hr><p style="color:#888;font-size:12px;">Nightwatch AI Monitoring Platform</p>
</body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())

        log.info("email_alert_sent", to=to_addrs, title=title)

    # ─── Resolution ───────────────────────────────────────────────────────────

    async def resolve_pagerduty(self, incident_id: str) -> bool:
        """Resolve a PagerDuty incident (marks it as resolved)."""
        if not self.pagerduty_config.get("routing_key"):
            return False

        payload = {
            "routing_key": self.pagerduty_config["routing_key"],
            "event_action": "resolve",
            "dedup_key": incident_id,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            response.raise_for_status()

        log.info("pagerduty_resolved", incident_id=incident_id)
        return True
