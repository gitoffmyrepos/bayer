# ============================================================================
# Nightwatch ECS Module — Variables
# Generic: works for ANY application adapter
# ============================================================================

variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
}

variable "app_name" {
  description = "Application name — used as resource name prefix"
  type        = string
  default     = "nightwatch"
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
  default     = "nightwatch"
}

variable "image_uri" {
  description = "Docker image URI for the Nightwatch container (any registry)"
  type        = string
}

variable "cpu" {
  description = "Fargate task CPU units (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Desired number of running tasks"
  type        = number
  default     = 1
}

variable "vpc_id" {
  description = "VPC ID where ECS tasks will run"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "execution_role_arn" {
  description = "IAM role ARN for ECS task execution"
  type        = string
}

variable "task_role_arn" {
  description = "IAM role ARN for the Nightwatch task"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment_variables" {
  description = "Environment variables to inject into the container (config/secrets)"
  type        = map(string)
  default     = {}
  # Example:
  # {
  #   NIGHTWATCH_CONFIG     = "config/nightwatch.yaml"
  #   ANTHROPIC_API_KEY     = "sk-ant-..."   # Use secrets manager in prod!
  #   SLACK_WEBHOOK_URL     = "https://..."
  #   LLM_PROVIDER          = "anthropic"
  # }
}

variable "health_check_path" {
  description = "Health check path for the ALB target group"
  type        = string
  default     = "/health"
}

variable "container_port" {
  description = "Port the Nightwatch API listens on"
  type        = number
  default     = 8080
}

variable "scale_up_cpu_threshold" {
  description = "CPU utilization % to trigger scale-out"
  type        = number
  default     = 70
}

variable "max_capacity" {
  description = "Maximum number of tasks for auto-scaling"
  type        = number
  default     = 3
}

variable "min_capacity" {
  description = "Minimum number of tasks"
  type        = number
  default     = 1
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ─── LLM Provider Config ─────────────────────────────────────────────────────

variable "llm_provider" {
  description = "LLM provider: anthropic | openai | deepseek | ollama"
  type        = string
  default     = "anthropic"
  validation {
    condition     = contains(["anthropic", "openai", "deepseek", "ollama"], var.llm_provider)
    error_message = "llm_provider must be one of: anthropic, openai, deepseek, ollama"
  }
}

variable "llm_model" {
  description = "LLM model name (provider-specific)"
  type        = string
  default     = "claude-3-haiku-20240307"
}

variable "ollama_base_url" {
  description = "Ollama base URL (only used when llm_provider = ollama)"
  type        = string
  default     = ""
}
