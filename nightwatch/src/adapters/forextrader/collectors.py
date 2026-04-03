"""
ForexTrader Platform Collectors
=================================
Low-level collectors for the ForexTrader FX trading platform.

Collects:
  - Kubernetes pod status (prod-forex namespace)
  - OANDA account balance and open positions
  - API gateway health endpoint
  - Prediction counts and ML pipeline status
  - Jenkins build status

Author: Nova ⚡ | Nightwatch Platform
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger("nightwatch.forextrader.collectors")


# ─── Kubernetes ───────────────────────────────────────────────────────────────

def collect_k8s_pod_status(k8s_namespace: str, kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect pod health from a Kubernetes namespace.

    Returns:
        {
            "total": int,
            "running": int,
            "failed": int,
            "pending": int,
            "pods": [{"name": str, "phase": str, "ready": bool, "restarts": int}]
        }
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace=k8s_namespace)

        pod_data = []
        for pod in pods.items:
            containers_ready = 0
            containers_total = len(pod.spec.containers)
            total_restarts = 0

            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    if cs.ready:
                        containers_ready += 1
                    total_restarts += cs.restart_count

            pod_data.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase or "Unknown",
                "ready": f"{containers_ready}/{containers_total}",
                "restarts": total_restarts,
                "node": pod.spec.node_name,
            })

        phases = [p["phase"] for p in pod_data]
        return {
            "namespace": k8s_namespace,
            "total": len(pod_data),
            "running": phases.count("Running"),
            "pending": phases.count("Pending"),
            "failed": phases.count("Failed"),
            "unknown": sum(1 for p in phases if p not in ("Running", "Pending", "Succeeded", "Failed")),
            "pods": pod_data,
        }

    except ImportError:
        log.warning("kubernetes_not_installed", hint="pip install kubernetes")
        return {"error": "kubernetes package not installed"}
    except Exception as e:
        log.error("k8s_collect_error", namespace=k8s_namespace, error=str(e))
        return {"error": str(e)}


def collect_k8s_all_deployments(k8s_namespace: str,
                                kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect status of ALL deployments in a namespace.
    Returns per-deployment ready/desired/restarts so we can build a full component map.
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        deploys = apps_v1.list_namespaced_deployment(namespace=k8s_namespace)
        result = {}
        for d in deploys.items:
            name = d.metadata.name
            spec_replicas = d.spec.replicas or 0
            ready = d.status.ready_replicas or 0
            available = d.status.available_replicas or 0
            if spec_replicas == 0:
                status = "scaled_down"
            elif ready >= spec_replicas:
                status = "healthy"
            elif ready > 0:
                status = "degraded"
            else:
                status = "unhealthy"
            result[name] = {
                "desired": spec_replicas,
                "ready": ready,
                "available": available,
                "status": status,
            }
        return result
    except Exception as e:
        log.error("collect_all_deployments_error", error=str(e))
        return {"error": str(e)}


def collect_k8s_nodes(kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect Kubernetes node health: Ready status, CPU/memory pressure, disk pressure.
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        v1 = client.CoreV1Api()
        nodes = v1.list_node()
        node_data = []
        ready_count = 0
        for node in nodes.items:
            name = node.metadata.name
            roles = []
            for label in node.metadata.labels or {}:
                if label.startswith("node-role.kubernetes.io/"):
                    roles.append(label.split("/", 1)[1])
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            is_ready = conditions.get("Ready") == "True"
            if is_ready:
                ready_count += 1
            node_data.append({
                "name": name,
                "ready": is_ready,
                "roles": roles,
                "memory_pressure": conditions.get("MemoryPressure") == "True",
                "disk_pressure": conditions.get("DiskPressure") == "True",
                "pid_pressure": conditions.get("PIDPressure") == "True",
                "cpu": node.status.capacity.get("cpu") if node.status.capacity else None,
                "memory": node.status.capacity.get("memory") if node.status.capacity else None,
            })
        return {
            "total": len(node_data),
            "ready": ready_count,
            "not_ready": len(node_data) - ready_count,
            "nodes": node_data,
        }
    except Exception as e:
        log.error("collect_k8s_nodes_error", error=str(e))
        return {"error": str(e)}


def collect_k8s_statefulsets(k8s_namespace: str, names: list[str],
                             kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect StatefulSet health (databases, message brokers).
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        result = {}

        # Try exact names first, fall back to listing all and matching prefixes
        all_sts = apps_v1.list_namespaced_stateful_set(namespace=k8s_namespace)
        sts_map = {s.metadata.name: s for s in all_sts.items}

        for name in names:
            # Try exact match, then prefix match
            sts = sts_map.get(name)
            if not sts:
                for k, v in sts_map.items():
                    if k.startswith(name) or name in k:
                        sts = v
                        name = k
                        break

            if not sts:
                result[name] = {"error": "not found"}
                continue

            desired = sts.spec.replicas or 1
            ready = sts.status.ready_replicas or 0
            if ready >= desired:
                status = "healthy"
            elif ready > 0:
                status = "degraded"
            else:
                status = "unhealthy"
            result[name] = {
                "desired": desired,
                "ready": ready,
                "status": status,
                "current_revision": sts.status.current_revision,
            }
        return result
    except Exception as e:
        log.error("collect_k8s_statefulsets_error", error=str(e))
        return {"error": str(e)}


def collect_k8s_namespace_summary(namespaces: list[str],
                                  kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect pod counts and failure summary for multiple namespaces.
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        v1 = client.CoreV1Api()
        result = {}
        for ns in namespaces:
            try:
                pods = v1.list_namespaced_pod(namespace=ns)
                total = len(pods.items)
                running = sum(1 for p in pods.items if p.status.phase == "Running")
                failed = sum(1 for p in pods.items if p.status.phase == "Failed")
                crashlooping = sum(
                    1 for p in pods.items
                    if p.status.container_statuses and
                    any(cs.restart_count >= 5 for cs in p.status.container_statuses)
                )
                result[ns] = {"total": total, "running": running,
                              "failed": failed, "crashlooping": crashlooping}
            except Exception as e:
                result[ns] = {"error": str(e)}
        return result
    except Exception as e:
        log.error("collect_namespace_summary_error", error=str(e))
        return {"error": str(e)}


def collect_k8s_deployment_status(k8s_namespace: str, deployments: list[str],
                                   kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect deployment health (desired vs available replicas).
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        result = {}

        for deploy_name in deployments:
            try:
                deploy = apps_v1.read_namespaced_deployment(name=deploy_name, namespace=k8s_namespace)
                status = deploy.status
                result[deploy_name] = {
                    "desired": deploy.spec.replicas or 0,
                    "ready": status.ready_replicas or 0,
                    "available": status.available_replicas or 0,
                    "updated": status.updated_replicas or 0,
                }
            except Exception as e:
                result[deploy_name] = {"error": str(e)}

        return result

    except Exception as e:
        log.error("k8s_deployment_error", error=str(e))
        return {"error": str(e)}


def collect_k8s_cnpg_clusters(namespace: str, names: list[str],
                              kubeconfig_path: Optional[str] = None) -> dict:
    """
    Collect CloudNativePG cluster health (TimescaleDB, etc.).
    Uses the custom objects API for postgresql.cnpg.io/v1/clusters.
    """
    try:
        from kubernetes import client, config as k8s_config

        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

        custom_api = client.CustomObjectsApi()
        try:
            resp = custom_api.list_namespaced_custom_object(
                group="postgresql.cnpg.io",
                version="v1",
                namespace=namespace,
                plural="clusters",
            )
            items = resp.get("items", [])
        except Exception:
            return {}

        # Build lookup by name
        cluster_map = {c["metadata"]["name"]: c for c in items}

        result = {}
        for name in names:
            cluster = cluster_map.get(name)
            if not cluster:
                result[name] = {"error": "not found"}
                continue

            status = cluster.get("status", {})
            phase = status.get("phase", "Unknown")
            ready = int(status.get("readyInstances", 0))
            total = int(status.get("instances", 0))

            # Phase contains error text for CNPG error states
            phase_lower = phase.lower()
            if "error" in phase_lower or "fail" in phase_lower:
                health = "degraded"
            elif ready >= total > 0:
                health = "healthy"
            elif ready > 0:
                health = "degraded"
            else:
                health = "unhealthy"

            result[name] = {
                "phase": phase,
                "ready": ready,
                "desired": total,
                "status": health,
            }
        return result
    except Exception as e:
        log.error("collect_cnpg_error", error=str(e))
        return {"error": str(e)}


# ─── OANDA API ────────────────────────────────────────────────────────────────

def collect_oanda_account_health(
    oanda_api_url: str,
    account_id: str,
    api_key: str,
) -> dict:
    """
    Collect OANDA account balance, margin, and open positions.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=15, headers=headers) as client:
            # Account summary
            resp = client.get(f"{oanda_api_url}/v3/accounts/{account_id}/summary")
            resp.raise_for_status()
            account = resp.json().get("account", {})

            # Open trades
            trades_resp = client.get(f"{oanda_api_url}/v3/accounts/{account_id}/openTrades")
            trades_resp.raise_for_status()
            open_trades = trades_resp.json().get("trades", [])

            return {
                "balance": float(account.get("balance", 0)),
                "nav": float(account.get("NAV", 0)),
                "unrealized_pl": float(account.get("unrealizedPL", 0)),
                "margin_used": float(account.get("marginUsed", 0)),
                "margin_available": float(account.get("marginAvailable", 0)),
                "open_trade_count": len(open_trades),
                "open_trades": [
                    {
                        "instrument": t.get("instrument"),
                        "units": t.get("currentUnits"),
                        "unrealized_pl": float(t.get("unrealizedPL", 0)),
                    }
                    for t in open_trades[:10]
                ],
            }

    except httpx.HTTPError as e:
        log.error("oanda_collect_error", error=str(e))
        return {"error": str(e)}


