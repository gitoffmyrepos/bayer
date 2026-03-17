# Nightwatch Adapter Guide ⚡
> Add a new application to Nightwatch in ~30 minutes

## Overview

Nightwatch is application-agnostic. To monitor a new application, you create an **adapter** — a Python class that implements the `BaseNightwatchAdapter` interface.

The core engine handles scheduling, AI diagnosis, alerting, and the API. Your adapter just needs to answer three questions:
1. **What is the current health?** (`run_health_checks`)
2. **What metrics are there?** (`collect_metrics`)
3. **Are there any recent errors?** (`collect_logs`)

---

## 30-Minute Quickstart

### Step 1: Create the adapter directory

```bash
mkdir -p src/adapters/my_app
touch src/adapters/my_app/__init__.py
touch src/adapters/my_app/adapter.py
touch src/adapters/my_app/collectors.py
touch src/adapters/my_app/config.yaml
```

### Step 2: Implement the adapter

```python
# src/adapters/my_app/adapter.py
from src.adapters.base_adapter import BaseNightwatchAdapter, HealthCheck, CheckStatus, Component
import httpx

class MyAppAdapter(BaseNightwatchAdapter):
    """Monitors My Application."""

    @property
    def application_name(self) -> str:
        return "My Application"

    def collect_metrics(self) -> dict:
        """Return a dict of current metrics."""
        try:
            resp = httpx.get(f"{self.config['api_url']}/metrics", timeout=10)
            data = resp.json()
            return {
                "requests_per_second": data.get("rps", 0),
                "error_rate": data.get("error_rate", 0),
                "active_users": data.get("active_users", 0),
            }
        except Exception as e:
            return {"error": str(e)}

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        """Return recent error log lines."""
        try:
            resp = httpx.get(
                f"{self.config['api_url']}/logs",
                params={"level": "error", "minutes": lookback_minutes},
                timeout=10,
            )
            return resp.json().get("lines", [])
        except Exception:
            return []

    def run_health_checks(self) -> list[HealthCheck]:
        """Run health checks. Return list of HealthCheck results."""
        checks = []
        metrics = self.collect_metrics()

        # Check 1: API is reachable
        try:
            resp = httpx.get(f"{self.config['api_url']}/health", timeout=5)
            if resp.status_code == 200:
                checks.append(self._ok("api_health", "API is healthy", component="HTTP API"))
            else:
                checks.append(self._fail(
                    "api_health",
                    f"API returned HTTP {resp.status_code}",
                    component="HTTP API",
                ))
        except Exception as e:
            checks.append(self._fail("api_health", f"API unreachable: {e}", component="HTTP API"))

        # Check 2: Error rate threshold
        error_rate = metrics.get("error_rate", 0)
        threshold = self.config.get("thresholds", {}).get("max_error_rate", 0.05)
        if error_rate > threshold:
            checks.append(self._warn(
                "error_rate",
                f"Error rate {error_rate:.1%} exceeds threshold {threshold:.1%}",
                component="Application",
                error_rate=error_rate,
            ))
        else:
            checks.append(self._ok("error_rate", f"Error rate {error_rate:.2%}", component="Application"))

        return checks

    def get_component_inventory(self) -> list[Component]:
        """List monitorable components."""
        return [
            Component("api", "api_endpoint", "HTTP API", description="My App REST API"),
        ]

    def describe_architecture(self) -> str:
        return "My Application is a web service that handles user requests. It exposes a REST API."
```

### Step 3: Create the config file

```yaml
# src/adapters/my_app/config.yaml
application_name: "My Application"
api_url: https://myapp.example.com
thresholds:
  max_error_rate: 0.05
```

### Step 4: Register the adapter in main.py

```python
# src/api/main.py — add to ADAPTER_REGISTRY:
try:
    from src.adapters.my_app.adapter import MyAppAdapter
    ADAPTER_REGISTRY["my_app"] = MyAppAdapter
except ImportError:
    pass
```

### Step 5: Enable in nightwatch.yaml

```yaml
# config/nightwatch.yaml
adapters:
  - name: my-application
    type: my_app
    config_file: my_app/config.yaml    # relative to config/
    enabled: true
```

### Step 6: Test it

```bash
# Run the API
python -m src.api.main

# Check status
curl http://localhost:8080/status

# Trigger a manual check
curl -X POST http://localhost:8080/check

# See components
curl http://localhost:8080/adapters
```

Done! ✅

---

## BaseNightwatchAdapter Reference

### Required Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `application_name` | `str` | Property: human-readable app name |
| `collect_metrics()` | `dict` | Current health metrics |
| `collect_logs(lookback_minutes)` | `list[str]` | Recent error logs |
| `run_health_checks()` | `list[HealthCheck]` | All health check results |
| `get_component_inventory()` | `list[Component]` | All monitorable components |

### Optional Methods (Override for richer behavior)

| Method | Default | Description |
|--------|---------|-------------|
| `describe_architecture()` | Auto-generated | App description for LLM context |
| `initialize()` | No-op | Validate credentials on startup |
| `cleanup()` | No-op | Clean up resources on shutdown |
| `get_runbook_url(check_name)` | None | Runbook URL for a failing check |

### Convenience Helpers

```python
# Pre-built HealthCheck factories
self._ok("check_name", "Everything is fine", component="MyService")
self._warn("check_name", "Something seems off", component="MyService")
self._fail("check_name", "This is broken!", component="MyService")
self._unknown("check_name", "Could not determine status", component="MyService")
```

---

## HealthCheck Object

