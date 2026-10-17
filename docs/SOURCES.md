# Primary implementation references

Consulted during implementation on 2026-10-16. These document the underlying interfaces; they do not certify this application or substitute for its integration tests.

- PostgreSQL SELECT / locking clauses: https://www.postgresql.org/docs/15/sql-select.html — `SKIP LOCKED` and queue-like consumers.
- Docker run reference: https://docs.docker.com/engine/containers/run/ — read-only filesystem, capabilities, user, networking and resource controls.
- Docker security: https://docs.docker.com/engine/security/ — daemon trust boundary and implications of host control.
- Tavily Search API: https://docs.tavily.com/documentation/api-reference/endpoint/search — HTTPS search endpoint, bearer authentication, result content.
- PyJWT API: https://pyjwt.readthedocs.io/en/latest/api.html — JWKS key resolution and validation parameters.
- OpenTelemetry Python instrumentation: https://opentelemetry.io/docs/languages/python/instrumentation/ — tracer provider, spans and exporters.

Model adapter contract: an OpenAI-compatible `/chat/completions` endpoint that accepts JSON-object response format and a bounded `max_tokens`. Verify the selected provider/model supports this exact contract. No provider-wide compatibility claim is made.
