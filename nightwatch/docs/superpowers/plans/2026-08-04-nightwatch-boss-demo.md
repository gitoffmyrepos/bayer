# Nightwatch Boss Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable read-only Nightwatch demo that discovers LocalStack EKS, EC2, and ECS resources, surfaces deterministic findings, explains them through Ollama, and exposes the approved Unified Operations navigation.

**Architecture:** Extend the existing adapter engine with a focused `aws_infrastructure` adapter so LocalStack and real AWS share boto3 code through endpoint configuration. Keep remediation dormant through an environment-and-config gate, add a Docker LocalStack fault lab, and build the first UI surfaces from the current API contracts. This is the first vertical slice of the broader approved design; PostgreSQL canonical persistence and external scanner normalization follow in later implementation phases.

**Tech Stack:** Python 3, FastAPI, boto3, pytest, Next.js 16, React 19, TypeScript, Docker Compose, LocalStack, Ollama.

---

## File Map

- `nightwatch/src/core/remediation_gate.py`: Pure observe/remediation capability decision.
- `nightwatch/src/core/engine.py`: Instantiate remediation only when the gate is explicitly enabled.
- `nightwatch/src/api/main.py`: Register the AWS infrastructure adapter and avoid remediation LLM setup in observe mode.
- `nightwatch/src/adapters/aws_infrastructure/adapter.py`: Read-only EKS, EC2, and ECS collection, inventory, and checks.
- `nightwatch/config/aws_infrastructure/config.yaml`: LocalStack-compatible provider settings.
- `nightwatch/config/nightwatch.yaml`: Ollama-first demo and AWS infrastructure adapter configuration.
- `nightwatch/tests/test_remediation_gate.py`: Safety-gate unit tests.
- `nightwatch/tests/test_aws_infrastructure_adapter.py`: Adapter tests with botocore Stubber responses.
- `nightwatch/docker-compose.demo.yml`: Demo services and LocalStack configuration.
- `nightwatch/localstack/init-aws.sh`: Idempotent AWS resource seed.
- `nightwatch/frontend/src/components/sidebar.tsx`: Approved Unified Operations navigation.
- `nightwatch/frontend/src/app/cloud/page.tsx`: Cloud Estate view.
- `nightwatch/frontend/src/app/kubernetes/page.tsx`: Kubernetes view.
- `nightwatch/frontend/src/app/topology/page.tsx`: Relationship-style resource visualization.
- `nightwatch/frontend/src/app/ai-analyst/page.tsx`: Incident report/Ollama investigation view.
- `nightwatch/README.md`: Complete demo and application integration guide.

### Task 1: Enforce Observe Mode

**Files:**
- Create: `nightwatch/src/core/remediation_gate.py`
- Modify: `nightwatch/src/core/engine.py`
- Modify: `nightwatch/src/api/main.py`
- Test: `nightwatch/tests/test_remediation_gate.py`

- [ ] **Step 1: Write the failing gate tests**

```python
from src.core.remediation_gate import remediation_enabled


def test_remediation_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)
    assert remediation_enabled({"healing": {"mode": "auto_remediate"}}) is False


def test_remediation_requires_env_and_config(monkeypatch):
    monkeypatch.setenv("REMEDIATION_ENABLED", "true")
    assert remediation_enabled({"healing": {"mode": "auto_remediate"}}) is True
    assert remediation_enabled({"healing": {"mode": "observe_only"}}) is False
```

- [ ] **Step 2: Verify the tests fail**

Run: `pytest -q tests/test_remediation_gate.py`  
Expected: import failure for `src.core.remediation_gate`.

- [ ] **Step 3: Implement the pure gate and wire it into startup**

```python
import os


def remediation_enabled(config: dict) -> bool:
    env_enabled = os.getenv("REMEDIATION_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    return env_enabled and config.get("healing", {}).get("mode") == "auto_remediate"
```

Use this function before constructing remediation clients, remediators, playbooks, or code analyzers. Log `observe_mode_enabled` when false.

- [ ] **Step 4: Verify safety tests and Python compilation**

Run: `pytest -q tests/test_remediation_gate.py && python -m py_compile src/core/remediation_gate.py src/core/engine.py src/api/main.py`  
Expected: tests pass and compilation exits zero.

- [ ] **Step 5: Commit**

```bash
git add nightwatch/src/core/remediation_gate.py nightwatch/src/core/engine.py nightwatch/src/api/main.py nightwatch/tests/test_remediation_gate.py
git commit -m "fix(nightwatch): enforce observe-only default"
```

