from datetime import datetime, timezone
from types import SimpleNamespace

from src.adapters.base_adapter import CheckStatus
from src.adapters.kubernetes_clusters import adapter as adapter_module
from src.adapters.kubernetes_clusters.adapter import (
    KubernetesClustersAdapter,
    _cronjob_records,
    _current_pod_failure_reasons,
)


class ClosingClient:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def close(self):
        self.closed = True


def _condition(condition_type, status="True", reason=None, message=None):
    return SimpleNamespace(
        type=condition_type,
        status=status,
        reason=reason,
        message=message,
    )


def _job(name, created, cronjob, *, conditions=None, active=0, succeeded=0):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace="operations",
            creation_timestamp=datetime.fromisoformat(created),
            owner_references=[SimpleNamespace(kind="CronJob", name=cronjob)],
        ),
        status=SimpleNamespace(
            conditions=conditions or [],
            active=active,
            succeeded=succeeded,
        ),
    )


def _cronjob(
    name="nightly-check",
    *,
    suspended=False,
    last_schedule_time=None,
    last_successful_time=None,
):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace="operations"),
        spec=SimpleNamespace(schedule="0 0 * * *", suspend=suspended),
        status=SimpleNamespace(
            last_schedule_time=last_schedule_time,
            last_successful_time=last_successful_time,
        ),
    )


def _pod(phase, *, waiting_reason=None, scheduled_condition=None, deleting=False):
    waiting = (
        SimpleNamespace(reason=waiting_reason) if waiting_reason else None
    )
    container_statuses = [
        SimpleNamespace(state=SimpleNamespace(waiting=waiting))
    ]
    conditions = [scheduled_condition] if scheduled_condition else []
    return SimpleNamespace(
        metadata=SimpleNamespace(
            deletion_timestamp=(
                datetime.now(timezone.utc) if deleting else None
            )
        ),
        status=SimpleNamespace(
            phase=phase,
            init_container_statuses=[],
            container_statuses=container_statuses,
            conditions=conditions,
        ),
    )


def test_terminal_pods_are_history_not_active_health_issues():
    assert _current_pod_failure_reasons(_pod("Failed")) == []
    assert _current_pod_failure_reasons(_pod("Succeeded")) == []
    assert _current_pod_failure_reasons(
        _pod("Running", waiting_reason="CrashLoopBackOff", deleting=True)
    ) == []


def test_current_container_and_scheduling_failures_remain_actionable():
    image_pull = _pod("Pending", waiting_reason="ImagePullBackOff")
    unschedulable = _pod(
        "Pending",
        scheduled_condition=_condition(
            "PodScheduled", "False", reason="Unschedulable"
        ),
    )
    unknown = _pod("Unknown")

    assert _current_pod_failure_reasons(image_pull) == ["ImagePullBackOff"]
    assert _current_pod_failure_reasons(unschedulable) == ["Unschedulable"]
    assert _current_pod_failure_reasons(unknown) == ["Unknown"]


def test_cronjob_health_uses_only_the_latest_owned_job():
    jobs = [
        _job(
            "nightly-check-old",
            "2026-07-29T00:00:00+00:00",
            "nightly-check",
            conditions=[
                _condition(
                    "Failed",
                    reason="BackoffLimitExceeded",
                    message="old failure",
                )
            ],
        ),
        _job(
            "nightly-check-current",
            "2026-08-05T00:00:00+00:00",
            "nightly-check",
            conditions=[_condition("Complete", reason="CompletionsReached")],
            succeeded=1,
        ),
    ]

    records = _cronjob_records(
        "production", [_cronjob()], jobs, "2026-08-05T00:01:00+00:00"
    )

    assert len(records) == 1
    assert records[0]["latest_job"] == "nightly-check-current"
    assert records[0]["latest_job_status"] == "complete"
    assert records[0]["status"] == "healthy"


def test_latest_failed_cronjob_is_reported_once_at_controller_level():
    jobs = [
        _job(
            "nightly-check-current",
            "2026-08-05T00:00:00+00:00",
            "nightly-check",
            conditions=[
                _condition(
                    "Failed",
                    reason="BackoffLimitExceeded",
                    message="latest run exhausted retries",
                )
            ],
        )
    ]

    records = _cronjob_records(
        "production", [_cronjob()], jobs, "2026-08-05T00:01:00+00:00"
    )

    assert len(records) == 1
    assert records[0]["status"] == "unhealthy"
    assert records[0]["reason"] == "BackoffLimitExceeded"
    assert records[0]["message"] == "latest run exhausted retries"


def test_suspended_cronjob_does_not_reactivate_an_old_failed_job():
    failed_job = _job(
        "nightly-check-old",
        "2026-07-29T00:00:00+00:00",
        "nightly-check",
        conditions=[_condition("Failed", reason="BackoffLimitExceeded")],
    )

    records = _cronjob_records(
        "production",
        [_cronjob(suspended=True)],
        [failed_job],
        "2026-08-05T00:01:00+00:00",
    )

    assert records[0]["status"] == "healthy"
    assert records[0]["latest_job_status"] == "suspended"


def test_cronjob_status_survives_zero_job_history_retention():
    completed_at = datetime.fromisoformat("2026-08-05T00:00:00+00:00")
    cronjob = _cronjob(
        last_schedule_time=completed_at,
        last_successful_time=completed_at,
    )

    records = _cronjob_records(
        "production", [cronjob], [], "2026-08-05T00:01:00+00:00"
    )

    assert records[0]["status"] == "healthy"
    assert records[0]["latest_job_status"] == "complete"
    assert records[0]["reason"] == "LastScheduledRunSucceeded"


