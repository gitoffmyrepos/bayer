# Nightwatch ⚡ — AI-Powered Proactive Monitoring Platform
## Bayer Pharma — ModelN.io Data Pipeline Monitoring

> **Version:** Phase 1 (Data Collection + Basic Alerting)
> **Author:** Nova ⚡ | StrategyBase
> **Architecture Doc:** [NIGHTWATCH-ARCHITECTURE.md](../NIGHTWATCH-ARCHITECTURE.md)

Nightwatch monitors the Bayer ModelN.io pharma data pipeline running in AWS US-East-1.
It collects metrics from Step Functions, Glue ETL jobs, S3 buckets, Lambda functions,
DynamoDB, and Transfer Family SFTP — then alerts on failures before they impact downstream
partners (McKesson, AXWAY) or the ModelN platform.

---

## Architecture (Phase 1)

```
AWS (us-east-1)                  Kubernetes (nightwatch namespace)
───────────────                  ──────────────────────────────────
Step Functions ──────────────── aws-pipeline-collector:8080/metrics
Glue Jobs      ──────────────── │
S3 Buckets     ──────────────── │
Lambda/DynamoDB ← CloudWatch ── cloudwatch-exporter:9106/metrics
Transfer Family ────────────── │
                                ▼
Container Logs ─── Fluent Bit ──── OpenSearch (100Gi)
                                │
                                ▼
                          Prometheus ──── VictoriaMetrics (50Gi, 90d)
                                │
                                ▼
                          AlertManager ──── Slack #nightwatch-incidents
                                │         ──── Email
                                ▼
                          Grafana:3000 ──── Dashboards
```

---

## Components

| Component | Image | Purpose |
|-----------|-------|---------|
| `aws-pipeline-collector` | Custom (Python/Flask) | Polls Step Functions, Glue, S3 via boto3 → Prometheus |
| `otel-collector` | otel/opentelemetry-collector-contrib:0.96.0 | OTel pipeline (traces/metrics/logs) |
| `fluent-bit` | cr.fluentbit.io/fluent/fluent-bit:3.0 | DaemonSet — ship container logs to OpenSearch |
| `prometheus` | prom/prometheus:v2.51.0 | Scrape metrics, evaluate rules, push to VictoriaMetrics |
| `victoriametrics` | victoriametrics/victoria-metrics:v1.99.0 | 90-day time-series storage (50Gi PVC) |
| `opensearch` | opensearchproject/opensearch:2.13.0 | Log storage + full-text search (100Gi PVC) |
| `grafana` | grafana/grafana:10.4.0 | Dashboards — VictoriaMetrics + OpenSearch (5Gi PVC) |
| `alertmanager` | prom/alertmanager:v0.27.0 | Alert routing → Slack + Email |

---

## Pre-deployment Configuration

### 1. AWS Credentials (Required)
Edit `k8s/collectors/aws-pipeline-collector.yaml`:
```yaml
stringData:
  AWS_ACCESS_KEY_ID: "your-access-key"
  AWS_SECRET_ACCESS_KEY: "your-secret-key"
```
Or use IAM roles (recommended for production) via pod identity/IRSA.

Update the AWS Account ID:
```yaml
STEP_FUNCTION_ARNS: |
  arn:aws:states:us-east-1:YOUR_ACCOUNT_ID:stateMachine:bay-modeln-jobs-workflow,...
```

### 2. Alert Destinations (Required)
Edit `k8s/alerting/alertmanager.yaml`:
```yaml
stringData:
  slack_webhook_url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
  alert_email_to: "team@bayer.com"
  smtp_host: "smtp.your-provider.com:587"
  smtp_auth_username: "alerts@domain.com"
  smtp_auth_password: "smtp-password"
```

### 3. Grafana Password (Optional)
Edit `k8s/dashboards/grafana.yaml`:
```yaml
stringData:
  admin-password: "YourSecurePassword!"
```

### 4. OpenSearch Password (Optional)
Edit `k8s/collectors/fluent-bit.yaml` and `k8s/storage/opensearch.yaml`:
```yaml
stringData:
  password: "YourOpenSearchPassword!"
```

