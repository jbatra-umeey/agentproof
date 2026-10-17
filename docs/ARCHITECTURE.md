# Architecture and design

## Objective and boundaries

AgentProof is an inspectable engineering portfolio with a shared runtime that makes four agent patterns executable. Each pattern has a distinct risk: unsupported claims, unsafe code execution, unauthorized financial actions, or unsubstantiated parallelism benefits. The fifth project is the infrastructure needed to run those patterns reliably.

The implementation supports bounded asynchronous jobs, persistent progress and human intervention. It does not include autonomous repository merging, payment execution, arbitrary browsing, vector retrieval, Kubernetes provisioning, or a hosted identity provider. Those are separate integrations, not hidden stubs. The application never substitutes scripted responses when credentials are missing.

## Components and ownership

| Component | Responsibility | Important boundary |
|---|---|---|
| FastAPI service | Authenticate, validate, enforce tenant scope, enqueue, stream, approve, cancel | Does not execute user code or LLM work in HTTP handlers |
| Store | Transactions, admission limits, leases, events, checkpoints, decisions and refund ledger | Sole writer of durable application state |
| Worker process | Claim one job, heartbeat, run bounded workflow, commit or retry | One active job per process; scale processes for concurrency |
| Workflow context | Memoized stages, persistent model-call budget, traces | Cached stages prevent many repeated calls after restart |
| Model adapter | JSON responses, schema validation, timeout, token usage, cost estimation | Server-owned endpoint; not request-configurable |
| Search adapter | Tavily snippets and source metadata | No arbitrary URL fetcher, filesystem connector or browser |
| Docker sandbox | Execute submitted Python source/tests with hard resource limits | Dedicated host and restricted container; no fallback to host execution |
| Dashboard | Submit jobs, inspect results, replay events, export trace, approve as authorized user | Token held in page memory, no localStorage or query-string token |

## Submission path

The authenticated principal supplies tenant and subject; request payloads cannot override either. Input schemas reject unknown fields and bound text sizes. A request must provide an idempotency key. The store hashes the workflow kind plus normalized payload. Reusing a key with the same content returns the original job; changing content returns HTTP 409. The uniqueness boundary is `(tenant, idem_key)`.

A per-tenant sentinel row serializes admission checks so concurrent submissions cannot bypass the active-run limit. Queued, running and approval-waiting jobs all consume capacity. The default limit is 20 active jobs per tenant. This is an admission limit, not a complete HTTP rate limiter or financial budget.

## Claiming and recovery

PostgreSQL claim transactions select eligible rows with `FOR UPDATE SKIP LOCKED`, ordered by creation time. SQLite development transactions use `BEGIN IMMEDIATE` and WAL. These are different concurrency mechanisms; SQLite tests do not validate PostgreSQL behavior.

A successful claim increments an attempt counter and creates a random lease token. Every checkpoint, result, event, heartbeat and refund-ledger write verifies both the token and the unexpired running state under a row lock. An expired or replaced owner cannot commit. A worker crash leaves the job recoverable after its lease expires. The default lease is 120 seconds with a heartbeat approximately every 40 seconds.

Delivery is **at least once**. Completed steps are durable, but a crash after a provider accepted a request and before the checkpoint commits can repeat that external request. Fencing prevents stale database writes; it does not undo an already-started provider call. Provider billing may therefore exceed the successful-response usage recorded locally. The repo deliberately does not promise exactly-once LLM execution.

## Checkpoints and retry semantics

Each named step saves a JSON result inside the run checkpoint. A resumed workflow reconstructs the same control flow and returns stored values for completed steps. The names are stable workflow identifiers; renaming them without a migration changes replay semantics. Model call reservations persist before the provider call, providing a conservative cap of 24 calls per run.

Transient network errors, HTTP 429 and provider 5xx responses cause bounded whole-job retries with delays of `2 ** attempt` seconds. Permanent authentication/schema errors fail the job. Maximum worker claims before exhaustion: three, excluding the intentionally reset claim count after a human decision. Code repair has a separate maximum of three patch attempts inside a workflow. These two limits must not be confused.

The worker's run deadline is 600 seconds. Cancellation changes state and invalidates the lease. It prevents later commits; in-flight provider calls or sandbox work may continue briefly until the worker sees fencing or heartbeat failure. Containers have their own timeout and cleanup.

## Human decisions

A support request may propose a refund using an order ID and amount in integer cents. Both values are frozen in the original payload. A model can request review but cannot approve. The API requires a `refund_approver` role and a subject distinct from the original requester. Decision insertion and requeue happen in one transaction. The worker resumes from its route/reply checkpoints, reads the decision and inserts at most one ledger record per run.

The ledger status is `approved_pending_payment_integration`. **No money is moved.** Order ownership, previous refunds, payment capture validation, currencies, accounting reconciliation and an idempotent payment-provider outbox are release work before enabling real refunds.

## Streaming and observability

Events are stored in the database with increasing IDs and timestamps. The SSE endpoint replays events after a cursor, including across API replicas. Each connection lasts up to 60 seconds and can reconnect with `Last-Event-ID` or `after`. The browser uses authenticated `fetch`, not query-string tokens. Streaming means execution events; model token streaming is not implemented.

OpenTelemetry spans record run and step boundaries. Workflow spans are connected within one process execution. A resumed claim creates a new trace, correlated by `run.id`; distributed W3C trace propagation across retries is not implemented. Prometheus exposes HTTP counts and latency. Queue-age and workflow metrics are currently operational SQL queries, not exported gauges.

Event summaries omit prompts, but checkpoints, original payloads and final results contain user content and retrieved snippets. Encryption at rest, backup controls and retention must be configured at the database/platform boundary. User-facing traces must be treated as sensitive artifacts.

## Capacity model

Each worker handles one run at a time. A report run fans out three model calls concurrently, then synthesizes. The model adapter allows four concurrent calls per worker process. Aggregate concurrency is therefore bounded by replica count times four, not a global distributed limit. Size replicas against provider quotas and PostgreSQL connections. Large evidence corpora and long reports exceed this release's deliberately bounded payload and token limits.

## Data integrity

The ER diagram shows logical relationships. Run IDs in events/approvals/refunds are indexed or unique as needed but are not all SQL foreign keys. The application currently has no deletion API, avoiding partially deleted runs. A future retention process must delete dependent rows transactionally. The schema has an initial version record and a readiness check; follow-on schema upgrades need explicit versioned migration scripts.

## Technology choice

Python, FastAPI, SQLAlchemy and PostgreSQL provide an accessible service boundary and transaction model. The workflows use explicit async functions and durable steps instead of depending on an agent framework's opaque replay semantics. This is intentional: the four patterns do not require LangGraph to be valid. A framework adapter can be added later without weakening store ownership and approval rules.
