"""
Multi-repo router for K8s events → GitHub issues.

Rules are YAML, loaded from a configmap-mounted file (with sensible
built-in defaults if the file is missing).

Rule schema (one entry of `routing_rules`):
  - match:
      namespace:        "argocd"               # exact match
      namespace_regex:  "^(cilium|gpu-.*)$"    # regex match
      kind:             "Pod"                  # involvedObject.kind
      name:             "forextrader-foo"      # exact match
      name_prefix:      "forextrader-"
      name_regex:       "^foo-.*$"
      reason:           "CrashLoopBackOff"
    repo:   {owner: "gitoffmyrepos", name: "FX"}
    labels: ["microservice"]

A rule matches if **all specified keys** in its `match` block match.
First matching rule wins. If nothing matches, `default` is used.

Built-in defaults (used when YAML is unavailable):
  - argocd / kube-system → sb-gitops or sb-dev-infra
  - prod-forex with forextrader- prefix → FX
  - everything else → FX with `needs-routing` label
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog

log = structlog.get_logger("nightwatch.k8s.routing")

__all__ = ["RoutingDecision", "RepoRouter", "DEFAULT_ROUTING_CONFIG"]


@dataclass
class RoutingDecision:
    owner: str
    name: str
    extra_labels: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


DEFAULT_ROUTING_CONFIG: dict = {
    "routing_rules": [
        {
            "match": {"kind": "Application", "namespace": "argocd"},
            "repo": {"owner": "gitoffmyrepos", "name": "sb-gitops"},
            "labels": ["gitops", "argocd"],
        },
        {
            "match": {"namespace": "argocd"},
            "repo": {"owner": "gitoffmyrepos", "name": "sb-gitops"},
            "labels": ["argocd"],
        },
        {
            "match": {
                "namespace_regex": r"^(cilium|gpu-operator|kube-system|metallb-system|cert-manager|ingress-nginx|memory-stack|monitoring|nightwatch|nvidia)$"
            },
            "repo": {"owner": "gitoffmyrepos", "name": "sb-dev-infra"},
            "labels": ["infra"],
        },
        {
            "match": {"namespace": "prod-forex", "name_prefix": "forextrader-"},
            "repo": {"owner": "gitoffmyrepos", "name": "FX"},
            "labels": ["microservice"],
        },
        {
            "match": {"namespace": "prod-forex"},
            "repo": {"owner": "gitoffmyrepos", "name": "FX"},
            "labels": ["fx-platform"],
        },
    ],
    "default": {
        "repo": {"owner": "gitoffmyrepos", "name": "FX"},
        "labels": ["needs-routing"],
    },
}


class _CompiledRule:
    """Precompiled match predicates for one rule."""

    __slots__ = (
        "namespace",
        "namespace_regex",
        "kind",
        "name",
        "name_prefix",
        "name_regex",
        "reason",
        "owner",
        "repo_name",
        "labels",
    )

    def __init__(self, rule: dict):
        match = rule.get("match", {}) or {}
        self.namespace: Optional[str] = match.get("namespace")
        self.kind: Optional[str] = match.get("kind")
        self.name: Optional[str] = match.get("name")
        self.name_prefix: Optional[str] = match.get("name_prefix")
        self.reason: Optional[str] = match.get("reason")

        self.namespace_regex: Optional[re.Pattern] = (
            re.compile(match["namespace_regex"]) if match.get("namespace_regex") else None
        )
        self.name_regex: Optional[re.Pattern] = (
            re.compile(match["name_regex"]) if match.get("name_regex") else None
        )

        repo = rule.get("repo", {}) or {}
        self.owner: str = repo.get("owner") or ""
        self.repo_name: str = repo.get("name") or ""
        self.labels: list[str] = list(rule.get("labels") or [])

    def matches(self, namespace: str, kind: str, name: str, reason: str) -> bool:
        if self.namespace is not None and self.namespace != namespace:
            return False
        if self.namespace_regex is not None and not self.namespace_regex.search(namespace or ""):
            return False
        if self.kind is not None and self.kind != kind:
            return False
        if self.name is not None and self.name != name:
            return False
        if self.name_prefix is not None and not (name or "").startswith(self.name_prefix):
            return False
        if self.name_regex is not None and not self.name_regex.search(name or ""):
            return False
        if self.reason is not None and self.reason != reason:
            return False
        return True


class RepoRouter:
    """
    Routes a K8s event to a (owner, name) GitHub repo by first-match-wins.

    Construction:
        router = RepoRouter(config_dict)           # in-memory config
        router = RepoRouter.from_yaml(path)        # loads + falls back to defaults

    Lookup:
        decision = router.route(namespace="prod-forex",
                                kind="Pod",
                                name="forextrader-trade-executor-abc",
                                reason="CrashLoopBackOff")
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or DEFAULT_ROUTING_CONFIG
        rules = cfg.get("routing_rules") or []
        self._rules: list[_CompiledRule] = []
        for i, r in enumerate(rules):
            try:
                cr = _CompiledRule(r)
                if not cr.owner or not cr.repo_name:
                    log.warning("routing_rule_missing_repo", index=i, rule=r)
                    continue
                self._rules.append(cr)
            except re.error as e:
                log.warning("routing_rule_bad_regex", index=i, error=str(e), rule=r)

        default_cfg = cfg.get("default") or DEFAULT_ROUTING_CONFIG["default"]
        default_repo = default_cfg.get("repo") or {}
        self._default = RoutingDecision(
            owner=default_repo.get("owner") or "gitoffmyrepos",
            name=default_repo.get("name") or "FX",
            extra_labels=list(default_cfg.get("labels") or ["needs-routing"]),
        )
        log.info(
            "router_initialized",
            rules=len(self._rules),
            default_repo=f"{self._default.owner}/{self._default.name}",
        )

    @classmethod
    def from_yaml(cls, path: str) -> "RepoRouter":
        try:
            import yaml  # local import — yaml already in requirements
        except ImportError:
            log.warning("yaml_unavailable_using_defaults", path=path)
            return cls(DEFAULT_ROUTING_CONFIG)
        p = Path(path)
        if not p.exists():
            log.info("routing_yaml_missing_using_defaults", path=str(p))
            return cls(DEFAULT_ROUTING_CONFIG)
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cls(cfg)
        except (OSError, yaml.YAMLError) as e:
            log.warning("routing_yaml_load_failed_using_defaults", path=str(p), error=str(e))
            return cls(DEFAULT_ROUTING_CONFIG)

    def route(
        self,
        namespace: str,
        kind: str,
        name: str,
        reason: str,
    ) -> RoutingDecision:
        for cr in self._rules:
            if cr.matches(namespace=namespace, kind=kind, name=name, reason=reason):
                return RoutingDecision(
                    owner=cr.owner, name=cr.repo_name, extra_labels=list(cr.labels)
                )
        return RoutingDecision(
            owner=self._default.owner,
            name=self._default.name,
            extra_labels=list(self._default.extra_labels),
        )

    def all_repos(self) -> set[tuple[str, str]]:
        """All (owner, name) pairs reachable via this router."""
        out: set[tuple[str, str]] = {(self._default.owner, self._default.name)}
        for cr in self._rules:
            out.add((cr.owner, cr.repo_name))
        return out

    @property
    def rule_count(self) -> int:
        return len(self._rules)
