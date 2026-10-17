# Evaluation design and evidence

## Evidence levels

1. **Deterministic tests:** Verify application behavior using synthetic inputs, scripted model doubles and real local database transactions.
2. **Rules baseline:** Measures a simple classifier on the 50-case support dataset. It is independent of the live support model.
3. **Live integrations:** Exercise actual model/search responses and Docker. Require credentials and an isolated runner.
4. **Deployment acceptance:** Verify PostgreSQL under concurrency, real OIDC, ingress, restarts, backup/restore and load in the target environment.

A result at one level does not imply success at another. Stored reports include dataset SHA-256, mode, timestamp, per-case outcomes and model identity where applicable. Do not copy rules-baseline results into a model accuracy slide.

## Support: 50 cases

The authored dataset has 18 billing, 16 account and 16 technical cases. Categories include routine requests, paraphrases, ambiguity and prompt injection. Expected routing labels are authored judgments, not independently adjudicated production ground truth. Classifier accuracy does not establish refund safety; separate tests enforce the authorization boundary.

Measured local rules baseline: **43 correct of 50 (86%)**, macro-F1 **0.8619**. Approximate 95% Wilson interval: **73.81%–93.05%**. This interval assumes independent cases; because these are curated synthetic examples, it is descriptive rather than evidence of real-world generalization.

| Expected / predicted | Billing | Technical | Account |
|---|---:|---:|---:|
| Billing | 15 | 3 | 0 |
| Technical | 1 | 14 | 1 |
| Account | 0 | 2 | 14 |

Errors include indirect billing/access requests and mixed-topic messages. Keep the initial result unchanged as a baseline; improving heuristics on these same cases would overfit the evaluation set.

```bash
python scripts/evaluate.py --suite support --mode baseline --output evals/results/support-baseline.json
python scripts/evaluate.py --suite support --mode live --output evals/results/live-support.json
```

The live runner includes failed jobs in the denominator. Add a separately authored, frozen holdout before making production accuracy claims. Measure per-class recall, escalation recall, injection resistance and confidence calibration. The current model's numeric confidence is not calibrated by this release.

## Code repair: 20 issues

Each issue has broken Python source, a natural-language requirement, public regression tests and hidden input cases. Hidden tests are never supplied to the model. Tasks span arithmetic, sequences, strings, sorting, parsing and interval merging. They are small synthetic tasks, not a substitute for SWE-bench or a real repository issue distribution.

A live workflow first confirms a failing baseline, then runs at most three repair attempts. Success on public tests is followed by a separate held-out sandbox execution. The evaluation reports public and hidden outcomes, attempt count, latency and failures for every issue. The denominator is all selected issues, including infrastructure failures.

```bash
export SANDBOX_ENABLED=true
python scripts/evaluate.py --suite codefix --mode live --output evals/results/live-codefix.json
```

Report `hidden_pass_count / 20`, public-vs-hidden gap, pass by attempt, infrastructure errors and token cost. The script permits `--limit` for smoke checks and records the actual smaller denominator. No repair pass rate has been measured in this environment because Docker and live model credentials are unavailable.

## Research grounding

The workflow validates citation identity and verbatim quote containment before asking an entailment judge. This blocks invented source IDs and invented quotations but does not prove the source is correct. A judge can share the answer model's biases. Search snippets can omit context, change over time or contain injection.

```bash
python scripts/evaluate.py --suite research --mode live --output evals/results/live-research.json
```

The included live research case is a smoke case, not a statistically meaningful benchmark. Expand to a frozen question set with independent assessors, known unanswerable questions and malicious source snippets. Score citation precision, supported-claim precision, answer completeness, abstention correctness, source quality and search cost. Tests already cover exact-match rejection and unsupported-claim abstention.

## Reports: honest parallel comparison

The live report suite repeats the same fixed task five times. Each run has three specialist calls plus supervisor synthesis, then a single-agent call on the same topic/evidence. The same model and per-call output cap apply. Multi-agent therefore has a larger total call/token budget, and the default order is fixed. These are explicit confounders.

```bash
python scripts/evaluate.py --suite reports --mode live --output evals/results/live-reports.json
```

Compare successful runs' latency, token use and estimated model cost, while reporting failures separately. Before claiming an advantage, randomize execution order, use multiple topics, repeat enough trials, and have blinded reviewers score correctness, coverage and usefulness. Exact evidence quotes are only a lexical check; the release does not provide a comprehensive quality judge or demonstrate that multi-agent is better.

## Cost accounting

For each completed model response:

`estimated USD = (input tokens × input rate + output tokens × output rate) / 1,000,000`.

Set `LLM_INPUT_USD_PER_MILLION` and `LLM_OUTPUT_USD_PER_MILLION` to verified prices for the chosen model. If prices or provider token counts are absent, cost is `null`, not zero. The estimate excludes search charges, compute, database, storage, network, cached-token discounts, reasoning-token nuances and any provider request whose usage was lost before a durable event. These are **model response estimates**, not a billing reconciliation.

## Reproducibility

Commit the dataset and prompt changes together with raw results and environment metadata. Keep live traces private until reviewed for sensitive content. CI publishes validation artifacts but does not call paid providers. Lock dependencies for repeatability, record the model revision if supported, and retain date/source snapshots for search evaluations. The source archive includes the local test and drill evidence actually generated during creation.
