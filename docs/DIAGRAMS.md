# Diagram atlas

All diagrams describe implemented code except deployment, which describes the target topology. Mermaid sources are editable in `docs/diagrams/`. The data model uses logical relationships; see architecture notes for SQL constraints.

## Architecture

```mermaid
flowchart TD
    user["Operator dashboard or API client"] --> api["FastAPI: authentication and tenant scope"]
    idp["OIDC identity provider"] -->|"Verified JWT claims"| api
    api -->|"Atomic enqueue and replay"| db[("PostgreSQL: jobs, checkpoints, events")]
    db -->|"Lease and fencing token"| worker["General worker pool"]
    db -->|"Codefix queue"| repair["Dedicated repair worker"]
    worker --> research["Research workflow"]
    worker --> support["Support workflow"]
    worker --> reports["Report workflow"]
    research --> search["Tavily search"]
    research --> model["Model gateway"]
    support --> model
    reports --> model
    repair --> model
    repair --> sandbox["Restricted Docker sandbox"]
    support -->|"Pause and approved ledger"| db
    api -->|"SSE event replay"| user
    worker --> otel["OpenTelemetry collector"]
    repair --> otel
```

## Run Lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued: validated submission
    queued --> running: worker claim
    running --> running: fenced checkpoint
    running --> queued: transient error and retry budget
    running --> running: expired lease reclaimed
    running --> waiting: refund proposal
    waiting --> queued: distinct human decision
    running --> succeeded: committed result
    running --> failed: permanent error or exhausted retries
    queued --> cancelled: cancellation
    running --> cancelled: cancellation fences owner
    waiting --> cancelled: cancellation
    succeeded --> [*]
    failed --> [*]
    cancelled --> [*]
```

## Research

```mermaid
flowchart TD
    question["Research question"] --> plan["Choose search or finish"]
    plan -->|"Search, at most 3 iterations"| search["Search provider"]
    search --> evidence["Bounded snippets and source IDs"]
    evidence --> plan
    plan -->|"Finish or iteration cap"| synth["Structured atomic claims"]
    synth --> quote{"Exact quote and known source?"}
    quote -->|"No"| reject["Reject claim"]
    quote -->|"Yes"| judge{"Evidence entails claim?"}
    judge -->|"No"| reject
    judge -->|"Yes"| accepted["Accepted cited claim"]
    reject --> final["Return supported claims or abstain"]
    accepted --> final
```

## Codefix

```mermaid
flowchart TD
    input["Issue, source and immutable tests"] --> baseline["Sandbox baseline"]
    baseline -->|"Already passing"| nofix["Return without repair claim"]
    baseline -->|"Failing"| patch["Model proposes complete source"]
    patch --> test["Fresh restricted sandbox"]
    test -->|"Failed and attempts remain"| reflect["Failure log and previous source"]
    reflect --> patch
    test -->|"Third failure"| failed["Report not fixed"]
    test -->|"Passed"| result["Candidate and public test evidence"]
    result --> hidden["Evaluation: held-out tests"]
    hidden --> review["Human review before merge"]
```

## Support Approval

```mermaid
sequenceDiagram
    participant U as Requester
    participant A as API
    participant W as Worker
    participant D as Database
    participant H as Approver
    U->>A: Message and optional refund proposal
    A->>D: Insert tenant-scoped job
    W->>D: Claim lease
    W->>W: Classifier and specialist response
    W->>D: Checkpoint and waiting state
    H->>A: Decision with separate identity
    A->>D: Atomic decision and requeue
    W->>D: Reclaim and read decision
    W->>D: Insert unique local refund ledger
    W->>D: Commit final result
    A-->>U: SSE status and result
```

## Reports

```mermaid
flowchart TD
    evidence["Topic and fixed evidence"] --> fanout["Launch three worker tasks"]
    fanout --> summary["Executive summary"]
    fanout --> risks["Risk analysis"]
    fanout --> delivery["Delivery plan"]
    summary --> supervisor["Supervisor synthesis"]
    risks --> supervisor
    delivery --> supervisor
    evidence --> single["Single agent baseline"]
    supervisor --> compare["Compare latency, model cost and quote checks"]
    single --> compare
    compare --> result["Results with experimental limitations"]
```

## Data Model

```mermaid
erDiagram
    TENANT_LOCKS ||--o{ RUNS : serializes_admission
    RUNS ||--o{ EVENTS : records
    RUNS ||--o| APPROVALS : receives
    RUNS ||--o| REFUNDS : creates
    RUNS {
        string id PK
        string tenant
        string idem_key
        string status
        string lease_token
        float lease_until
        int attempt
        json payload
        json checkpoint
        json result
    }
    EVENTS {
        int id PK
        string run_id
        string type
        json data
    }
    APPROVALS {
        string run_id PK
        string actor
        string decision
        string reason
    }
    REFUNDS {
        string run_id PK
        string tenant
        int amount_cents
        string status
    }
    TENANT_LOCKS {
        string id PK
    }
```

## Deployment

```mermaid
flowchart TD
    browser["Browser or service client"] --> gateway["TLS ingress and rate limits"]
    gateway --> api["API replicas"]
    api --> db[("Managed PostgreSQL")]
    general["General worker replicas"] --> db
    repair["Dedicated repair runner host"] --> db
    general --> providers["Model and search providers"]
    repair --> providers
    repair --> containers["Network-isolated sandbox containers"]
    general --> otel["Telemetry backend"]
    api --> idp["Identity provider JWKS"]
    backup["Backup and restore service"] --> db
```
