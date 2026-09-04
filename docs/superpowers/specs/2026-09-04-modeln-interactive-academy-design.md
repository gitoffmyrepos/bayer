# ModelN Interactive Academy Design

**Date:** 2026-09-04  
**Status:** Approved for implementation  
**Audience:** A new ModelN integration engineer learning the platform, then returning as an operator or developer  
**Source:** `ModelN-Complete-End-to-End-New-Hire-Study-Guide.docx` and its canonical Markdown and JSON inventories

## Objective

Replace a 300-plus-page cover-to-cover learning burden with a private, visual, game-like academy that teaches the same evidenced ModelN integration landscape. The learner follows files and transactions, makes decisions, answers questions, investigates simulated incidents, and builds durable mastery through spaced review.

The academy must run in the `sb-ha-cluster` homelab, synchronize progress across devices, remain isolated from Bayer runtime systems, and retain the guide's evidence boundaries.

## Product Principles

1. **Learn by doing.** Each concept appears in a trace, choice, map, or investigation before it appears as terminology to memorize.
2. **Teach the system story.** The learner repeatedly explains source, business object, middleware boundary, transformation, target, and evidence.
3. **Accuracy over trivia.** Every scored answer has a source citation and an explicit explanation.
4. **Evidence remains evidence.** Configured, documented, verified-in-code, environment-specific, legacy/test, unconfirmed, and hypothesis claims are never blended.
5. **No production dependency.** The deployed academy contains sanitized, versioned learning material and has no Bayer production credentials or connectivity.
6. **Mastery is earned over time.** Unlocking depends on retained understanding across question forms, not XP alone.
7. **Delight without distraction.** Motion illustrates state transitions and cause/effect. Repetitive interactions remain quick and calm.

## Learner Journey

The 40 numbered chapters become seven connected worlds:

1. **See the System** — Model N, middleware, identities, files versus rows, runs, and the three primary lanes.
2. **Follow Inbound** — master data, SAP transactions, McKesson shared stages, Axway EDI 844, and dependencies.
3. **Run the Engine** — SFTP, S3 zones, triggers, Lambda, Step Functions, Glue, configuration, security, and observability.
4. **Shape the Data** — parsing, validation, Snowflake layers and procedures, RODB enrichment, null/cardinality boundaries, and current-load selection.
5. **Close the Loop** — outbound 3xx requests, file construction, delivery, EDI 845/849, and request/acknowledgment correlation.
6. **Operate Safely** — evidence packets, retries, catches, skips, failure classification, console investigation, and safe-rerun decisions.
7. **Incident Capstone** — the sanitized FGI 301 package `0009343` case plus an unfamiliar-FGI end-to-end trace.

The initial campaign follows the guide's 15-hour Friday-to-Sunday route. Afterward, a daily 15-to-20-minute loop presents due recall cards, one weak-path visualization, and one mini incident.

## Mission Loop

Every mission follows five beats:

1. **Brief:** A two-minute business story and mission objective.
2. **Explore:** An interactive map, sequence, dependency graph, or file/data animation.
3. **Decide:** A meaningful choice about identity, evidence, next stage, diagnosis, or safe action.
4. **Recall:** Two to four questions answered without looking back.
5. **Debrief:** Explanation, misconception correction, cited evidence, mastery update, and future-review scheduling.

Question forms include mapping, ordering, classification, evidence judgments, branching incident decisions, short teach-back prompts, and unsafe-assumption detection. Wrong answers do not remove lives. They trigger a concise explanation, a simpler contrast question, and a rescheduled review.

## Visual Direction

The selected **Systems Adventure** direction uses a light mineral background, deep forest navigation, one teal interaction accent, and amber for investigation pressure or cautions. Typography uses a modern sans-serif with a mono companion for identifiers. The main campaign is map-like and spacious; incident simulations shift into a darker focused console.

The interface avoids childish mascots, noisy dashboards, generic equal-card grids, excessive animation, and fake operational metrics. All motion observes `prefers-reduced-motion` and uses transform/opacity rather than layout-changing properties.

Core screens are:

- Sign in and learner onboarding
- Mission-control home with recommended next action and mastery map
- World map and mission picker
- Interactive lesson player
- Visual trace explorer
- Incident simulation console
- Daily review queue
- Searchable FGI/runtime/data atlas
- Progress and mastery profile
- Content release and health view for administrators

