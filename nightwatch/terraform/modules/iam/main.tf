# =============================================================================
# Nightwatch IAM Module
# =============================================================================
# Creates all IAM roles for Nightwatch:
#   1. nightwatch-execution-role  — ECS task execution (pull ECR, write CW logs)
#   2. nightwatch-task-role       — Application permissions (monitor AWS services)
#   3. nightwatch-collector-irsa  — IRSA role for EKS pod-level AWS auth
#
# Cross-account role (deployed in EACH monitored account) is in cross_account.tf
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------
variable "environment" {
  description = "Environment name"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name (used for IRSA trust policy)"
  type        = string
  default     = ""
}

variable "oidc_provider_arn" {
  description = "EKS OIDC provider ARN (for IRSA)"
  type        = string
  default     = ""
}

variable "oidc_provider_url" {
  description = "EKS OIDC provider URL without https:// (for IRSA)"
  type        = string
  default     = ""
}

variable "deployment_type" {
  description = "Deployment type: ecs or eks"
  type        = string
  default     = "ecs"
}

# ModelN.io pipeline resources to grant read access to
variable "modeln_step_functions" {
  description = "ARNs of Step Functions state machines to monitor"
  type        = list(string)
  default     = ["*"]
}

variable "modeln_glue_jobs" {
  description = "Names of Glue jobs to monitor (used for resource ARNs)"
  type        = list(string)
  default     = []
}

variable "modeln_s3_buckets" {
  description = "S3 bucket names to monitor"
  type        = list(string)
  default     = []
}

variable "modeln_dynamodb_tables" {
  description = "DynamoDB table names to monitor"
  type        = list(string)
  default     = []
}

variable "modeln_lambda_functions" {
  description = "Lambda function names to monitor"
  type        = list(string)
  default     = []
}

variable "monitored_account_ids" {
  description = "AWS account IDs that nightwatch will assume roles into for monitoring"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Local computed values
# -----------------------------------------------------------------------------
locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # Build S3 bucket ARNs from names
  s3_bucket_arns = [
    for b in var.modeln_s3_buckets : "arn:aws:s3:::${b}"
  ]
  s3_object_arns = [
    for b in var.modeln_s3_buckets : "arn:aws:s3:::${b}/*"
  ]

  # Build Glue job ARNs
  glue_job_arns = length(var.modeln_glue_jobs) > 0 ? [
    for j in var.modeln_glue_jobs : "arn:aws:glue:${local.region}:${local.account_id}:job/${j}"
  ] : ["arn:aws:glue:${local.region}:${local.account_id}:job/*"]

  # Build Lambda function ARNs
  lambda_arns = length(var.modeln_lambda_functions) > 0 ? [
    for f in var.modeln_lambda_functions : "arn:aws:lambda:${local.region}:${local.account_id}:function:${f}"
  ] : ["arn:aws:lambda:${local.region}:${local.account_id}:function:*"]

  # Build DynamoDB table ARNs
  dynamodb_arns = length(var.modeln_dynamodb_tables) > 0 ? [
    for t in var.modeln_dynamodb_tables : "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${t}"
  ] : ["arn:aws:dynamodb:${local.region}:${local.account_id}:table/*"]

  # Cross-account role ARNs (roles in monitored accounts that nightwatch assumes)
  cross_account_role_arns = [
    for acct in var.monitored_account_ids :
    "arn:aws:iam::${acct}:role/NightwatchMonitorRole"
  ]
}

# =============================================================================
# 1. ECS Task Execution Role
# =============================================================================
# Used by the ECS control plane to: pull images from ECR, write CloudWatch logs
# This is NOT the application — it's the infrastructure plumbing role.

resource "aws_iam_role" "execution" {
  name        = "nightwatch-execution-role-${var.environment}"
  description = "ECS task execution role — pull ECR images, write CloudWatch logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "nightwatch-execution-role-${var.environment}"
  }
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow pulling from ECR (private repos)
resource "aws_iam_role_policy" "execution_ecr" {
  name = "nightwatch-execution-ecr-${var.environment}"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRPull"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "arn:aws:ecr:${local.region}:${local.account_id}:repository/nightwatch*"
      }
    ]
  })
}

# =============================================================================
# 2. Nightwatch Task Role (Application Role)
# =============================================================================
# This role is assumed BY the running nightwatch container.
# Grants read-only access to all AWS services that Nightwatch monitors.

