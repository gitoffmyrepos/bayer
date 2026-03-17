# StackIT vs AWS — Deep Comparative Analysis
## For GDPR-Compliant Hybrid Storage Architecture

> **Authored by:** Nova ⚡  
> **Date:** 2026-03-16  
> **Context:** Kelvin's Bayer pharma revenue management pipeline (ModelN.io) on AWS needs GDPR-compliant storage for European data residency

---

## Executive Summary

**Yes — running the application on AWS with storage in StackIT is architecturally sound and operationally viable.**

StackIT provides fully S3-compatible object storage with standard access key/secret authentication, meaning **boto3 requires zero code changes** beyond pointing `endpoint_url` to StackIT's EU endpoint. Managed PostgreSQL (PostgreSQL Flex), MongoDB Flex, Redis, and MariaDB are all available with Terraform support.

The architecture works like this:
- **AWS** handles compute (Glue ETL, Lambda, EC2) and non-GDPR-sensitive data
- **StackIT EU01 (Germany)** stores PII, financial records, and any data with EU residency requirements
- **Network path:** AWS → HTTPS → `object.storage.eu01.onstackit.cloud` (public internet, TLS 1.3)
- **No private peering exists today** between AWS and StackIT — data travels over the public internet (encrypted)

**Verdict:** Strongly conditional YES. Best for storage workloads where cross-cloud latency is acceptable (object storage reads/writes, async database access). Not ideal for latency-sensitive OLTP workloads querying StackIT from AWS real-time.

---

## StackIT Overview

| Attribute | Details |
|-----------|---------|
| **Parent Company** | Schwarz Group (Lidl + Kaufland retail conglomerate, ~€140B revenue) |
| **Division** | Schwarz Digits (IT/Digital arm) |
| **Legal Entity** | Schwarz Digits Cloud GmbH & Co. KG |
| **Headquarters** | Neckarsulm, Baden-Württemberg, Germany |
| **Founded** | Internally 2018 (as Schwarz IT), externally available ~2022 |
| **Target Market** | European enterprises, public sector, healthcare, retail, SMB |
| **Positioning** | "European Hyperscaler" — digital sovereignty focus |
| **Notable Customers** | Sana Clinics, internal Schwarz Group companies |

### Data Centers & Regions

| Region ID | Location | Country | Availability Zones |
|-----------|----------|---------|-------------------|
| **EU01** | Neckarsulm (DC01) + Ellhofen (DC08) | Germany 🇩🇪 | 3 AZs |
| **EU02** | Ostermiething (DC10) | Austria 🇦🇹 | 3 AZs |
| **Planned** | Lübbenau | Germany 🇩🇪 | TBD |

- **AZ latency:** ~0.5ms within a region
- **Metro AZ:** Automatic cross-AZ distribution for VMs and Block Storage
- **Data governance:** 100% EU-based — no data leaves Germany/Austria

### GDPR & Security Certifications

| Certification | Status | Scope |
|---------------|--------|-------|
| **GDPR (Art. 28 DPA)** | ✅ Fully compliant | All services |
| **ISO 27001** (TÜV SÜD) | ✅ Certified | ISMS-wide |
| **ISO 20000** (TÜV SÜD) | ✅ Certified | IT Service Management |
| **ISO 50001** (TÜV SÜD) | ✅ Certified | Energy Management (DC10) |
| **BSI C5 Type 2** | ✅ Certified | IaaS, DBaaS, K8s, Object Storage, Secrets |
| **TÜVIT Trusted Site Infrastructure** | ✅ Certified | Physical data center security |

**C5 Type 2 certified services specifically:**  
Compute Engine, Block Storage, Network & Security, Object Storage, Kubernetes Engine (SKE), PostgreSQL Flex, MongoDB Flex, SQLServer Flex, Secrets Manager, Observability

