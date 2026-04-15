"""
Nightwatch Base Adapter
========================
Abstract base class that every application adapter MUST implement.

To add a new application to Nightwatch:
  1. Create src/adapters/<your_app>/adapter.py
  2. Subclass BaseNightwatchAdapter
  3. Implement all @abstractmethod methods
  4. Register it in config/nightwatch.yaml

See docs/ADAPTER_GUIDE.md for a full walkthrough.

Author: Nova ⚡ | Nightwatch Platform
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class CheckStatus(Enum):
    """Result status for a single health check."""
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """
    Result of a single health check.

    Attributes:
        name:       Short check identifier, e.g. "step_function_running"
        status:     CheckStatus enum value
        message:    Human-readable description of the result
        component:  Which component this check covers, e.g. "AWS Step Functions"
        metadata:   Optional structured data (ARNs, counts, etc.)
        checked_at: When this check was run (defaults to now)
    """
    name: str
    status: CheckStatus
    message: str
    component: str = ""
    metadata: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_healthy(self) -> bool:
        return self.status == CheckStatus.OK

    def is_failing(self) -> bool:
        return self.status in (CheckStatus.FAIL, CheckStatus.WARN)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "component": self.component,
            "metadata": self.metadata,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class Component:
    """
    A monitorable component within the application.

    Examples:
        Component("bay-modeln-jobs-workflow", "step_function", "AWS Step Functions")
        Component("bay-modeln-raw-job-us-east-1", "glue_job", "AWS Glue")
        Component("forextrader-ml-trainer", "k8s_deployment", "Kubernetes")
    """
    name: str
    type: str          # step_function | glue_job | s3_bucket | k8s_deployment | api_endpoint | etc.
    category: str      # Human-readable category, e.g. "AWS Step Functions", "Kubernetes"
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "category": self.category,
            "description": self.description,
            "metadata": self.metadata,
            # Flatten status/last_seen from metadata to top level for frontend compatibility
            "status": self.metadata.get("status", "unknown"),
            "last_seen": self.metadata.get("last_seen"),
        }


class BaseNightwatchAdapter(ABC):
    """
    Abstract base for all Nightwatch application adapters.

    Every adapter implements this interface. The core engine only talks to this
    interface — it has zero knowledge of AWS, Kubernetes, OANDA, or anything
    application-specific.

    Minimal implementation example:
    --------------------------------
        class MyAppAdapter(BaseNightwatchAdapter):
            @property
            def application_name(self) -> str:
                return "My Application"

            def collect_metrics(self) -> dict:
                return {"requests_per_second": 42, "error_rate": 0.01}

            def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
                return ["ERROR 2026-01-01 Something failed"]

            def run_health_checks(self) -> list[HealthCheck]:
                return [HealthCheck("api_up", CheckStatus.OK, "API is healthy", "API")]

            def get_component_inventory(self) -> list[Component]:
                return [Component("api", "api_endpoint", "HTTP API")]

    Full walkthrough: docs/ADAPTER_GUIDE.md
    """

    def __init__(self, config: dict):
        """
        Args:
            config: Adapter-specific config dict (loaded from config_file in nightwatch.yaml)
        """
        self.config = config
        self._initialized = False

    # ─── Required Methods ─────────────────────────────────────────────────────

    @property
    @abstractmethod
    def application_name(self) -> str:
        """
        Human-readable application name. Used in alerts and reports.
        Examples: "Bayer ModelN", "ForexTrader", "My SaaS App"
        """

    @abstractmethod
    def collect_metrics(self) -> dict:
        """
        Collect current health metrics from the application.

        Returns a flat or nested dict of current metrics. Used by the AI
        diagnosis engine to understand application state.

        Example return:
            {
                "step_functions": {"running": 2, "failed": 0},
                "glue_jobs": {"running": 1, "succeeded": 3, "failed": 0},
                "s3": {"landing_bucket_objects": 142, "last_file_age_seconds": 3600},
            }
        """

    @abstractmethod
    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """
        Collect recent error/warning logs from the application.

        Only return logs relevant to diagnosing issues (errors, warnings).
        Limit to 50-100 lines — these are fed to the LLM.

        Args:
            lookback_minutes: How far back to look for logs

        Returns:
            List of log line strings, most recent last.
        """

    @abstractmethod
    def run_health_checks(self) -> list[HealthCheck]:
        """
        Run all health checks for this application.

        Each check should be independent and fast (< 5 seconds each).
        Return one HealthCheck per meaningful thing to monitor.

        Examples:
            - Step Function has had a successful execution in the last 2 hours
            - S3 landing bucket received files in the last hour
            - Kubernetes deployment has at least 1 ready pod
            - API health endpoint returns 200
        """

    @abstractmethod
    def get_component_inventory(self) -> list[Component]:
        """
        List all monitorable components in this application.

        Used by the API to show what Nightwatch is watching.
        Should be static or cached — called frequently.
        """

    # ─── Optional Methods (override for richer behavior) ──────────────────────

    def describe_architecture(self) -> str:
        """
        Return a description of the application architecture for LLM context.

        The LLM uses this to understand the application and provide better
        root cause analysis. Override with a detailed description of your app.

        Example:
            "Bayer ModelN.io AWS data pipeline: Step Functions orchestrates
            Glue ETL jobs that process pharmaceutical pricing data from S3
            landing zone through to DynamoDB and SFTP delivery to McKesson/AXWAY..."
        """
        components = self.get_component_inventory()
        component_list = ", ".join(f"{c.name} ({c.type})" for c in components[:10])
        return f"{self.application_name} monitoring adapter. Components: {component_list}"

    def initialize(self) -> None:
        """
        Optional: perform any setup (validate credentials, test connectivity).
        Called once before the first check cycle.
        Raise an exception if the adapter cannot connect.
        """
        pass

    def cleanup(self) -> None:
        """Optional: clean up resources (close connections, etc.)."""
        pass

    def get_runbook_url(self, check_name: str) -> Optional[str]:
        """
        Optional: return a runbook URL for a specific failing check.
        Used to include runbook links in alerts.
        """
        return None

    # ─── Utility Helpers ──────────────────────────────────────────────────────

    def _ok(self, name: str, message: str, component: str = "", **metadata) -> HealthCheck:
        """Convenience: create an OK health check."""
        return HealthCheck(name=name, status=CheckStatus.OK, message=message,
                          component=component, metadata=metadata)

    def _warn(self, name: str, message: str, component: str = "", **metadata) -> HealthCheck:
        """Convenience: create a WARN health check."""
        return HealthCheck(name=name, status=CheckStatus.WARN, message=message,
                          component=component, metadata=metadata)

    def _fail(self, name: str, message: str, component: str = "", **metadata) -> HealthCheck:
        """Convenience: create a FAIL health check."""
        return HealthCheck(name=name, status=CheckStatus.FAIL, message=message,
                          component=component, metadata=metadata)

    def _unknown(self, name: str, message: str, component: str = "", **metadata) -> HealthCheck:
        """Convenience: create an UNKNOWN health check."""
        return HealthCheck(name=name, status=CheckStatus.UNKNOWN, message=message,
                          component=component, metadata=metadata)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} application='{self.application_name}'>"
