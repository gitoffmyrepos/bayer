# Technical Environment Description: Model N Integration

## Document Information

| Field | Detail |
|-------|--------|
| Project | Model N – Pharma Revenue Management Integration |
| Organization | Bayer AG |
| Classification | Internal |
| Date | April 2026 |

---

## System Architecture and Interfaces

This document describes the technical environment required for the integration of the Model N Revenue Management software solution within Bayer's enterprise landscape. The solution connects multiple SAP source systems to Model N's SaaS platform through a multi-layered AWS-based data pipeline, ultimately delivering reporting and analytics through Galaxy Reports, the Model N user interface, and DBX-FI Reporting.

The architecture follows a five-layer design pattern:

- **Acquisition / Consumption Layer** — External source systems that produce data
- **Landing & Raw Layer** — Initial data receipt and raw storage
- **Enriched / Stage Layer** — Data validation, standardization, and transformation
- **Model N Layer** — The core SaaS application for pharmaceutical revenue management
- **Reporting Layer** — Data warehouse and business intelligence outputs

All layers are underpinned by a **Common Platform Services Layer** that provides governance, security, monitoring, DevOps, and infrastructure-as-code capabilities.

---

## External Source Systems (Acquisition / Consumption Layer)

The integration connects to the following enterprise source systems that feed data into the Model N platform:

### SAP Systems

| Source System | Full Name | Purpose | Data Types |
|---------------|-----------|---------|------------|
| **SAP P2R** | Procure-to-Receive | Procurement and receiving processes | Purchase orders, goods receipts, vendor invoices, material movements |
| **SAP P4S** | Plan-for-Supply | Supply chain planning and forecasting | Demand forecasts, supply plans, inventory positions, production schedules |
| **SAP MDM** | Master Data Management | Centralized master data governance | Customer master records, material master records, pricing hierarchies, organizational structures |
| **SAP H2R** | Hire-to-Retire | Human resources and personnel management | Employee records, organizational units, cost center assignments (relevant to revenue allocation) |

### Middleware and Payment Systems

| Source System | Purpose | Data Types |
|---------------|---------|------------|
| **Axway** | Managed File Transfer (MFT) and B2B integration gateway | External partner files, EDI transactions, secure file transfers from third-party data providers |
| **SAP A/P Payments** | Accounts Payable payment processing | Payment transactions, remittance data, chargeback information, rebate payment records |

### Data Ingestion Patterns

Two distinct ingestion patterns are used to move data from source systems into the AWS data platform:

- **Bulk / Historical Load** — Used during initial data migration and periodic full refreshes. Transfers large volumes of historical data (e.g., multi-year transaction histories) into the landing zone. This is typically used during the initial go-live cutover or when onboarding a new data source.

- **Incremental Load** — Used for ongoing, day-to-day operations. Captures only new or changed records since the last extraction. This reduces processing time, lowers costs, and ensures near-real-time data availability in the platform.

- **SFTP** — Secure File Transfer Protocol connections are used for file-based data exchanges, particularly with the Axway gateway and external partners who deliver flat files (CSV, XML, fixed-width).

---

## AWS Data Platform (Landing, Raw, and Enriched Layers)

The core data processing platform is built entirely on Amazon Web Services (AWS) and follows a medallion-style architecture (landing → raw → enriched/staged).

### Landing & Raw Layer

This layer receives data as-is from source systems and stores it in its original format before any transformation.

| Technology | Service | Role in the Architecture |
|------------|---------|--------------------------|
| **Amazon S3** (Landing Zone) | Object Storage | First point of receipt for all incoming data. Files from SAP systems, Axway, and SFTP are deposited here in their original format (CSV, XML, Parquet, JSON). Data is organized by source system, date, and batch identifier. |
| **Amazon S3** (Raw Zone) | Object Storage | Stores a copy of the landing data after initial cataloging and partitioning. This is the immutable historical record — data in the raw zone is never modified or deleted during normal operations. It serves as the single source of truth for reprocessing. |
| **AWS Glue** | ETL (Extract, Transform, Load) | Performs the initial movement from landing to raw. Glue crawlers catalog the data structure (schema discovery), and Glue jobs handle format conversion and partitioning for efficient downstream querying. |

