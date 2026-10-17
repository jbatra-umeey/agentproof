# Release gates and remaining work

The repository is a substantive executable implementation with tests and deployment configuration. **It is not a claim of a deployed or production-certified service.** Production readiness is environment-specific and requires evidence below.

| Area | Implemented now | Remaining gate |
|---|---|---|
| Agent workflows | Four bounded workflows, real provider adapters, strict output schemas | Live runs on the selected model/search account |
| Research | Quotes, citations, judge and abstention | Independent grounding benchmark and source-quality review |
| Repair | Docker adapter, three-attempt loop, 20 public/hidden tasks | Real Docker execution, held-out pass rate, hostile-code isolation review |
| Support | Three specialists, confidence escalation, human approval and local ledger | Live 50-case evaluation, holdout, calibration, business-system eligibility |
| Reports | Parallel workers, supervisor, single baseline, usage/cost/latency | Repeated randomized quality-and-cost comparison |
| Queue | Leases, fencing, atomic transitions and checkpoint reuse | Real PostgreSQL concurrency, failure and load tests |
| Identity | RS256/JWKS, tenant claims, approver separation | Real IdP integration, key rotation and browser login flow |
| Persistence | SQLite development and PostgreSQL adapter; schema v1 | Backup/restore drill, retention/deletion, subsequent migration tooling |
| Observability | Durable events, step spans, HTTP metrics | Production trace backend, queue gauges, alert routing and SLO dashboards |
| Deployment | Compose, non-root containers, Kubernetes templates, CI | Build/run on Docker, image scan, configured cloud rollout and acceptance |
| UI | Responsive console, live API calls, SSE and trace export | Broader browser/accessibility matrix and organizational login UX |
| Cost | Token-based estimated model cost when configured | Provider billing reconciliation, search/infra costs and global spend ceilings |
| Security | Input caps, limited tools, restricted sandbox settings | Penetration test, egress allowlists, dependency/image review and secret manager |

## Deliberately absent capabilities

No real refunds, external account updates, repository commits/PRs, arbitrary shell tools, full-document web crawler, hybrid RAG, vector database, LangGraph runtime, token-level LLM streaming, multi-region failover or turnkey SaaS billing. These are not required to demonstrate the reference's four agent patterns, and they should not be inferred from diagrams or names.

## Acceptance evidence to attach before labeling production-ready

A versioned deployment URL and image digest; passing CI including PostgreSQL and Docker integration; selected provider contract smoke results; real OIDC/tenant tests; the 20-issue repair result and 50-case live support report; an independent research assessment; multi-vs-single report measurements; a worker failure drill; backup restore evidence; security review; and named service/incident ownership. Until then, present this as a validated local engineering portfolio and deployment candidate.
