# Nightwatch — AI-Powered Proactive Monitoring Platform
## Architecture for ModelN.io — Bayer Pharma Data Pipeline (AWS US-East-1)

> **Version:** 1.0 | **Author:** Nova ⚡ | **Date:** 2026-03-16
> **Classification:** Internal — Bayer Work Project

---

## Executive Summary

Nightwatch is a cloud-agnostic, open-source AI monitoring platform that proactively monitors
the ModelN.io data pipeline regardless of which cloud provider it's deployed on. For Bayer,
this pipeline runs in AWS US-East-1 but Nightwatch uses zero AWS-specific APIs — it works via
standard protocols so it remains portable.

**The Problem It Solves:** The ModelN.io pipeline processes critical pharma revenue management
data (chargebacks, Medicaid claims, price lists, customer data) through a multi-stage AWS
pipeline involving S3 buckets, Glue ETL jobs, Step Functions, DynamoDB, Transfer Family SFTP,
and downstream Snowflake/Databricks layers. A silent failure anywhere in this pipeline can cause:
- Incorrect chargeback calculations (financial impact)
- Failed Medicaid claims submissions (compliance impact)
- Stale price lists in ModelN (revenue impact)
- Missing outbound SFTP files to AXWAY/McKesson (partner SLA breach)

**Nightwatch detects and remediates these failures before they reach ModelN or downstream partners.**

---

## ModelN.io Application Overview (Extracted from Architecture Diagram)

### Parsed from `ModelN.io.drawio` — 59 Components, 96 Data Flow Edges

### Layer 1: External Systems & Data Sources
| Component | Type | Description |
|-----------|------|-------------|
| ModelN | External SaaS | Pharma revenue management platform (master system) |
| McKesson | External Partner | Drug distributor — sends/receives EDI/SFTP files |
| AXWAY | External Gateway | B2B integration middleware for partner file exchange |
| External ERP Systems | External | Enterprise resource planning systems feeding data |
| Galaxy Team | Internal Team | Bayer internal team consuming pipeline output |

### Layer 2: Data Ingestion (SFTP / Transfer Family)
| Component | Type | Description |
|-----------|------|-------------|
| Transfer Family | AWS Service | Managed SFTP server — inbound file ingestion |
| SFTP VPC Endpoint | Network | Private VPC endpoint for SFTP access |
| SFTP Endpoint | Network | Outbound SFTP endpoint for file delivery |
| AXWAY | Integration | Routes files from partners to SFTP |
| s3-landing-us-east-1 | S3 Bucket | Landing zone — raw inbound files (CSV, XML) |
| s3-landing-us-east-1/USRMT/Inbound/Source | S3 Path | Inbound source path |
| s3-landing-us-east-1/USRMT/Outbound/Source | S3 Path | Outbound source path |

### Layer 3: Orchestration (Step Functions + EventBridge)
| Component | Type | Description |
|-----------|------|-------------|
| Event Bridge | AWS Service | Time-based trigger for step functions |
| Inbound step function: bay-modeln-jobs-workflow | Step Function | Master inbound pipeline orchestrator |
| bay-modeln-outbound-jobs-wrkflw | Step Function | Master outbound pipeline orchestrator |
| bay-modeln-capture-audit-info | SF Task / Lambda | Captures audit trail for each run |
| bay-modeln-email-attachment-error | SF Task / Lambda | Sends email alerts on file attachment errors |
| bay-modeln-initialize-parameter-stpfnc | SF Task / Lambda | Initializes step function parameters |
| bay-modeln-fetch-source-file-to-S3 | SF Task / Lambda | Fetches source files into S3 landing |
| S-F Task: Conditional Raw Glue Job Trigger | SF Task | Decides whether to run raw Glue job |
| [Choice: Run Raw Glue Job?] | SF Choice State | Conditional branch — checks if raw job needed |
| Conditional Model Glue Job Trigger | SF Task | Triggers enriched/model Glue job conditionally |

### Layer 4: ETL Processing (Glue Jobs)
| Component | Type | Description |
|-----------|------|-------------|
| bay-modeln-raw-job-us-east-1 | Glue Job | Raw layer ETL — landing → raw S3 |
| bay-modeln-enriched-job-us-east-1 | Glue Job | Enriched layer ETL — raw → enriched S3 |
| bay-modeln-rodb-job-us-east-1 | Glue Job | RODB write — enriched → read-only DB |
| bay-modeln-s3-to-sftp-pythonshell-job-us-east-1 | Glue Job (Python) | Outbound delivery — S3 → SFTP |