**Key GDPR advantage over AWS:**  
StackIT is 100% German-incorporated with no US parent company → no CLOUD Act exposure. AWS (US-domiciled) could theoretically be compelled by US authorities to provide data even for EU-stored data.

---

## Architecture Pattern: AWS Compute + StackIT Storage

```
╔══════════════════════════════════════════════════════════════╗
║                     AWS US-East-1                            ║
║                                                              ║
║  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐  ║
║  │  AWS Glue    │────▶│   Lambda     │────▶│  SQS / SNS  │  ║
║  │  ETL Jobs    │     │  Processors  │     │  (non-PII)  │  ║
║  └──────────────┘     └──────┬───────┘     └─────────────┘  ║
║                              │                               ║
║              ┌───────────────┼─────────────────────┐         ║
║              │ Non-sensitive │ GDPR-sensitive data  │         ║
║              ▼               ▼                      │         ║
║         ┌────────┐    boto3/SDK call                 │         ║
║         │ AWS S3 │    endpoint_url=StackIT           │         ║
║         │ (raw)  │           │                      │         ║
║         └────────┘           │                      │         ║
╚══════════════════════════════│══════════════════════╝         ║
                               │                                 
                     HTTPS / TLS 1.3                             
                    (public internet)                            
                    ~10-30ms latency                             
                    AWS us-east-1 → EU01                         
                    ~80-100ms latency                            
                               │                                 
╔══════════════════════════════▼══════════════════════════════╗
║                  StackIT EU01 (Germany South)                ║
║                                                              ║
║  ┌──────────────────┐    ┌──────────────────────────────┐   ║
║  │  Object Storage  │    │      PostgreSQL Flex          │   ║
║  │  (S3-compatible) │    │  (PII, financial records)     │   ║
║  │                  │    │  3 replicas, HA               │   ║
║  │  Buckets:        │    └──────────────────────────────┘   ║
║  │  - pii-data      │    ┌──────────────────────────────┐   ║
║  │  - chargebacks   │    │      MongoDB Flex             │   ║
║  │  - medicaid-eu   │    │  (document storage, EU data)  │   ║
║  └──────────────────┘    └──────────────────────────────┘   ║
║                                                              ║
║  ISO 27001 ✅  BSI C5 ✅  GDPR ✅  100% Germany 🇩🇪          ║
╚══════════════════════════════════════════════════════════════╝
```

### Latency Considerations

| Route | Estimated Latency | Notes |
|-------|------------------|-------|
| AWS eu-central-1 → StackIT EU01 | ~8-15ms | Frankfurt to Neckarsulm, same region pair |
| AWS eu-west-1 → StackIT EU01 | ~20-30ms | Ireland to Germany |
| AWS us-east-1 → StackIT EU01 | ~80-100ms | Cross-Atlantic |
| StackIT EU01 AZ-to-AZ | ~0.5ms | Same region internal |

> ⚠️ **Critical:** For the Bayer ModelN.io pipeline running on AWS US-East-1, expect 80-100ms latency to StackIT storage. This is fine for batch ETL, object storage writes, and async processing. **Problematic for synchronous query patterns.**

### Network Connectivity Options

| Option | Status | Details |
|--------|--------|---------|
| Public Internet (HTTPS) | ✅ Available | Default, TLS 1.3, works today |
| AWS Direct Connect → StackIT | ❌ Not available | No StackIT-AWS dedicated link |
| VPN (Site-to-Site) | ⚠️ Possible | You manage VPN gateway on both ends |
| DE-CIX Peering | ✅ Ostermiething is DE-CIX enabled | Possible for StackIT EU02; requires colocation |

**Today's reality:** Traffic goes over the public internet. StackIT does not offer an AWS Direct Connect equivalent for cross-cloud peering (unlike GCP's Partner Interconnect with AWS). This is the biggest architectural risk.

---

## Service Comparison Table

