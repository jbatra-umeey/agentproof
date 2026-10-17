import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, update

from agentproof.db import Capacity, Conflict, LostLease, refunds, runs


def create(store, key="first-key", tenant="one", actor="requester"):
    return store.create(
        tenant,
        actor,
        "support",
        {"message": "Refund please", "order_id": "o1", "refund_cents": 100},
        key,
    )[0]


def test_idempotency_and_conflict(store):
    row = create(store)
    assert create(store)["id"] == row["id"]
    with pytest.raises(Conflict):
        store.create("one", "requester", "research", {"question": "Different"}, "first-key")
    assert create(store, tenant="two")["id"] != row["id"]


def test_tenant_isolation(store):
    row = create(store)
    assert store.get(row["id"], "two") is None
    assert store.list("two") == []
    with pytest.raises(KeyError):
        store.cancel(row["id"], "two")


def test_capacity_counts_waiting(store):
    create(store)
    with pytest.raises(Capacity):
        store.create("one", "r", "support", {}, "another-key", limit=1)


def test_concurrent_claims_are_distinct(store):
    for i in range(12):
        create(store, key=str(i))
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda _: store.claim(), range(12)))
    assert len({r["id"] for r in rows}) == 12


def test_expired_worker_cannot_checkpoint_or_finish(store):
    create(store)
    old = store.claim()
    with store.tx() as c:
        c.execute(update(runs).where(runs.c.id == old["id"]).values(lease_until=time.time() - 1))
    fresh = store.claim()
    assert fresh["attempt"] == 2
    with pytest.raises(LostLease):
        store.checkpoint(old["id"], old["lease_token"], "x", 1)
    with pytest.raises(LostLease):
        store.finish(old["id"], old["lease_token"], {})
    store.finish(fresh["id"], fresh["lease_token"], {"ok": True})


def test_cancel_fences_worker(store):
    create(store)
    row = store.claim()
    store.cancel(row["id"], "one")
    with pytest.raises(LostLease):
        store.finish(row["id"], row["lease_token"], {})


def test_retry_limit(store):
    create(store)
    for _ in range(3):
        row = store.claim()
        store.fail(row["id"], row["lease_token"], "Transient", retry=True)
        with store.tx() as c:
            c.execute(update(runs).where(runs.c.id == row["id"]).values(available=0))
    assert store.get(row["id"])["status"] == "failed"
    assert store.claim() is None


def test_resume_checkpoints(store):
    create(store)
    row = store.claim()
    store.checkpoint(row["id"], row["lease_token"], "completed-stage", {"answer": 42})
    with store.tx() as c:
        c.execute(update(runs).where(runs.c.id == row["id"]).values(lease_until=0))
    resumed = store.claim()
    assert resumed["checkpoint"]["completed-stage"]["answer"] == 42


def test_approval_atomic_and_refund_idempotent(store):
    create(store)
    row = store.claim()
    with pytest.raises(Conflict):
        store.record_refund(row["id"], row["lease_token"])
    store.finish(row["id"], row["lease_token"], {}, waiting=True)
    with pytest.raises(Conflict):
        store.decide(row["id"], "one", "requester", "approved", "self approval forbidden")
    store.decide(row["id"], "one", "approver", "approved", "Duplicate charge verified")
    with pytest.raises(Conflict):
        store.decide(row["id"], "one", "approver", "approved", "duplicate")
    resumed = store.claim()
    one = store.record_refund(row["id"], resumed["lease_token"])
    two = store.record_refund(row["id"], resumed["lease_token"])
    assert one == two
    with store.engine.connect() as c:
        assert len(c.execute(select(refunds)).all()) == 1
    assert one["status"] == "approved_pending_payment_integration"


def test_rejected_refund_cannot_record(store):
    create(store)
    row = store.claim()
    store.finish(row["id"], row["lease_token"], {}, waiting=True)
    store.decide(row["id"], "one", "approver", "rejected", "Not eligible")
    row = store.claim()
    with pytest.raises(Conflict):
        store.record_refund(row["id"], row["lease_token"])


def test_claim_filters_worker_kind(store):
    create(store)
    assert store.claim(kinds=["codefix"]) is None
    assert store.claim(kinds=["support"]) is not None


def test_event_replay_cursor(store):
    row = create(store)
    initial = store.event_list(row["id"])
    store.claim()
    later = store.event_list(row["id"], initial[-1]["id"])
    assert [e["type"] for e in later] == ["claimed"]