### Layer 5: Storage (S3 + DynamoDB)
| Component | Type | Description |
|-----------|------|-------------|
| s3-landing-us-east-1 | S3 Bucket | Landing zone (raw inbound files) |
| S3-Raw-bucket-us-east-1 | S3 Bucket | Processed raw layer |
| s3-Enriched-us-east-1 | S3 Bucket | Enriched/transformed data |
| Dynamo DB (6 tables) | DynamoDB | Inbound reference tables queried by Lambda/Glue/S3 |
| Dynamo DB (4 tables) | DynamoDB | Outbound reference tables |

### Layer 6: Read-Only Database (RODB)
| Component | Type | Description |
|-----------|------|-------------|
| RODB-EC2 | EC2 Instance | Read-only database for query access |
| RODB Endpoint | VPC Endpoint | Private endpoint routing to RODB-EC2 |
| DNS mapped to RODB endpoint | DNS | DNS resolution for RODB access |

### Layer 7: Downstream Analytics
| Component | Type | Description |
|-----------|------|-------------|
| Snowflake Data Warehouse Layer | Data Warehouse | Analytics/BI layer (appears twice — inbound + outbound) |
| Databricks | Analytics Platform | Spark-based analytics (appears twice) |

### Layer 8: Network Infrastructure
| Component | Type | Description |
|-----------|------|-------------|
| AWS Cloud | Cloud | AWS US-East-1 region |
| VPC | Network | Virtual Private Cloud |
| Public Subnet | Network | Public-facing resources |
| Public Subnet-2 | Network | Second public subnet |
| Private Subnet | Network | Internal resources |
| Bastion EC2 | EC2 | Jump host for admin access |
| DNS to IP Map | DNS | Internal DNS resolution |
| S3 Endpoint | VPC Endpoint | Private S3 access from VPC |

### Data Types Flowing Through the Pipeline
- 👥 Customers
- 💊 Products
- 📦 Units of Measure (UoM)
- 📄 Price Lists
- 📍 Sales Alignment
- 🛒 Direct Sales
- 🔁 Chargebacks
- ⚙️ Custom Sales
- 📊 Utilization Data
- 🏥 Medicaid Claims
- CSV files (inbound from partners)
- XML files (inbound from ModelN/ERP)

---

## Nightwatch Architecture — 6 Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NIGHTWATCH MONITORING PLATFORM                            │
│                                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐ │
│  │ LAYER 1  │───▶│ LAYER 2  │───▶│ LAYER 3  │───▶│ LAYER 4  │───▶│LAYER 5+6│ │
│  │Collect   │    │ Storage  │    │  AI/ML   │    │Remediate │    │Alerts  │ │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Layer 1: Universal Data Collection (Cloud-Agnostic)

| Collector | What It Collects | Source in ModelN Pipeline |
|-----------|-----------------|--------------------------|
| **OpenTelemetry Collector** | Traces, metrics, logs from any service | Lambda functions, Glue jobs |
| **Prometheus + AWS exporters** | CloudWatch metrics via prometheus-cloudwatch-exporter | S3 bucket metrics, Step Function execution states |
| **Fluent Bit** | Log aggregation from CloudWatch Log Groups | All Lambda and Glue job logs |
| **Custom Python collectors** | Step Function execution history, Glue job run status | AWS SDK polling (no CloudWatch dependency) |
| **Kafka / Redpanda** | Event streaming backbone — all events flow through here | Unified event bus |

**Key Metrics Collected:**
- Step Function execution: started, succeeded, failed, timed_out, aborted
- Glue Job: run duration, DPU usage, rows processed, errors
- S3: object count deltas, last-modified timestamps, failed PUT events
- Lambda: invocations, errors, duration, concurrent executions
- DynamoDB: read/write capacity, throttled requests, item count
- Transfer Family: file upload events, failed transfers
- RODB-EC2: CPU, memory, disk, connection count
- EventBridge: rule trigger count, failed invocations

---

### Layer 2: Storage & Indexing