| Category | AWS Service | StackIT Equivalent | StackIT Maturity (1-5) | Notes |
|----------|-------------|-------------------|----------------------|-------|
| **Object Storage** | S3 | STACKIT Object Storage | ⭐⭐⭐⭐ (4/5) | Fully S3-compatible; AES256 at-rest; access key/secret auth; endpoint: `object.storage.eu01.onstackit.cloud` |
| **Block Storage** | EBS | STACKIT Block Storage | ⭐⭐⭐⭐ (4/5) | SSD-based, Metro AZ replication available; BSI C5 certified |
| **File Storage** | EFS | STACKIT File Storage | ⭐⭐⭐ (3/5) | NFS-based; less mature than AWS EFS |
| **Backup Storage** | S3 Glacier | STACKIT Backup/Archiving Service | ⭐⭐⭐ (3/5) | Audit-proof archiving; GDPR-compliant long-term storage |
| **Managed PostgreSQL** | RDS/Aurora | STACKIT PostgreSQL Flex | ⭐⭐⭐⭐⭐ (5/5) | BSI C5 certified; 3-replica HA; daily backups; full Terraform support; point-in-time recovery |
| **Managed MySQL** | RDS MySQL | STACKIT MariaDB | ⭐⭐⭐ (3/5) | MariaDB (MySQL-compatible); full TF support; no MySQL 8.x native |
| **Managed MongoDB** | DocumentDB | STACKIT MongoDB Flex | ⭐⭐⭐⭐ (4/5) | BSI C5 certified; full Terraform support; true MongoDB (not compatibility layer) |
| **Managed Redis** | ElastiCache | STACKIT Redis | ⭐⭐⭐⭐ (4/5) | Full Terraform support |
| **Search** | OpenSearch Service | STACKIT OpenSearch | ⭐⭐⭐ (3/5) | Full Terraform support |
| **Message Queue** | SQS/MSK | STACKIT RabbitMQ | ⭐⭐⭐ (3/5) | AMQP-based; no Kafka equivalent (yet); full Terraform support |
| **Container Registry** | ECR | STACKIT Container Registry | ⭐⭐⭐ (3/5) | Available via portal; Terraform coverage through `git` resource |
| **Kubernetes** | EKS | STACKIT SKE (Kubernetes Engine) | ⭐⭐⭐⭐ (4/5) | BSI C5 certified; full Terraform support |
| **Serverless** | Lambda | ❌ Not available | N/A | No FaaS offering; use SKE with event-driven containers |
| **DNS** | Route 53 | STACKIT DNS | ⭐⭐⭐ (3/5) | Full Terraform support (zones + record sets) |
| **Load Balancer** | ALB/NLB | STACKIT Load Balancer + App LB | ⭐⭐⭐ (3/5) | Both `loadbalancer` and `application_load_balancer` in Terraform |
| **CDN** | CloudFront | STACKIT CDN | ⭐⭐⭐ (3/5) | Full Terraform support (distributions, custom domains) |
| **Secrets Manager** | Secrets Manager | STACKIT Secrets Manager | ⭐⭐⭐⭐ (4/5) | BSI C5 certified; full Terraform support |
| **Key Management** | KMS | STACKIT KMS | ⭐⭐⭐ (3/5) | Full Terraform support (keys, keyrings, wrapping keys) |
| **IAM** | IAM | STACKIT IAM (Authorization) | ⭐⭐⭐ (3/5) | Project-based; custom roles in Terraform; less granular than AWS IAM |
| **Monitoring/Observability** | CloudWatch | STACKIT Observability | ⭐⭐⭐ (3/5) | Prometheus/Grafana based; BSI C5; Terraform support |
| **Logging** | CloudWatch Logs | STACKIT LogMe / Logs | ⭐⭐⭐ (3/5) | Full Terraform support |
| **SQL Server** | RDS SQL Server | STACKIT SQL Server Flex | ⭐⭐⭐ (3/5) | BSI C5 certified; no Terraform resource found |
| **Edge Compute** | Lambda@Edge | STACKIT EdgeCloud | ⭐⭐ (2/5) | Terraform support present; early-stage |
| **GPU Compute** | EC2 p-series | STACKIT Compute Engine GPU | ⭐⭐⭐ (3/5) | Available; pricing not published |
| **AI/Data** | SageMaker | STACKIT AI Model Serving, Dremio | ⭐⭐ (2/5) | Early stage; Dremio-based data lakehouse |
| **Cloud Foundry** | Elastic Beanstalk | STACKIT SCAP / SCF | ⭐⭐⭐ (3/5) | Cloud Foundry-based PaaS; BSI C5 certified |
| **VPC/Networking** | VPC | STACKIT Network + Security Groups | ⭐⭐⭐ (3/5) | Networks, subnets, security groups, routing tables — all in Terraform |
| **Windows Server** | EC2 Windows | STACKIT Windows Server | ⭐⭐⭐ (3/5) | Pre-licensed Windows VMs |

