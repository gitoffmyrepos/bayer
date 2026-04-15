---
marp: true
theme: gaia
class: lead
paginate: true
backgroundColor: #fff
backgroundImage: url('https://marp.app/assets/hero-background.svg')
size: 16:9
style: |
  section {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 22px;
    padding: 30px 40px 50px 40px;
    overflow: hidden;
  }
  section.lead {
    padding: 40px 50px 60px 50px;
  }
  section.lead h1 {
    font-size: 2.2em;
    color: #1a1a2e;
  }
  section.lead h2 {
    color: #16213e;
    font-size: 1.2em;
  }
  section h1 {
    color: #1a1a2e;
    border-bottom: 3px solid #0f3460;
    padding-bottom: 8px;
    font-size: 1.5em;
    margin-bottom: 12px;
  }
  section h2 {
    color: #0f3460;
    font-size: 1.1em;
    margin-top: 10px;
    margin-bottom: 8px;
  }
  table {
    font-size: 0.62em;
    width: 100%;
    margin-top: 5px;
    margin-bottom: 5px;
  }
  th {
    background-color: #0f3460;
    color: white;
    padding: 5px 6px;
  }
  td {
    padding: 4px 6px;
  }
  code {
    background-color: #e8f4f8;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.8em;
  }
  pre {
    font-size: 0.65em;
    margin: 5px 0;
    padding: 8px;
  }
  ul, ol {
    font-size: 0.88em;
    margin: 4px 0;
    line-height: 1.4;
  }
  li {
    margin-bottom: 2px;
  }
  p {
    margin: 4px 0;
    line-height: 1.4;
  }
  .green { color: #27ae60; font-weight: bold; }
  .red { color: #e74c3c; font-weight: bold; }
  .orange { color: #f39c12; font-weight: bold; }
  blockquote {
    border-left: 4px solid #0f3460;
    background: #f0f4ff;
    padding: 6px 14px;
    font-size: 0.78em;
    margin: 6px 0;
  }
  em {
    color: #555;
  }
  section::after {
    font-size: 0.6em;
    padding-bottom: 20px;
  }
---

# StackIT vs AWS
## Deep Comparative Analysis
### GDPR-Compliant Hybrid Storage Architecture

**Bayer Pharma Revenue Management Pipeline**
*ModelN.io on AWS + EU Data Residency*

*Prepared by: Nova | March 2026*

---

# Executive Summary

**Yes** — running compute on AWS with storage on StackIT is **architecturally sound**.

| Component | Where | Why |
|-----------|-------|-----|
| **Compute** | AWS | Glue ETL, Lambda, EC2 — no GDPR issue |
| **EU PII Storage** | StackIT EU01 | 100% German jurisdiction, no CLOUD Act |
| **Network** | HTTPS/TLS 1.3 | Public internet, ~10-100ms depending on route |

> **Verdict:** Strongly conditional YES. Best for storage workloads where cross-cloud latency is acceptable.

---

# What is StackIT?

| Attribute | Details |
|-----------|---------|
| **Parent** | Schwarz Group (Lidl + Kaufland, ~**€140B** revenue) |
| **Division** | Schwarz Digits (IT/Digital arm) |
| **HQ** | Neckarsulm, Germany |
| **Founded** | 2018 internally, public ~2022 |
| **Positioning** | "European Hyperscaler" — digital sovereignty |
| **Customers** | Sana Clinics, Schwarz Group internal |

**Two regions:** EU01 (Germany), EU02 (Austria) — 3 AZs each
**Data governance:** 100% EU-based — data never leaves Germany/Austria

---

# GDPR & Security Certifications

| Certification | StackIT | AWS |
|--------------|---------|-----|
| **GDPR (Art. 28 DPA)** | ✅ Fully compliant | ✅ Available |
| **ISO 27001** | ✅ TUV SUD certified | ✅ Certified |
| **BSI C5 Type 2** | ✅ Broad coverage | ✅ Available |
| **No CLOUD Act exposure** | ✅ German company | ⚠️ US-domiciled |
| **Schrems II compliant** | ✅ No 3rd-country transfers | ⚠️ Requires SCCs/BCRs |
| **Data encrypted at rest** | ✅ AES-256 | ✅ AES-256 |
| **Customer-managed keys** | ✅ SSE-C | ✅ KMS + SSE-C |

> **Key advantage:** StackIT = German company, no US parent = **zero CLOUD Act exposure**

---

# Architecture: AWS Compute + StackIT Storage

```
  ┌──────────── AWS US-East-1 ────────────┐
  │  Glue ETL → Lambda → SQS/SNS          │
  │       │              │                 │
  │   Non-PII        GDPR data            │
  │       ▼              ▼                 │
  │    AWS S3      boto3 → StackIT         │
  └──────────────────────┼─────────────────┘
                         │
              HTTPS / TLS 1.3
              ~80-100ms latency
                         │
  ┌──────── StackIT EU01 (Germany) ────────┐
  │  Object Storage    PostgreSQL Flex     │
  │  (S3-compatible)   (PII, financials)   │
  │                    MongoDB Flex        │
  │                    (EU documents)      │
  │                                        │
  │  ISO 27001 ✅  BSI C5 ✅  GDPR ✅       │
  └────────────────────────────────────────┘
```

---

# Latency Considerations

| Route | Latency | Suitable For |
|-------|---------|-------------|
| AWS **eu-central-1** → StackIT EU01 | **8-15ms** | Real-time queries OK |
| AWS **eu-west-1** → StackIT EU01 | **20-30ms** | Async processing |
| AWS **us-east-1** → StackIT EU01 | **80-100ms** | Batch ETL only |
| StackIT AZ-to-AZ | **0.5ms** | Internal workloads |

> **Critical for Bayer:** ModelN.io runs on US-East-1. Expect 80-100ms to StackIT.
> **Fine for:** Batch ETL, object storage writes, async processing
> **Not suitable for:** Synchronous OLTP query patterns

---

# Network Connectivity

| Option | Status | Details |
|--------|--------|---------|
| Public Internet (HTTPS) | ✅ Available | Default, TLS 1.3, works today |
| AWS Direct Connect | ❌ Not available | No StackIT-AWS dedicated link |
| Site-to-Site VPN | ⚠️ Possible | Self-managed on both ends |
| DE-CIX Peering | ✅ EU02 only | Requires colocation |

**Today's reality:** All traffic over public internet (encrypted).
No AWS Direct Connect equivalent exists for StackIT.

> This is the **biggest architectural risk** — no private peering.

---

# Service Comparison (Highlights)

| Category | AWS | StackIT | Maturity |
|----------|-----|---------|----------|
| **Object Storage** | S3 | S3-compatible | ⭐⭐⭐⭐ |
| **PostgreSQL** | RDS/Aurora | PostgreSQL Flex | ⭐⭐⭐⭐⭐ |
| **MongoDB** | DocumentDB | MongoDB Flex | ⭐⭐⭐⭐ |
| **Kubernetes** | EKS | SKE | ⭐⭐⭐⭐ |
| **Redis** | ElastiCache | Redis | ⭐⭐⭐⭐ |
| **Secrets** | Secrets Manager | Secrets Manager | ⭐⭐⭐⭐ |
| **Serverless** | Lambda | ❌ N/A | — |
| **Kafka** | MSK | ❌ (RabbitMQ only) | — |
| **AI/ML** | SageMaker | Early stage | ⭐⭐ |

---

# Pricing Comparison

## Compute — StackIT is 15-60% Cheaper

| Instance | AWS (eu-central-1) | StackIT EU01 | Savings |
|----------|-------------------|-------------|---------|
| 1 vCPU / 4GB | ~$70/mo | **€27/mo** | **~60%** |
| 2 vCPU / 8GB | ~$96/mo | **€55/mo** | **~43%** |
| 4 vCPU / 16GB | ~$140/mo | **€109/mo** | **~22%** |
| 8 vCPU / 32GB | ~$280/mo | **€218/mo** | **~22%** |

## Storage — Comparable

| Metric | AWS S3 | StackIT | Notes |
|--------|--------|---------|-------|
| Per GB/month | $0.023 | €0.027 | Slightly higher |
| Cold tier | $0.004 (Glacier) | €0.027 | No cold tier yet |

---

# Managed Database Pricing

| Service | AWS Price/Month | StackIT Price/Month | Notes |
|---------|----------------|--------------------|-|
| PostgreSQL 2CPU/4GB HA | ~$100 | **€142** (3 nodes) | StackIT: 3 replicas vs AWS 2 |
| PostgreSQL 4CPU/8GB HA | ~$180 | **€272** (3 replicas) | Higher but more redundant |
| PostgreSQL Single | ~$50 | ~€70 | Comparable |

> **Note:** StackIT defaults to **3-node replica clusters** for HA.
> AWS Multi-AZ = 2 nodes. Not apples-to-apples.

## Kubernetes
- AWS EKS control plane: **$72/mo**
- StackIT SKE: **Included in worker pricing** (free control plane)

---

# Terraform Provider Comparison

| Dimension | AWS | StackIT |
|-----------|-----|---------|
| Registry | `hashicorp/aws` | `stackitcloud/stackit` |
| Tier | **Official** | Community |
| Version | ~5.x (stable) | **0.88.0** (pre-1.0) |
| Resources | ~1,100+ | ~80-100 |
| Downloads | 4+ billion | 6.49 million |
| Release Frequency | Weekly | Weekly |

> ⚠️ **Pre-1.0 Warning:** Breaking changes possible between versions.
> Always pin: `version = "= 0.88.0"`

---

# boto3 — Zero Code Changes

```python
import boto3
from botocore.config import Config

# Just change endpoint_url — everything else works
stackit_s3 = boto3.client("s3",
    endpoint_url="https://object.storage.eu01.onstackit.cloud",
    aws_access_key_id="YOUR_STACKIT_KEY",
    aws_secret_access_key="YOUR_STACKIT_SECRET",
    config=Config(signature_version="s3v4",
                  region_name="eu01")
)

# All standard S3 operations work:
stackit_s3.put_object(Bucket="eu-pii", Key="data.parquet", Body=data)
stackit_s3.get_object(Bucket="eu-pii", Key="data.parquet")
```

> **Recommended:** Store StackIT creds in AWS Secrets Manager, inject at runtime.

---

# Data Segmentation Strategy

## Stays on AWS (no EU residency required)
- Raw vendor data before normalization (non-EU)
- Processing state / intermediate results
- AWS Glue catalog metadata
- Lambda function code and configs
- Non-EU customer data

## Moves to StackIT EU01 (GDPR required)
- EU patient/customer PII
- Medicaid EU claims data
- European chargeback records
- Price lists with EU customer data
- Any data subject to GDPR Article 44+ restrictions

---

# For Bayer Pharma Specifically

| Data Type | Recommendation | Why |
|-----------|---------------|-----|
| **Patient PII** | StackIT | EU residency guaranteed |
| **PHI (Protected Health)** | StackIT | ISO 27001 + BSI C5 = healthcare-ready |
| **Financial records** | StackIT | German jurisdiction, no US legal exposure |
| **Medicaid EU claims** | StackIT | GDPR Article 28 DPA compliant |
| **US chargeback data** | AWS | No EU residency requirement |
| **ETL compute** | AWS | Processing in flight, no GDPR issue |
| **ML/Analytics** | AWS | SageMaker + Glue more mature |

---

# Operational Complexity Added

| Concern | Impact | Mitigation |
|---------|--------|-----------|
| Two cloud portals | Low | Document runbooks |
| Two billing accounts | Low | Cost allocation tags |
| Two credential systems | Medium | Centralize in AWS Secrets Manager |
| Two monitoring systems | Medium | Consolidate dashboards |
| Network dependency | Medium | Async patterns, retry logic |
| Terraform state | Low | Single state manages both ✅ |

---

# Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Cross-cloud latency | **Medium** | Use async patterns, avoid sync US→EU queries |
| No direct peering | **Medium** | Accept latency or colocation via DE-CIX |
| Provider pre-1.0 changes | **Medium** | Pin Terraform provider version |
| StackIT service gaps | **Low** | Keep Lambda/Kafka on AWS |
| Egress costs | **Medium** | Measure volume, negotiate contract |
| Company risk | **Low** | Backed by €140B Schwarz Group |

---

<!-- _class: lead -->

# Recommendation

## ✅ YES — Use StackIT for EU-Regulated Storage

**Best for:**
- EU PII object storage (S3-compatible)
- PostgreSQL Flex (structured EU data + GDPR)
- MongoDB Flex (EU document data)
- Archiving (audit-proof, long-term retention)

**Keep on AWS:**
- All compute (Glue, Lambda, EC2)
- Non-EU data
- Latency-sensitive OLTP
- Serverless / Kafka workloads

---

<!-- _class: lead -->

# Next Steps

1. **Create StackIT account** → Request EU01 project
2. **Provision Object Storage** → Create PII bucket via Terraform
3. **Configure boto3** → Point `endpoint_url` to StackIT
4. **Migrate EU data** → `rclone copy` from AWS S3 to StackIT
5. **Set up PostgreSQL Flex** → 3-replica HA for structured EU data
6. **Store creds in AWS Secrets Manager** → Single source of truth
7. **Update Glue ETL jobs** → Route EU-sensitive writes to StackIT
8. **Monitor latency** → Track cross-cloud performance

---

<!-- _class: lead -->

# Thank You

**StackIT vs AWS — Hybrid Architecture**
*GDPR-Compliant Storage for Bayer Pharma*

Nova | StrategyBase | March 2026

*Full analysis: `STACKIT-VS-AWS-ANALYSIS.md`*
