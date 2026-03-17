# =============================================================================
# Nightwatch Storage Module
# =============================================================================
# Provisions:
#   1. S3 bucket: nightwatch-state-${environment}
#      - Versioned, encrypted (AES256), lifecycle expire after 90 days
#   2. DynamoDB: nightwatch-terraform-locks
#      - For Terraform state locking (prevents concurrent applies)
#   3. S3 bucket: nightwatch-metrics-archive-${environment}
#      - Long-term metrics archive: IA after 30d, Glacier after 90d
#
# Note: For EKS deployment, EBS storage classes are handled by the EBS CSI
# driver add-on (installed in the EKS module).
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
  description = "Cluster name (EKS) — used for tagging"
  type        = string
  default     = "nightwatch-prod"
}

variable "victoriametrics_size_gb" {
  description = "EBS volume size for VictoriaMetrics PVC (GB)"
  type        = number
  default     = 100
}

variable "opensearch_size_gb" {
  description = "EBS volume size for OpenSearch PVC (GB)"
  type        = number
  default     = 200
}

variable "grafana_size_gb" {
  description = "EBS volume size for Grafana PVC (GB)"
  type        = number
  default     = 10
}

variable "state_bucket_expiry_days" {
  description = "Days after which state objects expire"
  type        = number
  default     = 90
}

variable "metrics_ia_transition_days" {
  description = "Days after which metrics objects transition to IA storage"
  type        = number
  default     = 30
}

variable "metrics_glacier_transition_days" {
  description = "Days after which metrics objects transition to Glacier"
  type        = number
  default     = 90
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete non-empty buckets (dev only)"
  type        = bool
  default     = false
}

# =============================================================================
# 1. Terraform State Bucket — nightwatch-state-${environment}
# =============================================================================

resource "aws_s3_bucket" "state" {
  bucket        = "nightwatch-state-${var.environment}"
  force_destroy = var.force_destroy

  tags = {
    Name    = "nightwatch-state-${var.environment}"
    Purpose = "Terraform state storage"
  }
}

# Enable versioning — allows rollback to previous state files
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption with AES256
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: expire current versions after 90 days, clean up old versions after 30
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-state-objects"
    status = "Enabled"

    expiration {
      days = var.state_bucket_expiry_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# =============================================================================
# 2. DynamoDB — Terraform State Locking
# =============================================================================
# Prevents concurrent terraform applies from corrupting state.
# PAY_PER_REQUEST billing — near-zero cost for low-frequency lock operations.

resource "aws_dynamodb_table" "terraform_locks" {
  name         = "nightwatch-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # Enable point-in-time recovery for durability
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name    = "nightwatch-terraform-locks"
    Purpose = "Terraform state locking"
  }
}

# =============================================================================
# 3. Metrics Archive Bucket — nightwatch-metrics-archive-${environment}
# =============================================================================
# Long-term storage for exported metrics.
# Tiered lifecycle: IA → Glacier for cost optimization.

resource "aws_s3_bucket" "metrics_archive" {
  bucket        = "nightwatch-metrics-archive-${var.environment}"
  force_destroy = var.force_destroy

  tags = {
    Name    = "nightwatch-metrics-archive-${var.environment}"
    Purpose = "Long-term metrics archive"
  }
}

resource "aws_s3_bucket_versioning" "metrics_archive" {
  bucket = aws_s3_bucket.metrics_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "metrics_archive" {
  bucket = aws_s3_bucket.metrics_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "metrics_archive" {
  bucket                  = aws_s3_bucket.metrics_archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Tiered lifecycle for cost optimization
resource "aws_s3_bucket_lifecycle_configuration" "metrics_archive" {
  bucket = aws_s3_bucket.metrics_archive.id

  rule {
    id     = "metrics-tiered-storage"
    status = "Enabled"

    # Current version transitions
    transition {
      days          = var.metrics_ia_transition_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.metrics_glacier_transition_days
      storage_class = "GLACIER"
    }

    # Old versions cleanup
    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# =============================================================================
# EKS Storage Classes (annotated for EBS CSI)
# =============================================================================
# These are Kubernetes StorageClass annotations — actual K8s resources
# are managed via Helm/kubectl, but we document sizing expectations here.

# Outputs for reference by other modules
locals {
  storage_config = {
    victoriametrics = {
      size_gb      = var.victoriametrics_size_gb
      storage_class = "gp3"
      description  = "VictoriaMetrics TSDB — high IOPS, gp3 for cost"
    }
    opensearch = {
      size_gb      = var.opensearch_size_gb
      storage_class = "gp3"
      description  = "OpenSearch — large volume, gp3"
    }
    grafana = {
      size_gb      = var.grafana_size_gb
      storage_class = "gp2"
      description  = "Grafana — small, gp2 sufficient"
    }
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "state_bucket_id" {
  description = "S3 state bucket name"
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  description = "S3 state bucket ARN"
  value       = aws_s3_bucket.state.arn
}

output "metrics_archive_bucket_id" {
  description = "Metrics archive bucket name"
  value       = aws_s3_bucket.metrics_archive.id
}

output "metrics_archive_bucket_arn" {
  description = "Metrics archive bucket ARN"
  value       = aws_s3_bucket.metrics_archive.arn
}

output "terraform_locks_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  value       = aws_dynamodb_table.terraform_locks.name
}

output "terraform_locks_table_arn" {
  description = "DynamoDB table ARN"
  value       = aws_dynamodb_table.terraform_locks.arn
}

output "storage_sizes" {
  description = "Map of storage component names to their configured sizes"
  value = {
    victoriametrics_gb = var.victoriametrics_size_gb
    opensearch_gb      = var.opensearch_size_gb
    grafana_gb         = var.grafana_size_gb
  }
}
