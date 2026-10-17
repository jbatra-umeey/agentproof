# Threat model and security boundaries

## Trust zones

The browser, customer messages, retrieved snippets, proposed source code and submitted tests are untrusted inputs. The API, queue worker and database are trusted application components. The model/search services are external processors. The Docker runner is privileged infrastructure and must live on a dedicated host; test containers are the untrusted execution boundary.

## Controls and residual risks

| Threat | Implemented control | Remaining requirement |
|---|---|---|
| Cross-tenant access | Tenant derived from verified JWT; tenant-filtered reads/mutations; isolation tests | Database row-level security and tenant-specific encryption are not implemented |
| JWT forgery | RS256 allowlist, signature, issuer, audience, expiry, required tenant/subject, bounded claims | Validate real issuer configuration, key rotation, revocation and outage behavior |
| Duplicate jobs | Tenant/idempotency-key uniqueness and request-content hash | Browser submit creates a fresh key per click; use a stable key for network retries |
| Stale worker writes | Lease token, running-state and expiry checked under lock | External requests may still complete after lease loss |
| Unauthorized refund | Distinct role-bearing approver, frozen proposal, unique ledger | No payment integration or order ownership checks; keep ledger nonfinancial |
| Prompt injection | Strict schemas, untrusted-data prompts, small tool surface, no arbitrary actions | Prompt instructions alone are not a security boundary; models can misclassify or hallucinate |
| Sandbox abuse | No network, read-only root, non-root UID, no capabilities, no privilege escalation, CPU/memory/PID/time/output limits | Shared-kernel container risk remains; use microVM/gVisor isolation for hostile public workloads |
| Credential theft | Keys from environment; no key in browser, checkpoint, model prompt or query string | Secret manager, process isolation, credential rotation and provider-scoped keys |
| Resource exhaustion | Body and field limits, bounded loops, run deadline, admission cap, call cap, worker semaphore | Gateway rate limits, global provider quotas, spend budgets, connection/read timeouts |
| XSS | UI renders results with `textContent`, restrictive CSP, no third-party scripts | Full penetration test and accessibility/browser matrix |
| Sensitive traces | Tenant-scoped trace endpoints, payload-free event summaries | Checkpoints/results still contain data; retention, backups, DLP and encryption at rest |

## Identity contract

Production mode rejects SQLite and development-token authentication. Configure an HTTPS JWKS endpoint, issuer and audience; JWTs must contain `sub`, `tenant_id`, `iat`, `exp`, and optionally a list of `roles`. The trusted issuer owns tenant and role assignment. Tokens cannot self-select a tenant from request JSON.

`refund_approver` authorizes human decisions; `operator` authorizes metrics. Other authenticated users can operate jobs within their tenant. Per-user ownership ACLs inside a tenant are not implemented. A development token authenticates one fixed local identity with operator privileges, not refund approval privileges.

The dashboard accepts a bearer token for a technical demo. It does not implement browser OAuth authorization-code/PKCE login, refresh tokens or a session BFF. Add your organization's login flow before exposing it to end users.

## Code runner specifics

The sandbox starts a new container for every baseline, candidate and hidden test run. Source/tests arrive over stdin, not host-mounted directories. It receives no application secrets or Docker socket. Its Python harness writes only to a bounded tmpfs, captures limited output and runs `unittest` with a 15-second subprocess limit. The host bounds the container operation to 25 seconds and explicitly removes the container even if the client times out.

This release is for trusted internal engineering users working on reviewed Python tasks. Submitted tests and source share an interpreter during unittest discovery, so malicious code could tamper with test machinery or fake success. A green sandbox result is not a trust proof. Before accepting public arbitrary code, replace the execution boundary with independently managed microVM jobs, trusted evaluation harnesses, syscall policy, artifact verification and a separate hidden evaluator. Never mount the host Docker socket into the API or general worker containers.

## Data handling

No retention sweep runs automatically. Operators must define retention, legal deletion, archival and backup policies before real customer data is ingested. Do not place payment card data, secrets, private keys or regulated records in sample jobs. Exported traces can include original inputs and final outputs. The administrative CLI can access every tenant because it runs with direct DB credentials; restrict this path to authorized operators.

## Secure release checks

Run dependency and container vulnerability scanning, pin deployed images by digest, configure TLS and egress allowlists, test authentication against the actual identity provider, set provider spend ceilings, review role assignment and perform an isolated sandbox breakout assessment. These are target-environment gates, not completed checks in this artifact.