## System Architecture

The platform is a monorepo with independently deployable services:

### Academy Web

A React/TypeScript progressive web app serves the learner experience. It handles responsive presentation, offline shell caching, reduced-motion behavior, interactive SVG/CSS diagrams, and accessible keyboard/touch interactions. It never holds source credentials or computes authoritative mastery.

### Academy API

A Python FastAPI service owns users, sessions, enrollments, world/mission progress, achievements, lesson attempts, and the public API facade. It uses secure HTTP-only session cookies and calls internal services through cluster-local DNS.

### Content Service

A Python FastAPI service loads immutable validated course bundles. It serves worlds, missions, concepts, glossary entries, FGI records, evidence labels, citations, diagrams, and search results. Content versions are immutable; in-progress mission attempts remain pinned to their starting version.

### Learning Engine

A Python FastAPI service scores objective questions, records rubric-based self-evaluation for teach-backs, calculates skill mastery, selects adaptive follow-ups, and schedules spaced reviews. The first release uses deterministic SM-2-style scheduling and transparent weighted mastery rules, not opaque ML.

### Simulation Engine

A Python FastAPI service executes deterministic branching incident scenarios. A scenario declares states, available evidence, choices, consequences, hints, scoring dimensions, terminal outcomes, and source citations. It cannot execute actions against real AWS, Snowflake, SFTP, or Model N systems.

### PostgreSQL

A dedicated CloudNativePG cluster stores account, session, progress, attempt, review, mastery, achievement, and content-release metadata. Services use separate database roles and schemas. Backups follow the homelab's existing CNPG pattern.

### Grounded Coach

The coach is an optional internal capability behind the Academy API. It retrieves only from the active sanitized course bundle, must cite supporting sections, preserves evidence labels, and returns an explicit insufficient-evidence response when retrieval cannot support an answer. The academy remains fully usable when the coach is disabled or unavailable.

## Content and Evidence Pipeline

The DOCX is not parsed in production. A build-time content tool consumes the canonical guide Markdown, coverage ledger, selected sanitized inventory records, and diagrams. It emits a versioned JSON course bundle and a searchable text index.

The curated course model contains:

- worlds and missions;
- concepts and mastery skills;
- lesson beats and visual graph definitions;
- objective and teach-back questions;
- misconception feedback and hints;
- simulations and evidence packets;
- glossary and atlas records;
- citations back to stable source section identifiers;
- evidence classifications and limitations.

Release validation fails when:

- any required guide chapter or weekend outcome is unmapped;
- any primary FGI/source identity is absent from both missions and atlas;
- required runtime, Glue, DynamoDB, data-layer, or investigation categories are uncovered;
- a scored question lacks an accepted answer, explanation, mastery skill, or citation;
- a citation target does not exist;
- a simulation has unreachable states or nonterminal dead ends;
- duplicate stable IDs exist;
- secret-like values, unsanitized account identifiers, private records, or absolute workstation paths remain;
- JSON schema validation fails.

## Mastery and Progress

Mastery is tracked per capability rather than only per chapter:

- explain platform architecture;
- resolve FGI and source identity;
- trace inbound flow;
- trace outbound and acknowledgment flow;
- read runtime orchestration;
- follow data lineage;
- classify evidence;
- diagnose failures;
- choose safe rerun boundaries.

An answer updates mastery based on correctness, question difficulty, hint use, and whether the concept remains correct in later sessions and different question forms. XP, badges, world completion, and streaks add visible momentum but cannot mask weak mastery. Streaks are forgiving and never erase progress.

## API and Data Flow

1. The web client signs in through the Academy API and receives a secure session cookie.
2. The home endpoint combines progress from PostgreSQL, due reviews from the Learning Engine, and current content from the Content Service.
3. Starting a mission creates a version-pinned attempt.
4. Lesson content is retrieved from the Content Service through the API facade.
5. Objective answers are submitted server-side to the Learning Engine; correct answers are never embedded in the browser payload before submission.
6. Learning results update attempts, mastery, achievements, and review schedules transactionally.
7. Simulation choices advance only through valid scenario transitions supplied by the Simulation Engine.
8. The client can resume a mission from the last completed beat on another device.