def test_cronjob_evidence_builds_health_check_without_argument_collisions():
    adapter = KubernetesClustersAdapter({})
    adapter._snapshot = {
        "clusters": [],
        "nodes": [],
        "deployments": [],
        "pods": [],
        "cronjobs": [
            {
                "cluster": "production",
                "namespace": "operations",
                "name": "nightly-check",
                "schedule": "0 0 * * *",
                "suspended": False,
                "latest_job": "nightly-check-1",
                "latest_job_status": "failed",
                "reason": "BackoffLimitExceeded",
                "message": "Latest owned Job failed",
                "last_run_at": "2026-08-05T00:00:00+00:00",
                "last_scheduled_at": "2026-08-05T00:00:00+00:00",
                "last_successful_at": None,
                "status": "unhealthy",
                "observed_at": "2026-08-05T00:01:00+00:00",
            }
        ],
    }

    checks = adapter.run_health_checks()

    assert len(checks) == 1
    assert checks[0].status == CheckStatus.FAIL
    assert "Latest owned Job failed" in checks[0].message
    assert "message" not in checks[0].metadata


def test_discovers_and_connects_every_kubeconfig_context(monkeypatch, tmp_path):
    kubeconfig = tmp_path / "clusters.yaml"
    kubeconfig.write_text("apiVersion: v1\nkind: Config\n")
    contexts = [{"name": "development"}, {"name": "production"}]
    clients = []

    config_api = SimpleNamespace()
    monkeypatch.setattr(adapter_module, "kubernetes_config", config_api)
    monkeypatch.setattr(adapter_module, "client", SimpleNamespace())

    config_api.list_kube_config_contexts = lambda config_file: (
        contexts,
        contexts[0],
    )

    def build_client(config_file, context):
        assert config_file == str(kubeconfig)
        result = ClosingClient(context)
        clients.append(result)
        return result

    config_api.new_client_from_config = build_client
    adapter = KubernetesClustersAdapter(
        {
            "discover_kubeconfig_contexts": True,
            "kubeconfig_path": str(kubeconfig),
        }
    )

    adapter.initialize()

    assert set(adapter._connections) == {"development", "production"}
    assert [item.context for item in clients] == ["development", "production"]
    adapter.cleanup()
    assert all(item.closed for item in clients)


def test_health_checks_derive_only_from_collected_cluster_evidence():
    adapter = KubernetesClustersAdapter(
        {"clusters": [{"name": "production", "in_cluster": True}]}
    )
    adapter._snapshot = {
        "clusters": [
            {
                "name": "production",
                "status": "healthy",
                "version": "v1.31.0",
                "observed_at": "2026-08-04T12:00:00+00:00",
                "stale": False,
            }
        ],
        "nodes": [
            {
                "cluster": "production",
                "name": "worker-01",
                "ready": "False",
                "status": "unhealthy",
                "observed_at": "2026-08-04T12:00:00+00:00",
            }
        ],
        "deployments": [
            {
                "cluster": "production",
                "namespace": "payments",
                "name": "api",
                "desired": 3,
                "ready": 2,
                "status": "degraded",
                "observed_at": "2026-08-04T12:00:00+00:00",
            }
        ],
        "pods": [
            {
                "cluster": "production",
                "namespace": "payments",
                "name": "api-0",
                "phase": "Running",
                "reasons": ["CrashLoopBackOff"],
                "status": "unhealthy",
                "observed_at": "2026-08-04T12:00:00+00:00",
            }
        ],
    }

    checks = adapter.run_health_checks()

    assert any(item.status == CheckStatus.OK for item in checks)
    assert sum(item.status == CheckStatus.FAIL for item in checks) == 3


def test_missing_cluster_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(adapter_module, "client", SimpleNamespace())
    monkeypatch.setattr(adapter_module, "kubernetes_config", SimpleNamespace())
    adapter = KubernetesClustersAdapter({})

    try:
        adapter.initialize()
    except ValueError as error:
        assert "No Kubernetes clusters configured" in str(error)
    else:
        raise AssertionError("adapter must reject an empty cluster registry")


def test_condition_status_reads_ready_condition():
    from src.adapters.kubernetes_clusters.adapter import _condition_status

    conditions = [SimpleNamespace(type="Ready", status="True")]
    assert _condition_status(conditions, "Ready") == "True"


def test_one_invalid_connection_does_not_hide_other_configured_clusters(
    monkeypatch, tmp_path
):
    valid_config = tmp_path / "valid.yaml"
    valid_config.write_text("apiVersion: v1\nkind: Config\n")
    config_api = SimpleNamespace(
        new_client_from_config=lambda config_file, context: ClosingClient(context)
    )
    monkeypatch.setattr(adapter_module, "kubernetes_config", config_api)
    monkeypatch.setattr(adapter_module, "client", SimpleNamespace())
    adapter = KubernetesClustersAdapter(
        {
            "clusters": [
                {
                    "name": "reachable",
                    "kubeconfig_path": str(valid_config),
                    "context": "observer",
                },
                {
                    "name": "missing",
                    "kubeconfig_path": str(tmp_path / "missing.yaml"),
                },
            ]
        }
    )

    adapter.initialize()

    assert set(adapter._connections) == {"reachable"}
    assert "missing" in adapter._connection_errors