# ─── API Health ───────────────────────────────────────────────────────────────

def collect_api_health(endpoints: list[dict]) -> dict:
    """
    Check health of HTTP endpoints.

    Args:
        endpoints: [{"name": "ForexTrader API", "url": "https://forex.strategybase.io/api/health", "expected_status": 200}]

    Returns:
        {
            "<name>": {"status": "ok"|"fail", "response_time_ms": float, "status_code": int}
        }
    """
    result = {}
    for endpoint in endpoints:
        name = endpoint.get("name", endpoint.get("url"))
        url = endpoint.get("url")
        expected_status = endpoint.get("expected_status", 200)

        try:
            with httpx.Client(timeout=10) as client:
                start = datetime.now(timezone.utc)
                resp = client.get(url)
                elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                result[name] = {
                    "url": url,
                    "status": "ok" if resp.status_code == expected_status else "fail",
                    "status_code": resp.status_code,
                    "response_time_ms": round(elapsed_ms, 1),
                }
        except httpx.TimeoutException:
            result[name] = {"url": url, "status": "fail", "error": "timeout"}
        except Exception as e:
            result[name] = {"url": url, "status": "fail", "error": str(e)}

    return result


# ─── Jenkins ──────────────────────────────────────────────────────────────────

def collect_jenkins_build_status(
    jenkins_url: str,
    username: str,
    api_token: str,
    jobs: list[str],
) -> dict:
    """
    Collect latest build status for Jenkins jobs.
    """
    result = {}
    auth = (username, api_token)

    for job_name in jobs:
        # Handle nested jobs (e.g., "ForexTrader/tier-0-ml-framework-base/master")
        job_path = job_name.replace("/", "/job/")
        url = f"{jenkins_url}/job/{job_path}/lastBuild/api/json"

        try:
            with httpx.Client(timeout=15, auth=auth) as client:
                resp = client.get(url)
                resp.raise_for_status()
                build = resp.json()

                result[job_name] = {
                    "result": build.get("result"),  # SUCCESS, FAILURE, UNSTABLE, ABORTED, None (in progress)
                    "building": build.get("building", False),
                    "number": build.get("number"),
                    "duration_ms": build.get("duration"),
                    "timestamp": build.get("timestamp"),
                    "url": build.get("url"),
                }
        except Exception as e:
            log.error("jenkins_collect_error", job=job_name, error=str(e))
            result[job_name] = {"error": str(e)}

    return result