resource "aws_iam_role" "task" {
  name        = "nightwatch-task-role-${var.environment}"
  description = "Nightwatch application role — read AWS services + assume cross-account roles"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      # ECS Fargate trust (deployment_type = ecs)
      var.deployment_type == "ecs" ? [
        {
          Effect    = "Allow"
          Principal = { Service = "ecs-tasks.amazonaws.com" }
          Action    = "sts:AssumeRole"
        }
      ] : [],

      # EKS IRSA trust (deployment_type = eks)
      var.deployment_type == "eks" && var.oidc_provider_arn != "" ? [
        {
          Effect = "Allow"
          Principal = {
            Federated = var.oidc_provider_arn
          }
          Action = "sts:AssumeRoleWithWebIdentity"
          Condition = {
            StringEquals = {
              "${var.oidc_provider_url}:sub" = "system:serviceaccount:nightwatch:nightwatch-collector"
              "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
            }
          }
        }
      ] : []
    )
  })

  tags = {
    Name = "nightwatch-task-role-${var.environment}"
  }
}

# ---- CloudWatch: read metrics ----
resource "aws_iam_role_policy" "task_cloudwatch" {
  name = "nightwatch-cloudwatch-${var.environment}"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchRead"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:DescribeAlarmsForMetric"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---- Step Functions: list and inspect executions ----
resource "aws_iam_role_policy" "task_stepfunctions" {
  name = "nightwatch-stepfunctions-${var.environment}"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StepFunctionsRead"
        Effect = "Allow"
        Action = [
          "states:ListExecutions",
          "states:DescribeExecution",
          "states:GetExecutionHistory",
          "states:DescribeStateMachine",
          "states:ListStateMachines"
        ]
        Resource = length(var.modeln_step_functions) > 0 ? var.modeln_step_functions : ["*"]
      }
    ]
  })
}

# ---- AWS Glue: inspect job runs ----
resource "aws_iam_role_policy" "task_glue" {
  name = "nightwatch-glue-${var.environment}"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GlueRead"
        Effect = "Allow"
        Action = [
          "glue:GetJobRun",
          "glue:GetJobRuns",
          "glue:ListJobs",
          "glue:GetJob",
          "glue:GetJobs",
          "glue:BatchGetJobs"
        ]
        Resource = local.glue_job_arns
      }
    ]
  })
}

# ---- S3: read monitored buckets ----
resource "aws_iam_role_policy" "task_s3" {
  name  = "nightwatch-s3-${var.environment}"
  role  = aws_iam_role.task.id
  count = length(var.modeln_s3_buckets) > 0 ? 1 : 0

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ListBuckets"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketVersioning"]
        Resource = local.s3_bucket_arns
      },
      {
        Sid      = "S3GetObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion", "s3:HeadObject"]
        Resource = local.s3_object_arns
      }
    ]
  })
}

# ---- DynamoDB: query monitored tables ----
resource "aws_iam_role_policy" "task_dynamodb" {
  name  = "nightwatch-dynamodb-${var.environment}"
  role  = aws_iam_role.task.id
  count = length(var.modeln_dynamodb_tables) > 0 ? 1 : 0

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBRead"
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:GetItem",
          "dynamodb:DescribeTable",
          "dynamodb:ListTables"
        ]
        Resource = local.dynamodb_arns
      }
    ]
  })
}

# ---- CloudWatch Logs: read log groups ----
resource "aws_iam_role_policy" "task_logs" {
  name = "nightwatch-logs-${var.environment}"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LogsRead"
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents",
          "logs:GetLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:StartQuery",
          "logs:GetQueryResults",
          "logs:StopQuery"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---- Lambda: inspect function configurations ----
resource "aws_iam_role_policy" "task_lambda" {
  name  = "nightwatch-lambda-${var.environment}"
  role  = aws_iam_role.task.id
  count = length(var.modeln_lambda_functions) > 0 ? 1 : 0

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaRead"
        Effect = "Allow"
        Action = [
          "lambda:GetFunctionConfiguration",
          "lambda:GetFunction",
          "lambda:ListFunctions",
          "lambda:GetFunctionConcurrency",
          "lambda:ListEventSourceMappings"
        ]
        Resource = local.lambda_arns
      }
    ]
  })
}

# ---- SFTP Transfer: describe server ----
resource "aws_iam_role_policy" "task_transfer" {
  name = "nightwatch-transfer-${var.environment}"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TransferRead"
        Effect = "Allow"
        Action = [
          "transfer:DescribeServer",
          "transfer:ListServers",
          "transfer:DescribeUser",
          "transfer:ListUsers"
        ]
        Resource = "*"
      }
    ]
  })
}

# ---- Cross-account: assume NightwatchMonitorRole in monitored accounts ----
resource "aws_iam_role_policy" "task_cross_account" {
  name  = "nightwatch-cross-account-${var.environment}"
  role  = aws_iam_role.task.id
  count = length(var.monitored_account_ids) > 0 ? 1 : 0

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CrossAccountAssume"
        Effect = "Allow"
        Action = ["sts:AssumeRole"]
        # Assumes the NightwatchMonitorRole in each monitored account
        Resource = local.cross_account_role_arns
      }
    ]
  })
}

# =============================================================================
# 3. IRSA Role (EKS only) — pods authenticate to AWS without static keys
# =============================================================================
# When deployment_type = "eks", pods use this role instead of task_role.
# The trust policy ties the role to a specific Kubernetes service account.

