# =============================================================================
# Nightwatch Production Environment
# =============================================================================
# Supports two deployment types — set var.deployment_type:
#   "ecs" → ECS Fargate (simpler, no k8s to manage, default)
#   "eks" → EKS (existing setup, more flexible, Kubernetes-based)
#
# Both types share: VPC, IAM, Storage modules
# Conditional: ECS or EKS module activates based on deployment_type
#
# Usage:
#   terraform apply -var="deployment_type=ecs"
#   terraform apply -var="deployment_type=eks"
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  # Remote state backend — uses S3 + DynamoDB locking (provisioned by storage module)
  backend "s3" {
    bucket         = "nightwatch-state-prod"
    key            = "prod/nightwatch.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "nightwatch-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Nightwatch"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Team        = "StrategyBase"
      Client      = "Bayer"
      DeployedAt  = timestamp()
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Locals
# -----------------------------------------------------------------------------
locals {
  account_id      = data.aws_caller_identity.current.account_id
  is_ecs          = var.deployment_type == "ecs"
  is_eks          = var.deployment_type == "eks"
  cluster_name    = "${var.cluster_name_prefix}-${var.environment}"
}

# =============================================================================
# Module: VPC
# Shared between ECS and EKS deployments
# =============================================================================
module "vpc" {
  source = "../../modules/vpc"

  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  private_subnet_cidrs = var.private_subnet_cidrs
  public_subnet_cidrs  = var.public_subnet_cidrs
  cluster_name         = local.cluster_name

  # Use single NAT in non-prod to save cost
  single_nat_gateway = var.environment != "prod"
}

# =============================================================================
# Module: Storage
# Shared — Terraform state bucket, DynamoDB locks, metrics archive
# =============================================================================
module "storage" {
  source = "../../modules/storage"

  environment             = var.environment
  cluster_name            = local.cluster_name
  victoriametrics_size_gb = var.victoriametrics_size_gb
  opensearch_size_gb      = var.opensearch_size_gb
  grafana_size_gb         = var.grafana_size_gb

  # Allow destroy in non-prod only
  force_destroy = var.environment != "prod"

  depends_on = [module.vpc]
}

# =============================================================================
# Module: EKS (active when deployment_type = "eks")
# =============================================================================
module "eks" {
  source = "../../modules/eks"
  count  = local.is_eks ? 1 : 0

  environment        = var.environment
  cluster_name       = local.cluster_name
  cluster_version    = var.cluster_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  aws_region         = var.aws_region

  node_groups              = var.node_groups
  enable_alb_controller    = true

  depends_on = [module.vpc]
}

# =============================================================================
# Module: IAM (always created — provides roles for both ECS and EKS)
# =============================================================================
module "iam" {
  source = "../../modules/iam"

  environment    = var.environment
  cluster_name   = local.cluster_name
  deployment_type = var.deployment_type

  # IRSA settings (EKS only — ignored for ECS)
  oidc_provider_arn = local.is_eks && length(module.eks) > 0 ? module.eks[0].oidc_provider_arn : ""
  oidc_provider_url = local.is_eks && length(module.eks) > 0 ? module.eks[0].oidc_provider_url : ""

  # ModelN.io pipeline resources to monitor in THIS account
  modeln_step_functions   = var.modeln_step_functions
  modeln_glue_jobs        = var.modeln_glue_jobs
  modeln_s3_buckets       = var.modeln_s3_buckets
  modeln_dynamodb_tables  = var.modeln_dynamodb_tables
  modeln_lambda_functions = var.modeln_lambda_functions

  # Cross-account monitoring
  monitored_account_ids = var.monitored_account_ids

  depends_on = [module.eks]
}

# =============================================================================
# Module: ECS Fargate (active when deployment_type = "ecs")
# =============================================================================
module "ecs" {
  source = "../../modules/ecs"
  count  = local.is_ecs ? 1 : 0

  environment        = var.environment
  cluster_name       = local.cluster_name
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  aws_region         = var.aws_region

  # Image to run — must be built and pushed to ECR first
  image_uri     = var.nightwatch_image_uri
  cpu           = var.ecs_cpu
  memory        = var.ecs_memory
  desired_count = var.ecs_desired_count

  # IAM roles created above
  execution_role_arn = module.iam.execution_role_arn
  task_role_arn      = module.iam.task_role_arn

  # Runtime config injected as environment variables
  environment_variables = merge(
    {
      "ENVIRONMENT"           = var.environment
      "AWS_REGION"            = var.aws_region
      "ALERT_EMAIL"           = var.alert_email
      "METRICS_BUCKET"        = module.storage.metrics_archive_bucket_id
      "MONITORED_ACCOUNTS"    = join(",", var.monitored_account_ids)
    },
    var.extra_env_vars
  )

  scale_up_cpu_threshold = 70
  max_capacity           = var.ecs_max_capacity
  min_capacity           = var.ecs_min_capacity

  depends_on = [module.vpc, module.iam]
}

# =============================================================================
# EKS: Kubernetes Resources (active when deployment_type = "eks")
# =============================================================================

# Configure kubernetes provider after EKS is created
provider "kubernetes" {
  host                   = local.is_eks && length(module.eks) > 0 ? module.eks[0].cluster_endpoint : "https://placeholder"
  cluster_ca_certificate = local.is_eks && length(module.eks) > 0 ? base64decode(module.eks[0].cluster_ca_certificate) : ""

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", local.cluster_name]
  }
}

