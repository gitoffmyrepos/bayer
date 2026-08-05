import sys
from types import SimpleNamespace

from src.adapters.forextrader import collectors


def _pod(name, phase, *, ready=False, restarts=0, deleting=False):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            deletion_timestamp=object() if deleting else None,
        ),
        spec=SimpleNamespace(
            containers=[SimpleNamespace(name="service")],
            node_name="worker-01",
        ),
        status=SimpleNamespace(
            phase=phase,
            container_statuses=[
                SimpleNamespace(ready=ready, restart_count=restarts)
            ],
        ),
    )


def test_forextrader_pod_snapshot_excludes_terminal_history(monkeypatch):
    pods = [
        _pod("api-current", "Running", ready=True),
        _pod("worker-image-pull", "Pending"),
        _pod("old-eviction", "Failed"),
        _pod("old-job-success", "Succeeded"),
        _pod("terminating-api", "Running", deleting=True),
    ]

    core_api = SimpleNamespace(
        list_namespaced_pod=lambda namespace: SimpleNamespace(items=pods)
    )
    fake_kubernetes = SimpleNamespace(
        client=SimpleNamespace(CoreV1Api=lambda: core_api)
    )
    monkeypatch.setitem(sys.modules, "kubernetes", fake_kubernetes)
    monkeypatch.setattr(collectors, "load_k8s_config", lambda _path: None)

    result = collectors.collect_k8s_pod_status("prod-forex")

    assert result["total"] == 2
    assert result["running"] == 1
    assert result["pending"] == 1
    assert result["failed"] == 0
    assert {pod["name"] for pod in result["pods"]} == {
        "api-current",
        "worker-image-pull",
    }
