# ModelN Interactive Academy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a private, multi-service, interactive ModelN learning academy that covers the complete new-hire guide through visual missions, adaptive questions, simulations, reference search, and cross-device progress.

**Architecture:** A React PWA talks to one Academy API facade. Content, learning, and simulation services have narrow internal APIs and share a dedicated PostgreSQL cluster through service-specific schemas and roles. An offline content builder produces a sanitized, schema-validated, immutable course bundle from the canonical ModelN guide and inventories; Kubernetes deploys the services behind private Tailscale ingress through GitOps.

**Tech Stack:** React 19, TypeScript, Vite, native SVG/CSS motion, Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL 17/CloudNativePG, pytest, Vitest, Playwright, Docker/BuildKit, Kubernetes, Kustomize, Argo CD, Harbor.

---

## File Map

- `modeln-academy/content/` — sanitized source bundle, course definition, JSON schemas, and deterministic builder.
- `modeln-academy/services/content/` — immutable course delivery and search.
- `modeln-academy/services/learning/` — scoring, mastery, and spaced review.
- `modeln-academy/services/simulation/` — deterministic scenario state machine.
- `modeln-academy/services/api/` — authentication, sessions, progress persistence, and facade endpoints.
- `modeln-academy/web/` — responsive PWA and visual learning interactions.
- `modeln-academy/shared/python/` — shared API/domain types without service implementation coupling.
- `modeln-academy/tests/` — integration, content coverage, and security contracts.
- `modeln-academy/deploy/local/` — local Compose stack for end-to-end validation.
- `modeln-academy/.github/workflows/` — test, image-build, and security checks.
- `sb-gitops/prod/platform-workloads/manifests/modeln-academy/` — production manifests.
- `sb-gitops/prod/platform-workloads/apps/modeln-academy.yaml` — Argo CD application registration.

### Task 1: Monorepo and Shared Contracts

**Files:**
- Create: `modeln-academy/pyproject.toml`
- Create: `modeln-academy/Makefile`
- Create: `modeln-academy/.gitignore`
- Create: `modeln-academy/shared/python/modeln_academy_shared/models.py`
- Create: `modeln-academy/tests/unit/test_shared_models.py`

- [ ] Write failing tests proving evidence classes are closed, stable IDs reject whitespace/absolute paths, and API errors require a safe message plus correlation ID.
- [ ] Run `python3 -m pytest modeln-academy/tests/unit/test_shared_models.py -q`; expect collection failure because the package does not exist.
- [ ] Implement Pydantic enums/models `EvidenceClass`, `Citation`, `ApiError`, `AnswerResult`, and `ServiceHealth` with boundary validation.
- [ ] Run the unit test and `python3 -m py_compile` over every Python module; expect all checks to pass.
- [ ] Commit with `feat(academy): establish service contracts`.

### Task 2: Sanitized Course Builder and Complete Bundle

**Files:**
- Create: `modeln-academy/content/build_course.py`
- Create: `modeln-academy/content/course.yaml`
- Create: `modeln-academy/content/simulations.yaml`
- Create: `modeln-academy/content/schemas/course.schema.json`
- Create: `modeln-academy/content/dist/course-v1.json`
- Create: `modeln-academy/content/dist/search-v1.json`
- Create: `modeln-academy/tests/content/test_course_bundle.py`

- [ ] Write failing coverage tests for all 37 numbered chapters, eight weekend outcomes, 35 configured FGI/source pairs, six workflow families, fourteen Glue jobs, fourteen DynamoDB tables, seven worlds, required evidence labels, resolvable citations, answer explanations, secret-pattern rejection, and scenario reachability.
- [ ] Run `python3 -m pytest modeln-academy/tests/content/test_course_bundle.py -q`; expect missing-builder failures.
- [ ] Implement a deterministic Markdown section parser that assigns stable slugs, strips absolute paths and account-like identifiers, preserves evidence labels, and emits cited reference sections.
- [ ] Curate seven worlds, at least 24 missions, at least 120 mixed-form questions, the FGI/runtime/data atlas, and two capstone scenarios from the canonical guide and inventories.
- [ ] Build the bundle and run coverage tests; expect all declared coverage counts and privacy checks to pass.
- [ ] Commit with `feat(academy): build complete evidence-backed course`.

### Task 3: Content Service

