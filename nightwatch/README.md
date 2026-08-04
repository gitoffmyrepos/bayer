# Nightwatch

Nightwatch is a read-only operations intelligence console for cloud infrastructure,
Kubernetes, and application pipelines. It collects provider evidence, evaluates
deterministic health checks, records findings, and can ask a local Ollama model to
explain those findings. The LLM does not decide whether a resource is healthy and
does not receive permission to change it.

This repository currently delivers the first cloud-security vertical slice:

- AWS EKS control-plane, EC2 instance, and ECS service discovery through one
  `aws_infrastructure` adapter that works with LocalStack or real AWS.
- Deterministic findings for non-active EKS clusters, stopped monitored EC2
  instances, and ECS desired/running capacity mismatch.
- A Unified Operations UI with Cloud Estate, Kubernetes, Live Check, Topology,
  Incidents, and AI Analyst views. Empty and failed providers remain visibly empty
  or unavailable; the UI does not substitute demonstration records.
- Ollama-backed incident explanations grounded in collected metrics, logs, and
  failed checks.
- Dormant remediation code protected by an environment-and-config gate. Observe
  mode is the default.

Nightwatch is not yet a feature-for-feature replacement for Rapid7 InsightCloudSec
or InsightAppSec. This release establishes the read-only inventory, finding, UI,
and AI-explanation path. Multi-account posture policies, vulnerability ingestion,
long-term canonical storage, AppSec scanning, and enterprise reporting are later
phases.

The approved expansion path keeps Nightwatch's asset/finding/evidence model and UI
as the product boundary while normalizing results from mature open-source engines:

- [Prowler](https://github.com/prowler-cloud/prowler) first for AWS/Kubernetes
  posture and compliance coverage.
- [Trivy](https://github.com/aquasecurity/trivy) or
  [Kubescape](https://github.com/kubescape/kubescape) for vulnerability and
  misconfiguration evidence.
- [K8sGPT](https://github.com/k8sgpt-ai/k8sgpt) as an optional source of codified
  Kubernetes diagnostics.
- [Coroot](https://github.com/coroot/coroot) as an observability and service-map
  reference, not an embedded competing dashboard.

Those integrations are a roadmap, not enabled capabilities in this demo. Active
DAST/AppSec scanning also remains a separately authorized later phase.

## How it works

```text
LocalStack or AWS APIs                 Kubernetes API / application APIs
          |                                          |
          +---------------- adapters ----------------+
                                 |
                    normalized components + checks
                                 |
                    deterministic finding lifecycle
                                 |
                  +--------------+---------------+
                  |                              |
           REST API and UI                Ollama explanation
                                                   |
                                         evidence in, prose out

Remediation packages remain installed but are not constructed unless BOTH
REMEDIATION_ENABLED=true and healing.mode=auto_remediate are configured.
```

## Ten-minute LocalStack demo

The demo runs LocalStack in Docker because its embedded EKS implementation needs
the host Docker socket. Do not move LocalStack into a Kubernetes pod for this lab;
EKS emulation is not supported in that deployment mode.

EKS emulation is an Ultimate-tier LocalStack for AWS feature and requires a valid
`LOCALSTACK_AUTH_TOKEN`. The boss-demo Compose file deliberately fails during
interpolation when either the token or image is missing. It never substitutes a
fabricated EKS record. If Ultimate is unavailable, use a read-only real AWS sandbox for
the full EKS path; an EC2/ECS-only LocalStack run is not equivalent to this demo.

### Prerequisites

- Linux with Docker Engine and Docker Compose v2 (`docker compose version`).
- Access to `/var/run/docker.sock` for the current user. Mounting the Docker socket
  gives the LocalStack container root-equivalent control of the host Docker daemon.
  Run this lab only on a trusted, isolated demo workstation; never mount an
  untrusted script or image beside that socket.
- Enough free memory for LocalStack, an embedded k3d/k3s control plane, Nightwatch,
  and the selected Ollama model.
- Ollama reachable from the Docker host. The checked-in configuration uses
  `qwen3:14b`; either pull that model or change `llm.model` in
  `config/nightwatch.demo.yaml` to a model already installed locally.
- A LocalStack Ultimate auth token and a LocalStack for AWS image tag/digest that
  your team has validated.

The ten-minute target assumes the Docker images and Ollama model are already
cached. Initial image/model downloads can take longer.

### 1. Verify Ollama

```bash
curl -fsS http://localhost:11434/api/tags
# Only when qwen3:14b is not already listed:
ollama pull qwen3:14b
```

If Ollama runs elsewhere, set the URL that is reachable **from the Nightwatch
container**, not merely from the browser:

```bash
export OLLAMA_BASE_URL=http://192.168.1.25:11434
```

The Compose default is `http://host.docker.internal:11434`; the file adds the
Linux `host-gateway` mapping.

### 2. Start the lab

```bash
read -rsp 'LocalStack auth token: ' LOCALSTACK_AUTH_TOKEN && echo
export LOCALSTACK_AUTH_TOKEN

# `latest` is a moving stable release, useful for the first pull. For a repeatable
# presentation, replace this with the tested calendar-version tag or RepoDigest.
export LOCALSTACK_IMAGE='localstack/localstack-pro:latest'

# These are operator-selected inputs, not records fabricated by Nightwatch.
export NIGHTWATCH_DEMO_PREFIX='nightwatch-demo'
export NIGHTWATCH_EC2_AMI_ID='ami-024f768332f0'
export NIGHTWATCH_ECS_CONTAINER_IMAGE='public.ecr.aws/docker/library/busybox:1.36'
export NIGHTWATCH_ECS_DESIRED_COUNT='2'

cd nightwatch
docker compose -f docker-compose.demo.yml up -d --build
docker compose -f docker-compose.demo.yml ps
docker compose -f docker-compose.demo.yml logs -f localstack nightwatch-api
```

Do not commit the token to `.env` or paste it into shared shell history. Docker
stores container environment values in its local metadata, so protect access to the
Docker daemon and remove the demo containers when finished.

After validating a release, record and reuse its immutable digest:

```bash
docker pull "$LOCALSTACK_IMAGE"
docker image inspect --format '{{index .RepoDigests 0}}' "$LOCALSTACK_IMAGE"
# Example shape only; paste the digest printed above:
# export LOCALSTACK_IMAGE='localstack/localstack-pro@sha256:...'
```

The demo config is `config/nightwatch.demo.yaml`. It enables only the
`aws-infrastructure` and `kubernetes-clusters` adapters, uses Ollama, disables
external alert severities, and sets `healing.mode: observe_only`. LocalStack uses the current
`MANAGED_K8S_PROVIDER=k3s` setting to create the embedded Kubernetes control plane.
Its Docker EC2 manager creates a real backing container rather than a CRUD-only
resource record. The ready hook writes the EKS kubeconfig into a read-only shared
volume so Nightwatch connects to the embedded Kubernetes API server as well as the
AWS EKS API.

The LocalStack ready hook is idempotent. Recreating the stack preserves and
reconciles the same named resources instead of adding duplicates:

- EKS cluster `${NIGHTWATCH_DEMO_PREFIX}-eks`.
- EC2 instance tagged `Name=${NIGHTWATCH_DEMO_PREFIX}-stopped`, forced to `stopped`.
- ECS cluster `${NIGHTWATCH_DEMO_PREFIX}-ecs` and service
  `${NIGHTWATCH_DEMO_PREFIX}-capacity`, configured with the operator-selected
  desired count and no registered
  EC2 container instances.

The seed log prints the states returned by LocalStack. Those returned states—not
the storyline above—are authoritative for what Nightwatch displays.

### 3. Prove the seed and safety state

```bash
docker compose -f docker-compose.demo.yml exec localstack \
  awslocal eks describe-cluster --name "${NIGHTWATCH_DEMO_PREFIX}-eks" \
  --query 'cluster.{name:name,status:status,version:version}'

docker compose -f docker-compose.demo.yml exec localstack \
  awslocal ec2 describe-instances \
  --filters "Name=tag:Name,Values=${NIGHTWATCH_DEMO_PREFIX}-stopped" \
  --query 'Reservations[].Instances[].{id:InstanceId,state:State.Name,name:Tags[?Key==`Name`]|[0].Value}'

docker compose -f docker-compose.demo.yml exec localstack \
  awslocal ecs describe-services \
  --cluster "${NIGHTWATCH_DEMO_PREFIX}-ecs" \
  --services "${NIGHTWATCH_DEMO_PREFIX}-capacity" \
  --query 'services[].{name:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount,status:status}'

docker compose -f docker-compose.demo.yml exec nightwatch-api \
  sh -c 'test "$REMEDIATION_ENABLED" = false && echo observe-mode-environment-ok'
```

If the EKS resource remains `CREATING` briefly, Nightwatch reports that observed
state. It does not rewrite it to `ACTIVE` for the demo.

### 4. Trigger a check and open the console

```bash
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/adapters
curl -fsS -X POST http://localhost:8080/check
curl -fsS http://localhost:8080/status
curl -fsS http://localhost:8080/incidents
```

Open:

- Unified Operations UI: <http://localhost:3000>
- Interactive API documentation: <http://localhost:8080/docs>
- LocalStack edge endpoint: <http://localhost:4566>

Boss-demo path:

1. Start on Command Center and show that the resources come from the adapter API.
2. Open Cloud Estate and inspect the stopped EC2 instance and ECS capacity values.
3. Open Kubernetes and show the EKS control-plane resource and its actual status.
4. Open Live Check to trigger collection, then Incidents for failed checks.
5. Open Topology to relate provider, cluster, instance, and service components.
6. Open AI Analyst and generate an explanation for a real incident. If Ollama is
   unavailable, the page reports the provider error rather than showing prewritten AI
   text.

### 5. Stop or reset the lab

```bash
# Stop containers and keep the emulated AWS state:
docker compose -f docker-compose.demo.yml down

# Reset only this demo, including its LocalStack named volume:
docker compose -f docker-compose.demo.yml down -v --remove-orphans
```

The second command permanently removes the emulated resources in this local demo
volume. It does not address real AWS.

## Connect to real AWS

The same adapter uses boto3 for LocalStack and AWS. The switch is the endpoint:

```yaml
# config/aws_infrastructure/config.yaml
application_name: AWS Infrastructure
region: ${AWS_REGION}
endpoint_url: ${AWS_ENDPOINT_URL}
```

- LocalStack: `AWS_ENDPOINT_URL=http://localstack:4566`.
- Real AWS: leave `AWS_ENDPOINT_URL` unset/empty. boto3 selects the standard AWS
  service endpoints for the configured region.

Region resolution is `config region` → `AWS_REGION` → `AWS_DEFAULT_REGION` →
`us-east-1`. Credentials use the standard boto3 chain. In production, prefer an
EKS workload identity/IRSA role, ECS task role, or EC2 instance profile. Do not
bake access keys into an image or commit them to YAML.

### Minimal read-only IAM policy

Start with a dedicated role and reduce it further after checking CloudTrail for
the selected deployment. The current infrastructure adapter only needs list and
describe operations:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "NightwatchIdentity",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    },
    {
      "Sid": "NightwatchEKSRead",
      "Effect": "Allow",
      "Action": ["eks:ListClusters", "eks:DescribeCluster"],
      "Resource": "*"
    },
    {
      "Sid": "NightwatchEC2Read",
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"],
      "Resource": "*"
    },
    {
      "Sid": "NightwatchECSRead",
      "Effect": "Allow",
      "Action": [
        "ecs:ListClusters",
        "ecs:DescribeClusters",
        "ecs:ListServices",
        "ecs:DescribeServices"
      ],
      "Resource": "*"
    }
  ]
}
```

AWS requires `Resource: "*"` for several list/describe APIs. This is still a
read-only action set; use organization SCPs and permission boundaries as an
additional guard.

Validate the identity and every operation before starting Nightwatch:

```bash
unset AWS_ENDPOINT_URL
export AWS_REGION=us-east-1

aws sts get-caller-identity
aws eks list-clusters --region "$AWS_REGION"
aws ec2 describe-instances --region "$AWS_REGION" --max-results 5
aws ecs list-clusters --region "$AWS_REGION"
```

Run outside Compose for the clearest real-AWS credential behavior:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export NIGHTWATCH_CONFIG=config/nightwatch.yaml
export OLLAMA_BASE_URL=http://localhost:11434
export REMEDIATION_ENABLED=false
export NIGHTWATCH_GH_ENABLED=false
unset AWS_ENDPOINT_URL

python -m src.api.main
```

One adapter instance currently represents one credential context and region. For
separate AWS accounts, run isolated Nightwatch deployments with separate IAM roles
until cross-account assume-role support is implemented. Do not share a broad
organization-wide credential as a shortcut.

## Connect to an EKS or Kubernetes cluster

The `aws_infrastructure` adapter discovers the EKS **control-plane resource** via
AWS APIs. Pod, workload, event, and log visibility is a separate Kubernetes API
connection. Keep that distinction visible in reviews: a healthy EKS control plane
does not prove every workload is healthy.

### Outside the cluster

Creating kubeconfig does not grant a principal access to EKS. A platform
administrator must first create a dedicated access entry and associate a read-only
access policy. These two onboarding calls require administrator permissions; they
are not permissions granted to the Nightwatch runtime role:

```bash
export EKS_CLUSTER_NAME=my-cluster
export AWS_REGION=us-east-1
export NIGHTWATCH_ROLE_ARN='arn:aws:iam::123456789012:role/NightwatchObserver'

aws eks create-access-entry \
  --cluster-name "$EKS_CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --principal-arn "$NIGHTWATCH_ROLE_ARN" \
  --type STANDARD

aws eks associate-access-policy \
  --cluster-name "$EKS_CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --principal-arn "$NIGHTWATCH_ROLE_ARN" \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy \
  --access-scope type=cluster

aws eks update-kubeconfig \
  --name "$EKS_CLUSTER_NAME" \
  --region "$AWS_REGION" \
  --role-arn "$NIGHTWATCH_ROLE_ARN" \
  --alias nightwatch-my-cluster

kubectl --context nightwatch-my-cluster auth can-i get pods --all-namespaces
kubectl --context nightwatch-my-cluster auth can-i list events --all-namespaces
kubectl --context nightwatch-my-cluster auth can-i patch deployments --all-namespaces
```

The first two checks should return `yes`; the mutation check should return `no`.
Mount the resulting kubeconfig read-only and use an explicit context. Do not mount a
developer kubeconfig that contains cluster-admin credentials. For clusters still
using legacy `aws-auth` mapping, migrate to EKS access entries or map the role to a
dedicated read-only Kubernetes group; never map Nightwatch to `system:masters`.

Nightwatch can connect to every context in one kubeconfig, or to an explicit
registry of kubeconfig/context pairs. It creates a separate API client for every
entry and reads nodes, pods, and deployments from each API server:

```yaml
application_name: Kubernetes Clusters
discover_kubeconfig_contexts: true
kubeconfig_path: ${KUBECONFIG}
request_timeout_seconds: 10
clusters: []
```

For kubeconfigs stored separately, disable discovery and enumerate them:

```yaml
application_name: Kubernetes Clusters
discover_kubeconfig_contexts: false
clusters:
  - name: production-us
    kubeconfig_path: /var/run/nightwatch/clusters/production-us.yaml
    context: nightwatch
  - name: production-eu
    kubeconfig_path: /var/run/nightwatch/clusters/production-eu.yaml
    context: nightwatch
    namespaces: [payments, platform]
```

Mount each kubeconfig read-only. The adapter fails closed on a missing file,
duplicate name, missing client dependency, or empty registry; an unreachable API
server becomes an `UNKNOWN` collection check rather than a healthy cluster. When
`namespaces` is omitted, the adapter reads all namespaces allowed by that
connection's RBAC. The adapter calls only Kubernetes read/list endpoints.

### In the cluster

Deploy Nightwatch with a dedicated ServiceAccount and only observation verbs. This
is the minimum pattern; add resources only when an adapter demonstrably needs them:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nightwatch
  namespace: nightwatch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nightwatch-observer
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services", "endpoints", "nodes", "namespaces", "events"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets", "daemonsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nightwatch-observer
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: nightwatch-observer
subjects:
  - kind: ServiceAccount
    name: nightwatch
    namespace: nightwatch
```

Validate the deployed identity, not your workstation identity:

```bash
kubectl auth can-i --as=system:serviceaccount:nightwatch:nightwatch \
  list pods --all-namespaces
kubectl auth can-i --as=system:serviceaccount:nightwatch:nightwatch \
  patch deployments --all-namespaces
```

Do not bind the optional remediation Role/RoleBinding in observe-only deployments.
`REMEDIATION_ENABLED=false` is a software gate; read-only RBAC is the independent
authorization boundary.

## Expose Nightwatch through kgateway

The production layout uses two ClusterIP Services and one hostname:

```text
https://nightwatch.example.com/api/* -> nightwatch:8080 (strip /api prefix)
https://nightwatch.example.com/*     -> nightwatch-frontend:3000
```

Deployment checklist:

1. Label the application namespace `kgateway.dev/discover=true` if the gateway's
   discovery selector requires it.
2. Expose backend port 8080 and frontend port 3000 as ClusterIP Services.
3. Attach the HTTPRoute to the existing Gateway and its HTTPS listener; in this
   environment that is `ha-cluster-gateway` in `kgateway-system` with
   `sectionName: https`.
4. Route `/api` to the backend with `URLRewrite.ReplacePrefixMatch` set to `/`.
   Route `/` to the frontend. Keep the rules separate.
5. If the HTTPRoute and Services are in different namespaces, create a narrowly
   scoped `ReferenceGrant` in the Service namespace.
6. Apply the platform's existing OIDC TrafficPolicy to the UI/API route. Do not
   publish a second unauthenticated hostname for the API.
7. Restrict backend ingress to kgateway, readiness probes, and required
   intra-namespace traffic. Allow only the AWS, Kubernetes, Ollama, DNS, and alert
   egress destinations actually used.

In this homelab the GitOps source of truth is
`sb-gitops/prod/platform-workloads/manifests/nightwatch/nightwatch.yaml`. Change and
commit that source; do not patch the live route as a permanent fix.

Verify routing and authentication:

```bash
kubectl get httproute -A | grep nightwatch
kubectl describe httproute nightwatch-route -n prod-forex
curl -I https://nightwatch.example.com/
curl -I https://nightwatch.example.com/api/health
```

An unauthenticated request should follow the configured OIDC flow. An authenticated
`/api/health` request should reach FastAPI without retaining the `/api` prefix.

## Argo Workflows and Harbor delivery

A push to `bayer` master is consumed by the shared `github-push/external-push`
event source. The `external-repo-build` Sensor submits two independent Kaniko
workflows through `external-repo-kaniko-build`:

| Build context | Harbor destination | Rolling tag |
| --- | --- | --- |
| `bayer/nightwatch/Dockerfile` | `harbor.strategybase.io/sb-custom-docker-images/nightwatch-agent` | `prod-latest` |
| `bayer/nightwatch/frontend/Dockerfile` | `harbor.strategybase.io/sb-custom-docker-images/nightwatch-frontend` | `prod-latest` |

Kaniko also pushes `git-<short-sha>` for traceability. The workflow uses the
existing `harbor-push` Docker configuration secret and runs both images as numeric
UID/GID `1000:1000`. On a successful Harbor push, its exit handler restarts the
declared Nightwatch deployments; failed builds never trigger a rollout.

The source of truth is in `sb-gitops/prod/platform-workloads/manifests/argo-workflows-ci/`:

- `20-external-repo-build-workflowtemplate.yaml`
- `21-external-repo-sensors.yaml`
- `17-prod-forex-rollout-rbac.yaml`

Inspect a build without changing the cluster:

```bash
kubectl get workflows -n argo-ci -l build-target=nightwatch-agent
kubectl get workflows -n argo-ci -l build-target=nightwatch-frontend
kubectl get deployment -n nightwatch nightwatch nightwatch-frontend \
  -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image
```

## Connect Nightwatch to your application

An adapter is a boundary between an application/provider API and the Nightwatch
core. It must return observed values and deterministic checks. It must not fabricate
success when credentials, network access, or fields are missing.

### 1. Define an observable contract

For example, an application may expose `GET /health` with `status`, `database`, and
`queue_depth` fields. Protect the endpoint with workload identity, mTLS, or a
read-only token and avoid returning secrets or customer data.

### 2. Implement the adapter

Create `src/adapters/checkout/adapter.py`:

```python
from __future__ import annotations

from typing import Any

import httpx

from src.adapters.base_adapter import BaseNightwatchAdapter, Component, HealthCheck


class CheckoutAdapter(BaseNightwatchAdapter):
    """Read-only adapter for a checkout service health contract."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._snapshot: dict[str, Any] = {}
        self._collection_error: str | None = None

    @property
    def application_name(self) -> str:
        return "Checkout"

    def collect_metrics(self) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.config['base_url'].rstrip('/')}/health",
                headers={"Authorization": f"Bearer {self.config['read_token']}"},
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("health response must be a JSON object")

            status = payload.get("status")
            database = payload.get("database")
            queue_depth = payload.get("queue_depth")
            if not isinstance(status, str) or not isinstance(database, str):
                raise ValueError("status and database must be strings")
            if not isinstance(queue_depth, int) or queue_depth < 0:
                raise ValueError("queue_depth must be a non-negative integer")

            self._snapshot = {
                "available": True,
                "status": status,
                "database": database,
                "queue_depth": queue_depth,
            }
            self._collection_error = None
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._collection_error = str(exc)
            self._snapshot = {"available": False, "collection_error": str(exc)}
        return dict(self._snapshot)

    def collect_logs(self, lookback_minutes: int = 15) -> list[str]:
        # This application contract exposes no log API. Return no evidence rather
        # than inventing log lines or reading a source without authorization.
        return []

    def run_health_checks(self) -> list[HealthCheck]:
        snapshot = self.collect_metrics()
        if not snapshot.get("available"):
            return [self._fail(
                "checkout_collection",
                f"Health evidence unavailable: {self._collection_error}",
                component="checkout-api",
            )]

        checks = []
        checks.append(
            self._ok("checkout_status", "Checkout reports healthy", "checkout-api")
            if snapshot["status"] == "ok"
            else self._fail(
                "checkout_status",
                f"Checkout reports {snapshot['status']}",
                "checkout-api",
                observed_status=snapshot["status"],
            )
        )
        checks.append(
            self._ok("checkout_database", "Database reports ready", "checkout-db")
            if snapshot["database"] == "ready"
            else self._fail(
                "checkout_database",
                f"Database reports {snapshot['database']}",
                "checkout-db",
                observed_status=snapshot["database"],
            )
        )

        maximum = int(self.config.get("max_queue_depth", 100))
        checks.append(
            self._warn(
                "checkout_queue_depth",
                f"Queue depth {snapshot['queue_depth']} exceeds {maximum}",
                "checkout-worker",
                observed=snapshot["queue_depth"],
                threshold=maximum,
            )
            if snapshot["queue_depth"] > maximum
            else self._ok(
                "checkout_queue_depth",
                f"Queue depth {snapshot['queue_depth']} is within {maximum}",
                "checkout-worker",
                observed=snapshot["queue_depth"],
                threshold=maximum,
            )
        )
        return checks

    def get_component_inventory(self) -> list[Component]:
        return [
            Component("checkout-api", "api_endpoint", "Application"),
            Component("checkout-db", "database", "Application"),
            Component("checkout-worker", "worker", "Application"),
        ]
```

Keep collection and evaluation separate when the adapter becomes larger. Bound
response sizes and timeouts because metrics/log evidence may be sent to the LLM.

### 3. Configure and register it

Create `config/checkout/config.yaml`:

```yaml
base_url: ${CHECKOUT_BASE_URL}
read_token: ${CHECKOUT_READ_TOKEN}
max_queue_depth: 100
```

Add the class to `ADAPTER_REGISTRY` in `src/api/main.py`:

```python
try:
    from src.adapters.checkout.adapter import CheckoutAdapter
    ADAPTER_REGISTRY["checkout"] = CheckoutAdapter
except ImportError:
    log.warning("adapter_unavailable", type="checkout")
```

Enable it in `config/nightwatch.yaml`:

```yaml
adapters:
  - name: checkout-production
    type: checkout
    config_file: checkout/config.yaml
    enabled: true
```

Missing environment variables resolve to empty strings and are logged. Treat that
as a configuration failure; never replace a missing credential or endpoint with a
test value in production.

### 4. Test deterministic behavior

Test the adapter with controlled HTTP responses and assert check names, statuses,
and evidence metadata. At minimum cover:

- healthy response;
- non-200/timeout and invalid schema produce an explicit collection failure;
- each threshold boundary (`==`, just below, just above);
- no secret token appears in `HealthCheck.message`, metadata, logs, or exceptions;
- `get_component_inventory()` contains only resources actually represented by the
  adapter.

Run the focused test and compilation gate:

```bash
pytest -q tests/test_checkout_adapter.py
python -m py_compile src/adapters/checkout/adapter.py
```

Then start Nightwatch and verify the live contract:

```bash
curl -fsS http://localhost:8080/adapters
curl -fsS -X POST 'http://localhost:8080/check?adapter=checkout-production'
curl -fsS http://localhost:8080/status
curl -fsS 'http://localhost:8080/incidents?adapter=checkout-production'
```

### Finding, alert, and LLM behavior

1. The adapter collects bounded evidence.
2. `run_health_checks()` produces `OK`, `WARN`, `FAIL`, or `UNKNOWN` from explicit
   code and thresholds.
3. WARN/FAIL checks create or update incidents through the engine's deduplication
   lifecycle.
4. The evidence and architecture description may be passed to Ollama for a root
   cause explanation and operator recommendation.
5. Configured alert channels receive eligible severities. An alerting failure does
   not turn the underlying finding healthy.
6. With remediation disabled, recommendations remain text. No suggested command is
   executed.

See [docs/ADAPTER_GUIDE.md](docs/ADAPTER_GUIDE.md) and
[`BaseNightwatchAdapter`](src/adapters/base_adapter.py) for the complete interface.

## REST API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Nightwatch process health; not monitored-resource health |
| `GET` | `/status` | Current adapter health and latest check summaries |
| `GET` | `/adapters` | Configured adapters and real component inventory |
| `POST` | `/check?adapter=name` | Trigger one adapter or all adapters |
| `GET` | `/incidents` | Query incidents; supports adapter and active filters |
| `GET` | `/metrics` | Current collected metrics snapshot |
| `GET` | `/schedule` | Monitor-loop scheduling state |
| `POST` | `/report` | Generate an Ollama report for an existing incident ID |

The API does not currently provide authentication itself. Put it behind the same
kgateway/OIDC policy as the UI or another trusted identity-aware proxy. Do not
expose port 8080 directly to the public internet.

## Safety model

Observe mode uses defense in depth:

1. `config/nightwatch.demo.yaml` sets `healing.mode: observe_only` for the lab;
   production configuration must retain the same default.
2. `REMEDIATION_ENABLED` defaults to `false` in code and the demo Compose file.
3. Remediation clients, playbooks, and code analyzers are not constructed unless
   **both** controls explicitly enable remediation.
4. Production IAM and Kubernetes RBAC should contain only read verbs, so an
   accidental application flag cannot grant mutation authority.
5. `NIGHTWATCH_GH_ENABLED=false` disables the separate Kubernetes-event-to-GitHub
   issue writer in the demo. Enable it only after deciding that external issue
   creation is an authorized side effect; its dry-run switch is independent of
   infrastructure remediation.

Future remediation requires a deliberate change to both controls:

```text
REMEDIATION_ENABLED=true
healing.mode=auto_remediate
```

That is necessary but not sufficient: operators must separately review the
remediation allowlist, workload identity, writable RBAC/IAM, Git credentials,
approval flow, audit logging, rollback, and blast radius. Never enable it merely to
make a finding disappear.

## Troubleshooting

### No AWS adapter appears

```bash
docker compose -f docker-compose.demo.yml logs nightwatch-api
curl -fsS http://localhost:8080/adapters
```

Confirm the adapter is enabled in `config/nightwatch.yaml`, its config file exists,
and `AWS_ENDPOINT_URL` resolves inside the container. A failed provider connection
must remain an unavailable adapter/finding, not an empty healthy estate.

### LocalStack EKS fails to start

- Confirm `/var/run/docker.sock` is mounted and usable by LocalStack.
- Confirm LocalStack is running directly in Docker, not inside Kubernetes.
- Inspect `docker compose ... logs localstack` for the ready-hook error.
- Confirm `LOCALSTACK_AUTH_TOKEN` is valid for Ultimate EKS and
  `LOCALSTACK_IMAGE` points to a LocalStack for AWS image that supports it.
- Remove the demo volume only when a clean local reset is intended.

LocalStack service behavior and licensing can change between releases. The Compose
file requires `LOCALSTACK_IMAGE` instead of silently selecting a moving image. Pin
the validated calendar-version tag or, preferably, the immutable RepoDigest for
repeatable presentations.

### Findings exist but AI Analyst fails

```bash
curl -fsS http://localhost:11434/api/tags
docker compose -f docker-compose.demo.yml exec nightwatch-api \
  python -c 'import os; print(os.environ["OLLAMA_BASE_URL"])'
```

Ensure the configured model exists and the URL is reachable from the API container.
Deterministic findings remain valid while Ollama is offline; Nightwatch should show
the analysis failure explicitly.

### UI cannot reach the API

The demo frontend bakes `http://localhost:8080` into its browser bundle at build
time. Rebuild after changing `NEXT_PUBLIC_API_URL`. In kgateway deployments, build
with `/api` and ensure the gateway strips that prefix before forwarding to FastAPI.

## Verification

Run these gates before presenting or deploying:

```bash
pytest -q
python -m py_compile $(rg --files src -g '*.py')

(cd frontend && npm run lint && npm run build)

LOCALSTACK_AUTH_TOKEN=compose-validation-only \
LOCALSTACK_IMAGE=localstack/localstack-pro:latest \
  docker compose -f docker-compose.demo.yml config -q
bash -n localstack/init-aws.sh
```

Passing static checks proves the code/configuration is internally valid. It does
not prove AWS credentials, Kubernetes authorization, LocalStack EKS provisioning,
Ollama reachability, kgateway/OIDC behavior, or the live finding storyline; verify
those with the runtime commands above.
