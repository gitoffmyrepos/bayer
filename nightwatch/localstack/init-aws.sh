#!/usr/bin/env bash
set -Eeuo pipefail

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

: "${NIGHTWATCH_DEMO_PREFIX:?NIGHTWATCH_DEMO_PREFIX is required}"
: "${NIGHTWATCH_EC2_AMI_ID:?NIGHTWATCH_EC2_AMI_ID is required}"
: "${NIGHTWATCH_ECS_CONTAINER_IMAGE:?NIGHTWATCH_ECS_CONTAINER_IMAGE is required}"
: "${NIGHTWATCH_ECS_DESIRED_COUNT:?NIGHTWATCH_ECS_DESIRED_COUNT is required}"

if ! [[ "$NIGHTWATCH_ECS_DESIRED_COUNT" =~ ^[1-9][0-9]*$ ]]; then
  printf 'NIGHTWATCH_ECS_DESIRED_COUNT must be a positive integer\n' >&2
  exit 1
fi

EKS_CLUSTER_NAME="${NIGHTWATCH_DEMO_PREFIX}-eks"
EKS_ROLE_NAME="${NIGHTWATCH_DEMO_PREFIX}-eks-role"
EC2_INSTANCE_NAME="${NIGHTWATCH_DEMO_PREFIX}-stopped"
ECS_CLUSTER_NAME="${NIGHTWATCH_DEMO_PREFIX}-ecs"
ECS_SERVICE_NAME="${NIGHTWATCH_DEMO_PREFIX}-capacity"
ECS_TASK_FAMILY="${NIGHTWATCH_DEMO_PREFIX}-task"

log() {
  printf '[nightwatch-seed] %s\n' "$*"
}

is_missing() {
  [[ -z "$1" || "$1" == "None" || "$1" == "null" ]]
}

log "seeding AWS resources in ${AWS_DEFAULT_REGION}"

if role_arn="$(
  awslocal iam get-role \
    --role-name "$EKS_ROLE_NAME" \
    --query 'Role.Arn' \
    --output text 2>/dev/null
)"; then
  log "IAM role ${EKS_ROLE_NAME} already exists"
else
  role_arn="$(
    awslocal iam create-role \
      --role-name "$EKS_ROLE_NAME" \
      --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"eks.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
      --query 'Role.Arn' \
      --output text
  )"
  log "created IAM role ${EKS_ROLE_NAME}"
fi

if awslocal eks describe-cluster --name "$EKS_CLUSTER_NAME" >/dev/null 2>&1; then
  log "EKS cluster ${EKS_CLUSTER_NAME} already exists"
else
  awslocal eks create-cluster \
    --name "$EKS_CLUSTER_NAME" \
    --role-arn "$role_arn" \
    --resources-vpc-config '{}' >/dev/null
  log "created EKS cluster ${EKS_CLUSTER_NAME}"
fi

for _ in $(seq 1 60); do
  eks_status="$(awslocal eks describe-cluster --name "$EKS_CLUSTER_NAME" --query 'cluster.status' --output text)"
  [[ "$eks_status" == "ACTIVE" ]] && break
  sleep 1
done
if [[ "$eks_status" != "ACTIVE" ]]; then
  log "EKS cluster ${EKS_CLUSTER_NAME} did not reach ACTIVE state (observed ${eks_status})"
  exit 1
fi
mkdir -p /kubeconfigs
awslocal eks update-kubeconfig \
  --name "$EKS_CLUSTER_NAME" \
  --kubeconfig /kubeconfigs/localstack.yaml >/dev/null
chmod 0644 /kubeconfigs/localstack.yaml
log "wrote Kubernetes API connection for ${EKS_CLUSTER_NAME}"