**Files:**
- Create: `modeln-academy/services/content/app/main.py`
- Create: `modeln-academy/services/content/app/store.py`
- Create: `modeln-academy/services/content/tests/test_api.py`
- Create: `modeln-academy/services/content/Dockerfile`

- [ ] Write failing API tests for health, course metadata, worlds, missions, atlas search, citation lookup, unknown IDs, and immutable version headers.
- [ ] Implement a startup-validated in-memory `CourseStore` and FastAPI read endpoints with bounded search and stable errors.
- [ ] Run service tests and verify malformed bundles make readiness fail closed.
- [ ] Build the service container and run it with a read-only root filesystem.
- [ ] Commit with `feat(academy): serve immutable course content`.

### Task 4: Learning Engine

**Files:**
- Create: `modeln-academy/services/learning/app/main.py`
- Create: `modeln-academy/services/learning/app/scoring.py`
- Create: `modeln-academy/services/learning/app/scheduler.py`
- Create: `modeln-academy/services/learning/tests/test_scoring.py`
- Create: `modeln-academy/services/learning/tests/test_api.py`
- Create: `modeln-academy/services/learning/Dockerfile`

- [ ] Write failing tests for objective scoring, ordered/map answers, hints, transparent mastery weights, SM-2 review intervals, weak-skill selection, and idempotency keys.
- [ ] Implement pure scoring and scheduling functions using immutable inputs and UTC timestamps.
- [ ] Expose internal endpoints for score, mastery update, due-review calculation, and adaptive next-question selection.
- [ ] Run unit/API tests and verify answers absent from the course bundle fail closed.
- [ ] Commit with `feat(academy): add adaptive mastery engine`.

### Task 5: Simulation Engine

**Files:**
- Create: `modeln-academy/services/simulation/app/main.py`
- Create: `modeln-academy/services/simulation/app/engine.py`
- Create: `modeln-academy/services/simulation/tests/test_engine.py`
- Create: `modeln-academy/services/simulation/tests/test_api.py`
- Create: `modeln-academy/services/simulation/Dockerfile`

- [ ] Write failing tests for valid transitions, evidence unlocks, scoring dimensions, safe/unsafe outcomes, unreachable-state rejection, tampered state rejection, and idempotent choice replay.
- [ ] Implement a deterministic transition engine that accepts scenario, current state, and choice and returns only the declared next state and consequences.
- [ ] Expose start, advance, and explain endpoints without any network/action execution capability.
- [ ] Run tests and assert the image has no cloud SDK or production connector dependencies.
- [ ] Commit with `feat(academy): add branching incident simulations`.

### Task 6: Academy API, Authentication, and Persistence

**Files:**
- Create: `modeln-academy/services/api/app/main.py`
- Create: `modeln-academy/services/api/app/config.py`
- Create: `modeln-academy/services/api/app/auth.py`
- Create: `modeln-academy/services/api/app/db.py`
- Create: `modeln-academy/services/api/app/models.py`
- Create: `modeln-academy/services/api/app/routes/`
- Create: `modeln-academy/services/api/migrations/001_initial.sql`
- Create: `modeln-academy/services/api/tests/`
- Create: `modeln-academy/services/api/Dockerfile`

- [ ] Write failing tests for password hashing, sign-in/out, secure cookies, CSRF rejection, session expiry/revocation, authorization, idempotent submissions, mission version pinning, cross-device resume, and safe dependency failures.
- [ ] Implement Argon2 password verification, opaque rotating sessions stored as hashes, CSRF tokens, and rate-limited authentication.
- [ ] Implement SQLAlchemy models for users, sessions, attempts, beat progress, answers, mastery, reviews, achievements, content releases, and simulation runs.
- [ ] Implement facade routes for dashboard, mission lifecycle, answers, reviews, atlas, simulations, progress, and optional grounded-coach requests.
- [ ] Run API tests against ephemeral PostgreSQL and verify logs never include cookies, passwords, answers, or course payloads.
- [ ] Commit with `feat(academy): persist secure cross-device learning`.

### Task 7: Systems Adventure PWA

**Files:**
- Create: `modeln-academy/web/package.json`
- Create: `modeln-academy/web/src/`
- Create: `modeln-academy/web/public/manifest.webmanifest`
- Create: `modeln-academy/web/tests/`
- Create: `modeln-academy/web/Dockerfile`

