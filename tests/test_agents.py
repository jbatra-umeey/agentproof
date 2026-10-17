import hashlib

import pytest
from conftest import FakeSandbox, ScriptedModel

from agentproof.agents.research import citation_valid
from agentproof.runtime import BudgetExceeded, Context
from agentproof.sandbox import DockerSandbox, SandboxUnavailable
from agentproof.schemas import Grounding
from agentproof.worker import execute


def context(store, settings, kind, payload, model, sandbox=None, search=None):
    store.create("one", "requester", kind, payload, "key")
    row = store.claim()
    return Context(store, row, model, search, sandbox, settings)


def test_citation_unknown_source_and_fabricated_quote():
    source = {"s": {"content": "PostgreSQL can skip locked rows in a queue."}}
    assert citation_valid({"source_id": "s", "quote": "skip locked rows in a queue"}, source)
    assert not citation_valid({"source_id": "x", "quote": "skip locked rows in a queue"}, source)
    assert not citation_valid(
        {"source_id": "s", "quote": "This invented evidence does not exist"}, source
    )


async def test_research_rejects_unsupported_claim(store, settings):
    from agentproof.agents.research import run

    url = "https://example.org/queue"
    source_id = hashlib.sha256(url.encode()).hexdigest()[:12]

    class Search:
        async def search(self, query):
            return [
                {
                    "url": url,
                    "title": "Queue",
                    "content": "A lease can expire after a worker crashes.",
                }
            ]

    model = ScriptedModel(
        [
            {"action": "search", "query": "queue leases", "rationale": "Find evidence"},
            {"action": "finish", "rationale": "Evidence retrieved"},
            {
                "claims": [
                    {
                        "text": "All queues guarantee exactly-once execution",
                        "source_id": source_id,
                        "quote": "A lease can expire after a worker crashes.",
                    }
                ],
                "limitations": "One source",
            },
            {"supported": False, "reason": "Quote does not entail exactly-once"},
        ]
    )
    ctx = context(store, settings, "research", {}, model, search=Search())
    result = await run(ctx, {"question": "Queue semantics?"})
    assert result["abstained"] and len(result["rejected"]) == 1


async def test_research_no_evidence_abstains(store, settings):
    from agentproof.agents.research import run

    model = ScriptedModel([{"action": "finish", "rationale": "No reliable evidence"}])
    ctx = context(store, settings, "research", {}, model)
    assert (await run(ctx, {"question": "Unknown fact?"}))["abstained"]


async def test_code_reflection_capped_at_three_and_tests_immutable(store, settings):
    from agentproof.agents.codefix import run

    sandbox = FakeSandbox([False] * 4)
    model = ScriptedModel([{"source": "def solve(): return 1", "explanation": "repair"}] * 3)
    ctx = context(store, settings, "codefix", {}, model, sandbox=sandbox)
    result = await run(
        ctx, {"issue": "Fix function", "source": "broken", "tests": "immutable tests"}
    )
    assert not result["fixed"] and len(result["attempts"]) == 3
    assert len(model.calls) == 3 and len(sandbox.calls) == 4
    assert all(tests == "immutable tests" for _, tests in sandbox.calls)


async def test_code_stops_after_success(store, settings):
    from agentproof.agents.codefix import run

    model = ScriptedModel([{"source": "fixed", "explanation": "repair"}])
    sandbox = FakeSandbox([False, True])
    ctx = context(store, settings, "codefix", {}, model, sandbox=sandbox)
    result = await run(ctx, {"issue": "Fix function", "source": "broken", "tests": "tests"})
    assert result["fixed"] and len(result["attempts"]) == 1


async def test_support_pauses_and_resumes_without_repeated_model_calls(store, settings):
    payload = {"message": "Refund my duplicate charge", "order_id": "o1", "refund_cents": 2500}
    model = ScriptedModel(
        [
            {"specialist": "billing", "confidence": 0.95, "refund_requested": True},
            {"response": "A human must review this request", "escalate": True},
        ]
    )
    store.create("one", "requester", "support", payload, "key")
    row = store.claim()
    await execute(store, row, settings, model=model)
    assert store.get(row["id"])["status"] == "waiting"
    store.decide(row["id"], "one", "approver", "approved", "Duplicate charge verified")
    await execute(store, store.claim(), settings, model=model)
    final = store.get(row["id"])
    assert final["status"] == "succeeded"
    assert final["result"]["refund_status"] == "approved_pending_payment_integration"
    assert len(model.calls) == 2


async def test_parallel_reports_and_single_baseline(store, settings):
    from agentproof.agents.reports import run

    section = {
        "title": "Report",
        "body": "Plan based on the evidence",
        "evidence_quotes": ["The team has six engineers."],
    }
    model = ScriptedModel([section] * 5)
    ctx = context(store, settings, "reports", {}, model)
    result = await run(
        ctx, {"topic": "Delivery", "evidence": "The team has six engineers.", "benchmark": True}
    )
    assert len(model.calls) == 5
    assert len(result["parallel"]["sections"]) == 3
    assert result["parallel"]["estimated_model_usd"] is None
    assert result["single"]["report"]["quote_check_passed"]


async def test_cached_step_not_repeated(store, settings):
    ctx = context(store, settings, "support", {}, ScriptedModel([]))
    called = []

    async def operation():
        called.append(1)
        return {"answer": 1}

    assert await ctx.step("one", operation) == await ctx.step("one", operation)
    assert len(called) == 1


async def test_budget_is_enforced(store, settings):
    settings.max_model_calls = 0
    ctx = context(store, settings, "research", {}, ScriptedModel([]))
    with pytest.raises(BudgetExceeded):
        await ctx.ask("one", "test", {}, Grounding)


async def test_sandbox_fails_closed(settings):
    settings.sandbox_enabled = False
    with pytest.raises(SandboxUnavailable):
        await DockerSandbox(settings).run("untrusted", "untrusted")


def test_sandbox_controls(settings):
    args = DockerSandbox(settings).command("run-name")
    assert "--network=none" in args and "--read-only" in args
    assert "--cap-drop=ALL" in args and "--security-opt=no-new-privileges" in args
    assert not any("docker.sock" in x for x in args)


def test_production_rejects_development_auth(settings):
    settings.environment = "production"
    with pytest.raises(ValueError):
        settings.validate()