### Enriched / Stage Layer

This layer applies business logic, validates data quality, and prepares data for consumption by Model N and reporting systems.

| Technology | Service | Role in the Architecture |
|------------|---------|--------------------------|
| **Amazon S3** (Enriched Zone) | Object Storage | Stores validated, standardized, and enriched datasets. Data here has passed all quality checks and is ready for consumption. |
| **AWS Glue** | ETL Processing | Executes transformation jobs that apply business rules, join datasets across sources, standardize formats, and write enriched outputs. |
| **Amazon Athena** | Serverless SQL Query Engine | Provides SQL-based querying directly on S3 data without requiring a database. Used for data validation checks, ad-hoc exploration during development, and supporting the data governance layer. |
| **AWS Lambda** | Serverless Compute | Runs lightweight, event-driven processing tasks such as file validation (checking headers, row counts, file completeness), triggering downstream workflows, and custom transformation logic that does not warrant a full Glue job. |
| **Snowflake** | Cloud Data Warehouse | Serves as an additional data processing and storage layer for complex transformations, cross-source joins, and analytics workloads that benefit from Snowflake's performance optimization. Handles data validation and standardization alongside the AWS-native tools. |
| **File Validation** | Custom Logic (Lambda) | Validates incoming files against expected schemas — checking column names, data types, row counts, file sizes, and mandatory fields. Invalid files are quarantined and flagged for investigation. |
| **DQC (Data Quality Checks)** | Custom Framework | A dedicated data quality control layer that runs at the data level. Checks include completeness (are all required fields populated?), accuracy (do values fall within expected ranges?), consistency (do related records agree across sources?), and timeliness (did the data arrive on schedule?). |

### Data Flow Summary

```
SAP Systems / Axway / SFTP
        │
        ▼
   ┌─────────────────────┐
   │   S3 Landing Zone   │  ← Raw files deposited here
   └────────┬────────────┘
            │  AWS Glue (catalog + partition)
            ▼
   ┌─────────────────────┐
   │    S3 Raw Zone      │  ← Immutable historical copy
   └────────┬────────────┘
            │  AWS Glue + Lambda + Athena
            │  (validate, transform, enrich)
            ▼
   ┌─────────────────────┐
   │  S3 Enriched Zone   │  ← Business-ready data
   │  + Snowflake        │
   └────────┬────────────┘
            │
      ┌─────┴─────┐
      ▼           ▼
  Model N     Reporting
  (SaaS)      (Galaxy, DBX-FI)
```

---

## Orchestration and Workflow Management

The end-to-end data pipeline is coordinated by the following orchestration services:

| Technology | Role |
|------------|------|
| **AWS Step Functions** | Primary orchestration engine. Defines state machines that coordinate the sequence of data processing steps — from ingestion through transformation to delivery. Handles retries, error branching, parallel processing, and approval gates. Each data pipeline (e.g., "SAP P2R daily load") is defined as a Step Function workflow. |
| **Amazon CloudWatch** | Monitors pipeline execution. Triggers alarms when jobs fail, run longer than expected, or produce unexpected output volumes. CloudWatch Events can also trigger Step Functions on a schedule (e.g., daily at 02:00 UTC). |
| **AWS Lambda** | Acts as the glue between orchestration steps — invoked by Step Functions to perform lightweight tasks like file validation, notification sending, and status updates. |

---

## Model N Application Layer

### Platform Overview

| Attribute | Detail |
|-----------|--------|
| **Application** | Model N PhyN Full Suite |
| **Deployment Model** | SaaS (Software as a Service) — hosted and managed by Model N |
| **Purpose** | Pharmaceutical revenue management including government pricing, commercial contracting, Medicaid rebate processing, chargeback management, and 340B compliance |

### Integration Points

