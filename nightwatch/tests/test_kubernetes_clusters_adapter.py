from types import SimpleNamespace

from src.adapters.base_adapter import CheckStatus
from src.adapters.kubernetes_clusters import adapter as adapter_module
from src.adapters.kubernetes_clusters.adapter import KubernetesClustersAdapter


class ClosingClient:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def close(self):
        self.closed = True


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
