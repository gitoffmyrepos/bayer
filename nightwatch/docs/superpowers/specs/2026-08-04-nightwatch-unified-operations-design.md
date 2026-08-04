# Nightwatch Unified Operations Design

**Date:** 2026-08-04  
**Status:** Approved for implementation planning  
**Primary users:** Platform/SRE and DevSecOps engineers  
**Executive surface:** Command Center  
**First milestone:** Read-only CloudSec and operational monitoring using LocalStack and local Kubernetes  

## 1. Summary

Nightwatch will become a read-only intelligence plane for AWS, Kubernetes, and application data pipelines. It will discover resources, collect health and security evidence, normalize findings, correlate related issues, persist history, and use the local Ollama service to explain evidence. It will not remediate monitored resources by default.

The first production-shaped milestone focuses on the capabilities associated with cloud security posture and infrastructure operations: AWS and Kubernetes inventory, health, findings, topology, incidents, evidence, and AI-assisted investigation. Application security scanning is a separate later phase because it has a different asset model, execution model, authorization boundary, and test strategy.

The first demonstration environment will run in Docker Compose. LocalStack will emulate AWS APIs and create an embedded k3d-backed EKS cluster; the same Nightwatch providers will connect to real AWS through endpoint and credential configuration rather than separate code paths. LocalStack itself must not run inside Kubernetes for this demo because its EKS service requires Docker and is unsupported when LocalStack runs in a Kubernetes pod. See the [LocalStack EKS documentation](https://docs.localstack.cloud/aws/services/eks/) and [LocalStack Kubernetes limitations](https://docs.localstack.cloud/aws/customization/kubernetes/limitations/).

## 2. Current State

Nightwatch currently provides:

- A FastAPI service and Next.js frontend.
- An adapter abstraction for metrics, logs, health checks, and component inventory.
- ForexTrader and AWS pipeline adapters.
- In-memory status and incident history.
- Multi-provider LLM support, including Ollama.
- Kubernetes event-to-GitHub issue handling.
- GitOps and playbook remediation code that can modify monitored systems.
- Kubernetes manifests for collectors, storage, dashboards, alerting, and RBAC.

The current implementation does not yet provide:

- Durable canonical storage for assets, observations, findings, relationships, scan runs, or incidents.
- First-class EKS, EC2, and ECS inventory and health providers.
- A reproducible LocalStack lab.
- A stable, versioned integration API.
- A unified topology and evidence model.
- Explicit partial-scan and stale-data behavior.
- Read-only enforcement independent of the remediation configuration.
- A complete onboarding and integration guide.

## 3. Goals

1. Monitor Kubernetes clusters and AWS EKS, EC2, and ECS resources without mutating them.
2. Preserve and extend the existing Step Functions, Glue, Lambda, S3, DynamoDB, and application pipeline monitoring.
3. Persist inventory, observations, findings, evidence, topology, incidents, and analyses across restarts.
4. Expose a Unified Operations console through the existing kgateway surface.
5. Use Ollama for evidence-grounded explanation, correlation assistance, and investigation guidance.
6. Provide a reproducible LocalStack demonstration with deterministic fault scenarios.
7. Allow applications and external scanners to integrate through providers, signed ingestion, and versioned schemas.
8. Keep remediation available for possible future use while disabled and privilege-isolated by default.
9. Reuse mature open-source engines where they add coverage without turning Nightwatch into a set of embedded third-party dashboards.

## 4. Non-Goals for the First Milestone

- Automated remediation or GitOps changes.
- Active DAST against applications.
- A full Rapid7 feature-for-feature clone.
- Multi-cloud support beyond the provider contracts needed to add it later.
- A custom vulnerability database or a reimplementation of mature scanner rule libraries.
- LLM-generated health status, severity, or evidence.
- Production multi-tenancy. The schema may carry an organization or workspace boundary, but the first deployment is a single organization.

## 5. Product Principles

### 5.1 Evidence before explanation

Collectors and deterministic rules establish facts. Ollama may summarize and correlate those facts, but it may not create a finding, change severity, resolve an incident, or claim a resource is healthy.

### 5.2 Stale is not healthy

Missing, expired, or partially collected evidence produces `stale`, `unknown`, or `partial`, never a fabricated passing state.

### 5.3 Read-only by identity

Observe mode uses read-only IAM and Kubernetes RBAC. It does not merely hide write controls in the UI.

### 5.4 One model across providers

AWS, Kubernetes, pipelines, and external scanners produce the same canonical assets, relationships, observations, findings, incidents, and evidence references.

### 5.5 API-first integration

The frontend consumes the public versioned API. Applications and future interfaces can use the same contract without depending on frontend internals.

## 6. Recommended Architecture

Nightwatch owns the intelligence model and user experience. Native providers collect operational evidence and support LocalStack. Optional integrations add security depth by normalizing external results.

```text
Kubernetes API ─┐
AWS APIs ───────┼─> Provider scheduler -> Normalizer -> Rules/correlation
Pipeline APIs ──┤                              |              |
Scanner output ─┘                              v              v
                                           PostgreSQL <-> Ollama analyst
                                               |
                                               v
                                    FastAPI /api/v1 + event stream
                                               |
                                               v
                                  Next.js Unified Operations console
                                               |
                                           kgateway
```

### 6.1 Evidence sources

- **Kubernetes provider:** Nodes, namespaces, workloads, pods, events, services, ingresses, network policies, RBAC metadata, resource pressure, scheduling failures, restart state, image state, and rollout health.
- **AWS provider:** EKS clusters and node groups, EC2 instances and security groups, ECS clusters/services/tasks, IAM relationships needed for resource context, VPC/network exposure, CloudWatch metrics/logs, and CloudTrail change evidence where available.
- **Pipeline provider:** Existing Step Functions, Glue, Lambda, S3, DynamoDB, Transfer Family, and application-specific adapters.
- **Scanner providers:** Prowler first; Trivy or Kubescape next; K8sGPT optional. Their output is normalized into Nightwatch records rather than shown as embedded dashboards.

### 6.2 Intelligence core

- **Provider scheduler:** Independent jobs per connection and service, with timeouts, retries, backoff, freshness, and coverage tracking.
- **Normalizer:** Converts provider payloads into validated canonical records.
- **Rules engine:** Produces deterministic findings from observations.
- **Correlation engine:** Links findings by asset, dependency, time window, and shared evidence into incidents.
- **Ollama analyst:** Produces versioned analyses with evidence citations, confidence, impact, likely cause, and investigation steps.
- **Persistence:** PostgreSQL stores configuration metadata, inventory, relationships, observations, findings, evidence, scan runs, incidents, workflow history, and analyses. JSONB is used for provider-specific evidence while query-critical fields remain typed columns.
- **API:** FastAPI exposes `/api/v1` resources, actions, and an event stream.
- **Frontend:** Next.js provides the Unified Operations console.

### 6.3 Remediation trust boundary

Remediation remains in the codebase but is dormant.

- Default configuration: `REMEDIATION_ENABLED=false`.
- Observe-mode deployments do not mount a write-capable AWS role, kubeconfig, token, SSH key, or Git credential.
- Enabling remediation in the future requires both the feature flag and a separately scoped write identity.
- Startup logs and the UI report remediation capability and identity state explicitly.
- A missing or invalid observe identity fails the affected connection visibly; it never falls back to a write identity.

## 7. Canonical Data Model

All records include an immutable ID, timestamps, a connection or workspace boundary where applicable, and audit metadata.

### 7.1 Connection

Represents an AWS account, LocalStack endpoint, Kubernetes context, pipeline, or scanner source.

Key fields:

- Provider type and display name.
- Endpoint and region scope.
- Credential reference, never the secret value.
- Collection policy and enabled services.
- Last validation result, connection health, and error code.
- Last successful and attempted scan timestamps.

### 7.2 Asset

Represents a discoverable resource.

Key fields:

- Stable provider resource ID or ARN/UID.
- Asset type, name, account, region, cluster, namespace, and environment.
- Tags and labels.
- First seen, last seen, and lifecycle state.
- Source version and provider metadata.

### 7.3 Relationship

Represents typed topology edges such as:

- `member_of`
- `runs_on`
- `exposes`
- `routes_to`
- `depends_on`
- `assumes`
- `reads_from`
- `writes_to`

Each edge stores source, evidence references, first/last seen, and confidence derived from deterministic collection.

### 7.4 Observation

Represents a measured fact: configuration, status, metric, event, log pattern, or scanner result.

Key fields:

- Asset and source.
- Observation type and normalized status.
- Observed time and expiry time.
- Typed value fields plus provider payload.
- Evidence references.
- Scan run ID.

### 7.5 Finding

Represents an actionable issue.

Key fields:

- Stable fingerprint: source, rule, connection, asset, and relevant dimensions.
- Rule/source ID, category, title, severity, and affected asset.
- Workflow state: `open`, `acknowledged`, `suppressed`, `resolved`, or `reopened`.
- First seen, last seen, occurrence count, and resolution evidence.
- Evidence references and compliance mappings.
- Suppression policy and expiry when applicable.

### 7.6 Incident

Groups related findings into an operational investigation.

Key fields:

- Title, severity, status, owner, and timeline.
- Included findings and assets.
- Correlation reasons.
- First/last seen and resolved time.
- Analysis versions and workflow history.

### 7.7 Analysis

Stores an immutable Ollama response.

Key fields:

- Prompt template and model version.
- Input evidence IDs and hashes.
- Summary, likely cause, impact, and investigation steps.
- Model confidence and output validation result.
- Created time and retry lineage.

### 7.8 ScanRun

Captures a collection execution.

Key fields:

- Connection, provider, service scopes, collector version, and policy version.
- Started/finished time and status: `success`, `partial`, or `failed`.
- Coverage and asset/observation/finding counts.
- Structured errors and retry metadata.
- Published scope and omitted scope.

## 8. Collection and Finding Lifecycle

1. The scheduler starts a `ScanRun` for one connection and one or more scopes.
2. Providers collect evidence using read-only APIs.
3. Payloads are validated and staged.
4. Valid staged records are normalized and published transactionally by scope.
5. Deterministic rules create or update findings using stable fingerprints.
6. Correlation groups related findings into incidents.
7. Ollama analyses are generated asynchronously and cite stored evidence IDs.
8. A finding resolves only after a configurable number of successful confirming scans or explicit closure from its authoritative source.
9. A resolved finding with the same fingerprint becomes `reopened` if it recurs.

A partial scan may publish successful scopes. It may not resolve findings or mark assets healthy in uncollected scopes.

## 9. Provider Design

All providers implement a common contract:

- `validate_connection()`
- `discover_assets(scope)`
- `collect_observations(scope, cursor)`
- `collect_relationships(scope)`
- `health()`
- Provider metadata and capability declaration.

Providers return typed batches and structured errors. They do not write directly to persistence or create UI-specific objects.

### 9.1 Kubernetes

The provider supports:

- In-cluster service account authentication.
- External kubeconfig authentication.
- Namespace allow/deny filters.
- List/watch collection for supported resources.
- Event and workload-state fingerprints.
- Permission preflight using authorization review where available and safe list calls otherwise.

The initial rules cover crash loops, image pull failures, OOM kills, pending scheduling, failed probes, unavailable deployments, node pressure, risky public exposure, missing network policy signals, and stale collection.

### 9.2 AWS EKS

The EKS collector discovers clusters, versions, endpoint access, logging configuration, encryption configuration, node groups, add-ons, related VPC resources, and the Kubernetes connection needed for workload-level observations.

### 9.3 AWS EC2

The EC2 collector discovers instances, state, images, platform, launch time, VPC/subnet, public address, security groups, instance profile, volumes, tags, status checks, alarms, and relevant CloudTrail changes.

Initial findings include stopped or impaired monitored instances, public administrative exposure, missing expected monitoring, stale status evidence, and relationships to EKS or ECS capacity.

### 9.4 AWS ECS

The ECS collector discovers clusters, services, task definitions, running/pending/desired counts, deployments, tasks, capacity providers, load balancers, networking, events, and CloudWatch health.

Initial findings include desired/running mismatch, failed deployments, repeatedly stopped tasks, unhealthy targets, missing logs, and stale service evidence.

### 9.5 Pipelines

The current AWS pipeline adapter is migrated behind the provider contract. Existing Step Functions, Glue, S3, Lambda, DynamoDB, and SFTP collectors remain useful, but their outputs become canonical observations and findings rather than adapter-specific status blobs.

## 10. Open-Source Integration Strategy

Nightwatch will reuse engines through versioned subprocess, container, JSON, or API adapters. It will not copy large rule libraries or fork entire user interfaces unless a later review establishes a concrete need and compatible license obligations.

- [Prowler](https://github.com/prowler-cloud/prowler): First security integration for AWS and Kubernetes posture, compliance, and attack-path inputs.
- [K8sGPT](https://github.com/k8sgpt-ai/k8sgpt): Optional Kubernetes diagnostic enrichment and analyzer ideas. Nightwatch remains authoritative for its own evidence and finding lifecycle.
- [Trivy](https://github.com/aquasecurity/trivy) or [Kubescape](https://github.com/kubescape/kubescape): Container, Kubernetes, vulnerability, and misconfiguration findings.
- [Coroot](https://github.com/coroot/coroot): Product and architecture reference for service maps, SLO-oriented health, deployment change visibility, and evidence correlation.

Each integration records tool name, version, scan ID, raw artifact reference, normalization version, and source rule ID.

## 11. LocalStack Demonstration Environment

The local lab uses Docker Compose and includes:

- Nightwatch API.
- Nightwatch frontend.
- PostgreSQL.
- LocalStack with Docker socket access and persistence.
- LocalStack embedded k3d EKS.
- Seed and fault-injection jobs.
- Configurable Ollama endpoint; the existing cluster Ollama route is used when reachable.

The lab creates deterministic resources and scenarios:

1. An EKS cluster with a healthy workload and a crash-looping or unavailable workload.
2. EC2 instances including a stopped or impaired monitored instance and an instance with intentionally exposed administrative ingress.
3. An ECS cluster/service with desired/running mismatch or repeatedly stopped tasks.
4. A pipeline with a failed execution or stale S3 object.
5. Relationships connecting cloud resources, cluster nodes, workloads, services, and pipeline components.

The seed process is idempotent. Fault scenarios are named and reversible. Nightwatch never invokes the reversal.

The LocalStack endpoint, credentials, account ID, and region are configuration. Real AWS uses the same provider code with endpoint override omitted and AssumeRole enabled.

## 12. Ollama Analyst

Ollama analysis is asynchronous and optional for core monitoring.

Inputs:

- Finding and incident fields.
- Current and historical observations.
- Relevant assets and relationships.
- Selected logs/events after redaction and size limits.
- Evidence identifiers.

Outputs use a validated schema:

- Summary.
- Likely cause.
- Impact.
- Investigation steps.
- Evidence citations.
- Confidence.
- Explicit uncertainty.

If Ollama is unavailable, findings and incidents remain available. Analysis is marked `pending` or `unavailable` and may be retried. Nightwatch does not substitute canned text and label it as model output.

## 13. API Design

The public API is versioned under `/api/v1` and described by OpenAPI.

Primary resources:

- `GET /assets`
- `GET /relationships`
- `GET /findings`
- `GET /incidents`
- `GET /scan-runs`
- `GET /connections`
- `GET /analyses`
- `GET /events/stream`

Primary actions:

- `POST /connections/validate`
- `POST /scan-runs`
- `POST /ingest/observations`
- `PATCH /findings/{id}` for acknowledgment or suppression in Nightwatch only.
- `POST /incidents/{id}/analyze`

API requirements:

- Cursor pagination.
- Structured filters and stable sorting.
- Idempotency keys for ingestion and scan triggers.
- Consistent error envelopes with machine-readable codes.
- Request and response schema versioning.
- Audit records for workflow changes.
- Payload limits and redaction.
- Signed webhook or scoped token authentication for application ingestion.

## 14. Unified Operations Console

The approved left navigation is:

- **Command Center**
- **Observe**
  - Cloud Estate
  - Kubernetes
  - Pipelines
- **Investigate**
  - Findings
  - Topology
  - Incidents
  - AI Analyst
- **Manage**
  - Connections
  - Policies
  - Reports
  - Documentation

### 14.1 Command Center

Shows overall health, open risk, asset counts, freshness, coverage, prioritized attention, recent change, and a compact topology view. It is useful to engineers and suitable for an executive demonstration.

### 14.2 Resource surfaces

Cloud Estate, Kubernetes, and Pipelines provide inventory filters, health and freshness, finding counts, relationships, evidence, and time-based detail. They do not rely on adapter-specific response shapes.

### 14.3 Investigation surfaces

- **Findings:** Filterable, sortable finding list and evidence drawer.
- **Topology:** Resource and dependency graph with health/risk overlays and bounded expansion.
- **Incidents:** Correlated findings, timeline, assets, state, and analysis history.
- **AI Analyst:** Evidence-grounded questions about selected assets, findings, incidents, or scan runs.

### 14.4 Connection wizard

1. Choose AWS, Kubernetes, pipeline/scanner, or custom application.
2. Enter endpoint and credential reference.
3. Validate connection and read permissions.
4. Preview inventory scope.
5. Configure regions, namespaces, services, and scan schedule.
6. Run an initial scan and show progress, coverage, and errors.

## 15. Application Integration Paths

Nightwatch supports three integration modes.

### 15.1 Agentless pull

Nightwatch calls an application or cloud API through a provider. This is preferred when stable read-only APIs exist.

### 15.2 Signed push ingestion

Applications post schema-validated observations or events to `/api/v1/ingest/observations` using a scoped token or signed webhook. Requests require idempotency keys and source timestamps.

### 15.3 Python provider SDK

Users implement the provider contract in a focused package and register it through configuration or a plugin entry point. The SDK provides schemas, validation helpers, structured error types, and a contract test kit.

## 16. Error Handling and Resilience

- Isolate failures by connection and provider scope.
- Use explicit timeouts, bounded retries, exponential backoff, and circuit state.
- Publish successful scopes and mark a scan `partial` when other scopes fail.
- Preserve previous findings during uncollected scopes.
- Expose last attempt, last success, freshness, and error codes in the UI.
- Reject malformed provider output before persistence.
- Bound and redact logs and external tool artifacts.
- Retry Ollama independently from collection.
- Keep migrations forward-only with tested upgrade and rollback procedures for deployment, while application schema changes remain backward compatible during rolling upgrades.

## 17. Security

- Use secret references and workload identity; do not persist raw cloud or Kubernetes credentials.
- Provide least-privilege AWS and Kubernetes policies as versioned deployment artifacts.
- Separate observe and remediation identities.
- Redact secrets, tokens, authorization headers, environment variables, and sensitive payload fields before logs, evidence, or LLM prompts.
- Authorize workflow mutations such as acknowledgment and suppression independently from monitored-environment permissions.
- Record audit events for connection changes, scan triggers, finding workflow changes, and analysis requests.
- Apply input limits, schema validation, timeout limits, and safe subprocess execution to scanner integrations.
- Expose the UI/API through the existing kgateway path with the deployment's OIDC/auth policy rather than inventing a second authentication system.

## 18. Verification Strategy

### 18.1 Unit tests

Cover provider normalization, schemas, fingerprints, rules, severity, correlation, lifecycle, stale behavior, partial scans, configuration boundaries, redaction, and API validation. The target is at least 80% coverage for changed backend modules.

### 18.2 Contract tests

Cover provider payload versions, SDK behavior, OpenAPI compatibility, pagination, idempotency, migrations, and error envelopes.

### 18.3 LocalStack integration tests

Create actual emulated EKS, EC2, and ECS resources, run Nightwatch scans, and assert persisted assets, relationships, observations, findings, scan runs, and evidence. Tests also assert that Nightwatch performs no prohibited AWS or Kubernetes write operations.

### 18.4 Frontend end-to-end tests

Playwright covers navigation, filters, detail drawers, topology, connection validation, partial/stale states, Ollama failure, report views, and responsive sidebar behavior.

### 18.5 Deployment verification

- Python compilation and pytest.
- Frontend lint, tests, and production build.
- Container health and restart persistence.
- PostgreSQL migration from a clean and prior schema.
- kgateway route and authentication behavior.
- Read-only IAM and RBAC negative tests.
- Ollama reachable and unreachable behavior.

## 19. Delivery Phases

### Phase 0: Safety and persistence foundation

- Default remediation off.
- Separate observe/write identities.
- Canonical schemas and PostgreSQL repositories.
- Migrations and `/api/v1` skeleton.
- Engine refactor from in-memory adapter responses to scan runs and normalized records.

### Phase 1: Boss-ready local lab

- Docker LocalStack with embedded EKS.
- EC2/ECS/EKS seed and fault scenarios.
- Native AWS and Kubernetes providers.
- Persistent assets, findings, relationships, incidents, and Ollama analyses.
- Minimal Command Center, Findings, resource detail, and topology needed for the complete storyline.

### Phase 2: Complete Unified Operations console

- All approved navigation surfaces.
- Connection wizard.
- Policies, reports, and documentation pages.
- Event stream and UI freshness.

### Phase 3: Security depth and production AWS

- Prowler integration first.
- Trivy or Kubescape integration.
- Optional K8sGPT integration.
- Compliance mappings and reports.
- Real AWS AssumeRole onboarding and hardening.
- kgateway and OIDC deployment verification.

### Phase 4: Application integration maturity

- Stable provider SDK.
- Signed ingestion examples.
- OpenTelemetry-compatible event mapping where practical.
- Full external application onboarding documentation.

### Phase 5: AppSec expansion

Create and approve a separate design for authorized DAST and application risk. It will add application endpoints, scan authorization, scheduling, safe target controls, scanner ingestion, and correlation with the cloud asset graph.

## 20. README and Documentation Deliverables

The root README becomes the entry point and links to focused guides. It must include:

1. Product overview and screenshots.
2. Architecture and data flow.
3. Ten-minute LocalStack demonstration.
4. Seeded fault walkthrough.
5. Production deployment prerequisites.
6. Ollama configuration.
7. Connect real AWS with Terraform-created read-only role and external ID.
8. Connect Kubernetes with read-only RBAC and validation commands.
9. Connect a custom application through agentless pull, signed ingestion, or Python SDK.
10. Integrate Prowler and later scanners.
11. API examples and authentication.
12. Finding lifecycle and stale/partial semantics.
13. Remediation-disabled safety model.
14. Backups, upgrades, troubleshooting, and common permission errors.

Examples must use deterministic resources and fail clearly when required credentials or services are absent. Runtime code must not silently insert mock, random, or fabricated data.

## 21. Acceptance Criteria

The first boss-ready milestone is complete when all of the following are demonstrated:

1. A single command starts Nightwatch, PostgreSQL, and the LocalStack lab on a supported Linux Docker host.
2. Nightwatch discovers the seeded EKS, EC2, ECS, Kubernetes, and pipeline resources through provider APIs.
3. The UI displays assets, health, freshness, topology, evidence, findings, and incidents through the approved left navigation.
4. Deterministic faults produce the expected findings without random or precomputed result injection.
5. Ollama explains selected findings and cites evidence stored by Nightwatch.
6. With Ollama unavailable, findings remain visible and analysis is honestly marked unavailable.
7. With a provider scope unavailable, the scan is partial and prior issues are neither erased nor falsely resolved.
8. Assets, findings, incidents, workflow state, and analyses survive API/UI restart.
9. Remediation is visibly disabled, no write credential is mounted, and negative tests prove monitored resources cannot be modified.
10. Switching from LocalStack to a real AWS connection changes endpoint and credential configuration, not provider logic.
11. The README teaches a new user to run the demo and connect AWS, Kubernetes, or a custom application.

## 22. Risks and Mitigations

### LocalStack parity and plan differences

Use documented APIs, pin a tested LocalStack version, expose coverage in scan metadata, and keep provider contract tests runnable against real AWS test accounts when authorized.

### Scanner integration sprawl

Adopt one integration at a time, beginning with Prowler. Require a versioned normalizer and source metadata before adding a tool to the console.

### LLM hallucination

Keep finding creation and lifecycle deterministic. Validate analysis output and require evidence citations. Label uncertainty and model availability.

### Topology scale

Store relationships independently, use bounded graph expansion, filter by scope, and avoid rendering the entire estate at once.

### Credential exposure

Persist only references, redact before storage and prompting, use workload identity, and keep observe/write identities separate.

### Migration from existing adapter responses

Introduce canonical repositories behind compatibility facades, migrate one provider at a time, and retain API contract tests during the transition.

## 23. Approved Decisions

- Remediation remains dormant behind a disabled feature flag for possible future use.
- Observe mode is enforced with read-only IAM/RBAC and no mounted write identity.
- The first demo is local-first using LocalStack and local Kubernetes provider contracts.
- CloudSec and operational monitoring precede AppSec.
- Platform/SRE and DevSecOps engineers are the primary users; the Command Center is executive-ready.
- The console uses the Unified Operations navigation structure.
- Nightwatch uses a composable architecture with native providers and normalized open-source integrations.
- PostgreSQL provides durable canonical persistence.
- Ollama explains stored evidence but does not determine health or finding lifecycle.