---

## Terraform Provider Comparison

| Dimension | AWS Provider | StackIT Provider |
|-----------|-------------|-----------------|
| **Registry URL** | `hashicorp/aws` | `stackitcloud/stackit` |
| **Tier** | Official (HashiCorp partner) | Community |
| **Current Version** | ~5.x | **0.88.0** (as of 2026-03-16) |
| **Resources Count** | ~1,100+ | ~80-100 (estimated) |
| **Data Sources Count** | ~600+ | ~70 (counted from registry) |
| **Total Downloads** | 4+ billion | **6.49 million** |
| **Release Frequency** | Weekly | **Weekly** (v0.88.0 released same day as this analysis!) |
| **GitHub Repo** | `hashicorp/terraform-provider-aws` | `stackitcloud/terraform-provider-stackit` |
| **Documentation Quality** | Excellent | Good (improving rapidly) |
| **Community Size** | Massive (global) | Small-medium (EU-focused) |
| **Versioning** | Stable semver, 5.x | Pre-1.0 (0.88.x) — **breaking changes possible** |

> ⚠️ **Pre-1.0 Warning:** The StackIT provider is at v0.88.0 — still pre-1.0. Breaking changes between minor versions have occurred historically. Pin to specific versions in your `required_providers` block.

### StackIT Terraform Coverage — Service by Service

**✅ Full Terraform Resource Support:**
- `objectstorage_bucket`, `objectstorage_credential`, `objectstorage_credentials_group`
- `postgresflex_instance`, `postgresflex_database`, `postgresflex_user`
- `mongodbflex_instance`, `mongodbflex_user`
- `mariadb_instance`, `mariadb_credential`
- `redis_instance`, `redis_credential`
- `rabbitmq_instance`, `rabbitmq_credential`
- `opensearch_instance`, `opensearch_credential`
- `server`, `server_backup_schedule`, `server_update_schedule`
- `network`, `network_area`, `network_area_route`, `network_interface`
- `security_group`, `security_group_rule`
- `public_ip`, `routing_table`, `routing_table_route`
- `loadbalancer`, `application_load_balancer`
- `dns_zone`, `dns_record_set`
- `cdn_distribution`, `cdn_custom_domain`
- `secretsmanager_instance`, `secretsmanager_user`
- `kms_key`, `kms_keyring`, `kms_wrapping_key`
- `observability_instance`, `observability_alertgroup`, `observability_scrapeconfig`
- `logme_instance`, `logme_credential`
- `logs_instance`, `logs_access_token`
- `resourcemanager_project`, `resourcemanager_folder`
- `authorization_project_custom_role`
- `affinity_group`, `key_pair`, `image`
- `edgecloud_instances`, `edgecloud_plans`
- `scf_organization`, `scf_platform`

