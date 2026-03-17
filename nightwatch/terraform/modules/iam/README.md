# Module: IAM

Creates all IAM roles for Nightwatch.

## Roles Created

### 1. `nightwatch-execution-role-{env}` (ECS only)
ECS control plane role — pulls ECR images, writes CloudWatch logs. NOT the application.

### 2. `nightwatch-task-role-{env}` (always)
Application role assumed by running tasks/pods. Read-only access to:
- CloudWatch metrics
- Step Functions executions
- Glue job runs
- S3 buckets (monitored)
- DynamoDB tables (monitored)
- CloudWatch Logs
- Lambda functions
- Transfer Family servers
- `sts:AssumeRole` → `NightwatchMonitorRole` in monitored accounts

### 3. IRSA roles (EKS only)
- `nightwatch-irsa-{env}` — for main collector pod
- `nightwatch-aws-pipeline-collector-{env}` — for pipeline collector pod
- `nightwatch-cloudwatch-exporter-{env}` — for metrics exporter pod

All IRSA roles are bound to specific Kubernetes service accounts via OIDC — no static keys.

## Cross-Account Architecture

```
Nightwatch Account                    Monitored Account(s)
─────────────────────                 ────────────────────────
nightwatch-task-role ──sts:AssumeRole──▶ NightwatchMonitorRole
                                              │
                                         Read-only: StepFunctions,
                                         Glue, S3, DynamoDB, Lambda,
                                         CloudWatch, Transfer
```

**To enable cross-account monitoring:**
1. Note the `task_role_arn` output from this module
2. In each monitored account, apply `cross_account.tf` with:
   ```
   nightwatch_account_id = "<account where nightwatch runs>"
   nightwatch_task_role_name = "nightwatch-task-role-prod"
   ```

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `environment` | string | required | Environment name |
| `deployment_type` | string | `"ecs"` | `ecs` or `eks` |
| `oidc_provider_arn` | string | `""` | EKS OIDC provider ARN (EKS only) |
| `oidc_provider_url` | string | `""` | EKS OIDC URL without https:// |
| `modeln_step_functions` | list(string) | `["*"]` | Step Functions ARNs to allow |
| `modeln_s3_buckets` | list(string) | `[]` | S3 bucket names |
| `modeln_dynamodb_tables` | list(string) | `[]` | DynamoDB table names |
| `modeln_lambda_functions` | list(string) | `[]` | Lambda function names |
| `monitored_account_ids` | list(string) | `[]` | Accounts to assume into |

## Outputs

| Name | Description |
|------|-------------|
| `execution_role_arn` | ECS execution role ARN |
| `task_role_arn` | Application/task role ARN |
| `task_role_name` | Task role name |
| `irsa_role_arn` | IRSA role ARN (EKS only) |
| `aws_pipeline_collector_role_arn` | Pipeline collector IRSA ARN |
| `cloudwatch_exporter_role_arn` | CW exporter IRSA ARN |
| `monitoring_readonly_policy_arn` | Consolidated read-only policy ARN |