| Component | Purpose | Sizing (Bayer Pipeline) |
|-----------|---------|------------------------|
| **VictoriaMetrics** | Time-series metrics — Prometheus-compatible | ~50GB/month estimated |
| **OpenSearch** | Log storage + full-text search on Glue/Lambda logs | ~200GB/month estimated |
| **ClickHouse** | High-speed pipeline analytics (throughput, latency trends) | ~20GB/month |
| **Redis** | Alert state, deduplication, step function execution cache | ~1GB |

**Retention Policy:**
- Raw metrics: 90 days
- Aggregated metrics: 2 years
- Logs: 30 days (detailed), 1 year (error logs only)
- ClickHouse analytics: 1 year

---

### Layer 3: AI Intelligence Engine

#### 3.1 Anomaly Detection Models

| Model | Algorithm | Applied To | What It Detects |
|-------|-----------|-----------|-----------------|
| **Pipeline Trend Detector** | Facebook Prophet | Daily Glue job run times | Jobs taking unusually long — data volume spike or cluster degradation |
| **Point Anomaly Detector** | Isolation Forest | S3 object counts per pipeline run | Missing files — partner didn't send, or ETL dropped records |
| **Sequence Anomaly Detector** | LSTM Autoencoder | Step Function execution sequences | Unusual step ordering, unexpected Choice state paths |
| **Latency Detector** | Isolation Forest + Prophet | RODB query latency | Database performance degradation |
| **Transfer Anomaly Detector** | Isolation Forest | SFTP transfer volumes/timing | Missing outbound files to McKesson/AXWAY |

#### 3.2 Root Cause Analysis Engine

```python
# RCA Flow:
# 1. Alert fires → collect last 2hr of correlated metrics
# 2. Build causal graph: S3 event → Glue job → Step Function → DynamoDB
# 3. Traverse graph upstream from failure point
# 4. Query Ollama (local LLM) with context:
#    "Given this Glue job failed with error X, and S3 had Y objects, 
#     what is the most likely root cause?"
# 5. Return natural language RCA + confidence score + recommended action
```

**Causal Graph Edges (from drawio analysis):**
- EventBridge → Step Function → Lambda (fetch file) → S3 Landing
- S3 Landing → Glue Raw Job → S3 Raw → Glue Enriched Job → S3 Enriched
- S3 Enriched → Glue RODB Job → RODB EC2
- S3 Enriched → Glue S3-to-SFTP Job → SFTP Endpoint → AXWAY/McKesson
- All jobs query DynamoDB for reference data

#### 3.3 Alert Classifier

```
Incoming anomaly signal
        │
        ▼
  [Severity Classifier]
  - P1: Step Function FAILED + no retry remaining
  - P1: Glue job failed 3 consecutive runs  
  - P1: RODB-EC2 unreachable
  - P1: Outbound SFTP delivery failed (McKesson/AXWAY)
  - P2: Glue job > 2x normal duration
  - P2: S3 object count < expected threshold
  - P2: DynamoDB throttling > 10% of requests
  - P3: EventBridge rule didn't trigger on schedule
  - P3: Lambda duration > 80% of timeout
  - P4: S3 cost anomaly, DPU cost spike
```

#### 3.4 Prediction Engine

- **Pipeline Failure Prediction:** 30-60 min ahead using historical failure patterns
- **Data Volume Forecasting:** Expected file counts per partner per day
- **Capacity Planning:** DPU requirements for Glue jobs based on input volume

---

### Layer 4: Remediation Engine

#### Remediation Playbooks for ModelN.io Components

| Trigger | Severity | Auto-Action | Human Action |
|---------|----------|-------------|--------------|
| Step Function execution failed | P1 | Restart execution with same input, alert on-call | Review logs, investigate root cause |
| Glue job failed — transient error | P2 | Re-trigger Glue job via AWS SDK | — |
| Glue job failed — schema error | P1 | Halt pipeline, alert on-call | Fix schema mismatch |
| S3 landing file missing (expected not arrived) | P2 | Send alert to partner (email via Lambda), log | Check with McKesson/AXWAY |
| RODB-EC2 unhealthy | P1 | Restart EC2 instance (if safe), alert | Investigate disk/memory/DB |
| DynamoDB throttling | P2 | Auto-scale DynamoDB capacity | — |
| SFTP outbound delivery failed | P1 | Retry SFTP transfer, alert on-call | Coordinate with AXWAY |
| EventBridge rule missed trigger | P3 | Force-trigger Step Function manually | Investigate EventBridge |
| Snowflake load failed | P2 | Retry Snowflake COPY command | Check credentials/schema |
| Databricks job failed | P2 | Retry Databricks job | Check cluster config |

