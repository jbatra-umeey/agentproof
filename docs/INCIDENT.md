# Incident exercise: stale worker after lease expiry

**Classification:** deliberate local fault-injection exercise, not a customer outage or claimed production incident. **Scope:** one synthetic research job in a temporary SQLite database. **Evidence:** `evals/results/incident-drill.json`; reproduction: `python scripts/incident_drill.py`.

## What was caused

An active worker checkpointed a successful retrieval stage. The drill then forced its lease timestamp into the past while preserving the original worker's token. This models a worker that misses heartbeats because of process suspension, a long runtime pause or network partition, but later resumes and tries to commit.

## Observed sequence

1. Worker A claimed a job and persisted `retrieved` evidence.
2. The operator injected lease expiry directly in the drill database.
3. Worker B reclaimed the job with a new token and attempt number.
4. Worker A attempted to commit a stale result and received `LostLease`.
5. Worker B committed the recovered result, with the earlier checkpoint intact.

The timestamped JSON artifact records these events from the actual run. No synthetic latency or customer-impact estimate is attached.

## Root failure mode

A lease is not enough on its own. An old worker may continue executing after the lease has expired and another worker has taken ownership. Without a fencing check on every mutation, it can overwrite the new owner's state, duplicate decisions or append misleading completion events.

## Containment and fix demonstrated

The Store checks current status, unexpired lease and random ownership token under a row lock before every mutable worker operation. Reclamation changes the token. Cancellation clears ownership. Checkpoints are reused by the recovered owner. The old worker's completion is therefore rejected, and only the new owner publishes the final result.

## What this exercise proves

The local SQL implementation preserves the checkpoint and rejects a stale database commit during the injected sequence. It does not prove PostgreSQL behavior under distributed load, network partition safety for provider calls, exact recovery-time objectives or exactly-once external execution. PostgreSQL concurrency and real worker-kill drills remain deployment gates.

## Follow-up

Run the same scenario against staging PostgreSQL with two real worker processes; kill one during a provider call; measure recovery and duplicate provider billing. Add queue-age alerts and stalled-job dashboards. Preserve idempotency at each future side-effect boundary. A payment system would require a transactional outbox and provider reconciliation in addition to the current local ledger uniqueness constraint.
