# Architecture decision records

## ADR 001 — Transactional database queue

**Accepted.** Use PostgreSQL for queue state, checkpoints, events and approval transactions. This keeps approval/requeue and result/event writes atomic and avoids dual-write problems in this bounded portfolio. `SKIP LOCKED` supports multiple consumers. Trade-offs: database polling, operational connection load, no broker-level fanout, and contention at larger scale. Revisit a broker/outbox design when workload volume warrants it. SQLite is development-only.

## ADR 002 — Explicit workflow code

**Accepted.** Express the four patterns as async Python functions using named durable steps. This keeps replay behavior visible and limits framework coupling. Trade-offs: no visual graph editor, framework-managed checkpoint migrations or built-in graph inspection. A future LangGraph adapter must preserve tenant ownership, approval separation and store fencing rather than duplicating state authority.

## ADR 003 — Event streaming instead of token streaming

**Accepted.** SSE exposes durable workflow events, giving replay across replicas and resumable UI inspection. Model outputs use structured JSON and are committed as whole steps. Trade-offs: users do not see incremental model tokens; long model calls may have only heartbeat events until completion. Token streaming would need partial-output semantics that do not bypass final validation.

## ADR 004 — Refund ledger without payment execution

**Accepted.** Demonstrate the human approval pattern using an immutable local ledger with an explicit pending-integration status. No payment API is called. Trade-off: not a real refund product. Actual payment integration requires eligibility checks, idempotent outbox dispatch, verified callbacks and reconciliation.

## ADR 005 — Restricted Docker execution

**Accepted for trusted internal tasks only.** No network, capabilities, host mounts or credentials inside test containers; non-root execution, bounded resource/time/output limits. The runner itself lives separately. Trade-off: Docker shares a kernel and submitted source can tamper with Python tests. Public hostile workloads require stronger isolation and a trusted independent judge.

## ADR 006 — Evidence before performance claims

**Accepted.** Baseline, scripted-test and live results remain separate. Unknown costs are null, not zero. Multi-agent reports are compared against a single-agent path without assuming an improvement. Trade-off: the initial artifact does not contain fabricated impressive live benchmark numbers. This strengthens the portfolio's credibility.
