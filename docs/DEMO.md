# Seven-minute demonstration

## Preparation

Start API, database, general worker and isolated repair worker. Configure a JSON-capable model, search key and token prices if you want cost estimates. Use separate requester and approver OIDC tokens for the refund segment. Run paid evaluations ahead of time and keep their exported evidence. If a prerequisite is missing, say so and show the real local test result rather than presenting canned output as a live run.

## 0:00–0:45 — Architecture and evidence contract

Show the overview diagram and explain the separation between HTTP admission, durable job state and bounded workers. Open the readiness matrix. State which checks ran in the current environment. Explain that a workflow success and a high-quality answer are different claims.

## 0:45–2:00 — Grounded research

Submit the PostgreSQL queue question from the UI. Show the search action events, actual source snippets and returned claims. Identify a source ID and its exact quote. Explain why unsupported claims are rejected and why an entailment judge is fallible. Export the trace JSON.

## 2:00–3:15 — Code repair

Submit the addition regression preset. Show the failing baseline, first proposed patch and sandbox test result. Explain that tests are immutable and generated code runs in a fresh restricted container. Open the 20-task dataset and, if actually run, the held-out success report. A public-test pass alone is not repository-wide correctness.

## 3:15–4:30 — Support approval

Submit the duplicate-charge preset. Observe billing routing and the waiting state. Try approving with the requester token; the action must fail. Switch to a separate authorized identity, record a reason and approve. Observe resumption without repeating the routing calls. Highlight the pending-payment-integration ledger status: no funds were transferred.

## 4:30–5:45 — Parallel reports

Submit the mobile reliability preset. Show three worker steps, supervisor synthesis and the single-agent comparison. Compare measured latency and estimated model costs. Explain the larger total token budget and fixed-order confounder. Do not assume parallel is faster or cheaper.

## 5:45–7:00 — Recovery and operations

Replay the incident drill evidence, then run it locally if appropriate. Show the stale-owner rejection, preserved checkpoint and recovered result. Open the CI workflow, deployment manifests and release gates. Close on a concrete engineering trade-off: at-least-once execution with fenced state is honest; exactly-once external inference is not promised.

## Useful interview questions

Why one transactional database for queue and state? What happens after a provider responds but before checkpoint commit? Can a refund requester approve their own job? How do you distinguish public-test success from repair quality? Does parallelism improve latency after accounting for the supervisor? Which evidence is measured and which remains unverified?
