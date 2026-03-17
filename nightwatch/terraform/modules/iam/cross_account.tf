# =============================================================================
# Nightwatch Cross-Account IAM Role
# =============================================================================
# Deploy this module IN EACH AWS ACCOUNT that Nightwatch needs to monitor.
#
# Architecture:
#   Nightwatch Account: nightwatch-task-role → sts:AssumeRole →
#   Monitored Account: NightwatchMonitorRole (read-only)
#
# This pattern means:
#   - Nightwatch has ONE identity in its own account
#   - It assumes account-specific roles when monitoring each account
#   - No static credentials needed anywhere
#   - Audit trail: CloudTrail in each account shows nightwatch's activity
#
# To deploy in a monitored account:
#   cd terraform/modules/iam/cross-account-deployment
#   terraform init
#   terraform apply \
#     -var="nightwatch_account_id=123456789012" \
#     -var="nightwatch_task_role_name=nightwatch-task-role-prod"
# =============================================================================

# Variables specific to cross-account deployment
variable "nightwatch_account_id" {
  description = "AWS account ID where Nightwatch runs (the monitoring account)"
  type        = string
}

variable "nightwatch_task_role_name" {
  description = "Name of the nightwatch task role in the monitoring account"
  type        = string
  default     = "nightwatch-task-role-prod"
}

variable "nightwatch_environment" {
  description = "Environment label (used in role name)"
  type        = string
  default     = "prod"
}

# =============================================================================
# NightwatchMonitorRole — deployed in EACH monitored account
# =============================================================================
resource "aws_iam_role" "nightwatch_monitor_role" {
  name        = "NightwatchMonitorRole"
  description = "Assumed by Nightwatch (account ${var.nightwatch_account_id}) to monitor this account's ModelN.io pipeline"

  # Trust policy: only nightwatch-task-role from the monitoring account can assume this
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowNightwatchToAssume"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.nightwatch_account_id}:role/${var.nightwatch_task_role_name}"
        }
        Action = "sts:AssumeRole"
        # Optional: restrict to specific external ID for extra security
        # Condition = {
        #   StringEquals = {
        #     "sts:ExternalId" = "nightwatch-monitor-${var.nightwatch_environment}"
        #   }
        # }
      }
    ]
  })

  tags = {
    ManagedBy   = "Terraform"
    Purpose     = "Nightwatch cross-account monitoring"
    MonitoredBy = "Nightwatch (account ${var.nightwatch_account_id})"
    Environment = var.nightwatch_environment
  }
}

# =============================================================================
# Permissions Policy — read-only access to all monitored services
# =============================================================================
resource "aws_iam_role_policy" "nightwatch_monitor_policy" {
  name = "NightwatchReadOnly"
  role = aws_iam_role.nightwatch_monitor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch metrics and alarms
      {
        Sid    = "CloudWatchRead"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:GetDashboard",
          "cloudwatch:ListDashboards"
        ]
        Resource = "*"
      },

      # Step Functions — list executions, get history
      {
        Sid    = "StepFunctionsRead"
        Effect = "Allow"
        Action = [
          "states:ListExecutions",
          "states:DescribeExecution",
          "states:GetExecutionHistory",
          "states:DescribeStateMachine",
          "states:ListStateMachines",
          "states:DescribeActivity"
        ]
        Resource = "*"
      },

      # Glue — inspect job runs and crawlers
      {
        Sid    = "GlueRead"
        Effect = "Allow"
        Action = [
          "glue:GetJobRun",
          "glue:GetJobRuns",
          "glue:GetJob",
          "glue:GetJobs",
          "glue:ListJobs",
          "glue:BatchGetJobs",
          "glue:GetCrawler",
          "glue:GetCrawlerMetrics",
          "glue:ListCrawlers",
          "glue:GetWorkflowRun",
          "glue:GetWorkflowRunProperties"
        ]
        Resource = "*"
      },

      # S3 — list buckets and read objects (for monitoring landing zones)
      {
        Sid    = "S3Read"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:HeadObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:GetBucketVersioning",
          "s3:GetBucketNotification",
          "s3:GetLifecycleConfiguration",
          "s3:ListAllMyBuckets"
        ]
        Resource = "*"
      },

      # DynamoDB — query and scan monitored tables
      {
        Sid    = "DynamoDBRead"
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem",
          "dynamodb:DescribeTable",
          "dynamodb:ListTables",
          "dynamodb:DescribeTimeToLive"
        ]
        Resource = "*"
      },

      # CloudWatch Logs — read log events and run Insights queries
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
          "logs:StopQuery",
          "logs:DescribeQueries"
        ]
        Resource = "*"
      },

      # Lambda — inspect function configs and recent invocations
      {
        Sid    = "LambdaRead"
        Effect = "Allow"
        Action = [
          "lambda:GetFunctionConfiguration",
          "lambda:GetFunction",
          "lambda:ListFunctions",
          "lambda:GetFunctionConcurrency",
          "lambda:ListEventSourceMappings",
          "lambda:GetPolicy"
        ]
        Resource = "*"
      },

      # AWS Transfer Family — SFTP server status
      {
        Sid    = "TransferRead"
        Effect = "Allow"
        Action = [
          "transfer:DescribeServer",
          "transfer:ListServers",
          "transfer:DescribeUser",
          "transfer:ListUsers",
          "transfer:DescribeAccess"
        ]
        Resource = "*"
      },

      # SNS — check alert topic subscriptions
      {
        Sid    = "SNSRead"
        Effect = "Allow"
        Action = [
          "sns:GetTopicAttributes",
          "sns:ListTopics",
          "sns:ListSubscriptions",
          "sns:ListSubscriptionsByTopic"
        ]
        Resource = "*"
      },

      # IAM — read role metadata (needed for audit)
      {
        Sid    = "IAMRead"
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:ListRoles"
        ]
        Resource = "*"
      }
    ]
  })
}

# =============================================================================
# Outputs
# =============================================================================
output "nightwatch_monitor_role_arn" {
  description = "ARN of NightwatchMonitorRole — paste this into Nightwatch config"
  value       = aws_iam_role.nightwatch_monitor_role.arn
}

output "nightwatch_monitor_role_name" {
  description = "Role name"
  value       = aws_iam_role.nightwatch_monitor_role.name
}