resource "aws_iam_role" "irsa" {
  count = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0

  name        = "nightwatch-irsa-${var.environment}"
  description = "IRSA role for Nightwatch EKS pods — no static AWS keys needed"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = var.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            # Bind to the specific Kubernetes service account
            "${var.oidc_provider_url}:sub" = "system:serviceaccount:nightwatch:nightwatch-collector"
            "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = {
    Name = "nightwatch-irsa-${var.environment}"
  }
}

# Attach all monitoring policies to IRSA role (same permissions as task role)
resource "aws_iam_role_policy_attachment" "irsa_attach_task_policies" {
  count = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0

  role       = aws_iam_role.irsa[0].name
  policy_arn = aws_iam_policy.monitoring_readonly.arn
}

# Consolidated read-only monitoring policy (attached to IRSA and available standalone)
resource "aws_iam_policy" "monitoring_readonly" {
  name        = "NightwatchMonitoringReadOnly-${var.environment}"
  description = "Read-only access to all services Nightwatch monitors (CloudWatch, StepFunctions, Glue, S3, DynamoDB, Lambda, Transfer)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchRead"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics", "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Sid    = "StepFunctionsRead"
        Effect = "Allow"
        Action = [
          "states:ListExecutions", "states:DescribeExecution",
          "states:GetExecutionHistory", "states:DescribeStateMachine"
        ]
        Resource = "*"
      },
      {
        Sid    = "GlueRead"
        Effect = "Allow"
        Action = ["glue:GetJobRun", "glue:GetJobRuns", "glue:ListJobs", "glue:GetJob"]
        Resource = "*"
      },
      {
        Sid      = "S3Read"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"]
        Resource = "*"
      },
      {
        Sid    = "DynamoDBRead"
        Effect = "Allow"
        Action = ["dynamodb:Query", "dynamodb:Scan", "dynamodb:GetItem", "dynamodb:DescribeTable"]
        Resource = "*"
      },
      {
        Sid    = "LogsRead"
        Effect = "Allow"
        Action = [
          "logs:FilterLogEvents", "logs:GetLogEvents",
          "logs:DescribeLogGroups", "logs:DescribeLogStreams"
        ]
        Resource = "*"
      },
      {
        Sid    = "LambdaRead"
        Effect = "Allow"
        Action = ["lambda:GetFunctionConfiguration", "lambda:ListFunctions"]
        Resource = "*"
      },
      {
        Sid    = "TransferRead"
        Effect = "Allow"
        Action = ["transfer:DescribeServer", "transfer:ListServers"]
        Resource = "*"
      }
    ]
  })
}

# =============================================================================
# EKS: aws-pipeline-collector and cloudwatch-exporter service account roles
# (mirrors what the environments/prod/main.tf kubernetes resources expect)
# =============================================================================

resource "aws_iam_role" "aws_pipeline_collector" {
  count       = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0
  name        = "nightwatch-aws-pipeline-collector-${var.environment}"
  description = "IRSA for aws-pipeline-collector pod"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:nightwatch:aws-pipeline-collector"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "pipeline_collector_policy" {
  count      = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0
  role       = aws_iam_role.aws_pipeline_collector[0].name
  policy_arn = aws_iam_policy.monitoring_readonly.arn
}

resource "aws_iam_role" "cloudwatch_exporter" {
  count       = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0
  name        = "nightwatch-cloudwatch-exporter-${var.environment}"
  description = "IRSA for cloudwatch-exporter pod"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:nightwatch:cloudwatch-exporter"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cloudwatch_exporter_policy" {
  count      = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? 1 : 0
  role       = aws_iam_role.cloudwatch_exporter[0].name
  policy_arn = aws_iam_policy.monitoring_readonly.arn
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = aws_iam_role.execution.arn
}

output "task_role_arn" {
  description = "Nightwatch task/application role ARN"
  value       = aws_iam_role.task.arn
}

output "task_role_name" {
  description = "Nightwatch task role name (used in cross-account trust policies)"
  value       = aws_iam_role.task.name
}

output "irsa_role_arn" {
  description = "IRSA role ARN (EKS only)"
  value       = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? aws_iam_role.irsa[0].arn : ""
}

output "aws_pipeline_collector_role_arn" {
  description = "ARN for aws-pipeline-collector IRSA role (EKS only)"
  value       = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? aws_iam_role.aws_pipeline_collector[0].arn : ""
}

output "cloudwatch_exporter_role_arn" {
  description = "ARN for cloudwatch-exporter IRSA role (EKS only)"
  value       = var.deployment_type == "eks" && var.oidc_provider_arn != "" ? aws_iam_role.cloudwatch_exporter[0].arn : ""
}

output "monitoring_readonly_policy_arn" {
  description = "ARN of the consolidated read-only monitoring policy"
  value       = aws_iam_policy.monitoring_readonly.arn
}