### 5. Build the AWS Pipeline Collector
```bash
cd src/collectors/
docker build -t harbor.strategybase.io:8083/sb-custom-docker-images/nightwatch-aws-collector:1.0.0 .
docker push harbor.strategybase.io:8083/sb-custom-docker-images/nightwatch-aws-collector:1.0.0
```

---

## Deployment

```bash
# Full deploy
./deploy.sh

# Dry run (preview changes)
./deploy.sh --dry-run

# Namespace + RBAC only (first-time setup)
./deploy.sh --namespace-only

# Remove everything (WARNING: deletes PVCs and data)
./deploy.sh --uninstall
```

---

## Accessing the UI

After deploying, use port-forward to access services locally:

```bash
# Grafana dashboards
kubectl port-forward svc/grafana 3000:3000 -n nightwatch
# Open: http://localhost:3000 (admin / NightWatch2026!)

# AlertManager
kubectl port-forward svc/alertmanager 9093:9093 -n nightwatch
# Open: http://localhost:9093

# VictoriaMetrics (query UI)
kubectl port-forward svc/victoriametrics 8428:8428 -n nightwatch
# Open: http://localhost:8428/vmui

# OpenSearch Dashboards
kubectl port-forward svc/opensearch-dashboards 5601:5601 -n nightwatch
# Open: http://localhost:5601

# Prometheus
kubectl port-forward svc/prometheus 9090:9090 -n nightwatch
# Open: http://localhost:9090

# AWS Pipeline Collector metrics
kubectl port-forward svc/aws-pipeline-collector 8080:8080 -n nightwatch
curl http://localhost:8080/metrics  # Prometheus metrics
curl http://localhost:8080/config   # Current configuration
curl http://localhost:8080/health   # Health status
```

---

## Alert Severity Levels

| Level | Response | Slack Channel | Repeat |
|-------|----------|---------------|--------|
| P1 Critical | Immediate page | #nightwatch-incidents | Every 15min |
| P2 High | 15min SLA | #nightwatch-monitoring | Every 1h |
| P3 Medium | 1hr SLA | #nightwatch-monitoring | Every 4h |
| P4 Info | Log only | #nightwatch-info | Every 24h |

### P1 Alerts (Page Immediately)
- Step Function FAILED or TIMED_OUT for > 5 minutes
- No new objects in S3 landing bucket for 2+ hours
- Outbound SFTP delivery to McKesson/AXWAY failed
- Glue S3-to-SFTP job failed (partner SLA breach)
- RODB-EC2 instance unhealthy
- Glue RODB job failed (stale database)

### P2 Alerts (Auto-remediate + Notify)
- Glue job duration > 2x 7-day average
- Glue job failed (first/second failure)
- SFTP inbound volume < 50% of expected
- DynamoDB throttling > 5%
- Audit Lambda errors (compliance impact)
- EventBridge failed invocations

---

## Metrics Reference

### AWS Pipeline Collector (`nightwatch_*`)

| Metric | Labels | Description |
|--------|--------|-------------|
| `nightwatch_stepfunction_execution_status` | state_machine, execution_name, status | 1 if this status is current, 0 otherwise |
| `nightwatch_stepfunction_duration_seconds` | state_machine | Histogram of execution durations |
| `nightwatch_stepfunction_last_execution_timestamp` | state_machine, status | Unix timestamp of last execution per status |
| `nightwatch_glue_job_status` | job_name, status | 1 if this status is current |
| `nightwatch_glue_job_duration_seconds` | job_name | Most recent job run duration |
| `nightwatch_glue_job_dpu_seconds` | job_name | DPU-seconds consumed (cost metric) |
| `nightwatch_glue_job_consecutive_failures` | job_name | Count of consecutive failures |
| `nightwatch_s3_object_count` | bucket, prefix | Number of objects |
| `nightwatch_s3_last_modified_age_seconds` | bucket, prefix | Seconds since most recent modification |
| `nightwatch_s3_total_size_bytes` | bucket, prefix | Total storage size |
| `nightwatch_sftp_transfer_count` | direction (inbound/outbound) | Files transferred in scrape window |
| `nightwatch_sftp_bytes_transferred` | direction | Bytes transferred |