instance_id="$(
  awslocal ec2 describe-instances \
    --filters \
      "Name=tag:Name,Values=${EC2_INSTANCE_NAME}" \
      'Name=instance-state-name,Values=pending,running,stopping,stopped' \
    --query 'Reservations[].Instances[].InstanceId | [0]' \
    --output text
)"
if is_missing "$instance_id"; then
  instance_id="$(
    awslocal ec2 run-instances \
      --image-id "$NIGHTWATCH_EC2_AMI_ID" \
      --count 1 \
      --instance-type t3.micro \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}},{Key=NightwatchMonitored,Value=true}]" \
      --query 'Instances[0].InstanceId' \
      --output text
  )"
  log "created EC2 instance ${instance_id}"
else
  log "EC2 instance ${instance_id} already exists"
fi

instance_state="$(
  awslocal ec2 describe-instances \
    --instance-ids "$instance_id" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text
)"
if [[ "$instance_state" != "stopped" && "$instance_state" != "stopping" ]]; then
  awslocal ec2 stop-instances --instance-ids "$instance_id" >/dev/null
  log "requested stopped state for EC2 instance ${instance_id}"
fi

for _ in $(seq 1 30); do
  instance_state="$(
    awslocal ec2 describe-instances \
      --instance-ids "$instance_id" \
      --query 'Reservations[0].Instances[0].State.Name' \
      --output text
  )"
  [[ "$instance_state" == "stopped" ]] && break
  sleep 1
done
if [[ "$instance_state" != "stopped" ]]; then
  log "EC2 instance ${instance_id} did not reach stopped state"
  exit 1
fi

cluster_status="$(
  awslocal ecs describe-clusters \
    --clusters "$ECS_CLUSTER_NAME" \
    --query 'clusters[0].status' \
    --output text
)"
case "$cluster_status" in
  ""|None|null)
    awslocal ecs create-cluster --cluster-name "$ECS_CLUSTER_NAME" >/dev/null
    log "created ECS cluster ${ECS_CLUSTER_NAME}"
    ;;
  INACTIVE)
    awslocal ecs create-cluster --cluster-name "$ECS_CLUSTER_NAME" >/dev/null
    log "recreated inactive ECS cluster ${ECS_CLUSTER_NAME}"
    ;;
  ACTIVE)
    log "ECS cluster ${ECS_CLUSTER_NAME} already exists"
    ;;
  *)
    log "ECS cluster ${ECS_CLUSTER_NAME} has unsupported status ${cluster_status}"
    exit 1
    ;;
esac

for _ in $(seq 1 30); do
  cluster_status="$(
    awslocal ecs describe-clusters \
      --clusters "$ECS_CLUSTER_NAME" \
      --query 'clusters[0].status' \
      --output text
  )"
  [[ "$cluster_status" == "ACTIVE" ]] && break
  sleep 1
done
if [[ "$cluster_status" != "ACTIVE" ]]; then
  log "ECS cluster ${ECS_CLUSTER_NAME} did not reach ACTIVE state (observed ${cluster_status})"
  exit 1
fi

if task_definition_arn="$(
  awslocal ecs describe-task-definition \
    --task-definition "$ECS_TASK_FAMILY" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text 2>/dev/null
)"; then
  log "ECS task definition ${ECS_TASK_FAMILY} already exists"
else
  task_definition_arn="$(
    awslocal ecs register-task-definition \
      --family "$ECS_TASK_FAMILY" \
      --network-mode bridge \
      --requires-compatibilities EC2 \
      --cpu 128 \
      --memory 128 \
      --container-definitions "[{\"name\":\"workload\",\"image\":\"${NIGHTWATCH_ECS_CONTAINER_IMAGE}\",\"essential\":true,\"memory\":64,\"command\":[\"sleep\",\"3600\"]}]" \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text
  )"
  log "registered ECS task definition ${ECS_TASK_FAMILY}"
fi

create_ecs_service() {
  awslocal ecs create-service \
    --cluster "$ECS_CLUSTER_NAME" \
    --service-name "$ECS_SERVICE_NAME" \
    --task-definition "$task_definition_arn" \
    --desired-count "$NIGHTWATCH_ECS_DESIRED_COUNT" \
    --launch-type EC2 \
    --deployment-configuration 'maximumPercent=100,minimumHealthyPercent=0' >/dev/null
}

