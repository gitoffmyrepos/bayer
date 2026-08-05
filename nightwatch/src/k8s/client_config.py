"""
Kubernetes client config loader with in-cluster bearer-token normalization.
==========================================================================

Why this module exists
----------------------
Some `kubernetes` Python client builds (observed with client v36.0.0, which a
floated `kubernetes>=29` requirement resolved to) ship an `incluster_config`
loader that is out of sync with `Configuration.auth_settings()`:

  * `incluster_config` writes the service-account token under
    ``configuration.api_key['authorization']`` with a *lowercase* ``"bearer "``
    scheme.
  * ``Configuration.auth_settings()`` only emits an ``Authorization`` header when
    the token is stored under ``configuration.api_key['BearerToken']``.

Because the keys don't match, ``auth_settings()`` returns ``{}`` and the client
sends requests with **no Authorization header at all**. The API server then
treats the caller as ``system:anonymous`` and returns HTTP 403 — even though the
mounted ServiceAccount token and its RBAC are perfectly valid.

This module loads cluster config (in-cluster first, kubeconfig fallback) and
normalizes the bearer token onto the ``BearerToken`` api_key with a proper
``Bearer`` prefix, wrapping the token-refresh hook so SA-token rotation stays
normalized. After calling :func:`load_k8s_config`, plain ``client.CoreV1Api()``
/ ``client.AppsV1Api()`` / ``watch.Watch()`` authenticate correctly.
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "configure_incluster_bearer",
    "load_k8s_config",
    "normalize_incluster_bearer",
]


def normalize_incluster_bearer(configuration) -> None:
    """
    Ensure ``configuration.api_key['BearerToken']`` carries the SA token with a
    capitalized ``Bearer`` prefix so ``auth_settings()`` actually emits the
    Authorization header.

    Idempotent and safe to call repeatedly (e.g. from a refresh hook).
    """
    api_key = getattr(configuration, "api_key", None)
    if not api_key:
        return
    # The loader refresh hook updates `authorization`; prefer that fresh value
    # over a previously normalized BearerToken during ServiceAccount rotation.
    raw = api_key.get("authorization") or api_key.get("BearerToken")
    if not raw:
        return
    # Strip any existing scheme prefix ('bearer ' / 'Bearer ').
    token = raw.split(" ", 1)[1] if raw[:7].lower() == "bearer " else raw
    configuration.api_key["BearerToken"] = token
    configuration.api_key_prefix["BearerToken"] = "Bearer"


def configure_incluster_bearer(configuration) -> None:
    """Normalize the current token and keep rotated tokens normalized."""

    normalize_incluster_bearer(configuration)
    original_hook = getattr(configuration, "refresh_api_key_hook", None)

    if getattr(original_hook, "_nightwatch_normalizes_bearer", False):
        return

    def _refresh_and_normalize(refreshed_configuration) -> None:
        if original_hook is not None:
            original_hook(refreshed_configuration)
        normalize_incluster_bearer(refreshed_configuration)
        # The Kubernetes in-cluster loader reinstalls its own refresh hook each
        # time it reloads the projected token. Keep our wrapper authoritative.
        refreshed_configuration.refresh_api_key_hook = _refresh_and_normalize

    _refresh_and_normalize._nightwatch_normalizes_bearer = True
    configuration.refresh_api_key_hook = _refresh_and_normalize


def load_k8s_config(kubeconfig_path: Optional[str] = None) -> bool:
    """
    Load Kubernetes client configuration and normalize in-cluster auth.

    Order:
      1. explicit ``kubeconfig_path`` (if provided)
      2. in-cluster ServiceAccount (when running inside a pod)
      3. ambient kubeconfig (``~/.kube/config``)

    Returns ``True`` on success, ``False`` if no config could be loaded.
    Raises only ``ImportError`` if the ``kubernetes`` package is missing.
    """
    from kubernetes import client, config as k8s_config  # type: ignore

    in_cluster = False
    if kubeconfig_path:
        k8s_config.load_kube_config(config_file=kubeconfig_path)
    else:
        try:
            k8s_config.load_incluster_config()
            in_cluster = True
        except Exception:  # noqa: BLE001 — not in a cluster; fall back
            k8s_config.load_kube_config()

    if not in_cluster:
        return True

    # In-cluster: bridge the api_key key mismatch so requests are authenticated
    # instead of going out as system:anonymous.
    cfg = client.Configuration.get_default_copy()
    configure_incluster_bearer(cfg)
    client.Configuration.set_default(cfg)
    return True
