# Bayer Work Projects — Nova ⚡

This directory contains architecture and research documents for Bayer-related work.

## Projects

### Nightwatch — AI-Powered Proactive Monitoring
Cloud-agnostic monitoring platform for the ModelN.io data pipeline.
- Architecture: [NIGHTWATCH-ARCHITECTURE.md](./NIGHTWATCH-ARCHITECTURE.md)
- Diagram: [NIGHTWATCH-ARCHITECTURE.drawio](./NIGHTWATCH-ARCHITECTURE.drawio)
- Implementation: [nightwatch/](./nightwatch/)

### StackIT vs AWS Analysis
Deep comparison for GDPR-compliant hybrid cloud storage architecture.
- Analysis: [STACKIT-VS-AWS-ANALYSIS.md](./STACKIT-VS-AWS-ANALYSIS.md)

## Architecture Context

The ModelN.io pipeline runs on AWS US-East-1 and processes critical pharma
revenue management data (chargebacks, Medicaid claims, price lists).

### GDPR Consideration

For data with European residency requirements, a hybrid approach is being evaluated:
- **Compute**: Stays on AWS (processing power, existing integrations)
- **Storage**: Moves to StackIT (EU data center, GDPR-native, Schwarz Group)

### Key Architecture Facts

- **StackIT S3 Endpoint (EU01):** `https://object.storage.eu01.onstackit.cloud`
- **Authentication:** Access key + Secret key (same as AWS — boto3 just needs `endpoint_url`)
- **GDPR Certifications:** ISO 27001, BSI C5 Type 2, 100% German data centers
- **Terraform Provider:** `stackitcloud/stackit` v0.88.0 (weekly releases, pre-1.0)
- **Latency (US-East-1 → StackIT EU01):** ~80-100ms (async-friendly, not for OLTP)
- **No direct peering** between AWS and StackIT — traffic over public internet (TLS 1.3)

## Key Contacts
- Project: Bayer pharma revenue management
- Infrastructure: AWS US-East-1
- Monitoring: Nightwatch (see above)

## Files

| File | Description |
|------|-------------|
| [NIGHTWATCH-ARCHITECTURE.md](./NIGHTWATCH-ARCHITECTURE.md) | Nightwatch monitoring platform architecture doc |
| [NIGHTWATCH-ARCHITECTURE.drawio](./NIGHTWATCH-ARCHITECTURE.drawio) | Architecture diagram (draw.io) |
| [ModelN.io.drawio](./ModelN.io.drawio) | ModelN.io pipeline diagram |
| [STACKIT-VS-AWS-ANALYSIS.md](./STACKIT-VS-AWS-ANALYSIS.md) | StackIT vs AWS deep analysis for GDPR hybrid storage |
| [nightwatch/](./nightwatch/) | Nightwatch implementation files |