#### Remediation Engine Architecture

```python
# Remediation decision flow:
class RemediationEngine:
    def handle_alert(self, alert: Alert):
        playbook = self.playbook_registry.get(alert.component, alert.error_type)
        if alert.severity in ['P2', 'P3'] and playbook.is_safe_to_auto_remediate:
            result = playbook.execute(alert.context)
            self.audit_log.write(alert, result)
            if result.success:
                self.resolve_alert(alert)
            else:
                self.escalate_to_p1(alert, result)
        else:  # P1 or unsafe
            self.escalate(alert)
            self.notify_oncall(alert)
```

---

### Layer 5: Monitoring Targets — ModelN.io Specific Checks

#### 5.1 S3 Buckets

| Bucket | Check | Threshold | Frequency |
|--------|-------|-----------|-----------|
| s3-landing-us-east-1 | Object count increased since last run | > 0 new objects per pipeline schedule | Every 15min |
| s3-landing-us-east-1 | Expected file arrived from partner | File present within 2hr of scheduled delivery | Per schedule |
| S3-Raw-bucket-us-east-1 | Objects written by Glue raw job | Count matches landing input | After job run |
| s3-Enriched-us-east-1 | Objects written by enriched job | Count within 5% of expected | After job run |
| All buckets | Last-modified timestamp | No bucket stale > 24hr on business days | Daily |

#### 5.2 AWS Step Functions

| Step Function | Check | Alert Condition |
|---------------|-------|-----------------|
| bay-modeln-jobs-workflow (inbound) | Execution status | FAILED or TIMED_OUT → P1 |
| bay-modeln-jobs-workflow (inbound) | Execution duration | > 2x rolling 7-day average → P2 |
| bay-modeln-outbound-jobs-wrkflw | Execution status | FAILED or TIMED_OUT → P1 |
| Both | Execution frequency | Didn't start within 30min of scheduled time → P3 |
| Both | Choice state path | Unexpected branch taken → P3 |

#### 5.3 Glue ETL Jobs

| Job | Check | Alert Condition |
|-----|-------|-----------------|
| bay-modeln-raw-job-us-east-1 | Run state | FAILED → P1 (if 3rd consecutive failure) / P2 (first fail) |
| bay-modeln-raw-job-us-east-1 | Duration | > 2x 7-day average → P2 |
| bay-modeln-raw-job-us-east-1 | Rows output | < 90% of expected based on input → P2 |
| bay-modeln-enriched-job-us-east-1 | Run state | FAILED → P1/P2 same logic |
| bay-modeln-enriched-job-us-east-1 | Data quality | Null rate in key fields > 1% → P2 |
| bay-modeln-rodb-job-us-east-1 | Run state | FAILED → P1 (affects RODB queries) |
| bay-modeln-s3-to-sftp-pythonshell-job-us-east-1 | Run state | FAILED → P1 (McKesson/AXWAY SLA breach) |
| bay-modeln-s3-to-sftp-pythonshell-job-us-east-1 | Transfer confirmation | SFTP ACK not received within 30min → P1 |

#### 5.4 Lambda Functions

| Lambda | Check | Alert Condition |
|--------|-------|-----------------|
| bay-modeln-capture-audit-info | Error rate | > 0 errors → P2 (audit trail gap) |
| bay-modeln-email-attachment-error | Invocation count | Unexpected spike → P3 (partner file issues) |
| bay-modeln-initialize-parameter-stpfnc | Duration | > 80% of timeout → P3 |
| bay-modeln-fetch-source-file-to-S3 | Error rate | > 0 errors → P2 (file fetch failure) |

#### 5.5 DynamoDB Tables

| Check | Alert Condition |
|-------|-----------------|
| Consumed read capacity | > 80% provisioned → P2 (throttling risk) |
| Throttled requests | > 5% of total → P2 (active throttling) |
| Item count drift | Unexpected decrease in reference tables → P1 (data corruption) |
| Table availability | Table status ≠ ACTIVE → P1 |

#### 5.6 RODB-EC2

| Check | Alert Condition |
|-------|-----------------|
| EC2 instance state | != running → P1 |
| CPU utilization | > 85% sustained 10min → P2 |
| Disk usage | > 80% → P2 |
| Memory utilization | > 90% → P2 |
| DB query latency | > 2x baseline → P2 |
| Connection count | > 80% of max → P2 |

