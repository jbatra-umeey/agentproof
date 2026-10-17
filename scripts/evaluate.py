"""Reproducible evaluation runner. Baseline and live results are never merged."""

import argparse
import asyncio
import hashlib
import json
import math
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from agentproof.agents.support import rule_route
from agentproof.config import Settings
from agentproof.db import Store
from agentproof.providers import Model, Search
from agentproof.sandbox import DockerSandbox
from agentproof.worker import execute

ROOT = Path(__file__).resolve().parents[1]


def wilson(correct, n):
    if n == 0:
        return [0, 1]
    z, p = 1.96, correct / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    delta = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(center - delta, 4), round(center + delta, 4)]


def support_summary(rows):
    labels = ["billing", "technical", "account"]
    confusion = {x: {y: 0 for y in labels + ["error"]} for x in labels}
    for row in rows:
        confusion[row["expected"]][row.get("predicted") or "error"] += 1
    correct = sum(r.get("correct", False) for r in rows)
    f1 = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[x][label] for x in labels if x != label)
        fn = sum(v for k, v in confusion[label].items() if k != label)
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return {
        "cases": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "macro_f1": sum(f1) / len(f1),
        "accuracy_wilson_95": wilson(correct, len(rows)),
        "confusion_matrix": confusion,
    }


async def evaluate(args):
    settings = Settings()
    if args.mode == "live" and (not settings.llm_key or not settings.llm_model):
        raise SystemExit("Live evaluation requires LLM_API_KEY and LLM_MODEL; no fallback is used.")
    if args.mode == "baseline" and args.suite != "support":
        raise SystemExit(
            "Only support has a deterministic rules baseline. Use --mode live for other suites."
        )
    path = (
        ROOT / "evals/data" / ("support_50.json" if args.suite == "support" else "codefix_20.json")
    )
    if args.suite in ("support", "codefix"):
        cases = json.loads(path.read_text())
        dataset_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    elif args.suite == "research":
        cases = [
            {
                "id": "research-001",
                "question": "What trade-offs does PostgreSQL SKIP LOCKED introduce for a durable queue?",
            }
        ]
        dataset_sha = None
    else:
        cases = [
            {
                "id": f"report-{i:03}",
                "topic": "Mobile reliability rollout",
                "benchmark": True,
                "evidence": "The team has six engineers. Crash-free sessions are 99.7%. The target is 99.9%. Release frequency is weekly. Regression automation covers 72% of critical journeys. Low-memory Android devices cause 65% of failures.",
            }
            for i in range(1, 6)
        ]
        dataset_sha = None
    if args.limit:
        cases = cases[: args.limit]
    rows, exports = [], []
    with tempfile.TemporaryDirectory() as directory:
        settings.database_url = "sqlite:///" + directory + "/eval.db"
        store = Store(settings.database_url)
        store.migrate()
        model, search, sandbox = (
            Model(settings),
            Search(settings.tavily_key),
            DockerSandbox(settings),
        )
        for case in cases:
            started = time.perf_counter()
            if args.mode == "baseline":
                predicted = rule_route(case["message"])
                rows.append(
                    {**case, "predicted": predicted, "correct": predicted == case["expected"]}
                )
                continue
            if args.suite == "support":
                payload = {"message": case["message"], "order_id": None, "refund_cents": None}
            elif args.suite == "codefix":
                payload = {key: case[key] for key in ("issue", "source", "tests")}
            else:
                payload = {key: value for key, value in case.items() if key != "id"}
            job, _ = store.create("evaluation", "evaluation", args.suite, payload, case["id"])
            claimed = store.claim()
            await execute(store, claimed, settings, model, search, sandbox)
            final = store.get(job["id"])
            row = {
                "id": case["id"],
                "status": final["status"],
                "error": final["error"],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            result = final["result"] or {}
            if args.suite == "support":
                predicted = result.get("route", {}).get("specialist")
                row.update(
                    expected=case["expected"],
                    predicted=predicted,
                    correct=predicted == case["expected"],
                    category=case["category"],
                )
            elif args.suite == "codefix":
                row["public_pass"] = result.get("fixed", False)
                row["hidden_pass"] = False
                if row["public_pass"]:
                    try:
                        check = await sandbox.run(result["source"], case["hidden_tests"])
                        row["hidden_pass"] = check["passed"]
                        row["hidden_log"] = check["log"]
                    except Exception as exc:
                        row["hidden_error"] = type(exc).__name__
                row["attempts"] = len(result.get("attempts", []))
            else:
                row["result"] = result
            rows.append(row)
            exports.append(
                {
                    "run": {k: v for k, v in final.items() if k != "lease_token"},
                    "events": store.event_list(job["id"]),
                }
            )
        store.engine.dispose()
    summary = (
        support_summary(rows)
        if args.suite == "support"
        else {"cases": len(rows), "succeeded": sum(r["status"] == "succeeded" for r in rows)}
    )
    if args.suite == "codefix":
        fixed = sum(r["hidden_pass"] for r in rows)
        summary.update(
            hidden_pass_count=fixed,
            hidden_pass_rate=fixed / len(rows),
            wilson_95=wilson(fixed, len(rows)),
        )
    report = {
        "suite": args.suite,
        "mode": args.mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": dataset_sha,
        "model": settings.llm_model if args.mode == "live" else None,
        "qualification": "Synthetic author-curated dataset; not a production-quality certification. Baseline measures rules, not LLM accuracy.",
        "summary": summary,
        "cases": rows,
        "traces": exports,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite", choices=["support", "codefix", "research", "reports"], required=True
    )
    parser.add_argument("--mode", choices=["baseline", "live"], required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    asyncio.run(evaluate(args))