## Error Handling and Degraded Modes

- If PostgreSQL is unavailable, sign-in and progress mutation fail with a clear retry message; the client never pretends an answer was saved.
- If Content Service is unavailable, cached non-sensitive lesson shells may display, but new attempts and answer submissions are disabled.
- If Learning Engine is unavailable, lesson reading can continue, but scored submissions remain pending in the client only after explicit learner confirmation; duplicate submissions are idempotent.
- If Simulation Engine is unavailable, other missions and reviews remain available.
- If the grounded coach is unavailable or unsupported by evidence, the UI says so and offers cited reference sections.
- All services expose readiness and liveness endpoints. Readiness fails when required dependencies are unavailable.
- API errors use stable codes, correlation IDs, safe user messages, and structured logs without answer or session leakage.

## Security and Privacy

- Deploy in a dedicated `modeln-academy` namespace.
- Expose only through a private Tailscale ingress or an equivalently private homelab route; do not create a public DNS route.
- Use strong password hashes, rotating server-side sessions, secure HTTP-only cookies, CSRF protection, rate limits, and logout/revocation.
- Store secrets through the homelab's approved secret mechanism; never commit credentials.
- Run containers as numeric non-root users with read-only root filesystems, dropped Linux capabilities, runtime-default seccomp, resource limits, and explicit writable temporary volumes.
- Apply default-deny NetworkPolicies and allow only required service-to-service, DNS, PostgreSQL, and optional AI-gateway traffic.
- Do not label the namespace for ambient mesh unless the full traffic policy is intentionally designed and verified.
- The application and course bundle contain no Bayer credentials, tokens, private account IDs, production records, or direct production connectivity.

## Kubernetes and Delivery

Application images are multi-stage, multi-architecture builds published to private Harbor with immutable tags and digests. GitHub Actions/Argo Workflows build and scan images. `sb-gitops` owns namespace, CNPG, services, deployments, private ingress, policies, secrets references, disruption budgets, and monitoring rules. Argo CD reconciles the application; live `kubectl` patches are prohibited.

The deployment supports rolling updates for stateless services. Database migrations run as a pre-deploy job and are backward compatible for one application version. Content bundles publish independently and activate only after validation.

## Testing and Acceptance

### Unit and contract tests

- Content schemas, coverage rules, sanitization, citation resolution, and simulation reachability
- Mastery math, spaced scheduling, idempotency, and adaptive selection
- Authentication, authorization, CSRF, session expiry, and API validation
- Component behavior, keyboard navigation, reduced motion, and responsive layouts

### Integration tests

- API-to-service contracts against ephemeral PostgreSQL
- Cross-device resume and version-pinned mission attempts
- Failure/degraded modes for each internal service
- Content-release activation and rollback

### End-to-end tests

- Sign in, complete a mission, answer correctly and incorrectly, receive feedback, resume elsewhere, and complete a due review
- Complete a branching incident with both safe and unsafe choices
- Search for an FGI and trace it through its source-backed atlas
- Verify no correct answer is exposed before submission

### Content acceptance

- All 40 numbered chapters and eight weekend outcomes are covered
- All primary FGI/source identities appear in the atlas and at least one learning interaction
- All seven worlds contain at least one visual trace, one decision, and one recall checkpoint
- The capstone exercises evidence classification and safe-rerun reasoning

### Runtime acceptance

- All workloads are healthy in `sb-ha-cluster`
- The private endpoint is reachable from the Tailnet and not exposed through the public gateway
- PostgreSQL persistence survives pod replacement
- Progress synchronizes between two independent browser sessions
- Network policies, probes, resource constraints, backups, metrics, and logs are verified

## Initial Release Scope

The initial complete release includes the seven-world campaign, daily review, core atlas, deterministic incident simulator, cross-device progress, private authentication, content validation, and the grounded-coach interface with graceful disablement. Multiplayer competition, public enrollment, live Bayer system access, production incident ingestion, and authoring through the web UI are excluded.

## Success Criteria

The product succeeds when the learner can finish the weekend campaign without reading the 300-plus-page guide cover to cover, demonstrate every stated weekend outcome through interactive assessments, return for daily retention practice, and use the atlas and simulations later during safe operational learning.
