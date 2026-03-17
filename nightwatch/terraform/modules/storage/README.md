# Module: Storage

Provisions S3 buckets and DynamoDB for Nightwatch state and metrics archival.

## Resources Created

### `nightwatch-state-{env}` (S3)
- Terraform state storage
- Versioned + AES256 encrypted
- Lifecycle: expire objects after 90 days (configurable)

### `nightwatch-terraform-locks` (DynamoDB)
- Terraform state locking — prevents concurrent applies
- PAY_PER_REQUEST billing (near-zero cost)
- Point-in-time recovery enabled

### `nightwatch-metrics-archive-{env}` (S3)
- Long-term metrics export archive
- Cost-tiered lifecycle:
  - Day 0–30: S3 Standard
  - Day 30–90: S3 Standard-IA
  - Day 90+: Glacier

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `environment` | string | required | Environment name |
| `victoriametrics_size_gb` | number | `100` | VM volume size hint |
| `opensearch_size_gb` | number | `200` | OpenSearch volume size hint |
| `grafana_size_gb` | number | `10` | Grafana volume size hint |
| `state_bucket_expiry_days` | number | `90` | State objects TTL |
| `metrics_ia_transition_days` | number | `30` | Days until IA transition |
| `metrics_glacier_transition_days` | number | `90` | Days until Glacier |
| `force_destroy` | bool | `false` | Allow non-empty bucket destroy |

## Outputs

| Name | Description |
|------|-------------|
| `state_bucket_id` | State bucket name |
| `state_bucket_arn` | State bucket ARN |
| `metrics_archive_bucket_id` | Metrics bucket name |
| `terraform_locks_table_name` | DynamoDB lock table name |
| `storage_sizes` | Map of component → GB sizes |
