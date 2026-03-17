# Nightwatch ⚡ — Cloud-Agnostic AI Monitoring Platform
> **v2.0** — Redesigned as a universal, application-agnostic AI monitoring platform

**Author:** Nova ⚡ | StrategyBase  
**Version:** 2.0.0 (AI-powered adapter architecture)

---

## Vision

Nightwatch is NOT a Bayer-specific tool. It is a universal AI monitoring platform that can:

- 🌐 **Monitor ANY application** — AWS pipelines, Kubernetes services, SaaS, trading platforms
- ☁️ **Run ANYWHERE** — ECS, EKS, Docker, Kubernetes, bare VM
- 🧠 **Use ANY LLM** — Anthropic Claude, OpenAI, DeepSeek, or Ollama (local/free)
- 🔍 **Detect and diagnose issues END-TO-END** using AI root cause analysis
- ⚡ **Integrate a new app in ~30 minutes** via the adapter interface

**Current monitoring targets:**
- ✅ **Bayer ModelN.io** — AWS Step Functions, Glue, S3, Lambda, DynamoDB, SFTP
- 🚧 **ForexTrader** — Kubernetes pods, OANDA account, ML pipeline, Jenkins CI

---

## Architecture

```
nightwatch/
├── src/
│   ├── core/                    # Universal core — NO app-specific logic
│   │   ├── engine.py            # Monitoring loop: collect → check → diagnose → alert
│   │   ├── llm_client.py        # Multi-LLM: Anthropic | OpenAI | DeepSeek | Ollama
│   │   ├── alert_manager.py     # Alerting: Slack | Discord | PagerDuty | Email
│   │   ├── scheduler.py         # Cron-based check scheduling
│   │   └── config.py            # YAML config loader with ${ENV_VAR} substitution
│   │
│   ├── adapters/                # Application-specific adapters — plug in new apps here
│   │   ├── base_adapter.py      # Abstract interface all adapters implement
│   │   ├── aws_pipeline/        # Bayer ModelN AWS pipeline adapter
│   │   └── forextrader/         # ForexTrader FX platform adapter
│   │
│   ├── ai/                      # AI analysis layer
│   │   ├── analyzer.py          # Root cause analysis
│   │   ├── healer.py            # Auto-remediation suggestions
│   │   └── report_generator.py  # Incident reports + post-mortems
│   │
│   └── api/                     # FastAPI REST API
│       ├── main.py              # App entry point + adapter registry
│       └── routes.py            # Endpoints
│
├── config/
│   ├── nightwatch.yaml          # Master config (LLM, adapters, alerting)
│   ├── aws_pipeline/config.yaml # Bayer ModelN adapter config
│   └── forextrader/config.yaml  # ForexTrader adapter config
│
├── docs/
│   └── ADAPTER_GUIDE.md         # How to add a new application in 30 min
│
├── terraform/
│   ├── modules/ecs/             # Generic ECS Fargate deployment
│   ├── modules/eks/             # Generic EKS deployment
│   └── environments/prod/       # Production terraform vars
│
├── Dockerfile                   # Single image, supports all adapters
└── requirements.txt
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure (copy and edit)
cp config/nightwatch.yaml config/nightwatch.local.yaml
# Edit: LLM provider, adapter config, alerting webhooks

# 3. Set environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/...
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...

# 4. Run
NIGHTWATCH_CONFIG=config/nightwatch.local.yaml python -m src.api.main

# 5. Check status
curl http://localhost:8080/status
curl http://localhost:8080/adapters
```

---

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Nightwatch system health |
| GET | `/status` | Current monitored app status |
| GET | `/incidents` | Recent incidents (paginated) |
| POST | `/check` | Trigger immediate check cycle |
| GET | `/adapters` | List configured adapters + components |
| GET | `/metrics` | Current metrics snapshot |
| GET | `/schedule` | Scheduler task status |
| POST | `/report` | Generate AI incident report |

---

## LLM Providers

Switch with one config change in `config/nightwatch.yaml`:

```yaml
llm:
  provider: anthropic    # → openai | deepseek | ollama
  model: claude-3-haiku-20240307
  api_key: ${ANTHROPIC_API_KEY}
```

| Provider | Model | Cost | Privacy |
|----------|-------|------|---------|
| Anthropic | claude-3-haiku-20240307 | ~$0.001/call | Cloud |
| OpenAI | gpt-4o-mini | ~$0.001/call | Cloud |
| DeepSeek | deepseek-chat | ~$0.0001/call | Cloud |
| Ollama | qwen3:14b | FREE | Local ✅ |

---

## Adding a New Application

See **[docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md)** for the full walkthrough.

TL;DR — implement 5 methods:

```python
class MyAppAdapter(BaseNightwatchAdapter):
    @property
    def application_name(self) -> str: return "My App"
    def collect_metrics(self) -> dict: ...
    def collect_logs(self, lookback_minutes=15) -> list[str]: ...
    def run_health_checks(self) -> list[HealthCheck]: ...
    def get_component_inventory(self) -> list[Component]: ...
```

Register it in `src/api/main.py` and add to `config/nightwatch.yaml`. Done.

---

## Deployment

### Docker
```bash
docker build -t nightwatch:latest .
docker run -d -p 8080:8080 \
  -e ANTHROPIC_API_KEY=... -e SLACK_WEBHOOK_URL=... \
  -v $(pwd)/config:/app/config nightwatch:latest
```

### ECS Fargate
```bash
cd terraform/environments/prod
terraform apply -var="deployment_type=ecs" -var="llm_provider=anthropic"
```

### Kubernetes (existing cluster)
```bash
kubectl create namespace nightwatch
kubectl create secret generic nightwatch-secrets \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=slack-webhook=$SLACK_WEBHOOK_URL -n nightwatch
# Apply your k8s manifests...
```

---

## Alert Severity Levels

| Level | Response | Alert Channels |
|-------|----------|----------------|
| 🔴 Critical | Immediate | Slack + Discord + PagerDuty + Email |
| 🟠 High | 15min SLA | Slack + Discord |
| 🟡 Medium | 1hr SLA | Slack (configurable) |
| 🔵 Low | Log only | None |

---

*Built by Nova ⚡ | StrategyBase — Universal AI monitoring for any application, anywhere.*
