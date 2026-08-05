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


def _owner_name(resource: Any, owner_kind: str) -> str | None:
    for owner in getattr(resource.metadata, "owner_references", None) or []:
        if getattr(owner, "kind", None) == owner_kind:
            return str(owner.name)
    return None


def _resource_time(resource: Any) -> datetime:
    created = getattr(resource.metadata, "creation_timestamp", None)
    if isinstance(created, datetime):
        if created.tzinfo is None:
            return created.replace(tzinfo=timezone.utc)
        return created
    return datetime.min.replace(tzinfo=timezone.utc)


def _failure_condition(resource: Any) -> Any | None:
    for condition in getattr(resource.status, "conditions", None) or []:
        if (
            getattr(condition, "type", None) == "Failed"
            and str(getattr(condition, "status", "Unknown")) == "True"
        ):
            return condition
    return None


def _complete_condition(resource: Any) -> Any | None:
    for condition in getattr(resource.status, "conditions", None) or []:
        if (
            getattr(condition, "type", None) == "Complete"
            and str(getattr(condition, "status", "Unknown")) == "True"
        ):
            return condition
    return None


def _current_pod_failure_reasons(pod: Any) -> list[str]:
    """Return only actionable failure reasons for a non-terminal pod.

    Kubernetes deliberately retains terminal pod objects for Job history,
    evictions, and manual debugging. Those objects are evidence of past events,
    not active workloads. CronJob outcomes are evaluated separately from their
    latest owning Job.
    """
    if getattr(pod.metadata, "deletion_timestamp", None) is not None:
        return []

    phase = str(getattr(pod.status, "phase", None) or "Unknown")
    if phase in {"Succeeded", "Failed"}:
        return []

    failure_reasons = {
        "CrashLoopBackOff",
        "CreateContainerConfigError",
        "CreateContainerError",
        "ErrImagePull",
        "ImagePullBackOff",
        "InvalidImageName",
        "RunContainerError",
    }
    reasons: list[str] = []
    statuses = list(getattr(pod.status, "init_container_statuses", None) or [])
    statuses.extend(getattr(pod.status, "container_statuses", None) or [])
    for container_status in statuses:
        state = getattr(container_status, "state", None)
        waiting = getattr(state, "waiting", None) if state else None
        reason = getattr(waiting, "reason", None) if waiting else None
        if reason in failure_reasons and reason not in reasons:
            reasons.append(str(reason))

    for condition in getattr(pod.status, "conditions", None) or []:
        if (
            getattr(condition, "type", None) == "PodScheduled"
            and str(getattr(condition, "status", "Unknown")) == "False"
            and getattr(condition, "reason", None) == "Unschedulable"
            and "Unschedulable" not in reasons
        ):
            reasons.append("Unschedulable")

    if phase == "Unknown" and "Unknown" not in reasons:
        reasons.append("Unknown")
    return reasons


