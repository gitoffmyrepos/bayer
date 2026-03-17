# Module: ECS Fargate

Deploys Nightwatch on **ECS Fargate** — no EC2 instances to manage.

## Architecture

```
Internet → ALB → [ECS Fargate Tasks] → AWS APIs
                         ↑
                 Auto-scaling (CPU > 70%)
```

- **Cluster**: ECS Fargate + Container Insights enabled
- **Tasks**: `nightwatch-collector` container, 512 CPU / 1024 MiB default
- **Networking**: Tasks in private subnets, ALB in public subnets
- **Logging**: CloudWatch Logs, 30-day retention
- **HA**: 2 tasks across AZs by default
- **Rollback**: Deployment circuit breaker with automatic rollback

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `environment` | string | required | Environment name |
| `cluster_name` | string | `"nightwatch"` | ECS cluster name |
| `image_uri` | string | required | Docker image URI |
| `cpu` | number | `512` | Fargate task CPU units |
| `memory` | number | `1024` | Fargate task memory (MiB) |
| `desired_count` | number | `2` | Initial task count |
| `vpc_id` | string | required | VPC ID |
| `private_subnet_ids` | list(string) | required | Private subnets for tasks |
| `public_subnet_ids` | list(string) | required | Public subnets for ALB |
| `execution_role_arn` | string | required | ECS execution role ARN |
| `task_role_arn` | string | required | Application role ARN |
| `max_capacity` | number | `6` | Max tasks (auto-scaling) |
| `min_capacity` | number | `1` | Min tasks (auto-scaling) |
| `scale_up_cpu_threshold` | number | `70` | CPU % trigger for scale-out |

## Outputs

| Name | Description |
|------|-------------|
| `cluster_id` | ECS cluster ID |
| `cluster_name` | ECS cluster name |
| `service_name` | ECS service name |
| `alb_dns_name` | ALB DNS (use as `nightwatch_endpoint`) |
| `log_group_name` | CloudWatch log group |
| `task_definition_arn` | Latest task definition ARN |

## Usage

```hcl
module "ecs" {
  source = "../../modules/ecs"

  environment        = "prod"
  image_uri          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/nightwatch:latest"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  execution_role_arn = module.iam.execution_role_arn
  task_role_arn      = module.iam.task_role_arn
}
```
