# Contributing to CogniGuard

Thank you for your interest in contributing. This document covers the development workflow, coding standards, and the process for submitting changes.

---

## Development Setup

```bash
git clone https://github.com/RehanScripts/CogniGuard.git
cd Cogni_Guard
cp .env.example .env
docker compose up --build -d
make health          # confirm the stack is healthy
```

See [README.md](README.md) for full prerequisites.

---

## Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, always deployable |
| `phase-<N>-<name>` | Feature / phase branch — one PR per phase |
| `fix/<short-name>` | Bug fixes |
| `chore/<short-name>` | Non-functional changes (deps, tooling) |

Always branch from the latest `main`:

```bash
git switch main && git pull
git switch -c phase-<N>-<short-description>
```

---

## Before Opening a PR

1. **Tests must pass**
   ```bash
   make test           # backend + flink
   make test-frontend  # vitest
   ```

2. **Linting must be clean**
   ```bash
   make lint
   ```

3. **The phase acceptance check must pass** (defined per phase in the implementation plan).

4. **No secrets committed** — double-check `.env` is not staged.

---

## Commit Message Format

```
<type>(<scope>): <short summary>

<optional body>

Co-Authored-By: <name> <email>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`  
Scopes: `gateway`, `flink`, `training`, `android`, `web-app`, `bank-dashboard`, `behavior-sdk`, `docker`

Example:
```
feat(gateway): add Trust Score to DecisionResponse

Surfaces behavior_match_score and trust_score on every login and
payment response so the frontend can render the enrollment progress
banner without an extra API call.
```

---

## Code Standards

### Python
- **Type hints everywhere** — Pydantic v2 for all IO schemas
- **Async FastAPI routes** — routers stay thin; logic lives in `services/` and `scoring/`
- `ruff` + `black` clean (`make lint-python`)
- No PII in structured logs; no secrets in code

### TypeScript
- `strict` mode — no `any`
- Functional React components + hooks only
- Tailwind for styling — no ad-hoc CSS
- All API calls in `api.ts`; WebSocket in `ws.ts`

### Architecture invariants
Inference reads **Redis only** on the hot path. All other invariants are in the
Architecture Guardrails section of [docs/architecture.md](docs/architecture.md).
Violations will be caught in review.

---

## Pull Request Process

1. Open a PR against `main` with a clear title and description
2. Fill in the [PR template](.github/PULL_REQUEST_TEMPLATE.md)
3. Ensure all CI checks pass
4. Request a review — PRs need at least one approval before merge

---

## Reporting Issues

Use the GitHub issue templates:
- **Bug report** — something is broken
- **Feature request** — something is missing

For security vulnerabilities, see [SECURITY.md](SECURITY.md).
