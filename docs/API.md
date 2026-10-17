# API contract and examples

Interactive OpenAPI: `/docs`. Machine-readable specification: `/openapi.json`. All business endpoints require `Authorization: Bearer TOKEN`. Tenant identity comes from the verified token. Health endpoints and static UI assets are public; metrics require `operator`.

| Method and path | Behavior |
|---|---|
| `POST /v1/runs` | Validate and enqueue; returns 202 with `{run, created}` |
| `GET /v1/runs` | Latest 100 jobs belonging to the caller's tenant |
| `GET /v1/runs/{id}` | Result, input, status and timestamps; private lease/checkpoint fields excluded |
| `GET /v1/runs/{id}/events` | SSE replay after an event cursor, up to 60 seconds per connection |
| `GET /v1/runs/{id}/traces?after=ID` | Up to 500 event records; continue with the last ID |
| `POST /v1/runs/{id}/approval` | Role-protected, distinct-human decision on a waiting support run |
| `POST /v1/runs/{id}/cancel` | Invalidate a queued/running/waiting job's ownership |
| `GET /health/live` | API process liveness |
| `GET /health/ready` | Database reachable and schema version 1 present |
| `GET /metrics` | Prometheus HTTP metrics, operator role required |

## Research example

```bash
curl http://localhost:8000/v1/runs \
  -H "Authorization: Bearer $DEV_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: research-demo-001' \
  -d '{"kind":"research","payload":{"question":"What does SKIP LOCKED mean for a PostgreSQL queue?"}}'
```

Save the returned run ID. Poll the run or stream events:

```bash
curl -N "http://localhost:8000/v1/runs/$RUN_ID/events" \
  -H "Authorization: Bearer $DEV_API_TOKEN" \
  -H 'Last-Event-ID: 0'
```

A successful research result contains accepted claims, rejected claims with reasons, source metadata, limitations and an abstention flag. Absence of evidence can produce a successful execution with `abstained=true`; success of the workflow does not imply a factual answer exists.

## Inputs

Research: `question`, 5–2,000 characters.

Code repair: `issue`, 5–4,000 characters; `source`, at most 30,000 characters; `tests`, 10–30,000 characters. The harness expects `solution.py` and Python `unittest` tests importing from `solution`.

Support: `message`, 3–4,000 characters; optional `order_id`, a bounded alphanumeric/underscore/hyphen identifier; optional `refund_cents`, positive integer up to 100,000. This maximum is a proposal limit, not refund eligibility. A refund with missing order/amount completes with escalation and `needs_order_and_amount`.

Reports: `topic`, 5–2,000 characters; `evidence`, 50–20,000 characters; optional `benchmark`, default true. Disabling the benchmark omits the single-agent baseline and saves that model call.

All input objects reject additional fields. The HTTP body cap is 100,000 bytes, independent of the declared Content-Length. Upstream proxies should also impose body and read-time limits.

## Approval example

```bash
curl -X POST "http://localhost:8000/v1/runs/$RUN_ID/approval" \
  -H "Authorization: Bearer $APPROVER_OIDC_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approved","reason":"Duplicate charge reviewed against the order record"}'
```

The approver must be in the same tenant, have `refund_approver`, and have a different subject from the requester. The same run cannot receive a second decision. A rejection resumes the run and records rejection without a refund ledger entry.

## Status and errors

Status values: `queued`, `running`, `waiting`, `succeeded`, `failed`, `cancelled`. API errors: 401 missing/invalid identity; 403 insufficient role; 404 absent or another tenant's run; 409 idempotency/state/self-approval conflict; 413 body too large; 422 schema error; 429 tenant active-job capacity reached.

Worker failures store an error class, not raw provider bodies, keys or stack traces. Inspect trace events and sanitized worker logs for diagnosis. A missing provider key causes an explicit failure, never a synthetic answer. The export CLI is an administrative database operation and is not tenant-filtered; restrict shell/database access accordingly.
