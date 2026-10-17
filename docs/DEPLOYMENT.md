# Deployment guide

## Modes

| Mode | Persistence | Authentication | Purpose |
|---|---|---|---|
| Native local | SQLite WAL | Random development bearer token | Development and deterministic tests |
| Docker Compose | PostgreSQL 16 volume | Development or configured OIDC | Integrated staging-style local environment |
| Kubernetes target | External managed PostgreSQL | OIDC/JWKS, no development token | Target deployment after release gates |

No cloud environment is created or deployed by this archive. The Kubernetes YAML is a starting manifest that must be configured for your environment. The repair worker is deployed separately on an isolated runner host.

## Native local process setup

Install from `requirements.lock` and install the package with `--no-deps -e .`. Set `DATABASE_URL` and a random `DEV_API_TOKEN`, then run `agentproof migrate` once. Start `agentproof api` and `agentproof worker` in separate terminals sharing the same variables. The app does not source `.env` automatically outside Compose.

## Docker Compose

Copy `.env.example` to `.env`. Replace the PostgreSQL password in both `POSTGRES_PASSWORD` and `DATABASE_URL`. Set the API token, provider URL/key/model and Tavily key. Leave unknown token prices unset. Then run:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://localhost:8000/health/ready
docker compose logs --tail=100 worker
```

The migration service completes before API and worker start. The default worker handles research/support/reports. The collector writes basic trace summaries to logs; configure an authenticated OTLP backend for retained traces. Database data survives container replacement in `postgres-data`. `docker compose down -v` deletes that volume and is destructive.

## Dedicated code repair runner

Use a dedicated Linux VM or isolated runner host with a rootless Docker daemon where possible. Install Python 3.12 and this package. Pre-pull the sandbox image, preferably pinning a reviewed digest. Set the same reachable database URL and model settings, then:

```bash
docker pull python:3.12-slim
export SANDBOX_ENABLED=true
export SANDBOX_IMAGE=python:3.12-slim
agentproof worker --kinds codefix
```

A native worker requires an accessible Docker CLI and daemon. If the database is in Compose, `db` resolves only inside its network: use a deliberately exposed private database address or a shared managed database with TLS. Do not expose PostgreSQL publicly to make the runner connect. The general Compose deployment intentionally does not mount a Docker socket or start privileged nested Docker.

Enable the integration check only on the isolated runner:

```bash
RUN_DOCKER_TESTS=1 pytest -q -m docker
```

The default mutable image tag is suitable for development only. Production must use a reviewed digest and a sandbox infrastructure threat review.

## Kubernetes target

1. Build and scan the image; push to your registry and substitute its digest in `infra/k8s/base.yaml`.
2. Provision managed PostgreSQL with TLS, backups and a tested restore path. Supply `sslmode=verify-full` and trusted CA configuration as appropriate for the provider.
3. Create the `agentproof` namespace and a Secret named `agentproof-runtime` using your secret manager. Set `ENVIRONMENT=production`, `DATABASE_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `TAVILY_API_KEY`, optional prices and OTLP settings. Do not set `DEV_API_TOKEN` in production.
4. Apply the migration Job first and wait for completion. Then apply API/worker deployments and Service. The combined YAML lists the Job first, but Kubernetes application order does not itself wait for migration completion; use your deployment pipeline to enforce this gate.
5. Add your TLS ingress with request size, rate, read timeout and SSE buffering settings. The sample ingress policy assumes an `ingress-nginx` namespace; change selectors for your controller. No public ingress hostname or certificate is supplied.
6. Add environment-specific egress restrictions to the database, identity provider, model gateway, search provider and telemetry backend. The provided NetworkPolicies restrict ingress only.
7. Deploy the separate code worker and verify its private database connectivity and isolation.
8. Run the acceptance checklist. Roll out gradually and retain the previous image digest.

## Acceptance checks

- Health probes pass and migration version matches.
- Real signed JWTs work; wrong issuer/audience, expired tokens and cross-tenant access fail.
- A live research answer contains actual sources and a replayable trace.
- A repair runs real public and hidden tests in Docker; generated code never executes on the host.
- Refund requester cannot self-approve; a second identity can approve; repeated decisions cannot create duplicate ledger entries.
- Worker termination mid-run causes lease recovery with checkpoint reuse; stale commits are rejected.
- SSE reconnect preserves cursor order and leaks no other tenant's events.
- Backup restores a known run, its checkpoints, approval and events in an isolated environment.
- Load and provider quotas are tested before setting replica counts.

## Rollback

Stop admission at the ingress, allow active jobs to finish where practical, then roll back API and workers to the previous image. Keep database contents. This initial release has only schema v1; future incompatible migrations require a forward/rollback data plan. Do not run older workflows over newly shaped checkpoints unless compatibility was tested. Prefer additive fields and stable checkpoint names.
