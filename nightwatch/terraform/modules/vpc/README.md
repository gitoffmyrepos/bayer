# Module: VPC

Creates a production-grade VPC for Nightwatch.

## Architecture

```
Internet Gateway
    ↓
Public Subnets  (ALB, NAT Gateways)  — 3x AZs
    ↓ NAT
Private Subnets (ECS Tasks / EKS Nodes) — 3x AZs
```

## Features
- 3 public + 3 private subnets across AZs
- NAT Gateways (1 per AZ for HA in prod, single for dev)
- VPC Flow Logs → CloudWatch
- EKS subnet tags pre-configured for ALB discovery

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `vpc_cidr` | string | `10.100.0.0/16` | VPC CIDR |
| `availability_zones` | list | `us-east-1a/b/c` | AZs |
| `private_subnet_cidrs` | list | `10.100.1-3.0/24` | Private CIDRs |
| `public_subnet_cidrs` | list | `10.100.101-103.0/24` | Public CIDRs |
| `single_nat_gateway` | bool | `false` | Single NAT (cheaper, less HA) |

## Outputs

| Name | Description |
|------|-------------|
| `vpc_id` | VPC ID |
| `public_subnet_ids` | Public subnet IDs |
| `private_subnet_ids` | Private subnet IDs |