service_status="$(
  awslocal ecs describe-services \
    --cluster "$ECS_CLUSTER_NAME" \
    --services "$ECS_SERVICE_NAME" \
    --query 'services[0].status' \
    --output text
)"
case "$service_status" in
  ""|None|null|INACTIVE)
    create_ecs_service
    log "created ECS service ${ECS_SERVICE_NAME} with desired count ${NIGHTWATCH_ECS_DESIRED_COUNT} and no container instances"
    ;;
  DRAINING)
    log "waiting for draining ECS service ${ECS_SERVICE_NAME} to become INACTIVE"
    for _ in $(seq 1 30); do
      service_status="$(
        awslocal ecs describe-services \
          --cluster "$ECS_CLUSTER_NAME" \
          --services "$ECS_SERVICE_NAME" \
          --query 'services[0].status' \
          --output text
      )"
      [[ "$service_status" == "INACTIVE" ]] && break
      sleep 1
    done
    if [[ "$service_status" != "INACTIVE" ]]; then
      log "ECS service ${ECS_SERVICE_NAME} did not drain (observed ${service_status})"
      exit 1
    fi
    create_ecs_service
    log "recreated drained ECS service ${ECS_SERVICE_NAME}"
    ;;
  ACTIVE)
    awslocal ecs update-service \
      --cluster "$ECS_CLUSTER_NAME" \
      --service "$ECS_SERVICE_NAME" \
      --desired-count "$NIGHTWATCH_ECS_DESIRED_COUNT" >/dev/null
    log "ECS service ${ECS_SERVICE_NAME} already exists; enforced desired count ${NIGHTWATCH_ECS_DESIRED_COUNT}"
    ;;
  *)
    log "ECS service ${ECS_SERVICE_NAME} has unsupported status ${service_status}"
    exit 1
    ;;
esac

for _ in $(seq 1 30); do
  service_status="$(
    awslocal ecs describe-services \
      --cluster "$ECS_CLUSTER_NAME" \
      --services "$ECS_SERVICE_NAME" \
      --query 'services[0].status' \
      --output text
  )"
  [[ "$service_status" == "ACTIVE" ]] && break
  sleep 1
done
if [[ "$service_status" != "ACTIVE" ]]; then
  log "ECS service ${ECS_SERVICE_NAME} did not reach ACTIVE state (observed ${service_status})"
  exit 1
fi

eks_status="$(awslocal eks describe-cluster --name "$EKS_CLUSTER_NAME" --query 'cluster.status' --output text)"
ecs_counts="$(
  awslocal ecs describe-services \
    --cluster "$ECS_CLUSTER_NAME" \
    --services "$ECS_SERVICE_NAME" \
    --query 'services[0].[desiredCount,runningCount,pendingCount]' \
    --output text
)"

read -r ecs_desired ecs_running ecs_pending <<<"$ecs_counts"
if ! [[ "$ecs_desired" =~ ^[0-9]+$ && "$ecs_running" =~ ^[0-9]+$ && "$ecs_pending" =~ ^[0-9]+$ ]]; then
  log "ECS service returned invalid capacity counts: ${ecs_counts}"
  exit 1
fi
if [[ "$ecs_desired" -ne "$NIGHTWATCH_ECS_DESIRED_COUNT" || "$ecs_running" -ge "$ecs_desired" ]]; then
  log "ECS fault invariant missing: expected desired=${NIGHTWATCH_ECS_DESIRED_COUNT} and running<desired, observed ${ecs_counts}"
  exit 1
fi

log "seed complete: EKS=${EKS_CLUSTER_NAME}/${eks_status} EC2=${instance_id}/${instance_state} ECS=${ECS_CLUSTER_NAME}/${ECS_SERVICE_NAME} counts(desired running pending)=${ecs_counts}"
