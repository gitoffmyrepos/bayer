# Module: EKS

Creates an EKS v1.31 cluster for Nightwatch with IRSA and ALB controller.

## Key Features

- **Kubernetes 1.31** managed control plane
- **Managed node groups** — t3.medium, 2-3 nodes (configurable)
- **IRSA** — pods get AWS credentials via OIDC, no static keys
- **aws-load-balancer-controller** — creates ALBs from Kubernetes Ingress
- **EBS CSI driver** — enables PersistentVolumes (for VictoriaMetrics, OpenSearch, Grafana)
- **VPC Flow Logs** — enabled on the VPC

## IRSA Flow

```
Pod (annotated with role ARN)
  → kube API projects signed JWT
  → STS validates JWT against OIDC thumbprint
  → Returns temporary AWS credentials
  → No static keys, full CloudTrail audit
```

## Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `environment` | string | required | Environment name |
| `cluster_name` | string | `"nightwatch-prod"` | Cluster name |
| `cluster_version` | string | `"1.31"` | K8s version |
| `vpc_id` | string | required | VPC ID |
| `private_subnet_ids` | list(string) | required | Worker node subnets |
| `node_instance_type` | string | `"t3.medium"` | Default instance type |
| `node_desired_size` | number | `2` | Default desired nodes |
| `node_groups` | map(object) | `{}` | Custom node groups (overrides simple vars) |
| `enable_alb_controller` | bool | `true` | Install aws-load-balancer-controller |

## Outputs

| Name | Description |
|------|-------------|
| `cluster_endpoint` | EKS API server URL |
| `cluster_ca_certificate` | Base64 cluster CA cert |
| `cluster_name` | Cluster name |
| `oidc_provider_arn` | OIDC provider ARN (for IAM module) |
| `oidc_provider_url` | OIDC URL without https:// |

## Note on `alb-controller-policy.json`

This module expects `${path.module}/alb-controller-policy.json` — the official
AWS policy for the load balancer controller. Download from:
https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json
