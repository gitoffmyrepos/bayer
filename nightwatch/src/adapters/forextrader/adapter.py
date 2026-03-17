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
from typing import Optional

from src.adapters.base_adapter import BaseNightwatchAdapter, HealthCheck, CheckStatus, Component
from src.adapters.forextrader.collectors import (
    collect_k8s_pod_status,
    collect_k8s_deployment_status,
    collect_oanda_account_health,
    collect_api_health,
    collect_jenkins_build_status,
)

log = logging.getLogger("nightwatch.adapter.forextrader")


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
        self.min_pods_running = thresholds.get("min_pods_running", 10)
        self.max_pod_restarts = thresholds.get("max_pod_restarts", 5)
        self.min_balance = thresholds.get("min_balance", 90000)
        self.max_drawdown_pct = thresholds.get("max_drawdown_pct", 10.0)
        self.max_api_response_ms = thresholds.get("max_api_response_ms", 2000)

    # ─── Data Collection ──────────────────────────────────────────────────────

    def collect_metrics(self) -> dict:
        metrics = {}

        metrics["k8s"] = collect_k8s_pod_status(
            k8s_namespace=self.k8s_namespace,
            kubeconfig_path=self.kubeconfig_path,
        )

        if self.critical_deployments:
            metrics["deployments"] = collect_k8s_deployment_status(
                k8s_namespace=self.k8s_namespace,
                deployments=self.critical_deployments,
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

        return metrics

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """Collect recent error logs from failing pods via kubectl."""
        try:
            from kubernetes import client, config as k8s_config
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
            log.warning("log_collection_failed", error=str(e))
            return []

    # ─── Health Checks ────────────────────────────────────────────────────────

    def run_health_checks(self) -> list[HealthCheck]:
        checks = []
        metrics = self.collect_metrics()

        # Kubernetes pod checks
        if k8s := metrics.get("k8s"):
            checks.extend(self._check_k8s(k8s))

        # Deployment readiness checks
        if deployments := metrics.get("deployments"):
            checks.extend(self._check_deployments(deployments))

        # OANDA account checks
        if oanda := metrics.get("oanda"):
            checks.extend(self._check_oanda(oanda))

        # API health checks
        if api_health := metrics.get("api_health"):
            checks.extend(self._check_api_health(api_health))

        # Jenkins build checks
        if jenkins := metrics.get("jenkins"):
            checks.extend(self._check_jenkins(jenkins))

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

        # High restart count pods
        crashlooping = [
            p for p in k8s_data.get("pods", [])
            if p.get("restarts", 0) >= self.max_pod_restarts
        ]
        if crashlooping:
            checks.append(self._warn(
                "k8s_crashlooping",
                f"{len(crashlooping)} pod(s) with high restarts: {', '.join(p['name'] for p in crashlooping[:3])}",
                component="Kubernetes",
                pods=[{"name": p["name"], "restarts": p["restarts"]} for p in crashlooping],
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
                    f"{name} is DOWN: {data.get('error', f'HTTP {data.get(\"status_code\")}')}",
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

            short_name = job_name.split("/")[-1].replace("-", "_")

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
            elif result in ("FAILURE", "UNSTABLE"):
                checks.append(self._warn(
                    f"jenkins_{short_name}_build",
                    f"Jenkins {job_name}: last build #{data.get('number')} {result}",
                    component="Jenkins CI",
                    job=job_name, result=result, build_url=data.get("url"),
                ))

        return checks

    # ─── Component Inventory ──────────────────────────────────────────────────

    def get_component_inventory(self) -> list[Component]:
        components = [
            Component(
                name=self.k8s_namespace,
                type="k8s_namespace",
                category="Kubernetes",
                description=f"ForexTrader pods in {self.k8s_namespace}",
            ),
        ]

        for deploy in self.critical_deployments:
            components.append(Component(
                name=deploy, type="k8s_deployment", category="Kubernetes",
                description=f"Critical deployment: {deploy}",
                metadata={"namespace": self.k8s_namespace},
            ))

        if self.oanda_account_id:
            components.append(Component(
                name="oanda-account",
                type="broker_api",
                category="OANDA",
                description="OANDA FX broker account",
                metadata={"account_id": self.oanda_account_id},
            ))

        for endpoint in self.health_endpoints:
            components.append(Component(
                name=endpoint.get("name", endpoint.get("url")),
                type="api_endpoint",
                category="API",
                description=f"Health endpoint: {endpoint.get('url')}",
            ))

        for job in self.jenkins_jobs:
            components.append(Component(
                name=job, type="ci_job", category="Jenkins CI",
            ))

        return components

    def describe_architecture(self) -> str:
        return (
            "ForexTrader is an autonomous ML-based forex trading platform running on RKE2 Kubernetes.\n"
            f"- Kubernetes namespace: {self.k8s_namespace} (prod-forex)\n"
            f"- Critical deployments: {', '.join(self.critical_deployments) if self.critical_deployments else 'all pods monitored'}\n"
            f"- Broker: OANDA FX API (demo/live account)\n"
            "- ML Stack: PyTorch ensemble models, 48 model ensemble (LightGBM, LSTM, Transformer, RL agents)\n"
            "- Infrastructure: RKE2 Kubernetes, GPU nodes (DGX Spark ARM64 + RTX 5080/5090)\n"
            "- Data: Redpanda (Kafka), TimescaleDB, MongoDB, Redis, Qdrant vector store\n"
            "- CI/CD: Jenkins with Kaniko multi-arch builds, ArgoCD GitOps\n"
            "Issues typically involve: pod crashes, OOM kills, ML training failures, OANDA API errors."
        )