Model N connects to the AWS data platform through two primary interfaces:

| Interface | Direction | Format | Description |
|-----------|-----------|--------|-------------|
| **XML/dev** | Bidirectional | XML | API-based or structured XML data exchange between the enriched layer and Model N. Used for transactional data that requires real-time or near-real-time processing (e.g., pricing lookups, contract validations). |
| **XML/CSV File Ingestion** | Inbound to Model N | XML, CSV | Batch file-based ingestion for bulk data loads into Model N. Enriched and transformed data from the AWS platform is packaged into XML or CSV files that conform to Model N's import specifications and delivered to Model N's file ingestion endpoint. |

### Data Exchanged with Model N

The following categories of data flow into and out of Model N:

**Inbound to Model N (from AWS Platform):**
- Customer and product master data (from SAP MDM)
- Transaction data — sales, purchases, inventory movements (from SAP P2R, P4S)
- Payment and chargeback data (from SAP A/P Payments)
- Third-party data files (from Axway)
- Historical bulk data for initial migration

**Outbound from Model N (to Reporting Layer):**
- Calculated pricing results
- Rebate accruals and payment recommendations
- Contract compliance reports
- Government pricing submissions
- Chargeback resolution data
- Transformed data for downstream analytics

---

## Reporting Layer (Data Warehouse)

The reporting layer consumes processed data from both the enriched/stage layer and Model N to deliver business intelligence and analytics.

| Reporting System | Purpose | Users |
|------------------|---------|-------|
| **Galaxy Reports** | Enterprise reporting platform. Delivers standardized, scheduled reports for business stakeholders. Covers revenue analytics, contract performance, pricing compliance, and operational dashboards. | Business analysts, finance teams, commercial operations |
| **Model N UI** | The native Model N user interface. Provides in-application reporting, deal analysis, pricing simulations, and contract management views directly within the Model N platform. | Revenue management teams, pricing analysts, contract managers |
| **DBX-FI Reporting** | Financial reporting integration (likely Databricks or a dedicated financial reporting tool). Produces financial reconciliation reports, audit trails, and compliance documentation required for regulatory submissions. | Finance and accounting, audit and compliance teams |

---

## Common Platform Services Layer

A shared services layer supports all other layers with cross-cutting capabilities:

### Data Governance

| Service | Purpose |
|---------|---------|
| **Amazon Athena** | Enables SQL-based data exploration and governance queries. Data stewards use Athena to audit data lineage, run quality checks, and investigate anomalies across the S3 data lake. |
| **AWS Lake Formation** | Manages fine-grained access control over the data lake. Defines who can access which databases, tables, and columns. Enforces data classification policies and tracks data access for compliance. |

### Security

| Service | Purpose |
|---------|---------|
| **AWS IAM** (Identity and Access Management) | Controls who and what can access AWS resources. Defines roles, policies, and permissions for human users, service accounts, and application workloads. Enforces the principle of least privilege. |
| **AWS Key Management Service (KMS)** | Manages encryption keys used to protect data at rest (S3, DynamoDB, Snowflake) and in transit. All data stored in the platform is encrypted using KMS-managed keys. |

### Audit and Compliance

| Service | Purpose |
|---------|---------|
| **AWS CloudTrail** + Custom Extensions | Records every API call made within the AWS environment — who did what, when, and from where. Custom extensions enrich CloudTrail logs with business context (e.g., linking API calls to specific pipeline runs). Essential for SOX compliance and security investigations. |
| **Amazon CloudWatch** + Custom Extensions | Collects logs, metrics, and traces from all platform components. Custom dashboards and alarms provide real-time visibility into pipeline health, data volumes, error rates, and processing times. |

### Monitoring and Administration

| Service | Purpose |
|---------|---------|
| **Amazon CloudWatch** | Centralized monitoring for all AWS services. Collects logs from Glue jobs, Lambda functions, and Step Functions. Triggers alarms for failures and performance degradation. |
| **AWS CloudTrail** | Audit trail for all administrative and operational actions. |
| **ServiceNow** | IT service management integration. Pipeline failures and infrastructure incidents automatically create ServiceNow tickets for the operations team. Change requests for infrastructure modifications follow the ServiceNow approval workflow. |

