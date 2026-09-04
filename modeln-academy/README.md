# ModelN Academy

A private, game-like learning system compiled from the ModelN new-hire study guide. It turns the guide into seven connected worlds, 42 short missions, adaptive review, evidence-backed search, and branching incident simulations.

## Learning loop

Each mission follows five beats: brief, explore, decide, recall, and debrief. Progress, mastery, streaks, and review timing are stored per learner in PostgreSQL so a session can continue on another device.

The evidence coach is retrieval-only. It answers from the sanitized course bundle and fails closed when it cannot find supporting source material.

## Architecture

- `web`: React PWA and same-origin API proxy
- `services/api`: authentication, progress, mission orchestration, and dashboard
- `services/content`: sanitized course bundle, references, and search
- `services/learning`: deterministic grading and spaced-repetition scheduling
- `services/simulation`: branching incident scenarios
- CloudNativePG PostgreSQL: learner state

## Refresh course content

The source compiler reads the local guide and inventories, then produces deterministic JSON bundles:

```bash
uv run python -m services.content.app.compiler
```

No source document or production record is served directly by the application.

## Verify locally

```bash
uv run ruff check .
uv run pytest
uv run python -m py_compile services/api/app/main.py
cd web
npm test
npm run build
npm run test:e2e
```

## Homelab deployment

The GitOps source is `sb-gitops/prod/platform-workloads/manifests/modeln-academy`. Images are immutable Harbor digest references. Argo CD creates the namespace, generated runtime credentials, CloudNativePG database, migration job, five services, network policies, and an internal kgateway route.

Access the academy at `https://modeln.strategybase.io` from the homelab network. The learner username is `kelvin`. Retrieve the generated password without storing it in Git:

```bash
kubectl --context sb-ha-cluster -n modeln-academy get secret modeln-academy-runtime \
  -o jsonpath='{.data.SEED_USERS}' | base64 --decode | cut -d: -f3-
```