### Task 2: Add the AWS Infrastructure Adapter

**Files:**
- Create: `nightwatch/src/adapters/aws_infrastructure/__init__.py`
- Create: `nightwatch/src/adapters/aws_infrastructure/adapter.py`
- Create: `nightwatch/config/aws_infrastructure/config.yaml`
- Modify: `nightwatch/src/api/main.py`
- Modify: `nightwatch/config/nightwatch.yaml`
- Test: `nightwatch/tests/test_aws_infrastructure_adapter.py`

- [ ] **Step 1: Write failing tests for deterministic checks**

```python
def test_ec2_stopped_instance_is_a_finding(adapter):
    adapter._snapshot = {
        "eks": [],
        "ec2": [{"id": "i-123", "name": "demo-web", "state": "stopped", "public_ip": None}],
        "ecs": [],
    }
    checks = adapter.run_health_checks()
    assert any(c.name == "ec2_i-123_state" and c.status.value == "fail" for c in checks)


def test_ecs_capacity_mismatch_is_a_finding(adapter):
    adapter._snapshot = {
        "eks": [], "ec2": [],
        "ecs": [{"cluster": "demo", "service": "api", "desired": 2, "running": 0, "pending": 0}],
    }
    checks = adapter.run_health_checks()
    assert any(c.name == "ecs_demo_api_capacity" and c.status.value == "fail" for c in checks)
```

- [ ] **Step 2: Verify the tests fail**

Run: `pytest -q tests/test_aws_infrastructure_adapter.py`  
Expected: adapter import failure.

- [ ] **Step 3: Implement read-only collection**

The adapter creates boto3 EKS, EC2, and ECS clients using `region`, optional `endpoint_url`, and environment credentials. It only calls describe/list APIs. It stores a normalized snapshot shaped as:

```python
{
    "eks": [{"name": str, "status": str, "version": str, "endpoint_public": bool}],
    "ec2": [{"id": str, "name": str, "state": str, "public_ip": str | None}],
    "ecs": [{"cluster": str, "service": str, "desired": int, "running": int, "pending": int}],
}
```

`collect_metrics()` refreshes the snapshot. `run_health_checks()` reports failed EKS status, stopped/impaired monitored EC2 instances, public exposure metadata, and ECS desired/running mismatch. `get_component_inventory()` returns EKS, EC2, and ECS components for the frontend.

- [ ] **Step 4: Register and configure the adapter**

```yaml
adapters:
  - name: aws-infrastructure
    type: aws_infrastructure
    config_file: aws_infrastructure/config.yaml
    enabled: true
```

LocalStack config uses `AWS_ENDPOINT_URL` and `AWS_REGION`; real AWS leaves the endpoint empty.

- [ ] **Step 5: Verify adapter tests and compilation**

Run: `pytest -q tests/test_aws_infrastructure_adapter.py && python -m py_compile src/adapters/aws_infrastructure/adapter.py src/api/main.py`  
Expected: tests pass and compilation exits zero.

- [ ] **Step 6: Commit**

```bash
git add nightwatch/src/adapters/aws_infrastructure nightwatch/config/aws_infrastructure nightwatch/config/nightwatch.yaml nightwatch/src/api/main.py nightwatch/tests/test_aws_infrastructure_adapter.py
git commit -m "feat(nightwatch): monitor EKS EC2 and ECS"
```

### Task 3: Build the LocalStack Demo Lab

**Files:**
- Create: `nightwatch/docker-compose.demo.yml`
- Create: `nightwatch/localstack/init-aws.sh`

- [ ] **Step 1: Add the Docker Compose lab**

Compose runs LocalStack with EKS, EC2, ECS, IAM, STS, CloudWatch, Logs, S3, Lambda, Step Functions, and Glue enabled. It mounts `/var/run/docker.sock`, the init script, and a persistence volume. Nightwatch API receives test credentials, `AWS_ENDPOINT_URL=http://localstack:4566`, `LLM_PROVIDER=ollama`, and `REMEDIATION_ENABLED=false`.

- [ ] **Step 2: Add an idempotent seed script**

The script creates an EKS cluster, one stopped EC2 instance with a `Name=nightwatch-demo-stopped` tag, and an ECS cluster with a service configured to expose desired/running mismatch. It uses only `awslocal` and treats already-existing resources as success.