#### 5.7 Transfer Family / SFTP

| Check | Alert Condition |
|-------|-----------------|
| Inbound file received from McKesson/AXWAY | Missing within expected window → P2 |
| Outbound file delivered to McKesson/AXWAY | No delivery confirmation within 30min → P1 |
| Transfer Family server status | OFFLINE → P1 |
| Failed authentication attempts | > 5 in 10min → P3 (security alert) |

#### 5.8 EventBridge

| Check | Alert Condition |
|-------|-----------------|
| Rule trigger count | Less than expected per schedule → P3 |
| Failed invocations | > 0 → P2 |
| Rule state | DISABLED (unexpected) → P1 |

#### 5.9 Snowflake & Databricks (Downstream)

| Check | Alert Condition |
|-------|-----------------|
| Snowflake: table row count delta | < expected after pipeline run → P2 |
| Snowflake: COPY command failures | > 0 → P2 |
| Databricks: job run status | FAILED → P2 |
| Databricks: cluster startup time | > 15min → P3 |
| Both: last successful load timestamp | Stale > 1 business day → P1 |

---

### Layer 6: Alerting & Dashboard

#### Alert Severity Matrix

| Level | Condition | Action | SLA |
|-------|-----------|--------|-----|
| **P1** | Complete outage, data loss risk, partner SLA breach, >5min downtime | Page on-call immediately (PagerDuty + Slack #incidents + email) | 5 min response |
| **P2** | Degraded performance, partial failure, job failed once | Auto-remediate + notify #monitoring Slack | 15 min resolution |
| **P3** | Warning threshold crossed, schedule drift | Auto-remediate silently + log | 1 hr |
| **P4** | Informational, cost anomaly, slow trend | Log only, weekly digest | None |

#### Grafana Dashboards

1. **Pipeline Overview** — End-to-end pipeline health, last run status per job, SLA compliance
2. **S3 Data Flow** — Object counts per bucket per run, data volume trends
3. **Glue Job Performance** — Duration trends, DPU usage, row counts, failure rate
4. **Step Function Execution** — Execution timeline, branch statistics, failure breakdown
5. **SFTP Transfer Monitor** — Inbound/outbound file tracker, partner delivery status
6. **Infrastructure Health** — RODB-EC2 metrics, DynamoDB capacity, Transfer Family
7. **AI Anomaly Dashboard** — Active anomalies with confidence scores, predicted failures
8. **Business Data Quality** — Chargeback record counts, Medicaid claim volumes, price list currency

---

## Technology Stack (100% Open-Source, Cloud-Agnostic)

| Component | Tool | Version | Why |
|-----------|------|---------|-----|
| Metrics collection | Prometheus + OpenTelemetry | Latest | Industry standard, any cloud |
| AWS metric bridge | prometheus-cloudwatch-exporter | Latest | Pulls CloudWatch into Prometheus |
| Log collection | Fluent Bit | Latest | Lightweight, CloudWatch → OpenSearch |
| Time-series DB | VictoriaMetrics | Latest | Prometheus-compatible, cheaper than hosted |
| Log storage | OpenSearch | Latest | Elasticsearch-compatible, no licensing |
| Stream processing | Apache Kafka / Redpanda | Latest | Cloud-agnostic event bus |
| AI/ML runtime | Python 3.11 | 3.11 | scikit-learn, Prophet, PyTorch |
| Anomaly detection | scikit-learn Isolation Forest | Latest | Point anomalies |
| Trend detection | Facebook Prophet | Latest | Time-series trends |
| Sequence anomaly | PyTorch LSTM | Latest | Sequential patterns |
| LLM (RCA) | Ollama + local model | Latest | No cloud dependency, air-gapped capable |
| Orchestration | Kubernetes (any cloud) | Latest | True portability |
| Dashboards | Grafana | Latest | Universal, any data source |
| Alerting | AlertManager | Latest | Battle-tested routing + dedup |
| Incident management | PagerDuty-compatible webhook | — | Works with any on-call tool |
| Remediation runner | Python + boto3 | Latest | AWS SDK for auto-remediation actions |

---

## Deployment Model

Nightwatch deploys as a self-contained Kubernetes application:

```
Option A: Sidecar deployment (recommended for Bayer)
  └── Same AWS account, separate namespace: nightwatch
  └── Uses IAM role with read + limited write permissions
  └── CloudWatch log exporter runs as DaemonSet

Option B: Standalone monitoring cluster
  └── Separate cluster (or EC2) in same VPC
  └── Accesses AWS APIs via cross-account role

Option C: Docker Compose (development/testing)
  └── docker-compose -f nightwatch/docker-compose.yml up
```

**IAM Permissions Required (minimal):**
```json
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricData",
    "cloudwatch:ListMetrics",
    "logs:FilterLogEvents",
    "logs:GetLogEvents",
    "s3:GetBucketMetrics",
    "s3:ListBucket",
    "states:ListExecutions",
    "states:DescribeExecution",
    "glue:GetJobRuns",
    "glue:GetJob",
    "dynamodb:DescribeTable",
    "dynamodb:ListTables",
    "ec2:DescribeInstances",
    "transfer:ListServers",
    "events:ListRules"
  ],
  "Resource": "*"
}
```

Remediation also needs:
- `states:StartExecution` (restart Step Functions)
- `glue:StartJobRun` (restart Glue jobs)
- `ec2:StartInstances` / `ec2:StopInstances` (RODB-EC2 restart, only if approved)
- `dynamodb:UpdateTable` (auto-scale DynamoDB)

---

## Implementation Phases

### Phase 1 (Week 1-2): Data Collection + Basic Alerting
- [ ] Deploy OpenTelemetry collector, Prometheus, Fluent Bit in `nightwatch` namespace
- [ ] Configure `prometheus-cloudwatch-exporter` for all ModelN.io components
- [ ] Set up VictoriaMetrics + OpenSearch
- [ ] Grafana dashboards: Pipeline Overview + S3 Data Flow
- [ ] AlertManager with Slack + email routing
- [ ] Basic threshold alerts for all P1 conditions
- [ ] Validate: simulate a Glue job failure → alert fires within 5min

### Phase 2 (Week 3-4): AI Anomaly Detection
- [ ] Collect 1 week of baseline data
- [ ] Train Prophet models on Glue job duration, S3 object counts
- [ ] Deploy Isolation Forest for point anomalies (file counts, Lambda errors)
- [ ] Deploy LSTM Autoencoder for Step Function sequence anomalies
- [ ] Anomaly alerting with confidence scores in Grafana
- [ ] Tune thresholds: target < 5% false positive rate

### Phase 3 (Week 5-6): Auto-Remediation + RCA
- [ ] Build playbooks for each ModelN.io failure mode (see Layer 4 table)
- [ ] Deploy remediation engine with dry-run mode
- [ ] Test auto-fix for P2/P3: Glue job restart, DynamoDB auto-scale
- [ ] Deploy Ollama + local LLM for RCA summaries
- [ ] LLM RCA tested against last 10 real incidents
- [ ] Enable production auto-remediation (P2/P3 only)
- [ ] Go-live review with Bayer team

---

## Key Design Decisions

1. **Zero CloudWatch vendor lock-in**: All metrics pulled via `prometheus-cloudwatch-exporter` into standard Prometheus format. If Bayer moves to Azure/GCP, swap the exporter — nothing else changes.

2. **Causal graph from drawio**: The 96 edges in `ModelN.io.drawio` directly map to the causal dependency graph used by the RCA engine. If a Glue enriched job fails and S3 raw is empty, the RCA engine traverses upstream and identifies the raw job as root cause.

3. **SFTP = P1 by default**: McKesson and AXWAY are partners with SLAs. Any missed outbound delivery is P1. Any missed inbound delivery from them is P2 (since we don't control their systems).

4. **DynamoDB reference data is a silent killer**: 10 data entity types flow through DynamoDB (customers, products, price lists, etc). Schema changes or throttling here cause silent data quality issues in all downstream jobs. Special monitoring on item counts + throttling.

5. **Audit Lambda monitoring**: `bay-modeln-capture-audit-info` errors are treated as P2 (not P3) because if audit fails, there's no compliance trail — even if the pipeline completed successfully.

6. **No cloud-native alerting**: Despite being in AWS, Nightwatch deliberately avoids CloudWatch Alarms and SNS. This keeps the monitoring config portable and centralized in Grafana/AlertManager rather than scattered across AWS console.