**⚠️ Partial / Unclear Terraform Coverage:**
- SKE (Kubernetes Engine) — data source likely exists but not confirmed in truncated output
- Container Registry — `git` resource present but dedicated CR resource unclear
- SQL Server Flex — not found in registry docs (BSI C5 certified but may need portal)

**❌ No Terraform Resource (portal only or not available):**
- Lambda equivalent — does not exist
- Serverless FaaS — not offered
- Direct SQL Server Flex resource (check latest provider docs)

---

## Pricing Comparison

> Prices as of March 2026. StackIT prices in EUR (net, excl. VAT). AWS in USD.
> Monthly = hourly rate × 720 hours.

### Object Storage

| Metric | AWS S3 (eu-central-1) | StackIT EU01 | StackIT EU02 | Notes |
|--------|-----------------------|-------------|-------------|-------|
| Storage (per GB/month) | $0.023 | **€0.0266** (~$0.029) | €0.0280 | StackIT slightly higher |
| Storage (Archiving tier) | ~$0.004 (Glacier) | **€0.0266** | Same | No separate cold tier currently |
| PUT/GET requests | $0.004/10k PUTs | Not published | — | Check latest pricing |
| Data egress to internet | $0.09/GB | **Not published** | — | Request quote from StackIT |
| Data egress within EU | $0.02/GB | **Likely lower** | — | Same region transfers free likely |

### Compute

| Instance Type | AWS (eu-central-1) | StackIT EU01 | Monthly Savings |
|--------------|--------------------|-------------|----------------|
| 1 vCPU, 4GB (General) | m6i.large ~$70/mo | g1.1: **€27.30/mo** | ~60% cheaper |
| 2 vCPU, 8GB (General) | m6i.large ~$96/mo | g1.2: **€54.59/mo** | ~43% cheaper |
| 4 vCPU, 16GB (General) | m6i.xlarge ~$140/mo | g1.3: **€109.18/mo** | ~22% cheaper |
| 8 vCPU, 32GB (General) | m6i.2xlarge ~$280/mo | g1.4: **€218.37/mo** | ~22% cheaper |
| 2 vCPU, 16GB (Memory) | r6i.large ~$115/mo | m2i.2: **€97.33/mo** | ~15% cheaper |

### Managed Databases

| Service | AWS Equivalent | AWS Price/Month | StackIT Price/Month | Notes |
|---------|---------------|-----------------|--------------------|-|
| PostgreSQL Flex 2CPU/4GB HA | RDS db.t3.medium Multi-AZ | ~$100/mo | **€141.90/mo** (3-node replica) | StackIT: 3 nodes vs AWS 2; higher but more HA |
| PostgreSQL Flex 4CPU/8GB HA | RDS db.m6g.large Multi-AZ | ~$180/mo | **€271.75/mo** (3 replicas) | StackIT more expensive for same compute |
| PostgreSQL Single (2CPU/4GB) | RDS db.t3.medium single | ~$50/mo | ~€70/mo (1 node) | Comparable |

> 💡 StackIT PostgreSQL pricing reflects 3-node replica clusters by default (HA). AWS Multi-AZ = 2 nodes. Cost comparison isn't apples-to-apples.

### Kubernetes

| Metric | AWS EKS | StackIT SKE | Notes |
|--------|---------|------------|-------|
| Control Plane | $0.10/hr (~$72/mo) | **Included in worker node pricing** | StackIT does not charge separately for control plane |
| Worker Nodes | EC2 pricing | Compute Engine pricing (see above) | ~15-22% cheaper on worker nodes |

---

## GDPR & Compliance Deep Dive

### StackIT Compliance Posture

