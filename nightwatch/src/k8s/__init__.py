"""
Nightwatch K8s Event → GitHub Issues Integration
=================================================
Watches Kubernetes Warning events, dedups via fingerprint, routes to repos,
creates GitHub issues with LLM-authored bodies, escalates priority over time.

Modules:
  - fingerprint:   Deterministic SHA-256 fingerprint for dedup
  - dedup_store:   Durable JSON-on-disk fingerprint -> issue-number cache
  - routing:       Repo router based on YAML rules
  - priority:      K8s reason -> p0/p1/p2/p3 mapping
  - issue_body:    LLM-driven Markdown issue body generator
  - event_watcher: Async wrapper around the K8s events watch stream
  - issue_creator: End-to-end orchestration (event -> filter -> route -> dedup -> create/comment)
  - escalation_cli: Hourly CronJob entrypoint that runs the existing 6h escalation cycle

Author: Nova ⚡ | Nightwatch Platform
"""