provider "helm" {
  kubernetes {
    host                   = local.is_eks && length(module.eks) > 0 ? module.eks[0].cluster_endpoint : "https://placeholder"
    cluster_ca_certificate = local.is_eks && length(module.eks) > 0 ? base64decode(module.eks[0].cluster_ca_certificate) : ""

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", local.cluster_name]
    }
  }
}

# Nightwatch namespace (EKS only)
resource "kubernetes_namespace" "nightwatch" {
  count = local.is_eks ? 1 : 0

  metadata {
    name = "nightwatch"
    labels = {
      "app.kubernetes.io/name"       = "nightwatch"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  depends_on = [module.eks]
}

# Service account for aws-pipeline-collector with IRSA annotation (EKS only)
resource "kubernetes_service_account" "aws_pipeline_collector" {
  count = local.is_eks ? 1 : 0

  metadata {
    name      = "aws-pipeline-collector"
    namespace = kubernetes_namespace.nightwatch[0].metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = module.iam.aws_pipeline_collector_role_arn
    }
  }
}

# Service account for cloudwatch-exporter with IRSA annotation (EKS only)
resource "kubernetes_service_account" "cloudwatch_exporter" {
  count = local.is_eks ? 1 : 0

  metadata {
    name      = "cloudwatch-exporter"
    namespace = kubernetes_namespace.nightwatch[0].metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = module.iam.cloudwatch_exporter_role_arn
    }
  }
}

# =============================================================================
# Outputs
# =============================================================================

output "nightwatch_endpoint" {
  description = "Nightwatch collector endpoint (ALB DNS for ECS, cluster endpoint for EKS)"
  value = local.is_ecs ? (
    length(module.ecs) > 0 ? "http://${module.ecs[0].alb_dns_name}" : ""
  ) : (
    length(module.eks) > 0 ? module.eks[0].cluster_endpoint : ""
  )
}

output "deployment_type" {
  description = "Active deployment type"
  value       = var.deployment_type
}

output "grafana_url" {
  description = "Grafana dashboard URL (set after Grafana is deployed on top)"
  value = local.is_ecs ? (
    length(module.ecs) > 0 ? "http://${module.ecs[0].alb_dns_name}/grafana" : ""
  ) : "https://grafana.nightwatch.${var.environment}.strategybase.io"
}

output "alertmanager_url" {
  description = "Alertmanager URL"
  value = local.is_ecs ? (
    length(module.ecs) > 0 ? "http://${module.ecs[0].alb_dns_name}/alertmanager" : ""
  ) : "https://alertmanager.nightwatch.${var.environment}.strategybase.io"
}

output "state_bucket" {
  description = "Terraform state bucket name"
  value       = module.storage.state_bucket_id
}

output "metrics_archive_bucket" {
  description = "Metrics archive bucket name"
  value       = module.storage.metrics_archive_bucket_id
}

output "task_role_arn" {
  description = "Nightwatch task role ARN (for cross-account trust policies in monitored accounts)"
  value       = module.iam.task_role_arn
}

output "account_id" {
  description = "AWS account ID — needed for cross-account role trust policies"
  value       = local.account_id
}

output "eks_cluster_name" {
  description = "EKS cluster name (empty for ECS deployment)"
  value       = local.is_eks && length(module.eks) > 0 ? module.eks[0].cluster_name : ""
}

output "ecs_cluster_name" {
  description = "ECS cluster name (empty for EKS deployment)"
  value       = local.is_ecs && length(module.ecs) > 0 ? module.ecs[0].cluster_name : ""
}