| Requirement | StackIT | AWS |
|-------------|---------|-----|
| **Data residency (EU only)** | ✅ Guaranteed — Germany + Austria only | ⚠️ Available but requires explicit configuration; AWS is US-domiciled |
| **No CLOUD Act exposure** | ✅ German company, no US jurisdiction | ⚠️ Potential risk; AWS has committed to challenge orders but remains US-incorporated |
| **DPA (Art. 28 GDPR)** | ✅ Available | ✅ Available |
| **ISO 27001** | ✅ TÜV SÜD certified | ✅ Multiple certifications |
| **BSI C5 Type 2** | ✅ Broad service coverage | ✅ Also available |
| **GDPR-compliant DPA** | ✅ Standard offering | ✅ Standard offering |
| **Data encrypted at rest** | ✅ AES-256 (Object Storage) | ✅ AES-256 (S3) |
| **Data encrypted in transit** | ✅ TLS 1.3 | ✅ TLS 1.2/1.3 |
| **Customer-managed keys (BYOK)** | ✅ SSE-C for Object Storage | ✅ AWS KMS + SSE-C |
| **Audit logs** | ✅ Available | ✅ CloudTrail |
| **Schrems II compliant** | ✅ No transfer to 3rd countries | ⚠️ Requires SCCs/BCRs for EU→US transfers |

### For Bayer's Use Case (Pharma)

- **PII data** (patient info, chargeback recipients): StackIT strongly preferred — EU residency guaranteed
- **PHI (Protected Health Information)**: StackIT ISO 27001 + BSI C5 makes it suitable for healthcare data
- **Financial records** (Medicaid claims, price lists): StackIT's German jurisdiction removes US legal exposure
- **DPA Article 28 compliance**: StackIT can sign as a Data Processor under GDPR

---

## Hybrid Architecture: AWS + StackIT — Bayer Recommendation

### Data Segmentation Strategy

```
┌─────────────────────────────────────────────────────────────┐
│ STAYS ON AWS (no EU residency required)                      │
│ • Raw vendor data before normalization (non-EU)              │
│ • Processing state/intermediate results                      │
│ • AWS Glue catalog metadata                                  │
│ • Lambda function code and configs                           │
│ • Non-EU customer data                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MOVES TO STACKIT EU01 (GDPR / EU residency required)         │
│ • EU patient/customer PII                                    │
│ • Medicaid EU claims data                                    │
│ • European chargeback records                                │
│ • Price lists with EU customer data                          │
│ • Any data subject to EU GDPR Article 44+ restrictions       │
└─────────────────────────────────────────────────────────────┘
```

### boto3 Configuration for StackIT Object Storage

StackIT uses **access key + secret key authentication** (same as AWS), so boto3 requires only an `endpoint_url` change:

```python
import boto3
from botocore.config import Config

# StackIT Object Storage configuration
stackit_config = {
    "endpoint_url": "https://object.storage.eu01.onstackit.cloud",
    "aws_access_key_id": "YOUR_STACKIT_ACCESS_KEY",      # From StackIT Portal
    "aws_secret_access_key": "YOUR_STACKIT_SECRET_KEY",  # From StackIT Portal
    "config": Config(
        signature_version="s3v4",
        region_name="eu01",  # StackIT region
    )
}

# Create client — identical API to AWS S3
s3_client = boto3.client("s3", **stackit_config)

# All standard S3 operations work:
s3_client.put_object(Bucket="my-eu-bucket", Key="data/file.parquet", Body=data)
s3_client.get_object(Bucket="my-eu-bucket", Key="data/file.parquet")
s3_client.list_objects_v2(Bucket="my-eu-bucket", Prefix="data/")
```

**Credential Management:**
- Credentials are created per StackIT **project** (not per bucket)
- Use StackIT Portal or Terraform `objectstorage_credential` resource
- Store in AWS Secrets Manager and inject at Lambda/Glue runtime