```python
@dataclass
class HealthCheck:
    name: str           # Unique identifier: "api_up", "s3_freshness"
    status: CheckStatus # OK | WARN | FAIL | UNKNOWN
    message: str        # Human-readable description
    component: str      # Service name: "AWS S3", "Kubernetes", "HTTP API"
    metadata: dict      # Extra structured data (ARNs, counts, etc.)
    checked_at: datetime
```

**Severity mapping:**
- `OK` → healthy, no action needed
- `WARN` → degraded, investigate within 1 hour
- `FAIL` → broken, alert immediately
- `UNKNOWN` → could not check (permissions, network, etc.)

---

## Component Object

```python
@dataclass
class Component:
    name: str        # "my-api-service"
    type: str        # "api_endpoint", "k8s_deployment", "s3_bucket", "database", etc.
    category: str    # "Kubernetes", "AWS S3", "HTTP API"
    description: str
    metadata: dict
```

---

## How the Engine Uses Your Adapter

```
Every {check_interval_seconds} (default: 60):

1. collect_metrics()     → pass to AI for context
2. collect_logs(15)      → pass to AI for diagnosis  
3. run_health_checks()   → determine if app is healthy

If any checks FAIL/WARN:
4. llm.diagnose(metrics, logs, failing_checks, architecture)
   → AI identifies root cause + severity + recommendation
5. If severity in [critical, high]:
   → alert_manager.send_alert(title, body, severity, metadata)
   → sends to Slack, Discord, PagerDuty, email
```

---

## Real-World Example: AWS Pipeline Adapter

See `src/adapters/aws_pipeline/adapter.py` for a full production adapter that monitors:
- AWS Step Functions
- AWS Glue jobs
- S3 bucket freshness
- Lambda error rates
- DynamoDB throttling
- Transfer Family SFTP

Key patterns it uses:
- Lazy boto3 client initialization
- Separated collectors (`collectors.py`) from health logic
- Configurable thresholds via `config.yaml`
- Detailed `describe_architecture()` for better AI diagnosis

---

## Testing Your Adapter

```python
# tests/test_my_app.py
import pytest
from unittest.mock import patch, MagicMock
from src.adapters.my_app.adapter import MyAppAdapter

@pytest.fixture
def adapter():
    config = {"api_url": "https://myapp.example.com", "thresholds": {"max_error_rate": 0.05}}
    return MyAppAdapter(config)

def test_healthy_app(adapter):
    with patch("httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "ok"}
        
        checks = adapter.run_health_checks()
        assert any(c.name == "api_health" and c.status.value == "ok" for c in checks)

def test_unhealthy_app(adapter):
    with patch("httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        
        checks = adapter.run_health_checks()
        assert any(c.name == "api_health" and c.status.value == "fail" for c in checks)
```

Run tests:
```bash
pytest tests/ -v
```

---

## Switching LLM Providers

Change one line in `config/nightwatch.yaml`:

```yaml
llm:
  # Option 1: Anthropic Claude (default, best quality)
  provider: anthropic
  model: claude-3-haiku-20240307
  api_key: ${ANTHROPIC_API_KEY}

  # Option 2: OpenAI
  # provider: openai
  # model: gpt-4o-mini
  # api_key: ${OPENAI_API_KEY}

  # Option 3: DeepSeek (cheapest ~$0.001/1K tokens)
  # provider: deepseek
  # model: deepseek-chat
  # api_key: ${DEEPSEEK_API_KEY}

  # Option 4: Ollama (FREE — runs locally, fully private)
  # provider: ollama
  # model: qwen3:14b
  # base_url: http://localhost:11434
```

No code changes needed. The `NightwatchLLMClient` handles all routing.

---

## Deployment Options

### Docker (any machine)

```bash
docker build -t nightwatch:latest .
docker run -d \
  -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e SLACK_WEBHOOK_URL=https://... \
  -e AWS_ACCESS_KEY_ID=AKIA... \
  -e AWS_SECRET_ACCESS_KEY=... \
  -v $(pwd)/config:/app/config \
  nightwatch:latest
```

### ECS Fargate

```bash
cd terraform/environments/prod
terraform init
terraform apply -var="nightwatch_image_uri=<your-ecr-uri>" \
                -var="llm_provider=anthropic" \
                -var="deployment_type=ecs"
```

### Kubernetes

```yaml
# k8s/nightwatch-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nightwatch
  namespace: nightwatch
spec:
  replicas: 1
  selector:
    matchLabels: {app: nightwatch}
  template:
    metadata:
      labels: {app: nightwatch}
    spec:
      containers:
        - name: nightwatch
          image: harbor.strategybase.io:8083/sb-custom-docker-images/nightwatch:latest
          ports:
            - containerPort: 8080
          env:
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef: {name: nightwatch-secrets, key: anthropic-api-key}
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef: {name: nightwatch-secrets, key: slack-webhook}
          volumeMounts:
            - name: config
              mountPath: /app/config
      volumes:
        - name: config
          configMap:
            name: nightwatch-config
```

### EKS

```bash
terraform apply -var="deployment_type=eks"
```

---

## Checklist for a New Adapter

- [ ] Create `src/adapters/<name>/adapter.py`
- [ ] Implement all 5 required methods
- [ ] Create `src/adapters/<name>/config.yaml` with configurable thresholds
- [ ] Add `__init__.py` 
- [ ] Register adapter class in `src/api/main.py` `ADAPTER_REGISTRY`
- [ ] Add adapter entry to `config/nightwatch.yaml`
- [ ] Write at least 2 tests (healthy + unhealthy scenarios)
- [ ] Override `describe_architecture()` with a detailed description
- [ ] Test with `curl -X POST localhost:8080/check` and inspect `/status`

That's it. Welcome to Nightwatch. ⚡
