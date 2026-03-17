# =============================================================================
# Nightwatch VPC Module
# =============================================================================
# Creates a production-grade VPC with:
#   - Public subnets (for ALB/NAT gateways)
#   - Private subnets (for ECS tasks / EKS nodes)
#   - NAT gateways for private subnet egress
#   - VPC Flow Logs to CloudWatch
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

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.100.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnet placement"
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

variable "single_nat_gateway" {
  description = "Use a single NAT gateway (cheaper, less HA). Set false for HA in prod."
  type        = bool
  default     = false
}

variable "cluster_name" {
  description = "Cluster name for EKS subnet tagging"
  type        = string
  default     = "nightwatch-prod"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "nightwatch" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "nightwatch-vpc-${var.environment}"
    # EKS requires these tags on the VPC
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway (for public subnets)
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "nightwatch" {
  vpc_id = aws_vpc.nightwatch.id

  tags = {
    Name = "nightwatch-igw-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# Public Subnets
# -----------------------------------------------------------------------------
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.nightwatch.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "nightwatch-public-${var.availability_zones[count.index]}-${var.environment}"
    Tier = "public"
    # EKS ALB subnet discovery tag
    "kubernetes.io/role/elb"                             = "1"
    "kubernetes.io/cluster/${var.cluster_name}"         = "shared"
  }
}

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.nightwatch.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.nightwatch.id
  }

  tags = {
    Name = "nightwatch-public-rt-${var.environment}"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------------------
# Private Subnets
# -----------------------------------------------------------------------------
resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.nightwatch.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "nightwatch-private-${var.availability_zones[count.index]}-${var.environment}"
    Tier = "private"
    # EKS internal ALB subnet discovery tag
    "kubernetes.io/role/internal-elb"                    = "1"
    "kubernetes.io/cluster/${var.cluster_name}"         = "shared"
  }
}

# -----------------------------------------------------------------------------
# NAT Gateways (for private subnet egress)
# -----------------------------------------------------------------------------
resource "aws_eip" "nat" {
  count  = var.single_nat_gateway ? 1 : length(var.public_subnet_cidrs)
  domain = "vpc"

  tags = {
    Name = "nightwatch-nat-eip-${count.index}-${var.environment}"
  }
}

resource "aws_nat_gateway" "nightwatch" {
  count = var.single_nat_gateway ? 1 : length(var.public_subnet_cidrs)

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "nightwatch-nat-${count.index}-${var.environment}"
  }

  depends_on = [aws_internet_gateway.nightwatch]
}

# Private route tables — one per AZ (or one shared if single_nat_gateway)
resource "aws_route_table" "private" {
  count  = length(var.private_subnet_cidrs)
  vpc_id = aws_vpc.nightwatch.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.nightwatch[0].id : aws_nat_gateway.nightwatch[count.index].id
  }

  tags = {
    Name = "nightwatch-private-rt-${count.index}-${var.environment}"
  }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# -----------------------------------------------------------------------------
# VPC Flow Logs
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/aws/vpc/nightwatch-${var.environment}"
  retention_in_days = 30
}

resource "aws_iam_role" "flow_logs" {
  name = "nightwatch-vpc-flow-logs-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "flow_logs" {
  name = "nightwatch-flow-logs-${var.environment}"
  role = aws_iam_role.flow_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup", "logs:CreateLogStream",
        "logs:PutLogEvents", "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_flow_log" "nightwatch" {
  vpc_id          = aws_vpc.nightwatch.id
  traffic_type    = "ALL"
  iam_role_arn    = aws_iam_role.flow_logs.arn
  log_destination = aws_cloudwatch_log_group.flow_logs.arn

  tags = {
    Name = "nightwatch-vpc-flow-logs-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.nightwatch.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.nightwatch.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "nat_gateway_ids" {
  description = "NAT gateway IDs"
  value       = aws_nat_gateway.nightwatch[*].id
}

output "internet_gateway_id" {
  description = "Internet gateway ID"
  value       = aws_internet_gateway.nightwatch.id
}