```python
# Recommended pattern: fetch StackIT creds from AWS Secrets Manager
import json
import boto3

aws_sm = boto3.client("secretsmanager", region_name="us-east-1")
stackit_creds = json.loads(
    aws_sm.get_secret_value(SecretId="stackit/object-storage/eu01")["SecretString"]
)

stackit_s3 = boto3.client("s3",
    endpoint_url="https://object.storage.eu01.onstackit.cloud",
    aws_access_key_id=stackit_creds["access_key"],
    aws_secret_access_key=stackit_creds["secret_key"],
    config=Config(signature_version="s3v4", region_name="eu01")
)
```

### Terraform Infrastructure for Bayer

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    stackit = {
      source  = "stackitcloud/stackit"
      version = "~> 0.88.0"  # Pin to avoid breaking changes
    }
  }
}

provider "stackit" {
  # Auth via service account token or OAuth2
  # Set via STACKIT_SERVICE_ACCOUNT_TOKEN env var
}

# StackIT Object Storage bucket for EU PII data
resource "stackit_objectstorage_bucket" "eu_pii" {
  project_id = var.stackit_project_id
  name       = "bayer-eu-pii-data"
}

# Access credentials for the bucket
resource "stackit_objectstorage_credentials_group" "eu_pii" {
  project_id = var.stackit_project_id
  name       = "bayer-eu-pii-creds"
}

resource "stackit_objectstorage_credential" "eu_pii" {
  project_id         = var.stackit_project_id
  credentials_group_id = stackit_objectstorage_credentials_group.eu_pii.credentials_group_id
}

# Store StackIT creds in AWS Secrets Manager for Lambda/Glue access
resource "aws_secretsmanager_secret" "stackit_creds" {
  name = "stackit/object-storage/eu01"
}

resource "aws_secretsmanager_secret_version" "stackit_creds" {
  secret_id = aws_secretsmanager_secret.stackit_creds.id
  secret_string = jsonencode({
    access_key = stackit_objectstorage_credential.eu_pii.access_key
    secret_key = stackit_objectstorage_credential.eu_pii.secret_key
    endpoint   = "https://object.storage.eu01.onstackit.cloud"
  })
}

# StackIT PostgreSQL Flex for EU structured data
resource "stackit_postgresflex_instance" "eu_db" {
  project_id  = var.stackit_project_id
  name        = "bayer-eu-postgres"
  version     = "15"
  flavor_id   = "4.8"  # 4 vCPU, 8GB RAM
  replicas    = 3      # HA cluster

  network = {
    id = stackit_network.eu.id
  }
}
```

### S3 URL Formats

Both path-style and virtual-hosted style are supported:

```
# Virtual Hosted Style (preferred):
https://my-bucket.object.storage.eu01.onstackit.cloud/my-object

# Path Style:
https://object.storage.eu01.onstackit.cloud/my-bucket/my-object

# EU02 (Austria):
https://object.storage.eu02.onstackit.cloud
```

---

## Migration Complexity

### From AWS S3 to StackIT Object Storage

**Effort Level:** Low-Medium

1. **SDK compatibility:** `boto3` works out of the box with `endpoint_url` swap
2. **Data migration options:**
   - `rclone`: `rclone copy s3:my-bucket stackit:my-eu-bucket` (handles S3-compatible automatically)
   - `aws s3 sync` with `--endpoint-url`: Does NOT support non-AWS endpoints natively
   - `rclone` is the recommended tool for cross-cloud S3-compatible migration
3. **Feature gaps to check:**
   - Bucket policies: StackIT uses project-level credentials; check policy feature parity
   - Presigned URLs: Check if supported (likely yes for S3-compatible)
   - Multipart upload: Supported (standard S3 API)
   - Object versioning: Verify availability

### Terraform Migration

```hcl
# Before (AWS S3)
resource "aws_s3_bucket" "data" { ... }

