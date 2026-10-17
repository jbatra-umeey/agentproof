# Operations and reliability runbook

## Proposed service objectives

These are targets to validate, not measured SLO attainment: 99.9% API availability, admission p95 below 300 ms, queue wait p95 below 10 seconds at planned capacity, zero unauthorized refund ledger writes, and recovery after worker loss within lease duration plus queue delay. Provider latency, search quality and human approval time have separate budgets.

## Monitoring

HTTP counts and latency are available at authenticated `/metrics`. OpenTelemetry traces record run and step boundaries. Use structured event JSON for workflow progress, model usage and state changes. Do not log provider keys or raw exception responses. Correlate by run ID across worker retries.

Operational PostgreSQL queries:

```sql
SELECT status, count(*) FROM runs GROUP BY status;
SELECT kind, min(created) AS oldest_created, count(*)
FROM runs WHERE status = 'queued' GROUP BY kind;
SELECT id, tenant, kind, attempt, lease_until
FROM runs
WHERE status = 'running' AND lease_until < extract(epoch FROM now());
SELECT id, kind, error, updated FROM runs
WHERE status = 'failed' ORDER BY updated DESC LIMIT 50;
SELECT id, tenant, updated FROM runs
WHERE status = 'waiting' ORDER BY updated ASC;
```

Treat direct SQL access as administrative. Tenant isolation is enforced by the application, not automatically for arbitrary database queries. Alert on old queued jobs, expired leases, error spikes, waiting approvals exceeding the support SLA and repeated provider 429s.

## Queue backlog

Check whether workers are running with the correct `--kinds`. Code jobs will remain queued until a dedicated code worker exists. Check provider authentication, network access and database connections. Increase replicas only after checking provider quotas. All active runs, including waiting approvals, count against the tenant cap. Resolve aged approvals rather than raising the limit indefinitely.

## Provider failures

401/403 or invalid structured response: fix the key/model/adapter contract and submit a new run with a new idempotency key. The application does not endlessly retry permanent errors. 429/5xx and network errors retry up to the claim limit with bounded backoff. No circuit breaker or cross-replica rate limiter is shipped; a provider outage can affect all workers. Use a gateway with shared quotas/circuit policy for a scaled deployment.

## Lost worker

Inspect the run lease and event history. A crashed worker's lease will expire, allowing another worker to claim and reuse checkpoints. Do not manually set `status=succeeded` to unblock a queue. If a worker repeatedly crashes on the same job, the attempt cap eventually marks it failed. Investigate payload size, adapter failures and sandbox errors before resubmission.

## Cancellation

The cancel endpoint fences database mutations immediately. It is not a guarantee that an already-started external provider call is cancelled or free. The worker observes ownership loss at its next checkpoint or heartbeat, then cancels local tasks. The sandbox cleanup explicitly removes its container. Run-level deadlines and per-container limits provide independent bounds.

## Refund approval

Inspect the original proposal and verify the order in your actual business system. Use a separate authorized identity. Approving writes only the local pending-integration ledger. Do not tell the customer money was returned based on that status. Rejected proposals complete without a ledger entry. If a payment integration is added, require a transactional outbox, provider idempotency key, webhook verification and reconciliation before any funds-moved status.

## Backups and retention

Use managed database snapshots plus point-in-time recovery. Perform a restore drill into an isolated database and compare run/event/approval relationships. Define RPO and RTO with the deployment owner. No backup schedule, retention job or deletion API is automatically configured by this repo. Payloads, evidence and checkpoints may contain sensitive data. Archive/redact deliberately and delete dependent rows transactionally when adding retention.

## Incident exercise

Run `python scripts/incident_drill.py` in a development checkout. It creates an isolated temporary database, checkpoints a job, expires its lease, reclaims it and attempts a stale completion. The stale completion must be rejected and the recovered owner must succeed. The script writes real local evidence to `evals/results/incident-drill.json`. See the one-page [incident write-up](INCIDENT.md).