### DevOps and CI/CD

| Service | Purpose |
|---------|---------|
| **GitHub** | Source code repository for all infrastructure code (Terraform), Glue job scripts, Lambda function code, and Step Function definitions. Pull requests enforce code review before any change reaches an environment. |
| **Amazon SNS** (Simple Notification Service) | Sends notifications for pipeline events — job completions, failures, approvals needed. Delivers alerts via email, Slack, or PagerDuty to the operations team. |
| **Terraform** | Infrastructure as Code (IaC). Every AWS resource in the platform — S3 buckets, Glue jobs, Lambda functions, IAM roles, Step Functions — is defined in Terraform configuration files. This ensures environments are reproducible, version-controlled, and auditable. Changes are deployed through CI/CD pipelines (GitHub Actions). |

### Business Rules and Processing

| Service | Purpose |
|---------|---------|
| **AWS Lambda** | Executes business rules as serverless functions. Handles event-driven logic such as data routing, conditional processing, and lightweight calculations that do not require a full ETL job. |

### Archival and Storage Services

| Service | Purpose |
|---------|---------|
| **AWS Glacier** | Long-term archival storage for data that must be retained for compliance but is rarely accessed. Historical transaction data, audit logs, and superseded master data records are moved to Glacier after a defined retention period to reduce storage costs. |
| **Amazon SNS** | Supports archival workflows by notifying downstream systems when data has been archived or when archived data is requested for retrieval. |
| **Custom/LCS** | Custom lifecycle management services that automate the transition of data between storage tiers (S3 Standard → S3 Infrequent Access → Glacier) based on age and access patterns. |

---

## Data Migration Overview

The following data categories require migration or ongoing connection as part of the Model N integration:

### Initial Migration (One-Time Bulk Load)

| Data Category | Source System | Estimated Volume | Format | Notes |
|---------------|---------------|------------------|--------|-------|
| **Customer Master Data** | SAP MDM | Tens of thousands of records | CSV/XML | Customer hierarchies, ship-to/bill-to relationships, trade class assignments. Must be loaded before transactional data. |
| **Product Master Data** | SAP MDM | Thousands of SKUs | CSV/XML | Product hierarchies, NDC numbers, pack sizes, therapeutic classes. Critical for pricing engine configuration. |
| **Contract Data** | Legacy systems / SAP | Thousands of active contracts | XML | Government and commercial contracts, pricing terms, rebate schedules. Must be validated against Model N's contract model. |
| **Historical Transactions** | SAP P2R, P4S | Millions of records (multi-year) | CSV/Parquet | Sales transactions, chargebacks, rebate claims. Required for Model N to calculate accurate accruals and trending. Typically 2-3 years of history. |
| **Pricing Data** | SAP / Legacy pricing systems | Thousands of price records | CSV/XML | Government pricing submissions (AMP, BP, ASP, FCP, URA, WAC), commercial price lists. |
| **Payment History** | SAP A/P Payments | Millions of records | CSV | Historical rebate payments, chargeback settlements. Required for reconciliation and open balance calculations. |

### Ongoing Data Connections (Incremental / Daily)

| Data Flow | Source → Target | Frequency | Volume (Daily Est.) | Protocol |
|-----------|-----------------|-----------|---------------------|----------|
| **Sales Transactions** | SAP P2R → S3 Landing → Model N | Daily | Hundreds of thousands of records | SFTP / API |
| **Inventory Positions** | SAP P4S → S3 Landing → Model N | Daily | Thousands of records | SFTP |
| **Master Data Changes** | SAP MDM → S3 Landing → Model N | Daily/On-change | Hundreds of records | API / File |
| **Payment Files** | SAP A/P → S3 Landing → Model N | Daily | Thousands of records | SFTP |
| **Third-Party Data** | Axway → S3 Landing | Weekly/Monthly | Varies | SFTP / MFT |
| **Chargeback Files** | External partners → Axway → S3 Landing | Daily | Thousands of records | EDI / SFTP |
| **Model N Outputs** | Model N → S3 Enriched → Reporting | Daily | Varies | XML/CSV |
| **Reporting Feeds** | S3 Enriched → Galaxy / DBX-FI | Daily | Aggregated datasets | Direct query / File |