def _cronjob_records(
    cluster_name: str,
    cronjobs: list[Any],
    jobs: list[Any],
    observed_at: str,
) -> list[dict[str, Any]]:
    latest_jobs: dict[tuple[str, str], Any] = {}
    for job in jobs:
        cronjob_name = _owner_name(job, "CronJob")
        if not cronjob_name:
            continue
        key = (str(job.metadata.namespace), cronjob_name)
        current = latest_jobs.get(key)
        if current is None or _resource_time(job) > _resource_time(current):
            latest_jobs[key] = job

    records: list[dict[str, Any]] = []
    for cronjob in cronjobs:
        namespace = str(cronjob.metadata.namespace)
        name = str(cronjob.metadata.name)
        latest_job = latest_jobs.get((namespace, name))
        suspended = bool(getattr(cronjob.spec, "suspend", False))
        last_scheduled = getattr(cronjob.status, "last_schedule_time", None)
        last_successful = getattr(cronjob.status, "last_successful_time", None)
        status = "healthy" if suspended else "unknown"
        latest_job_name = None
        latest_job_status = "suspended" if suspended else "not_observed"
        reason = "Suspended" if suspended else "NoObservedRuns"
        message = (
            "CronJob is intentionally suspended"
            if suspended
            else "No Job owned by this CronJob was observed"
        )
        last_run_at = None

        if latest_job is not None:
            latest_job_name = str(latest_job.metadata.name)
            created = _resource_time(latest_job)
            last_run_at = None if created == datetime.min.replace(
                tzinfo=timezone.utc
            ) else created.isoformat()

        if latest_job is not None and not suspended:
            failed = _failure_condition(latest_job)
            completed = _complete_condition(latest_job)
            active = int(getattr(latest_job.status, "active", 0) or 0)
            succeeded = int(getattr(latest_job.status, "succeeded", 0) or 0)
            if failed is not None:
                status = "unhealthy"
                latest_job_status = "failed"
                reason = str(getattr(failed, "reason", None) or "JobFailed")
                message = str(
                    getattr(failed, "message", None)
                    or "Latest owned Job failed"
                )
            elif completed is not None or succeeded > 0:
                status = "healthy"
                latest_job_status = "complete"
                reason = str(
                    getattr(completed, "reason", None) or "CompletionsReached"
                )
                message = "Latest owned Job completed successfully"
            elif active > 0:
                status = "healthy"
                latest_job_status = "running"
                reason = "JobActive"
                message = "Latest owned Job is running"
            else:
                status = "unknown"
                latest_job_status = "unknown"
                reason = "JobStatusUnknown"
                message = "Latest owned Job has no terminal or active status"

        if latest_job is None and not suspended:
            if isinstance(last_successful, datetime) and (
                not isinstance(last_scheduled, datetime)
                or last_successful >= last_scheduled
            ):
                status = "healthy"
                latest_job_status = "complete"
                reason = "LastScheduledRunSucceeded"
                message = "CronJob reports its last scheduled run succeeded"
            elif not isinstance(last_scheduled, datetime):
                status = "healthy"
                latest_job_status = "not_observed"
                reason = "AwaitingFirstRun"
                message = "CronJob has not reached its first scheduled run"

        records.append(
            {
                "cluster": cluster_name,
                "namespace": namespace,
                "name": name,
                "schedule": str(getattr(cronjob.spec, "schedule", "")),
                "suspended": suspended,
                "latest_job": latest_job_name,
                "latest_job_status": latest_job_status,
                "reason": reason,
                "message": message,
                "last_run_at": last_run_at,
                "last_scheduled_at": (
                    last_scheduled.isoformat()
                    if isinstance(last_scheduled, datetime)
                    else None
                ),
                "last_successful_at": (
                    last_successful.isoformat()
                    if isinstance(last_successful, datetime)
                    else None
                ),
                "status": status,
                "observed_at": observed_at,
            }
        )
    return records


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
            "cronjobs": [],
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

    def _list_batch_workloads(
        self,
        batch_api: client.BatchV1Api,
        namespaces: list[str],
    ) -> tuple[list[Any], list[Any]]:
        timeout = self.request_timeout
        if namespaces:
            jobs: list[Any] = []
            cronjobs: list[Any] = []
            for namespace in namespaces:
                jobs.extend(
                    batch_api.list_namespaced_job(
                        namespace, _request_timeout=timeout
                    ).items
                )
                cronjobs.extend(
                    batch_api.list_namespaced_cron_job(
                        namespace, _request_timeout=timeout
                    ).items
                )
            return jobs, cronjobs
        return (
            batch_api.list_job_for_all_namespaces(
                _request_timeout=timeout
            ).items,
            batch_api.list_cron_job_for_all_namespaces(
                _request_timeout=timeout
            ).items,
        )

    def collect_metrics(self) -> dict:
        observed_at = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "clusters": [],
            "nodes": [],
            "deployments": [],
            "cronjobs": [],
            "pods": [],
        }
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
            batch_api = client.BatchV1Api(api_client)
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

            try:
                jobs, cronjobs = self._list_batch_workloads(
                    batch_api, connection["namespaces"]
                )
            except Exception as exc:
                self._record_error(cluster_name, "batch", exc)
                jobs, cronjobs = [], []

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

            cronjob_records = _cronjob_records(
                cluster_name, cronjobs, jobs, observed_at
            )

            unhealthy_pods = []
            for pod in pods:
                phase = str(pod.status.phase or "Unknown")
                failure_reasons = _current_pod_failure_reasons(pod)
                if failure_reasons:
                    unhealthy_pods.append(
                        {
                            "cluster": cluster_name,
                            "namespace": pod.metadata.namespace,
                            "name": pod.metadata.name,
                            "phase": phase,
                            "reasons": failure_reasons,
                            "status": "unhealthy",
                            "observed_at": observed_at,
                        }
                    )

            snapshot["nodes"].extend(node_records)
            snapshot["deployments"].extend(deployment_records)
            snapshot["cronjobs"].extend(cronjob_records)
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
                    "cronjobs_total": len(cronjob_records),
                    "cronjobs_unhealthy": sum(
                        item["status"] == "unhealthy"
                        for item in cronjob_records
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
        for cronjob in self._snapshot.get("cronjobs", []):
            if cronjob["status"] == "unhealthy":
                check = self._fail
            elif cronjob["status"] == "healthy":
                check = self._ok
            else:
                check = self._unknown
            metadata = {**cronjob, "resource_name": cronjob["name"]}
            metadata.pop("name", None)
            checks.append(
                check(
                    "kubernetes_"
                    f"{_check_id(cronjob['cluster'])}_"
                    f"{_check_id(cronjob['namespace'])}_"
                    f"{_check_id(cronjob['name'])}_latest_run",
                    f"CronJob {cronjob['namespace']}/{cronjob['name']} latest Job "
                    f"{cronjob['latest_job'] or 'not observed'} is "
                    f"{cronjob['latest_job_status']}: {cronjob['message']}",
                    component="Kubernetes CronJob",
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
            ("cronjobs", "Kubernetes CronJob"),
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
            "latest CronJob outcomes, and current non-terminal pod failures."
        )
