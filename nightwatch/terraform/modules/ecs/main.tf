# =============================================================================
# Nightwatch ECS Fargate Module
# =============================================================================
# Deploys Nightwatch collector on ECS Fargate — no EC2 to manage.
# Supports auto-scaling, ALB for health checks, and CloudWatch logging.
#
# Usage: var.deployment_type = "ecs" in environments/prod/main.tf
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
  description = "Environment name (prod, staging, dev)"
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
  default     = "nightwatch"
}

variable "image_uri" {
  description = "Docker image URI for the nightwatch-collector container"
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
  default     = 2
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
  description = "IAM role ARN for ECS task execution (pull ECR, write CloudWatch)"
  type        = string
}

variable "task_role_arn" {
  description = "IAM role ARN for the nightwatch task (AWS API permissions)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment_variables" {
  description = "Environment variables to inject into the container"
  type        = map(string)
  default     = {}
}

variable "health_check_path" {
  description = "Health check path for the ALB target group"
  type        = string
  default     = "/health"
}

variable "container_port" {
  description = "Port the nightwatch-collector listens on"
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
  default     = 6
}

variable "min_capacity" {
  description = "Minimum number of tasks for auto-scaling"
  type        = number
  default     = 1
}

# -----------------------------------------------------------------------------
# ECS Cluster
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "nightwatch" {
  name = "${var.cluster_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.cluster_name}-${var.environment}"
  }
}

resource "aws_ecs_cluster_capacity_providers" "nightwatch" {
  cluster_name       = aws_ecs_cluster.nightwatch.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "nightwatch" {
  name              = "/ecs/nightwatch-${var.environment}"
  retention_in_days = 30

  tags = {
    Name = "nightwatch-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# Security Groups
# -----------------------------------------------------------------------------

# ALB Security Group — allows inbound HTTP/HTTPS from internet
resource "aws_security_group" "alb" {
  name        = "nightwatch-alb-${var.environment}"
  description = "Nightwatch ALB — allow HTTP/HTTPS inbound"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP from internet"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS from internet"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = {
    Name = "nightwatch-alb-${var.environment}"
  }
}

# ECS Task Security Group — allows traffic only from the ALB
resource "aws_security_group" "ecs_tasks" {
  name        = "nightwatch-ecs-tasks-${var.environment}"
  description = "Nightwatch ECS tasks — allow from ALB only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "From ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound (AWS API calls, etc.)"
  }

  tags = {
    Name = "nightwatch-ecs-tasks-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# Application Load Balancer
# -----------------------------------------------------------------------------
resource "aws_lb" "nightwatch" {
  name               = "nightwatch-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod" ? true : false

  tags = {
    Name = "nightwatch-${var.environment}"
  }
}

resource "aws_lb_target_group" "nightwatch" {
  name        = "nightwatch-${var.environment}"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Required for Fargate

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = var.health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 10
    unhealthy_threshold = 3
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "nightwatch-${var.environment}"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.nightwatch.arn
  port              = 80
  protocol          = "HTTP"

  # Redirect HTTP → HTTPS in prod; allow in non-prod
  default_action {
    type = var.environment == "prod" ? "redirect" : "forward"

    dynamic "redirect" {
      for_each = var.environment == "prod" ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

    dynamic "forward" {
      for_each = var.environment != "prod" ? [1] : []
      content {
        target_group {
          arn = aws_lb_target_group.nightwatch.arn
        }
      }
    }
  }
}

# -----------------------------------------------------------------------------
# ECS Task Definition
# -----------------------------------------------------------------------------
resource "aws_ecs_task_definition" "nightwatch" {
  family                   = "nightwatch-collector-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    {
      name      = "nightwatch-collector"
      image     = var.image_uri
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        for k, v in var.environment_variables : { name = k, value = v }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.nightwatch.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "nightwatch"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}${var.health_check_path} || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "nightwatch-collector-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# ECS Service
# -----------------------------------------------------------------------------
resource "aws_ecs_service" "nightwatch" {
  name            = "nightwatch-collector"
  cluster         = aws_ecs_cluster.nightwatch.id
  task_definition = aws_ecs_task_definition.nightwatch.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    security_groups  = [aws_security_group.ecs_tasks.id]
    subnets          = var.private_subnet_ids
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.nightwatch.arn
    container_name   = "nightwatch-collector"
    container_port   = var.container_port
  }

  deployment_configuration {
    minimum_healthy_percent = 50
    maximum_percent         = 200

    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  # Allow external changes to desired_count (from auto-scaling)
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_ecs_cluster_capacity_providers.nightwatch,
  ]

  tags = {
    Name = "nightwatch-collector-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# Auto-Scaling
# -----------------------------------------------------------------------------

# Register ECS service as a scalable target
resource "aws_appautoscaling_target" "nightwatch" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.nightwatch.name}/${aws_ecs_service.nightwatch.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Scale out when CPU > threshold for 2 consecutive periods
resource "aws_appautoscaling_policy" "scale_out_cpu" {
  name               = "nightwatch-scale-out-cpu-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.nightwatch.resource_id
  scalable_dimension = aws_appautoscaling_target.nightwatch.scalable_dimension
  service_namespace  = aws_appautoscaling_target.nightwatch.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = var.scale_up_cpu_threshold
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Scale based on memory too
resource "aws_appautoscaling_policy" "scale_out_memory" {
  name               = "nightwatch-scale-out-memory-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.nightwatch.resource_id
  scalable_dimension = aws_appautoscaling_target.nightwatch.scalable_dimension
  service_namespace  = aws_appautoscaling_target.nightwatch.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }

    target_value       = 80
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.nightwatch.id
}

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.nightwatch.name
}

output "service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.nightwatch.name
}

output "alb_dns_name" {
  description = "ALB DNS name — use this as nightwatch_endpoint"
  value       = aws_lb.nightwatch.dns_name
}

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.nightwatch.arn
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.nightwatch.name
}

output "task_definition_arn" {
  description = "Latest task definition ARN"
  value       = aws_ecs_task_definition.nightwatch.arn
}
