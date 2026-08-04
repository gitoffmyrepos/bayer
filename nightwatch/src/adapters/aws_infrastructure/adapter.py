"""Read-only inventory and deterministic health checks for EKS, EC2, and ECS."""

import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

import boto3
import structlog
from botocore.config import Config

from src.adapters.base_adapter import (
    BaseNightwatchAdapter,
    Component,
    HealthCheck,
)


log = structlog.get_logger("nightwatch.adapter.aws_infrastructure")

_BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=30,
)


def _check_id(value: str) -> str:
    """Return a stable identifier suitable for HealthCheck names."""

    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


class AWSInfrastructureAdapter(BaseNightwatchAdapter):
    """Discover AWS compute infrastructure without any mutating API calls."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.region = (
            config.get("region")
            or config.get("aws_region")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.endpoint_url = config.get("endpoint_url") or os.getenv(
            "AWS_ENDPOINT_URL"
        ) or None
        self._eks_client = None
        self._ec2_client = None
        self._ecs_client = None
        self._snapshot: dict[str, list[dict[str, Any]]] = {
            "eks": [],
            "ec2": [],
            "ecs": [],
        }
        self._collection_errors: dict[str, str] = {}
        self._resource_observed_at: dict[tuple[str, str], str] = {}
        self._stale_resources: set[tuple[str, str]] = set()
        self._cycle_observed_at = datetime.now(timezone.utc).isoformat()

    @property
    def application_name(self) -> str:
        return self.config.get("application_name", "AWS Infrastructure")

    def _client(self, service: str):
        return boto3.client(
            service,
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            config=_BOTO_CONFIG,
        )

    @property
    def _eks(self):
        if self._eks_client is None:
            self._eks_client = self._client("eks")
        return self._eks_client

    @property
    def _ec2(self):
        if self._ec2_client is None:
            self._ec2_client = self._client("ec2")
        return self._ec2_client

    @property
    def _ecs(self):
        if self._ecs_client is None:
            self._ecs_client = self._client("ecs")
        return self._ecs_client

    def initialize(self) -> None:
        """Build clients without requiring every monitored service to be healthy."""

        # Client creation validates the provider configuration locally. Network
        # calls happen per service in collect_metrics so partial outages remain
        # visible instead of preventing the adapter from loading.
        self._eks
        self._ec2
        self._ecs
        self._initialized = True

    def _collect_service(
        self, name: str, collector: Callable[[], list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        for scope in list(self._collection_errors):
            if scope == name or scope.startswith(f"{name}:"):
                del self._collection_errors[scope]
        try:
            return collector()
        except Exception as exc:
            self._record_collection_error(name, exc)
            # A provider outage must not erase inventory that was successfully
            # observed on the prior cycle. The error finding marks it stale.
            return [
                self._mark_stale(name, item)
                for item in self._snapshot.get(name, [])
            ]

    @staticmethod
    def _resource_key(service: str, item: dict[str, Any]) -> tuple[str, str]:
        if service == "eks":
            identifier = item.get("name", "unknown")
        elif service == "ec2":
            identifier = item.get("id", "unknown")
        else:
            identifier = f"{item.get('cluster', 'unknown')}/{item.get('service', 'unknown')}"
        return service, str(identifier)

    def _mark_observed(
        self, service: str, item: dict[str, Any]
    ) -> dict[str, Any]:
        record = dict(item)
        key = self._resource_key(service, record)
        self._resource_observed_at[key] = self._cycle_observed_at
        self._stale_resources.discard(key)
        return record

    def _mark_stale(
        self, service: str, item: dict[str, Any]
    ) -> dict[str, Any]:
        record = dict(item)
        self._stale_resources.add(self._resource_key(service, record))
        return record

    def _record_collection_error(self, scope: str, error: Exception | str) -> None:
        self._collection_errors[scope] = str(error)
        log.warning(
            "aws_inventory_collection_failed", service=scope, error=str(error)
        )

    def collect_metrics(self) -> dict:
        """Refresh the normalized EKS, EC2, and ECS inventory snapshot."""

        self._cycle_observed_at = datetime.now(timezone.utc).isoformat()
        self._snapshot = {
            "eks": self._collect_service("eks", self._collect_eks),
            "ec2": self._collect_service("ec2", self._collect_ec2),
            "ecs": self._collect_service("ecs", self._collect_ecs),
        }
        return self._snapshot

    def _collect_eks(self) -> list[dict[str, Any]]:
        prior = {
            cluster["name"]: cluster
            for cluster in self._snapshot.get("eks", [])
            if cluster.get("name")
        }
        cluster_names: list[str] = []
        token = None
        list_failed = False
        while True:
            params = {"nextToken": token} if token else {}
            try:
                response = self._eks.list_clusters(**params)
            except Exception as exc:
                self._record_collection_error("eks:list", exc)
                list_failed = True
                break
            cluster_names.extend(response.get("clusters", []))
            token = response.get("nextToken")
            if not token:
                break

        clusters = []
        for name in cluster_names:
            try:
                cluster = self._eks.describe_cluster(name=name).get("cluster", {})
            except Exception as exc:
                self._record_collection_error(f"eks:{name}", exc)
                if name in prior:
                    clusters.append(self._mark_stale("eks", prior[name]))
                continue
            vpc_config = cluster.get("resourcesVpcConfig", {})
            clusters.append(
                self._mark_observed(
                    "eks",
                    {
                    "name": cluster.get("name", name),
                    "status": cluster.get("status", "UNKNOWN"),
                    "version": cluster.get("version", "unknown"),
                    "endpoint_public": bool(
                        vpc_config.get("endpointPublicAccess", False)
                    ),
                    },
                )
            )
        if list_failed:
            observed = {cluster["name"] for cluster in clusters}
            clusters.extend(
                self._mark_stale("eks", cluster)
                for name, cluster in prior.items()
                if name not in observed
            )
        return clusters

    def _collect_ec2(self) -> list[dict[str, Any]]:
        prior = {
            instance["id"]: instance
            for instance in self._snapshot.get("ec2", [])
            if instance.get("id")
        }
        instances = []
        token = None
        while True:
            params = {"NextToken": token} if token else {}
            response = self._ec2.describe_instances(**params)
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    tags = {
                        tag.get("Key"): tag.get("Value")
                        for tag in instance.get("Tags", [])
                    }
                    instance_id = instance.get("InstanceId", "unknown")
                    instances.append(
                        {
                            "id": instance_id,
                            "name": tags.get("Name", instance_id),
                            "state": instance.get("State", {}).get(
                                "Name", "unknown"
                            ),
                            "public_ip": instance.get("PublicIpAddress"),
                        }
                    )
            token = response.get("NextToken")
            if not token:
                break

        statuses: dict[str, dict[str, str]] = {}
        token = None
        status_collection_failed = False
        try:
            while True:
                params: dict[str, Any] = {"IncludeAllInstances": True}
                if token:
                    params["NextToken"] = token
                response = self._ec2.describe_instance_status(**params)
                for status in response.get("InstanceStatuses", []):
                    instance_id = status.get("InstanceId")
                    if instance_id:
                        statuses[instance_id] = {
                            "instance_status": status.get("InstanceStatus", {}).get(
                                "Status", "unknown"
                            ),
                            "system_status": status.get("SystemStatus", {}).get(
                                "Status", "unknown"
                            ),
                        }
                token = response.get("NextToken")
                if not token:
                    break
        except Exception as exc:
            self._record_collection_error("ec2:instance-status", exc)
            status_collection_failed = True

        for instance in instances:
            previous = prior.get(instance["id"], {})
            health = statuses.get(instance["id"], previous)
            instance["instance_status"] = health.get("instance_status", "unknown")
            instance["system_status"] = health.get("system_status", "unknown")
            reused_prior_health = instance["id"] not in statuses and bool(previous)
            if status_collection_failed or reused_prior_health:
                self._mark_stale("ec2", instance)
            else:
                self._mark_observed("ec2", instance)
        return instances

    def _collect_ecs(self) -> list[dict[str, Any]]:
        prior = {
            (service["cluster"], service["service"]): service
            for service in self._snapshot.get("ecs", [])
            if service.get("cluster") and service.get("service")
        }
        cluster_arns: list[str] = []
        token = None
        while True:
            params = {"nextToken": token} if token else {}
            response = self._ecs.list_clusters(**params)
            cluster_arns.extend(response.get("clusterArns", []))
            token = response.get("nextToken")
            if not token:
                break

        services: dict[tuple[str, str], dict[str, Any]] = {}
        for cluster_arn in cluster_arns:
            cluster_name = cluster_arn.rsplit("/", 1)[-1]
            service_arns: list[str] = []
            token = None
            list_failed = False
            while True:
                params = {"cluster": cluster_arn}
                if token:
                    params["nextToken"] = token
                try:
                    response = self._ecs.list_services(**params)
                except Exception as exc:
                    self._record_collection_error(
                        f"ecs:{cluster_name}:list", exc
                    )
                    list_failed = True
                    break
                service_arns.extend(response.get("serviceArns", []))
                token = response.get("nextToken")
                if not token:
                    break

            for offset in range(0, len(service_arns), 10):
                batch = service_arns[offset : offset + 10]
                try:
                    response = self._ecs.describe_services(
                        cluster=cluster_arn, services=batch
                    )
                except Exception as exc:
                    self._record_collection_error(
                        f"ecs:{cluster_name}:batch:{offset // 10}", exc
                    )
                    for arn in batch:
                        service_name = arn.rsplit("/", 1)[-1]
                        key = (cluster_name, service_name)
                        if key in prior:
                            services[key] = self._mark_stale("ecs", prior[key])
                    continue
                for service in response.get("services", []):
                    service_name = service.get("serviceName", "unknown")
                    services[(cluster_name, service_name)] = self._mark_observed(
                        "ecs",
                        {
                            "cluster": cluster_name,
                            "service": service_name,
                            "desired": int(service.get("desiredCount", 0)),
                            "running": int(service.get("runningCount", 0)),
                            "pending": int(service.get("pendingCount", 0)),
                        },
                    )
                for failure in response.get("failures", []):
                    arn = failure.get("arn", "unknown")
                    service_name = arn.rsplit("/", 1)[-1]
                    self._record_collection_error(
                        f"ecs:{cluster_name}:{service_name}",
                        failure.get("reason", "describe failed"),
                    )
                    key = (cluster_name, service_name)
                    if key in prior:
                        services[key] = self._mark_stale("ecs", prior[key])
            if list_failed:
                for key, service in prior.items():
                    if key[0] == cluster_name and key not in services:
                        services[key] = self._mark_stale("ecs", service)
        return list(services.values())

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """Return collection failures; no CloudWatch log read is required."""

        return [
            f"AWS {service} inventory collection failed: {error}"
            for service, error in sorted(self._collection_errors.items())
        ]

    def run_health_checks(self) -> list[HealthCheck]:
        """Evaluate deterministic health and exposure checks over the snapshot."""

        checks: list[HealthCheck] = []
        for service, error in sorted(self._collection_errors.items()):
            checks.append(
                self._unknown(
                    f"aws_{_check_id(service)}_collection",
                    f"Unable to collect {service.upper()} inventory: {error}",
                    component="AWS Provider",
                    service=service,
                )
            )

        for cluster in self._snapshot.get("eks", []):
            name = cluster["name"]
            identifier = _check_id(name)
            cluster_metadata = {**cluster, "resource_name": cluster["name"]}
            cluster_metadata.pop("name", None)
            if cluster["status"] == "ACTIVE":
                checks.append(
                    self._ok(
                        f"eks_{identifier}_status",
                        f"EKS cluster {name} is ACTIVE",
                        component="Amazon EKS",
                        **cluster_metadata,
                    )
                )
            else:
                checks.append(
                    self._fail(
                        f"eks_{identifier}_status",
                        f"EKS cluster {name} is {cluster['status']}",
                        component="Amazon EKS",
                        **cluster_metadata,
                    )
                )
            if cluster.get("endpoint_public"):
                checks.append(
                    self._warn(
                        f"eks_{identifier}_public_endpoint",
                        f"EKS cluster {name} exposes a public API endpoint",
                        component="Amazon EKS",
                        **cluster_metadata,
                    )
                )

        for instance in self._snapshot.get("ec2", []):
            instance_id = instance["id"]
            identifier = _check_id(instance_id)
            state = instance["state"]
            instance_metadata = {**instance, "resource_name": instance["name"]}
            instance_metadata.pop("name", None)
            if state == "running":
                state_check = self._ok
            elif state in {"pending", "stopping", "shutting-down"}:
                state_check = self._warn
            else:
                state_check = self._fail
            checks.append(
                state_check(
                    f"ec2_{identifier}_state",
                    f"EC2 instance {instance['name']} ({instance_id}) is {state}",
                    component="Amazon EC2",
                    **instance_metadata,
                )
            )
            if state == "running":
                instance_status = instance.get("instance_status", "unknown")
                system_status = instance.get("system_status", "unknown")
                if "impaired" in {instance_status, system_status}:
                    health_check = self._fail
                elif instance_status == system_status == "ok":
                    health_check = self._ok
                else:
                    health_check = self._unknown
                checks.append(
                    health_check(
                        f"ec2_{identifier}_instance_health",
                        f"EC2 instance/system status is {instance_status}/{system_status}",
                        component="Amazon EC2",
                        **instance_metadata,
                    )
                )
            if instance.get("public_ip"):
                checks.append(
                    self._warn(
                        f"ec2_{identifier}_public_ip",
                        f"EC2 instance {instance['name']} has public IP {instance['public_ip']}",
                        component="Amazon EC2",
                        **instance_metadata,
                    )
                )

        for service in self._snapshot.get("ecs", []):
            cluster_name = service["cluster"]
            service_name = service["service"]
            identifier = f"{_check_id(cluster_name)}_{_check_id(service_name)}"
            desired = service["desired"]
            running = service["running"]
            if running == desired:
                checks.append(
                    self._ok(
                        f"ecs_{identifier}_capacity",
                        f"ECS service {cluster_name}/{service_name} is at desired capacity ({running}/{desired})",
                        component="Amazon ECS",
                        **service,
                    )
                )
            else:
                checks.append(
                    self._fail(
                        f"ecs_{identifier}_capacity",
                        f"ECS service {cluster_name}/{service_name} is below desired capacity ({running}/{desired}, {service['pending']} pending)",
                        component="Amazon ECS",
                        **service,
                    )
                )
        return checks

    def get_component_inventory(self) -> list[Component]:
        """Expose the current normalized snapshot to the UI."""

        components: list[Component] = []
        for cluster in self._snapshot.get("eks", []):
            key = self._resource_key("eks", cluster)
            components.append(
                Component(
                    name=cluster["name"],
                    type="eks_cluster",
                    category="Amazon EKS",
                    description=f"Kubernetes {cluster['version']} cluster",
                    metadata={
                        **cluster,
                        "last_seen": self._resource_observed_at.get(key),
                        "stale": key in self._stale_resources,
                    },
                )
            )
        for instance in self._snapshot.get("ec2", []):
            key = self._resource_key("ec2", instance)
            components.append(
                Component(
                    name=instance["name"],
                    type="ec2_instance",
                    category="Amazon EC2",
                    description=f"Instance {instance['id']}",
                    metadata={
                        **instance,
                        "status": instance["state"],
                        "last_seen": self._resource_observed_at.get(key),
                        "stale": key in self._stale_resources,
                    },
                )
            )
        for service in self._snapshot.get("ecs", []):
            key = self._resource_key("ecs", service)
            status = (
                "healthy"
                if service["running"] == service["desired"]
                else "degraded"
            )
            components.append(
                Component(
                    name=f"{service['cluster']}/{service['service']}",
                    type="ecs_service",
                    category="Amazon ECS",
                    description=f"{service['running']}/{service['desired']} tasks running",
                    metadata={
                        **service,
                        "status": status,
                        "last_seen": self._resource_observed_at.get(key),
                        "stale": key in self._stale_resources,
                    },
                )
            )
        return components

    def describe_architecture(self) -> str:
        return (
            "Read-only AWS infrastructure estate containing Amazon EKS clusters, "
            "EC2 instances, and ECS services. Findings are derived from AWS "
            "describe/list responses and Ollama is used only for explanation."
        )