- [ ] Write failing component tests for sign-in, mission map, recommended action, lesson beats, wrong-answer feedback, reduced motion, resume state, daily review, atlas search, and incident choices.
- [ ] Implement the forest/teal/amber design tokens, responsive shell, accessible navigation, loading/empty/error states, and installable PWA metadata.
- [ ] Implement visual trace, sequence reorder, mapping, classification, teach-back, evidence judgment, and branching simulation components.
- [ ] Implement campaign/mastery views, forgiving streaks, achievements, cited debriefs, and private session handling.
- [ ] Run Vitest, accessibility checks, production build, and Playwright at desktop and mobile widths.
- [ ] Commit with `feat(academy): deliver systems adventure experience`.

### Task 8: Local Stack and End-to-End Verification

**Files:**
- Create: `modeln-academy/deploy/local/compose.yaml`
- Create: `modeln-academy/tests/e2e/academy.spec.ts`
- Create: `modeln-academy/scripts/wait-for-stack.sh`
- Create: `modeln-academy/README.md`

- [ ] Compose PostgreSQL and all services with health checks, private internal networks, and no production credentials.
- [ ] Add an idempotent seed command that creates the requested learner only from runtime environment values and publishes course v1.
- [ ] Run the full browser journey: sign in, complete a mission, answer wrong and right, inspect cited feedback, resume in a second context, complete a due review, run both incident paths, and search an FGI.
- [ ] Restart the stack and prove progress persists.
- [ ] Run dependency, secret, and container-configuration scans.
- [ ] Commit with `test(academy): verify complete learning journey`.

### Task 9: CI and Private Images

**Files:**
- Create: `modeln-academy/.github/workflows/academy-ci.yaml`
- Create: `modeln-academy/.github/workflows/academy-images.yaml`
- Create: `modeln-academy/scripts/build-images.sh`

- [ ] Add path-scoped CI for Python, TypeScript, coverage, content validation, dependency audit, and container build checks.
- [ ] Add immutable multi-architecture image builds for web and four services, with Harbor credentials supplied only through CI secrets.
- [ ] Build and push an initial immutable release to `harbor.strategybase.io/sb-custom-docker-images/` and record digests.
- [ ] Inspect every pushed manifest and verify both `linux/amd64` and `linux/arm64` are present.
- [ ] Commit with `ci(academy): automate tested image releases`.

### Task 10: GitOps Deployment

**Files:**
- Create: `sb-gitops/prod/platform-workloads/manifests/modeln-academy/`
- Create: `sb-gitops/prod/platform-workloads/apps/modeln-academy.yaml`
- Modify: `sb-gitops/prod/platform-workloads/apps/kustomization.yaml`

- [ ] Write render tests/assertions for namespace isolation, numeric non-root IDs, read-only roots, dropped capabilities, probes, requests/limits, disruption budgets, NetworkPolicies, CNPG, migrations, image digests, and private ingress only.
- [ ] Add CloudNativePG with service-specific roles, backup configuration, and migration job.
- [ ] Add Deployments/Services for web, API, content, learning, and simulation plus ExternalSecret/SealedSecret references and a Tailscale Ingress.
- [ ] Add default-deny ingress/egress and exact DNS, database, facade, and optional AI-gateway allowances; do not enable ambient mesh.
- [ ] Register the Argo CD application under the platform app-of-apps root with prune disabled at the root boundary.
- [ ] Render with Kustomize, validate with kubeconform, run policy tests, review the diff, commit, and push directly to `master` per Strategybase policy.

### Task 11: Live Acceptance and Handoff

**Files:**
- Modify: `modeln-academy/README.md`
- Create: `modeln-academy/docs/operations.md`
- Create: `modeln-academy/docs/content-authoring.md`

- [ ] Wait for Argo CD reconciliation and verify all CNPG and application workloads become healthy.
- [ ] Verify the endpoint is reachable through the Tailnet and absent from the public gateway routes.
- [ ] Execute the production smoke journey with the seeded learner from two independent browser contexts.
- [ ] Delete one application pod through its controller rollout and prove progress survives replacement.
- [ ] Verify readiness degradation, structured logs, metrics, backup status, and NetworkPolicy enforcement.
- [ ] Document learner access, content release, backup/restore, credential rotation, troubleshooting, and rollback.
- [ ] Run the complete requirement-by-requirement acceptance audit against the design specification.
- [ ] Commit final documentation with `docs(academy): add operations and authoring guides`, push the private source repository, and save a shared-memory note with backlinks.
