"""
ForexTrader Platform Adapter
==============================
Monitors the ForexTrader autonomous FX trading platform on Kubernetes.

Monitors:
  - Kubernetes pods in prod-forex namespace
  - OANDA account health (balance, margin, open trades)
  - ForexTrader API gateway health endpoint
  - ML training pipeline status
  - Jenkins CI/CD build status

Config (adapters/forextrader/config.yaml):
  k8s_namespace, api_gateway_url, oanda_account_id, jenkins_url

Auth:
  - Kubernetes: kubeconfig or in-cluster service account
  - OANDA: OANDA_API_KEY env var
  - Jenkins: JENKINS_API_TOKEN env var

Author: Nova ⚡ | Nightwatch Platform
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.adapters.base_adapter import BaseNightwatchAdapter, HealthCheck, CheckStatus, Component
from src.adapters.forextrader.collectors import (
    collect_k8s_pod_status,
    collect_k8s_deployment_status,
    collect_k8s_all_deployments,
    collect_k8s_nodes,
    collect_k8s_statefulsets,
    collect_k8s_namespace_summary,
    collect_k8s_cnpg_clusters,
    collect_oanda_account_health,
    collect_api_health,
    collect_jenkins_build_status,
)

log = logging.getLogger("nightwatch.adapter.forextrader")


# ─── Category Inference ───────────────────────────────────────────────────────

_TRADING_KW = (
    "autonomous-trading", "trade-executor", "signal-generator", "risk-manager",
    "order-flow", "position-sizing", "circuit-breaker", "active-trade-guardian",
    "fix-gateway", "ibkr", "weekend-gap", "outcome-resolver", "paper-trading",
    "shadow-mode", "copy-trading", "market-impact", "stacking-layer",
    "trading-goals", "fin-anchor", "portfolio-optimizer",
)
_ML_KW = (
    "ml-trainer", "ml-predictor", "rl-agents", "foundation-models",
    "ensemble", "neural-arch", "tensorrt", "model-management", "model-validation",
    "weight-updater", "prediction-decay", "prediction-validator",
    "prediction-forensics", "prediction-ledger", "confidence-calibrator",
    "conformal-predictor", "adaptive-regime", "correlation-regime",
    "causal-inference", "genetic-indicators", "multi-agent",
    "orderbook-simulator", "ab-testing", "accuracy-tracker", "backtesting",
    "xai-service",
)
_ETL_KW = (
    "etl-pipeline", "data-collector", "feature-engineering", "feature-store",
    "data-quality", "alternative-data", "news-sentiment", "news-platform",
    "news-reactive", "news-orchestrator", "market-intelligence", "geopolitical",
    "event-logger", "vpin-calculator", "ict-smart-money", "feedback-loop",
    "h2o-automl",
)
_ANALYTICS_KW = (
    "strategy-engine", "risk-analytics", "performance-analytics",
    "performance-attribution", "monitoring-analytics", "report-generator",
    "llm-orchestrator", "ensemble-monitor",
)
_DATA_KW = (
    "mongodb", "redis", "redpanda", "timescaledb", "qdrant", "cache-service",
)
_PLATFORM_KW = (
    "notification-service", "user-alerts", "user-auth", "audit-logger",
    "audit-service", "compliance-engine", "multi-tenancy", "infrastructure-services",
    "trade-reconciliation",
)
_FRONTEND_KW = (
    "forextrader-frontend", "docs-updater", "swagger", "streamlit",
    "adminer", "mongo-express", "redisinsight", "pgadmin", "open-webui",
    "automation-dashboard",
)
_OPS_KW = (
    "ai-monitor-agent", "ai-ops-agent", "jenkins-monitor-agent", "k8sgpt",
    "mlflow", "ollama", "automation-controller", "alertmanager-discord",
    "chaos-engineering", "federated-learning", "adversarial-testing",
    "api-gateway",
)


def _infer_deployment_category(name: str) -> str:
    """Map a deployment name to its UI category."""
    n = name.lower()
    if any(k in n for k in _TRADING_KW):   return "Trading Execution"
    if any(k in n for k in _ML_KW):        return "ML / AI"
    if any(k in n for k in _ETL_KW):       return "ETL Pipeline"
    if any(k in n for k in _ANALYTICS_KW): return "Analytics"
    if any(k in n for k in _DATA_KW):      return "Data Layer"
    if any(k in n for k in _PLATFORM_KW):  return "Platform Services"
    if any(k in n for k in _FRONTEND_KW):  return "Frontend & Tools"
    if any(k in n for k in _OPS_KW):       return "Ops & Infrastructure"
    return "Kubernetes"


class ForexTraderAdapter(BaseNightwatchAdapter):
    """
    Nightwatch adapter for the ForexTrader FX trading platform.

    ForexTrader is an autonomous ML-based forex trading system running on
    RKE2 Kubernetes with OANDA as the broker API.
    """

    @property
    def application_name(self) -> str:
        return "ForexTrader"

    def __init__(self, config: dict):
        super().__init__(config)

        # Kubernetes config
        self.k8s_namespace = config.get("k8s_namespace", "prod-forex")
        self.kubeconfig_path = config.get("kubeconfig_path")
        self.critical_deployments = config.get("critical_deployments", [])

        # StatefulSets config (databases, brokers)
        sts_config = config.get("statefulsets", {})
        self.statefulset_namespace = sts_config.get("namespace", self.k8s_namespace)
        self.statefulset_names = sts_config.get("names", [])

        # CNPG clusters (CloudNativePG — TimescaleDB etc.)
        cnpg_config = config.get("cnpg_clusters", {})
        self.cnpg_namespace = cnpg_config.get("namespace", self.k8s_namespace)
        self.cnpg_names = cnpg_config.get("names", [])

        # Namespaces to summarize
        self.monitor_namespaces = config.get("monitor_namespaces", [self.k8s_namespace])

        # OANDA config
        self.oanda_api_url = config.get("oanda_api_url", "https://api-fxtrade.oanda.com")
        self.oanda_account_id = config.get("oanda_account_id", "")
        self.oanda_api_key = config.get("oanda_api_key", "")

        # API health endpoints
        self.health_endpoints = config.get("health_endpoints", [])

        # Jenkins config
        self.jenkins_url = config.get("jenkins_url", "")
        self.jenkins_username = config.get("jenkins_username", "")
        self.jenkins_api_token = config.get("jenkins_api_token", "")
        self.jenkins_jobs = config.get("jenkins_jobs", [])

        # Thresholds
        thresholds = config.get("thresholds", {})
        self.min_pods_running = thresholds.get("min_pods_running", 20)
        self.max_pod_restarts = thresholds.get("max_pod_restarts", 5)
        self.min_balance = thresholds.get("min_balance", 90000)
        self.max_drawdown_pct = thresholds.get("max_drawdown_pct", 10.0)
        self.max_api_response_ms = thresholds.get("max_api_response_ms", 3000)
        self.min_nodes_ready = thresholds.get("min_nodes_ready", 3)

    # ─── Data Collection ──────────────────────────────────────────────────────

    def collect_metrics(self) -> dict:
        metrics = {}

        # All pods in namespace (overview)
        metrics["k8s"] = collect_k8s_pod_status(
            k8s_namespace=self.k8s_namespace,
            kubeconfig_path=self.kubeconfig_path,
        )

        # ALL deployments — full per-microservice component map
        metrics["all_deployments"] = collect_k8s_all_deployments(
            k8s_namespace=self.k8s_namespace,
            kubeconfig_path=self.kubeconfig_path,
        )

        # Cluster nodes
        metrics["nodes"] = collect_k8s_nodes(
            kubeconfig_path=self.kubeconfig_path,
        )

        # StatefulSets (databases, message brokers)
        if self.statefulset_names:
            metrics["statefulsets"] = collect_k8s_statefulsets(
                k8s_namespace=self.statefulset_namespace,
                names=self.statefulset_names,
                kubeconfig_path=self.kubeconfig_path,
            )

        # Multi-namespace summary
        if self.monitor_namespaces:
            metrics["namespace_summary"] = collect_k8s_namespace_summary(
                namespaces=self.monitor_namespaces,
                kubeconfig_path=self.kubeconfig_path,
            )

        if self.oanda_account_id and self.oanda_api_key:
            metrics["oanda"] = collect_oanda_account_health(
                oanda_api_url=self.oanda_api_url,
                account_id=self.oanda_account_id,
                api_key=self.oanda_api_key,
            )

        if self.health_endpoints:
            metrics["api_health"] = collect_api_health(self.health_endpoints)

        if self.jenkins_url and self.jenkins_jobs:
            metrics["jenkins"] = collect_jenkins_build_status(
                jenkins_url=self.jenkins_url,
                username=self.jenkins_username,
                api_token=self.jenkins_api_token,
                jobs=self.jenkins_jobs,
            )

        # CNPG clusters (TimescaleDB etc.)
        if self.cnpg_names:
            metrics["cnpg"] = collect_k8s_cnpg_clusters(
                namespace=self.cnpg_namespace,
                names=self.cnpg_names,
                kubeconfig_path=self.kubeconfig_path,
            )

        return metrics

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """Collect recent error logs from failing pods via kubectl."""
        try:
            import subprocess

            logs = []
            pod_data = collect_k8s_pod_status(self.k8s_namespace, self.kubeconfig_path)

            # Get logs from pods with high restart counts
            for pod in pod_data.get("pods", []):
                if pod.get("restarts", 0) >= 3 or pod.get("phase") in ("Failed", "Error"):
                    pod_name = pod["name"]
                    try:
                        result = subprocess.run(
                            ["kubectl", "logs", "-n", self.k8s_namespace, pod_name,
                             "--tail=20", "--previous"],
                            capture_output=True, text=True, timeout=10,
                        )
                        if result.stdout:
                            for line in result.stdout.strip().split("\n")[-10:]:
                                if any(w in line.lower() for w in ("error", "fail", "exception", "traceback")):
                                    logs.append(f"[{pod_name}] {line}")
                    except Exception:
                        pass

            return logs

        except Exception as e:
            log.warning("log_collection_failed | error=str(e)")
            return []

    # ─── Health Checks ────────────────────────────────────────────────────────

    def run_health_checks(self) -> list[HealthCheck]:
        checks = []
        metrics = self.collect_metrics()

        # Kubernetes overall pod health
        if k8s := metrics.get("k8s"):
            checks.extend(self._check_k8s(k8s))

        # Cluster node health
        if nodes := metrics.get("nodes"):
            checks.extend(self._check_nodes(nodes))

        # Per-microservice deployment health (full component map)
        if all_deploys := metrics.get("all_deployments"):
            checks.extend(self._check_all_deployments(all_deploys))

        # StatefulSets (databases, message brokers)
        if statefulsets := metrics.get("statefulsets"):
            checks.extend(self._check_statefulsets(statefulsets))

        # OANDA account checks
        if oanda := metrics.get("oanda"):
            checks.extend(self._check_oanda(oanda))

        # API health checks
        if api_health := metrics.get("api_health"):
            checks.extend(self._check_api_health(api_health))

        # Jenkins build checks
        if jenkins := metrics.get("jenkins"):
            checks.extend(self._check_jenkins(jenkins))

        # CNPG clusters (TimescaleDB)
        if cnpg := metrics.get("cnpg"):
            checks.extend(self._check_cnpg(cnpg))

        return checks

    def _check_k8s(self, k8s_data: dict) -> list[HealthCheck]:
        if "error" in k8s_data:
            return [self._fail(
                "k8s_accessible",
                f"Cannot access Kubernetes: {k8s_data['error']}",
                component="Kubernetes",
            )]

        checks = []
        total = k8s_data.get("total", 0)
        running = k8s_data.get("running", 0)
        failed = k8s_data.get("failed", 0)
        pending = k8s_data.get("pending", 0)

        # Overall pod health
        if running < self.min_pods_running:
            checks.append(self._fail(
                "k8s_pods_running",
                f"Only {running}/{total} pods running (minimum: {self.min_pods_running})",
                component="Kubernetes",
                running=running, total=total, failed=failed, pending=pending,
            ))
        else:
            checks.append(self._ok(
                "k8s_pods_running",
                f"{running}/{total} pods running in {k8s_data.get('namespace')}",
                component="Kubernetes",
                running=running, total=total,
            ))

        if failed > 0:
            failed_pods = [p["name"] for p in k8s_data.get("pods", []) if p.get("phase") == "Failed"]
            checks.append(self._warn(
                "k8s_pods_failed",
                f"{failed} pod(s) in Failed state: {', '.join(failed_pods[:3])}",
                component="Kubernetes",
                failed_pods=failed_pods,
            ))

        # High restart count pods — only flag if NOT currently healthy
        # (Running pods with historical restarts from node reboots are normal)
        crashlooping = [
            p for p in k8s_data.get("pods", [])
            if p.get("restarts", 0) >= self.max_pod_restarts
            and (p.get("phase") != "Running" or not p.get("ready", True))
        ]
        if crashlooping:
            checks.append(self._warn(
                "k8s_crashlooping",
                f"{len(crashlooping)} pod(s) crashlooping: {', '.join(p['name'] for p in crashlooping[:3])}",
                component="Kubernetes",
                pods=[{"name": p["name"], "restarts": p["restarts"], "phase": p.get("phase")} for p in crashlooping],
            ))

        return checks

    def _check_nodes(self, node_data: dict) -> list[HealthCheck]:
        """Check cluster node health — readiness and resource pressure."""
        if "error" in node_data:
            return [self._warn(
                "k8s_nodes_accessible",
                f"Cannot read node status: {node_data['error']}",
                component="Cluster",
            )]

        checks = []
        total = node_data.get("total", 0)
        ready = node_data.get("ready", 0)
        not_ready = node_data.get("not_ready", 0)

        if not_ready > 0:
            not_ready_names = [n["name"] for n in node_data.get("nodes", []) if not n.get("ready")]
            checks.append(self._fail(
                "k8s_nodes_ready",
                f"{not_ready}/{total} node(s) NOT Ready: {', '.join(not_ready_names)}",
                component="Cluster",
                not_ready=not_ready, total=total,
            ))
        else:
            checks.append(self._ok(
                "k8s_nodes_ready",
                f"All {total} cluster nodes Ready",
                component="Cluster",
                ready=ready, total=total,
            ))

        # Resource pressure
        pressured = [
            n for n in node_data.get("nodes", [])
            if n.get("memory_pressure") or n.get("disk_pressure") or n.get("pid_pressure")
        ]
        if pressured:
            cond_list = []
            for n in pressured:
                conds = []
                if n.get("memory_pressure"): conds.append("MemPressure")
                if n.get("disk_pressure"): conds.append("DiskPressure")
                if n.get("pid_pressure"): conds.append("PIDPressure")
                cond_list.append(f"{n['name']}({','.join(conds)})")
            checks.append(self._warn(
                "k8s_nodes_pressure",
                f"Node pressure detected: {'; '.join(cond_list)}",
                component="Cluster",
            ))

        return checks

    def _check_all_deployments(self, deploy_data: dict) -> list[HealthCheck]:
        """Check ALL deployments — one HealthCheck per microservice for the UI component map."""
        if "error" in deploy_data:
            return [self._warn(
                "all_deployments_accessible",
                f"Cannot list deployments: {deploy_data['error']}",
                component="Kubernetes",
            )]

        checks = []
        for name, data in deploy_data.items():
            if "error" in data:
                continue
            desired = data.get("desired", 0)
            ready = data.get("ready", 0)
            status = data.get("status", "unknown")

            if status == "scaled_down":
                checks.append(self._ok(
                    f"deploy_{name.replace('-', '_')}",
                    f"{name}: scaled to 0 (intentional)",
                    component=name,
                ))
            elif status == "unhealthy" and desired > 0:
                checks.append(self._fail(
                    f"deploy_{name.replace('-', '_')}",
                    f"{name}: 0/{desired} replicas ready — DOWN",
                    component=name,
                    ready=ready, desired=desired,
                ))
            elif status == "degraded":
                checks.append(self._warn(
                    f"deploy_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} replicas ready",
                    component=name,
                    ready=ready, desired=desired,
                ))
            else:
                checks.append(self._ok(
                    f"deploy_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} replicas ready",
                    component=name,
                    ready=ready, desired=desired,
                ))

        return checks

    def _check_statefulsets(self, sts_data: dict) -> list[HealthCheck]:
        """Check StatefulSets — TimescaleDB, Redis, Redpanda, MongoDB, Qdrant."""
        if "error" in sts_data:
            return [self._warn(
                "statefulsets_accessible",
                f"Cannot read StatefulSets: {sts_data['error']}",
                component="Data Layer",
            )]

        checks = []
        for name, data in sts_data.items():
            if "error" in data:
                checks.append(self._warn(
                    f"sts_{name.replace('-', '_')}",
                    f"{name} not found: {data['error']}",
                    component="Data Layer",
                ))
                continue

            desired = data.get("desired", 1)
            ready = data.get("ready", 0)
            status = data.get("status", "unknown")

            if status == "unhealthy":
                checks.append(self._fail(
                    f"sts_{name.replace('-', '_')}",
                    f"{name}: 0/{desired} pods ready — DOWN",
                    component="Data Layer",
                    ready=ready, desired=desired,
                ))
            elif status == "degraded":
                checks.append(self._warn(
                    f"sts_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} pods ready",
                    component="Data Layer",
                    ready=ready, desired=desired,
                ))
            else:
                checks.append(self._ok(
                    f"sts_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} pods ready",
                    component="Data Layer",
                    ready=ready, desired=desired,
                ))

        return checks

    def _check_deployments(self, deploy_data: dict) -> list[HealthCheck]:
        checks = []
        for deploy_name, data in deploy_data.items():
            if "error" in data:
                checks.append(self._warn(
                    f"deploy_{deploy_name.replace('-','_')}_found",
                    f"Cannot find deployment {deploy_name}: {data['error']}",
                    component="Kubernetes",
                ))
                continue

            desired = data.get("desired", 0)
            ready = data.get("ready", 0)

            if ready == 0 and desired > 0:
                checks.append(self._fail(
                    f"deploy_{deploy_name.replace('-','_')}_ready",
                    f"Deployment {deploy_name}: 0/{desired} replicas ready",
                    component="Kubernetes",
                    deployment=deploy_name, ready=ready, desired=desired,
                ))
            elif ready < desired:
                checks.append(self._warn(
                    f"deploy_{deploy_name.replace('-','_')}_ready",
                    f"Deployment {deploy_name}: {ready}/{desired} replicas ready",
                    component="Kubernetes",
                    deployment=deploy_name, ready=ready, desired=desired,
                ))
            else:
                checks.append(self._ok(
                    f"deploy_{deploy_name.replace('-','_')}_ready",
                    f"Deployment {deploy_name}: {ready}/{desired} replicas ready",
                    component="Kubernetes",
                    deployment=deploy_name, ready=ready, desired=desired,
                ))

        return checks

    def _check_oanda(self, oanda_data: dict) -> list[HealthCheck]:
        if "error" in oanda_data:
            return [self._warn(
                "oanda_accessible",
                f"Cannot access OANDA: {oanda_data['error']}",
                component="OANDA",
            )]

        checks = []
        balance = oanda_data.get("balance", 0)
        margin_available = oanda_data.get("margin_available", 0)
        unrealized_pl = oanda_data.get("unrealized_pl", 0)

        # Balance check
        if balance < self.min_balance:
            checks.append(self._warn(
                "oanda_balance",
                f"OANDA balance ${balance:,.2f} below minimum threshold ${self.min_balance:,.0f}",
                component="OANDA",
                balance=balance, min_balance=self.min_balance,
            ))
        else:
            checks.append(self._ok(
                "oanda_balance",
                f"OANDA balance: ${balance:,.2f}, {oanda_data.get('open_trade_count', 0)} open trades",
                component="OANDA",
                balance=balance, open_trades=oanda_data.get("open_trade_count", 0),
            ))

        # Margin check
        if margin_available <= 0:
            checks.append(self._fail(
                "oanda_margin",
                f"OANDA margin exhausted: ${margin_available:,.2f} available",
                component="OANDA",
                margin_available=margin_available,
            ))

        return checks

    def _check_api_health(self, api_data: dict) -> list[HealthCheck]:
        checks = []
        for name, data in api_data.items():
            if data.get("status") == "ok":
                response_ms = data.get("response_time_ms", 0)
                if response_ms > self.max_api_response_ms:
                    checks.append(self._warn(
                        f"api_{name.lower().replace(' ', '_')}_latency",
                        f"{name} is slow: {response_ms:.0f}ms (threshold: {self.max_api_response_ms}ms)",
                        component="API",
                        endpoint=name, response_time_ms=response_ms,
                    ))
                else:
                    checks.append(self._ok(
                        f"api_{name.lower().replace(' ', '_')}_health",
                        f"{name}: HTTP {data.get('status_code')} in {response_ms:.0f}ms",
                        component="API",
                        endpoint=name, response_time_ms=response_ms,
                    ))
            else:
                checks.append(self._fail(
                    f"api_{name.lower().replace(' ', '_')}_health",
                    "{} is DOWN: {}".format(name, data.get('error') or 'HTTP {}'.format(data.get('status_code'))),
                    component="API",
                    endpoint=name, error=data.get("error"),
                ))

        return checks

    def _check_jenkins(self, jenkins_data: dict) -> list[HealthCheck]:
        checks = []
        for job_name, data in jenkins_data.items():
            if "error" in data:
                continue  # Jenkins unavailable is not critical for trading

            result = data.get("result")
            building = data.get("building", False)

            # Use last 2 path components to avoid collisions (e.g., both jobs ending in /master)
            parts = job_name.split("/")
            short_name = "_".join(parts[-2:]).replace("-", "_") if len(parts) >= 2 else parts[-1].replace("-", "_")

            if building:
                checks.append(self._ok(
                    f"jenkins_{short_name}_build",
                    f"Jenkins {job_name}: build #{data.get('number')} in progress",
                    component="Jenkins CI",
                ))
            elif result == "SUCCESS":
                checks.append(self._ok(
                    f"jenkins_{short_name}_build",
                    f"Jenkins {job_name}: last build #{data.get('number')} SUCCESS",
                    component="Jenkins CI",
                ))
            elif result in ("FAILURE", "UNSTABLE", "ABORTED"):
                checks.append(self._warn(
                    f"jenkins_{short_name}_build",
                    f"Jenkins {job_name}: last build #{data.get('number')} {result}",
                    component="Jenkins CI",
                    job=job_name, result=result, build_url=data.get("url"),
                ))
            else:
                # result is None but not building — treat as OK (no data yet)
                checks.append(self._ok(
                    f"jenkins_{short_name}_build",
                    f"Jenkins {job_name}: no recent build",
                    component="Jenkins CI",
                ))

        return checks

    def _check_cnpg(self, cnpg_data: dict) -> list[HealthCheck]:
        """Check CloudNativePG clusters (TimescaleDB, etc.)."""
        if "error" in cnpg_data:
            return [self._warn(
                "cnpg_accessible",
                f"Cannot read CNPG clusters: {cnpg_data['error']}",
                component="Data Layer",
            )]

        checks = []
        for name, data in cnpg_data.items():
            if "error" in data:
                checks.append(self._warn(
                    f"cnpg_{name.replace('-', '_')}",
                    f"{name} not found",
                    component="Data Layer",
                ))
                continue

            status = data.get("status", "unknown")
            phase = data.get("phase", "?")
            ready = data.get("ready", 0)
            desired = data.get("desired", 0)

            if status == "unhealthy":
                checks.append(self._fail(
                    f"cnpg_{name.replace('-', '_')}",
                    f"{name}: 0/{desired} instances ready — DOWN (phase: {phase})",
                    component="Data Layer",
                    ready=ready, desired=desired, phase=phase,
                ))
            elif status == "degraded":
                checks.append(self._warn(
                    f"cnpg_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} ready, phase: {phase}",
                    component="Data Layer",
                    ready=ready, desired=desired, phase=phase,
                ))
            else:
                checks.append(self._ok(
                    f"cnpg_{name.replace('-', '_')}",
                    f"{name}: {ready}/{desired} instances ready",
                    component="Data Layer",
                    ready=ready, desired=desired,
                ))

        return checks

    # ─── Component Inventory ──────────────────────────────────────────────────

    def get_component_inventory(self) -> list[Component]:
        """Return live per-microservice component list with current status and categories."""
        now = datetime.now(timezone.utc).isoformat()
        components = []

        # ── Deployments (all, with category inference and live status) ──────────
        try:
            all_deploys = collect_k8s_all_deployments(
                k8s_namespace=self.k8s_namespace,
                kubeconfig_path=self.kubeconfig_path,
            )
            for name, data in all_deploys.items():
                if "error" not in data:
                    ready = data.get("ready", "?")
                    desired = data.get("desired", "?")
                    components.append(Component(
                        name=name,
                        type="k8s_deployment",
                        category=_infer_deployment_category(name),
                        description=f"{ready}/{desired} replicas",
                        metadata={
                            "namespace": self.k8s_namespace,
                            "status": data.get("status", "unknown"),
                            "ready": ready,
                            "desired": desired,
                            "last_seen": now,
                        },
                    ))
        except Exception:
            for deploy in self.critical_deployments:
                components.append(Component(
                    name=deploy, type="k8s_deployment",
                    category=_infer_deployment_category(deploy),
                    description=f"Critical deployment: {deploy}",
                    metadata={"namespace": self.k8s_namespace,
                              "status": "unknown", "last_seen": now},
                ))

        # ── StatefulSets (databases, brokers) — live status ─────────────────────
        if self.statefulset_names:
            try:
                sts_data = collect_k8s_statefulsets(
                    k8s_namespace=self.statefulset_namespace,
                    names=self.statefulset_names,
                    kubeconfig_path=self.kubeconfig_path,
                )
                for sts_name, data in sts_data.items():
                    if "error" not in data:
                        r = data.get("ready", "?")
                        d = data.get("desired", "?")
                        components.append(Component(
                            name=sts_name,
                            type="k8s_statefulset",
                            category="Data Layer",
                            description=f"{r}/{d} pods ready",
                            metadata={
                                "namespace": self.statefulset_namespace,
                                "status": data.get("status", "unknown"),
                                "ready": r,
                                "desired": d,
                                "last_seen": now,
                            },
                        ))
                    else:
                        components.append(Component(
                            name=sts_name,
                            type="k8s_statefulset",
                            category="Data Layer",
                            description="StatefulSet not found",
                            metadata={"namespace": self.statefulset_namespace,
                                      "status": "unknown", "last_seen": now},
                        ))
            except Exception:
                for sts_name in self.statefulset_names:
                    components.append(Component(
                        name=sts_name, type="k8s_statefulset", category="Data Layer",
                        description=f"StatefulSet: {sts_name}",
                        metadata={"namespace": self.statefulset_namespace,
                                  "status": "unknown", "last_seen": now},
                    ))

        # ── CNPG clusters (TimescaleDB etc.) — live status ───────────────────────
        if self.cnpg_names:
            try:
                cnpg_data = collect_k8s_cnpg_clusters(
                    namespace=self.cnpg_namespace,
                    names=self.cnpg_names,
                    kubeconfig_path=self.kubeconfig_path,
                )
                for name, data in cnpg_data.items():
                    if "error" not in data:
                        r = data.get("ready", "?")
                        d = data.get("desired", "?")
                        phase = data.get("phase", "?")
                        components.append(Component(
                            name=name,
                            type="cnpg_cluster",
                            category="Data Layer",
                            description=f"{r}/{d} instances | {phase}",
                            metadata={
                                "namespace": self.cnpg_namespace,
                                "status": data.get("status", "unknown"),
                                "phase": phase,
                                "ready": r,
                                "desired": d,
                                "last_seen": now,
                            },
                        ))
                    else:
                        components.append(Component(
                            name=name,
                            type="cnpg_cluster",
                            category="Data Layer",
                            description="CNPG cluster not found",
                            metadata={"namespace": self.cnpg_namespace,
                                      "status": "unknown", "last_seen": now},
                        ))
            except Exception:
                pass

        # ── Cluster nodes ────────────────────────────────────────────────────────
        try:
            node_data = collect_k8s_nodes(kubeconfig_path=self.kubeconfig_path)
            for node in node_data.get("nodes", []):
                is_ready = node.get("ready", False)
                has_pressure = (node.get("memory_pressure") or
                                node.get("disk_pressure") or
                                node.get("pid_pressure"))
                node_status = ("healthy" if is_ready and not has_pressure
                               else ("degraded" if is_ready else "unhealthy"))
                components.append(Component(
                    name=node["name"],
                    type="k8s_node",
                    category="Cluster",
                    description=(f"Node: {','.join(node.get('roles', ['worker']))} | "
                                 f"CPU:{node.get('cpu','?')} | {node.get('memory','?')}"),
                    metadata={"ready": is_ready, "status": node_status, "last_seen": now},
                ))
        except Exception:
            pass

        # ── OANDA ────────────────────────────────────────────────────────────────
        if self.oanda_account_id:
            components.append(Component(
                name="oanda-account",
                type="broker_api",
                category="OANDA",
                description="OANDA FX broker account",
                metadata={"account_id": self.oanda_account_id,
                          "status": "healthy", "last_seen": now},
            ))

        # ── API health endpoints ─────────────────────────────────────────────────
        for endpoint in self.health_endpoints:
            components.append(Component(
                name=endpoint.get("name", endpoint.get("url")),
                type="api_endpoint",
                category="API",
                description=f"{endpoint.get('url')}",
                metadata={"status": "healthy", "last_seen": now},
            ))

        # ── Jenkins jobs — live build result ─────────────────────────────────────
        if self.jenkins_url and self.jenkins_jobs:
            try:
                jenkins_data = collect_jenkins_build_status(
                    jenkins_url=self.jenkins_url,
                    username=self.jenkins_username,
                    api_token=self.jenkins_api_token,
                    jobs=self.jenkins_jobs,
                )
                for job in self.jenkins_jobs:
                    data = jenkins_data.get(job, {})
                    if "error" in data:
                        job_status = "unknown"
                    elif data.get("building"):
                        job_status = "healthy"  # actively building = alive
                    elif data.get("result") == "SUCCESS":
                        job_status = "healthy"
                    elif data.get("result") in ("FAILURE", "UNSTABLE", "ABORTED"):
                        job_status = "degraded"
                    else:
                        job_status = "healthy"  # no result yet = not failed
                    components.append(Component(
                        name=job, type="ci_job", category="Jenkins CI",
                        description=f"Build #{data.get('number', '?')} — {data.get('result', 'N/A')}",
                        metadata={"status": job_status, "last_seen": now},
                    ))
            except Exception:
                for job in self.jenkins_jobs:
                    components.append(Component(
                        name=job, type="ci_job", category="Jenkins CI",
                        description="CI/CD build pipeline",
                        metadata={"status": "unknown", "last_seen": now},
                    ))

        return components

    def describe_architecture(self) -> str:
        return (
            "ForexTrader is an autonomous ML-based forex trading platform running on RKE2 Kubernetes.\n"
            f"- Kubernetes namespace: {self.k8s_namespace}\n"
            f"- Deployments monitored: {len(self.critical_deployments)} critical + all namespace deployments\n"
            f"- StatefulSets (databases): {', '.join(self.statefulset_names) if self.statefulset_names else 'none'}\n"
            f"- Monitored namespaces: {', '.join(self.monitor_namespaces)}\n"
            "- Broker: OANDA FX API (demo/live account)\n"
            "- ML Stack: PyTorch ensemble models, 48 model ensemble (LightGBM, LSTM, Transformer, RL agents)\n"
            "- Infrastructure: RKE2 Kubernetes, GPU nodes (DGX Spark ARM64 + RTX 5080/5090)\n"
            "- Data: Redpanda (Kafka), TimescaleDB, MongoDB, Redis, Qdrant vector store\n"
            "- CI/CD: Jenkins with Kaniko multi-arch builds, ArgoCD GitOps\n"
            "Issues typically involve: pod crashes, OOM kills, ML training failures, OANDA API errors."
        )
