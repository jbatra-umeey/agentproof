# Validation record

Local validation performed during repository creation. This record reports observed results and explicit gaps.

| Check | Result | Evidence |
|---|---|---|
| Python functional/security tests | 48 passed | `evals/results/pytest.xml` |
| PostgreSQL integration | Skipped: TEST_DATABASE_URL unavailable | Gated test and CI service configured |
| Docker sandbox integration | Skipped: Docker unavailable | Gated test and CI runner configured |
| Support rules baseline | 43/50 correct; accuracy 86%; macro-F1 0.8619 | `evals/results/support-baseline.json` |
| Lease-expiry incident drill | Recovered checkpoint; stale commit rejected | `evals/results/incident-drill.json` |
| Python lint/format | Passed on source, tests and scripts | Ruff configuration and CI gate |
| Dashboard JavaScript syntax | Passed | `node --check web/app.js` |
| Compose/Kubernetes/collector/CI YAML | Parsed successfully | Static YAML check, not runtime deployment |
| Diagram rendering | All eight Mermaid diagrams rendered to SVG | `evals/results/diagram-validation.json` |
| Dashboard browser checks | Auth, navigation, submission, cancellation, SSE, desktop/mobile layout passed | `evals/results/browser-validation.json` |
| OpenAPI | Generated from application routes | `docs/openapi.json` |
| Live model/search evaluation | Not run: credentials not supplied | Runnable evaluation CLI included |
| Container image build and cloud rollout | Not run: no Docker/cloud target | Deployment guide and release gates |

Test coverage includes real local SQL transactions, concurrent claim uniqueness, tenant isolation, idempotency conflicts, stale leases, cancellation fencing, retry limits, checkpoint recovery, distinct-human approvals, duplicate-refund prevention, body/schema validation, SSE replay, real RSA signature/claim validation with a mocked JWKS fetch, mocked HTTP provider contract validation, agent branching and bounded repair attempts.

Scripted model doubles and mocked provider responses are test-only. They do not substantiate live model accuracy or provider interoperability. No application fallback returns scripted answers.

The installed Starlette TestClient emits a deprecation warning about its httpx transport. Tests pass; this is retained as a dependency maintenance item rather than silently hidden.

Production readiness requires the additional evidence in `PRODUCTION_READINESS.md`. A deployment manifest, a dataset, or a passing unit test is not proof of deployment, a measured live pass rate, or an operational SLO.
