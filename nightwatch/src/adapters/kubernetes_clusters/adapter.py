"""Read-only monitoring through each configured Kubernetes API server."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import structlog

try:
    from kubernetes import client, config as kubernetes_config
except ImportError:  # pragma: no cover - exercised in minimal installations
    client = None
    kubernetes_config = None

from src.adapters.base_adapter import BaseNightwatchAdapter, Component, HealthCheck


log = structlog.get_logger("nightwatch.adapter.kubernetes_clusters")


def _check_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def _condition_status(conditions: list[Any] | None, condition_type: str) -> str:
    for condition in conditions or []:
        if getattr(condition, "type", None) == condition_type:
            return str(getattr(condition, "status", "Unknown"))
    return "Unknown"


class KubernetesClustersAdapter(BaseNightwatchAdapter):
    """Collect cluster, node, deployment, and unhealthy-pod evidence.

    Connections are created only from kubeconfig contexts or an in-cluster
    service account. Every Kubernetes operation used here is a list/read call.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.request_timeout = int(config.get("request_timeout_seconds", 10))
        self._connections: dict[str, dict[str, Any]] = {}
        self._connection_errors: dict[str, str] = {}
        self._snapshot: dict[str, list[dict[str, Any]]] = {
            "clusters": [],
            "nodes": [],
            "deployments": [],
            "pods": [],
        }
        self._collection_errors: dict[str, str] = {}

    @property
    def application_name(self) -> str:
        return self.config.get("application_name", "Kubernetes Clusters")

    def _configured_clusters(self) -> list[dict[str, Any]]:
        configured = [dict(item) for item in self.config.get("clusters", [])]
        if self.config.get("discover_kubeconfig_contexts", False):
            kubeconfig_path = self.config.get("kubeconfig_path") or None
            contexts, _ = kubernetes_config.list_kube_config_contexts(
                config_file=kubeconfig_path
            )
            known_contexts = {item.get("context") for item in configured}
            for item in contexts or []:
                context_name = item.get("name")
                if context_name and context_name not in known_contexts:
                    configured.append(
                        {
                            "name": context_name,
                            "context": context_name,
                            "kubeconfig_path": kubeconfig_path,
                        }
                    )
        return configured

    def initialize(self) -> None:
        if client is None or kubernetes_config is None:
            raise ImportError(
                "The kubernetes package is required for Kubernetes cluster monitoring"
            )
        clusters = self._configured_clusters()
        if not clusters:
            raise ValueError(
                "No Kubernetes clusters configured; add clusters or enable "
                "discover_kubeconfig_contexts"
            )

        for cluster_config in clusters:
            name = str(cluster_config.get("name") or cluster_config.get("context") or "")
            if not name:
                raise ValueError("Every Kubernetes cluster connection needs a name")
            if name in self._connections:
                raise ValueError(f"Duplicate Kubernetes cluster name: {name}")

            try:
                if cluster_config.get("in_cluster", False):
                    kubernetes_config.load_incluster_config()
                    api_client = client.ApiClient()
                else:
                    kubeconfig_path = cluster_config.get("kubeconfig_path") or self.config.get(
                        "kubeconfig_path"
                    )
                    if kubeconfig_path and not Path(kubeconfig_path).is_file():
                        raise FileNotFoundError(
                            f"Kubeconfig for cluster {name} not found: {kubeconfig_path}"
                        )
                    api_client = kubernetes_config.new_client_from_config(
                        config_file=kubeconfig_path or None,
                        context=cluster_config.get("context") or None,
                    )
            except Exception as exc:
                self._connection_errors[name] = str(exc)
                log.error(
                    "kubernetes_connection_failed", cluster=name, error=str(exc)
                )
                continue

            self._connections[name] = {
                "api_client": api_client,
                "namespaces": list(cluster_config.get("namespaces", [])),
            }
        self._initialized = True

    def cleanup(self) -> None:
        for connection in self._connections.values():
            connection["api_client"].close()

    def _record_error(self, cluster: str, scope: str, error: Exception) -> None:
        key = f"{cluster}:{scope}"
        self._collection_errors[key] = str(error)
        log.warning(
            "kubernetes_collection_failed",
            cluster=cluster,
            scope=scope,
            error=str(error),
        )

    def _list_workloads(
        self,
        core_api: client.CoreV1Api,
        apps_api: client.AppsV1Api,
        namespaces: list[str],
    ) -> tuple[list[Any], list[Any]]:
        timeout = self.request_timeout
        if namespaces:
            pods: list[Any] = []
            deployments: list[Any] = []
            for namespace in namespaces:
                pods.extend(
                    core_api.list_namespaced_pod(
                        namespace, _request_timeout=timeout
                    ).items
                )
                deployments.extend(
                    apps_api.list_namespaced_deployment(
                        namespace, _request_timeout=timeout
                    ).items
                )
            return pods, deployments
        return (
            core_api.list_pod_for_all_namespaces(_request_timeout=timeout).items,
            apps_api.list_deployment_for_all_namespaces(
                _request_timeout=timeout
            ).items,
        )

    def collect_metrics(self) -> dict:
        observed_at = datetime.now(timezone.utc).isoformat()
        snapshot = {"clusters": [], "nodes": [], "deployments": [], "pods": []}
        self._collection_errors = {
            f"{cluster}:connection": error
            for cluster, error in self._connection_errors.items()
        }

        for cluster_name in self._connection_errors:
            snapshot["clusters"].append(
                {
                    "name": cluster_name,
                    "status": "unknown",
                    "version": None,
                    "observed_at": None,
                    "stale": True,
                }
            )

        for cluster_name, connection in self._connections.items():
            api_client = connection["api_client"]
            core_api = client.CoreV1Api(api_client)
            apps_api = client.AppsV1Api(api_client)
            version_api = client.VersionApi(api_client)
            try:
                version = version_api.get_code(_request_timeout=self.request_timeout)
                nodes = core_api.list_node(_request_timeout=self.request_timeout).items
                pods, deployments = self._list_workloads(
                    core_api, apps_api, connection["namespaces"]
                )
            except Exception as exc:
                self._record_error(cluster_name, "api", exc)
                snapshot["clusters"].append(
                    {
                        "name": cluster_name,
                        "status": "unknown",
                        "version": None,
                        "observed_at": None,
                        "stale": True,
                    }
                )
                continue

            node_records = []
            for node in nodes:
                ready = _condition_status(node.status.conditions, "Ready")
                node_records.append(
                    {
                        "cluster": cluster_name,
                        "name": node.metadata.name,
                        "ready": ready,
                        "status": "healthy" if ready == "True" else "unhealthy",
                        "observed_at": observed_at,
                    }
                )

            deployment_records = []
            for deployment in deployments:
                desired = int(deployment.spec.replicas or 0)
                available = int(deployment.status.available_replicas or 0)
                deployment_records.append(
                    {
                        "cluster": cluster_name,
                        "namespace": deployment.metadata.namespace,
                        "name": deployment.metadata.name,
                        "desired": desired,
                        "ready": available,
                        "status": "healthy" if available >= desired else "degraded",
                        "observed_at": observed_at,
                    }
                )

            unhealthy_pods = []
            for pod in pods:
                phase = str(pod.status.phase or "Unknown")
                waiting_reasons = [
                    state.waiting.reason
                    for container_status in pod.status.container_statuses or []
                    if (state := container_status.state) and state.waiting
                ]
                failure_reasons = {
                    "CrashLoopBackOff",
                    "CreateContainerConfigError",
                    "CreateContainerError",
                    "ErrImagePull",
                    "ImagePullBackOff",
                    "InvalidImageName",
                    "RunContainerError",
                }
                unhealthy = phase in {"Failed", "Unknown"} or bool(
                    failure_reasons.intersection(waiting_reasons)
                )
                if unhealthy:
                    unhealthy_pods.append(
                        {
                            "cluster": cluster_name,
                            "namespace": pod.metadata.namespace,
                            "name": pod.metadata.name,
                            "phase": phase,
                            "reasons": waiting_reasons,
                            "status": "unhealthy",
                            "observed_at": observed_at,
                        }
                    )

            snapshot["nodes"].extend(node_records)
            snapshot["deployments"].extend(deployment_records)
            snapshot["pods"].extend(unhealthy_pods)
            snapshot["clusters"].append(
                {
                    "name": cluster_name,
                    "status": "healthy",
                    "version": getattr(version, "git_version", None),
                    "nodes_total": len(node_records),
                    "nodes_ready": sum(item["ready"] == "True" for item in node_records),
                    "pods_total": len(pods),
                    "pods_unhealthy": len(unhealthy_pods),
                    "deployments_total": len(deployment_records),
                    "deployments_degraded": sum(
                        item["status"] == "degraded" for item in deployment_records
                    ),
                    "observed_at": observed_at,
                    "stale": False,
                }
            )

        self._snapshot = snapshot
        return snapshot

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        del lookback_minutes
        return [
            f"Kubernetes API collection failed for {scope}: {error}"
            for scope, error in sorted(self._collection_errors.items())
        ]

    def run_health_checks(self) -> list[HealthCheck]:
        checks: list[HealthCheck] = []
        for scope, error in sorted(self._collection_errors.items()):
            checks.append(
                self._unknown(
                    f"kubernetes_{scope.replace(':', '_')}_collection",
                    f"Unable to read Kubernetes API evidence for {scope}: {error}",
                    component="Kubernetes API",
                    scope=scope,
                )
            )
        for cluster in self._snapshot["clusters"]:
            if cluster["status"] == "healthy":
                metadata = {**cluster, "resource_name": cluster["name"]}
                metadata.pop("name", None)
                checks.append(
                    self._ok(
                        f"kubernetes_{_check_id(cluster['name'])}_api",
                        f"Kubernetes API server {cluster['name']} is reachable",
                        component="Kubernetes Cluster",
                        **metadata,
                    )
                )
        for node in self._snapshot["nodes"]:
            check = self._ok if node["ready"] == "True" else self._fail
            metadata = {**node, "resource_name": node["name"]}
            metadata.pop("name", None)
            checks.append(
                check(
                    f"kubernetes_{_check_id(node['cluster'])}_{_check_id(node['name'])}_ready",
                    f"Node {node['name']} Ready condition is {node['ready']}",
                    component="Kubernetes Node",
                    **metadata,
                )
            )
        for deployment in self._snapshot["deployments"]:
            check = self._ok if deployment["ready"] >= deployment["desired"] else self._fail
            metadata = {**deployment, "resource_name": deployment["name"]}
            metadata.pop("name", None)
            checks.append(
                check(
                    "kubernetes_"
                    f"{_check_id(deployment['cluster'])}_"
                    f"{_check_id(deployment['namespace'])}_"
                    f"{_check_id(deployment['name'])}_available",
                    f"Deployment {deployment['namespace']}/{deployment['name']} has "
                    f"{deployment['ready']}/{deployment['desired']} replicas available",
                    component="Kubernetes Deployment",
                    **metadata,
                )
            )
        for pod in self._snapshot["pods"]:
            metadata = {**pod, "resource_name": pod["name"]}
            metadata.pop("name", None)
            checks.append(
                self._fail(
                    "kubernetes_"
                    f"{_check_id(pod['cluster'])}_"
                    f"{_check_id(pod['namespace'])}_"
                    f"{_check_id(pod['name'])}_pod",
                    f"Pod {pod['namespace']}/{pod['name']} is {pod['phase']}"
                    + (f" ({', '.join(pod['reasons'])})" if pod["reasons"] else ""),
                    component="Kubernetes Pod",
                    **metadata,
                )
            )
        return checks

    def get_component_inventory(self) -> list[Component]:
        components: list[Component] = []
        for cluster in self._snapshot["clusters"]:
            components.append(
                Component(
                    cluster["name"],
                    "kubernetes_cluster",
                    "Kubernetes",
                    "Read-only Kubernetes API connection",
                    {**cluster, "last_seen": cluster.get("observed_at")},
                )
            )
        for resource_type, category in (
            ("nodes", "Kubernetes Node"),
            ("deployments", "Kubernetes Deployment"),
            ("pods", "Kubernetes Pod"),
        ):
            singular = resource_type[:-1]
            for resource in self._snapshot[resource_type]:
                components.append(
                    Component(
                        resource["name"],
                        f"kubernetes_{singular}",
                        category,
                        f"Observed through {resource['cluster']} API server",
                        {**resource, "last_seen": resource.get("observed_at")},
                    )
                )
        return components

    def describe_architecture(self) -> str:
        names = ", ".join(sorted(self._connections))
        return (
            "Read-only Kubernetes API monitoring for configured clusters: "
            f"{names}. Evidence includes node readiness, deployment availability, "
            "and unhealthy pod state."
        )