---

## AWS IAM Policy Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "states:ListExecutions",
        "states:DescribeExecution",
        "states:GetExecutionHistory",
        "glue:GetJobRuns",
        "glue:GetJob",
        "glue:ListJobs",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "transfer:ListServers",
        "transfer:DescribeServer"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Directory Structure

```
nightwatch/
├── deploy.sh                         # Single deploy script
├── README.md                         # This file
├── k8s/
│   ├── namespace/
│   │   └── nightwatch-namespace.yaml  # Namespace + ResourceQuota + LimitRange
│   ├── rbac/
│   │   └── nightwatch-rbac.yaml       # ServiceAccount, ClusterRole, Bindings
│   ├── collectors/
│   │   ├── otel-collector.yaml        # OpenTelemetry Collector
│   │   ├── fluent-bit.yaml            # Fluent Bit DaemonSet (log collection)
│   │   ├── prometheus.yaml            # Prometheus StatefulSet + alert rules
│   │   └── aws-pipeline-collector.yaml # Custom AWS metrics exporter
│   ├── storage/
│   │   ├── victoriametrics.yaml       # VictoriaMetrics (50Gi, 90-day retention)
│   │   └── opensearch.yaml            # OpenSearch + Dashboards (100Gi)
│   ├── alerting/
│   │   └── alertmanager.yaml          # AlertManager (Slack + Email routing)
│   └── dashboards/
│       └── grafana.yaml               # Grafana (VictoriaMetrics + OpenSearch)
├── config/
│   ├── targets/
│   │   └── modeln-pipeline-targets.yaml  # CloudWatch exporter config for all AWS services
│   └── alerts/
│       └── pipeline-alerts.yaml          # P1/P2/P3/P4 alert rules (detailed)
└── src/
    └── collectors/
        ├── aws_pipeline_collector.py   # Python AWS metrics collector
        ├── requirements.txt            # Python dependencies
        └── Dockerfile                  # Container build
```

---

## Troubleshooting

### Collector not scraping AWS
```bash
# Check collector logs
kubectl logs -n nightwatch deployment/aws-pipeline-collector -f

# Verify AWS credentials
kubectl exec -n nightwatch deployment/aws-pipeline-collector -- \
  python -c "import boto3; print(boto3.client('sts').get_caller_identity())"

# Check config
curl http://localhost:8080/config  # (after port-forward)
```

### Prometheus not receiving metrics
```bash
# Check Prometheus targets
kubectl port-forward svc/prometheus 9090:9090 -n nightwatch
# Open http://localhost:9090/targets

# Check remote write to VictoriaMetrics
kubectl logs -n nightwatch statefulset/prometheus | grep "remote_write"
```

### OpenSearch not accepting logs
```bash
# Check Fluent Bit status
kubectl logs -n nightwatch daemonset/fluent-bit | grep -E "error|Error|ERROR"

# Check OpenSearch health
kubectl exec -n nightwatch statefulset/opensearch -- \
  curl -s localhost:9200/_cluster/health | python -m json.tool
```

### Alerts not firing
```bash
# Check AlertManager config
kubectl port-forward svc/alertmanager 9093:9093 -n nightwatch
# Open http://localhost:9093

# Test Slack webhook manually
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  --data '{"text":"Nightwatch test alert ⚡"}'
```

---

## Next Phase

**Phase 2: AI Anomaly Detection (Week 3-4)**
- Collect 1 week of baseline pipeline data
- Train Facebook Prophet on Glue job duration trends
- Deploy Isolation Forest for S3 object count anomalies
- Deploy LSTM Autoencoder for Step Function sequence anomalies
- Anomaly alerting with confidence scores in Grafana
- Target: < 5% false positive rate

**Phase 3: Auto-Remediation + RCA (Week 5-6)**
- Build playbooks for each ModelN.io failure mode
- Deploy remediation engine with dry-run mode
- Integrate Ollama for natural language Root Cause Analysis
- Enable production auto-remediation (P2/P3 only)
- Go-live review with Bayer team
