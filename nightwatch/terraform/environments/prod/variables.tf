# =============================================================================
# Nightwatch Production Variables
# =============================================================================

# -----------------------------------------------------------------------------
# Deployment mode
# -----------------------------------------------------------------------------
variable "deployment_type" {
  description = "Deployment platform: 'ecs' for ECS Fargate (default), 'eks' for EKS"
  type        = string
  default     = "ecs"

  validation {
    condition     = contains(["ecs", "eks"], var.deployment_type)
    error_message = "deployment_type must be 'ecs' or 'eks'"
  }
}

# -----------------------------------------------------------------------------
# AWS / Environment
# -----------------------------------------------------------------------------
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "cluster_name_prefix" {
  description = "Prefix for the EKS/ECS cluster name"
  type        = string
  default     = "nightwatch"
}

# -----------------------------------------------------------------------------
# Networking
# -----------------------------------------------------------------------------
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.100.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones (must have at least 2)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.100.1.0/24", "10.100.2.0/24", "10.100.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.100.101.0/24", "10.100.102.0/24", "10.100.103.0/24"]
}

# -----------------------------------------------------------------------------
# ECS-specific variables (used when deployment_type = "ecs")
# -----------------------------------------------------------------------------
variable "nightwatch_image_uri" {
  description = "Docker image URI for nightwatch-collector (ECR repo)"
  type        = string
  default     = ""
  # Example: "123456789012.dkr.ecr.us-east-1.amazonaws.com/nightwatch-collector:latest"
}

variable "ecs_cpu" {
  description = "Fargate task CPU units (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "ecs_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "ecs_desired_count" {
  description = "Desired number of Fargate tasks"
  type        = number
  default     = 2
}

variable "ecs_min_capacity" {
  description = "Minimum tasks for auto-scaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum tasks for auto-scaling"
  type        = number
  default     = 6
}

variable "extra_env_vars" {
  description = "Extra environment variables to inject into the container"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# EKS-specific variables (used when deployment_type = "eks")
# -----------------------------------------------------------------------------
variable "cluster_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.31"
}

variable "node_groups" {
  description = "Map of EKS managed node group configurations (empty uses defaults)"
  type = map(object({
    instance_types = list(string)
    capacity_type  = string
    scaling_config = object({
      desired_size = number
      max_size     = number
      min_size     = number
    })
    labels = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = {
    "default" = {
      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
      scaling_config = {
        desired_size = 2
        max_size     = 5
        min_size     = 1
      }
      labels = {
        "workload-type" = "nightwatch"
      }
      taints = []
    }
  }
}

# -----------------------------------------------------------------------------
# Storage sizing
# -----------------------------------------------------------------------------
variable "victoriametrics_size_gb" {
  description = "VictoriaMetrics EBS volume size in GB"
  type        = number
  default     = 100
}

variable "opensearch_size_gb" {
  description = "OpenSearch EBS volume size in GB"
  type        = number
  default     = 200
}

variable "grafana_size_gb" {
  description = "Grafana EBS volume size in GB"
  type        = number
  default     = 10
}

# -----------------------------------------------------------------------------
# ModelN.io pipeline monitoring targets
# -----------------------------------------------------------------------------
variable "modeln_step_functions" {
  description = "ARNs of Step Functions state machines to monitor"
  type        = list(string)
  default = [
    # Example: "arn:aws:states:us-east-1:ACCOUNT:stateMachine:ModelN-Pipeline"
  ]
}

variable "modeln_glue_jobs" {
  description = "Names of Glue jobs to monitor"
  type        = list(string)
  default = [
    "bay-modeln-AgreementRateCards",
    "bay-modeln-RebateDocuments",
    "bay-modeln-PriceAvailability",
    "bay-modeln-ForecastDetails"
  ]
}

variable "modeln_s3_buckets" {
  description = "S3 bucket names to monitor (landing zones)"
  type        = list(string)
  default = [
    "s3-landing-us-east-1",
    "S3-Raw-bucket-us-east-1",
    "s3-Enriched-us-east-1"
  ]
}

variable "modeln_dynamodb_tables" {
  description = "DynamoDB table names to monitor"
  type        = list(string)
  default     = []
}

variable "modeln_lambda_functions" {
  description = "Lambda function names to monitor"
  type        = list(string)
  default = [
    "bay-modeln-capture-audit-info",
    "bay-modeln-email-attachment-error",
    "bay-modeln-initialize-parameter-stpfnc",
    "bay-modeln-fetch-source-file-to-S3"
  ]
}

# -----------------------------------------------------------------------------
# Cross-account monitoring
# -----------------------------------------------------------------------------
variable "monitored_account_ids" {
  description = "AWS account IDs that Nightwatch monitors via cross-account role assumption"
  type        = list(string)
  default     = []
  # Example: ["123456789012", "987654321098"]
  # Deploy terraform/modules/iam/cross_account.tf in each of these accounts
  # with nightwatch_account_id = <this account's ID>
}

# -----------------------------------------------------------------------------
# Alerting
# -----------------------------------------------------------------------------
variable "slack_webhook_url" {
  description = "Slack webhook URL for alerts"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alert_email" {
  description = "Email address for critical alerts"
  type        = string
  default     = "ops@strategybase.io"
}

variable "pagerduty_integration_key" {
  description = "PagerDuty integration key for on-call escalation"
  type        = string
  sensitive   = true
  default     = ""
}