- [ ] **Step 3: Validate Compose and shell syntax**

Run: `docker compose -f docker-compose.demo.yml config -q && bash -n localstack/init-aws.sh`  
Expected: both commands exit zero.

- [ ] **Step 4: Commit**

```bash
git add nightwatch/docker-compose.demo.yml nightwatch/localstack/init-aws.sh
git commit -m "feat(nightwatch): add LocalStack cloud demo"
```

### Task 4: Add Unified Operations UI Surfaces

**Files:**
- Modify: `nightwatch/frontend/src/components/sidebar.tsx`
- Create: `nightwatch/frontend/src/app/cloud/page.tsx`
- Create: `nightwatch/frontend/src/app/kubernetes/page.tsx`
- Create: `nightwatch/frontend/src/app/topology/page.tsx`
- Create: `nightwatch/frontend/src/app/ai-analyst/page.tsx`

- [ ] **Step 1: Replace flat navigation with approved groups**

The sidebar renders Command Center; Observe with Cloud Estate, Kubernetes, and Pipelines; Investigate with Findings, Topology, Incidents, and AI Analyst; and Manage with Connections, Settings, and Documentation.

- [ ] **Step 2: Implement Cloud Estate and Kubernetes pages**

Use `useAdapters()` and `useStatus()` to render real component inventory, health, identifiers, categories, and metadata. Empty or failed APIs show explicit unavailable states rather than sample resources.

- [ ] **Step 3: Implement topology and AI Analyst pages**

Topology renders adapter/component relationships as a dependency-oriented card graph without adding a graph dependency. AI Analyst lets a user select a real incident and invokes the existing report mutation; it labels Ollama/API errors honestly.

- [ ] **Step 4: Verify the frontend**

Run: `npm run lint && npm run build` from `nightwatch/frontend`.  
Expected: lint and production build exit zero.

- [ ] **Step 5: Commit**

```bash
git add nightwatch/frontend/src/components/sidebar.tsx nightwatch/frontend/src/app/cloud nightwatch/frontend/src/app/kubernetes nightwatch/frontend/src/app/topology nightwatch/frontend/src/app/ai-analyst
git commit -m "feat(nightwatch): add unified operations console"
```

### Task 5: Replace the README with an Operator and Integration Guide

**Files:**
- Modify: `nightwatch/README.md`

- [ ] **Step 1: Document the ten-minute demo**

Include prerequisites, exact Compose command, initialization checks, API/UI URLs, fault storyline, Ollama endpoint configuration, and teardown.

- [ ] **Step 2: Document real AWS and Kubernetes connection**

Include LocalStack-to-AWS endpoint switch, read-only IAM guidance, EKS kubeconfig/RBAC guidance, permission validation, kgateway deployment notes, and remediation-disabled proof.

- [ ] **Step 3: Document application integration**

Explain the existing adapter contract with a complete deterministic Python example, configuration registration, tests, REST endpoints, and alert/LLM behavior.

- [ ] **Step 4: Validate commands and links**

Run: `rg -n "localhost:4566|REMEDIATION_ENABLED|aws_infrastructure|Connect.*application" README.md`  
Expected: required demo, safety, provider, and integration terms are present.

- [ ] **Step 5: Commit**

```bash
git add nightwatch/README.md
git commit -m "docs(nightwatch): add cloud monitoring integration guide"
```

### Task 6: Integrated Verification

**Files:**
- Modify only files required to fix verification failures surfaced by this task.

- [ ] **Step 1: Run backend verification**

Run: `pytest -q && python -m py_compile $(rg --files src -g '*.py')` from `nightwatch`.  
Expected: all tests pass and all Python modules compile.

- [ ] **Step 2: Run frontend verification**

Run: `npm run lint && npm run build` from `nightwatch/frontend`.  
Expected: lint and production build pass.

- [ ] **Step 3: Validate the demo configuration**

Run: `docker compose -f docker-compose.demo.yml config -q && bash -n localstack/init-aws.sh` from `nightwatch`.  
Expected: Compose and shell validation pass.

- [ ] **Step 4: Review the change boundary**

Run: `git diff --check HEAD~5..HEAD && git status --short` from `bayer`.  
Expected: no whitespace errors; only pre-existing unrelated untracked paths remain.

- [ ] **Step 5: Commit any verification fixes**

```bash
git commit -am "fix(nightwatch): complete cloud demo verification"
```

If verification required no tracked-file fixes, do not create an empty commit.