### Data Migration Considerations

- **Sequencing** — Master data (customers, products) must be loaded before transactional data. Contracts must be loaded before pricing calculations can run. The migration must follow a strict dependency order.

- **Data Quality** — Source systems may contain duplicate, incomplete, or inconsistent records. The DQC framework in the enriched layer must validate all migrated data before it enters Model N. Quarantine processes must handle rejected records.

- **Mapping and Transformation** — SAP field names and structures differ from Model N's expected input format. Comprehensive field-level mapping documents must be created and validated for each data domain.

- **Historical Cutover** — A defined cutover date must be established. Transactions before this date come from the historical bulk load; transactions after come from the incremental feed. Overlaps and gaps must be reconciled.

- **Reconciliation** — Post-migration, record counts, financial totals, and key metric values must be compared between source systems and Model N to confirm data integrity. This typically involves running parallel systems for a validation period.

---

## Technology Stack Summary

| Layer | Technologies |
|-------|-------------|
| **Source Systems** | SAP P2R, SAP P4S, SAP MDM, SAP H2R, SAP A/P Payments, Axway MFT |
| **Data Ingestion** | AWS Step Functions, AWS Glue, SFTP, Batch/Incremental loaders |
| **Storage** | Amazon S3 (Landing, Raw, Enriched zones), AWS Glacier (archival) |
| **Processing & ETL** | AWS Glue, AWS Lambda, Amazon Athena, Snowflake |
| **Orchestration** | AWS Step Functions, Amazon CloudWatch Events |
| **Core Application** | Model N PhyN Full Suite (SaaS) |
| **Reporting** | Galaxy Reports, Model N UI, DBX-FI Reporting |
| **Security** | AWS IAM, AWS KMS, AWS Lake Formation |
| **Monitoring** | Amazon CloudWatch, AWS CloudTrail, ServiceNow |
| **DevOps / CI-CD** | GitHub, GitHub Actions, Terraform, Amazon SNS |
| **Data Governance** | Amazon Athena, AWS Lake Formation, DQC Framework |
| **Integration Protocols** | SFTP, XML, CSV, REST API, EDI |

---

## Network and Connectivity Considerations

| Connection | Type | Security |
|------------|------|----------|
| SAP → AWS | VPN or AWS Direct Connect | Encrypted tunnel, IP whitelisting |
| Axway → AWS S3 | SFTP over TLS | Certificate-based authentication, file-level encryption |
| AWS → Model N (SaaS) | HTTPS / SFTP | TLS 1.2+, API key or OAuth authentication |
| AWS → Snowflake | Private Link or VPC Peering | Encrypted, no public internet traversal |
| AWS → Reporting Tools | Internal network / VPC | IAM-based access control |
| External Partners → Axway | SFTP / EDI | Partner-specific certificates, AS2 protocol for EDI |

---

## Environment Landscape

The platform operates across four AWS accounts, each representing a stage in the deployment lifecycle:

| Environment | AWS Account | Purpose |
|-------------|-------------|---------|
| **Sandbox** | 850995573834 | Safe experimentation and early development testing. No production data. |
| **Development** | 905418426173 | Active development and integration testing. Uses synthetic or anonymized data. |
| **QA** | 533267067460 | Quality assurance and user acceptance testing. Uses production-representative data. |
| **Production** | 992382469710 | Live environment serving real business operations. Subject to change management controls. |

All environments are provisioned and managed through Terraform, ensuring consistency and reproducibility across the entire landscape.

---

*This document should be reviewed alongside the Model N Functional Architecture diagram for visual reference.*