# After (StackIT) - same Terraform run, different provider
resource "stackit_objectstorage_bucket" "data" { ... }
```

**Provider version stability risk:** StackIT provider is pre-1.0. Resource schema changes between versions have occurred. Use `version = "= 0.88.0"` to pin.

### Operational Complexity Added

| Concern | Detail |
|---------|--------|
| **Two cloud portals** | AWS Console + StackIT Portal |
| **Two billing accounts** | Separate invoices; need cost allocation tracking |
| **Two credential systems** | AWS IAM + StackIT project-level credentials |
| **Two monitoring systems** | CloudWatch + StackIT Observability |
| **Network dependency** | Data pipeline depends on cross-cloud internet connectivity |
| **Support model** | AWS Enterprise Support + separate StackIT support contract |
| **Terraform state** | Single state file can manage both providers simultaneously ✅ |

---

## Recommendation

### Should Bayer Use StackIT for EU-Regulated Storage?

**✅ YES — with the following conditions:**

**Recommended use cases for StackIT:**
1. **EU PII object storage** — patient/customer records required to stay in EU
2. **PostgreSQL Flex** — structured EU data that needs SQL + GDPR guarantees
3. **MongoDB Flex** — EU document data storage
4. **Archiving Service** — audit-proof, long-term retention of EU financial/medical records

**Keep on AWS:**
1. All compute (Glue ETL, Lambda, EC2) — no GDPR issue, processing happens in flight
2. Non-EU data (US chargeback records, US Medicaid data)
3. AWS-native integrations (Step Functions, EventBridge, SageMaker pipelines)
4. Anything with sub-10ms latency requirements

**Avoid StackIT for:**
- Real-time OLTP queries from AWS US-East-1 (80-100ms cross-Atlantic is too slow)
- Kafka/Redpanda replacement (StackIT only has RabbitMQ)
- Lambda/serverless (not offered)
- Heavy data analytics (Glue + S3 on AWS is more mature than StackIT Dremio for this)

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Cross-cloud internet latency | Medium | Use async patterns; avoid sync queries from US to StackIT |
| No direct peering (AWS↔StackIT) | Medium | Accept latency or evaluate colocation via DE-CIX |
| Provider pre-1.0 breaking changes | Medium | Pin Terraform provider version |
| Two-cloud operational complexity | Low-Medium | Document runbooks; consolidate monitoring |
| StackIT service gaps (Lambda, Kafka) | Low | Keep those workloads on AWS |
| Egress costs (AWS→StackIT) | Medium | Measure actual data transfer volume; negotiate StackIT contract |
| StackIT company risk | Low | Backed by Schwarz Group (€140B revenue); financially stable |

---

## References

1. **StackIT Main Site:** https://stackit.com/en
2. **StackIT Products Catalog:** https://stackit.com/en/products
3. **StackIT Regions & AZs:** https://docs.stackit.cloud/platform/regions/
4. **StackIT Object Storage Docs:** https://docs.stackit.cloud/products/storage/object-storage/
5. **StackIT Object Storage Pricing:** https://stackit.com/en/products/storage/stackit-object-storage
6. **StackIT PostgreSQL Flex Pricing:** https://stackit.com/en/products/database/stackit-postgresql-flex
7. **StackIT Compute Pricing:** https://stackit.com/en/products/compute-engine/stackit-compute-engine
8. **StackIT GDPR Certificates:** https://stackit.com/en/why-stackit/benefits/certificates
9. **StackIT Data Sovereignty:** https://stackit.com/en/why-stackit/benefits/data-sovereignty
10. **Terraform Registry — StackIT Provider:** https://registry.terraform.io/providers/stackitcloud/stackit/latest
11. **Terraform Provider GitHub:** https://github.com/stackitcloud/terraform-provider-stackit
12. **StackIT OpenInfra Profile:** https://openinfra.org/blog/openinfra-member-stackit/
13. **The Stack — StackIT Coverage:** https://www.thestack.technology/everyone-was-laughing-now-they-take-us-more-seriously-europes-biggest-retailer-turns-cloud-provider/

---

*Analysis by Nova ⚡ | Research date: 2026-03-16 | Terraform provider version verified: v0.88.0*
