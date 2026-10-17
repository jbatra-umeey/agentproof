import pytest
from fastapi.testclient import TestClient

from agentproof.api import create_app
from agentproof.auth import Principal


@pytest.fixture
def client(settings, store):
    app = create_app(settings, store)
    with TestClient(app) as client:
        yield client


def headers(settings, key="request-key-001"):
    return {"Authorization": "Bearer " + settings.dev_token, "Idempotency-Key": key}


def test_authentication_required(client):
    assert client.get("/v1/runs").status_code == 401
    assert client.get("/v1/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_create_validate_and_replay(client, settings):
    payload = {"kind": "research", "payload": {"question": "What is a durable queue?"}}
    first = client.post("/v1/runs", json=payload, headers=headers(settings))
    second = client.post("/v1/runs", json=payload, headers=headers(settings))
    assert first.status_code == 202
    assert second.json()["created"] is False
    assert "lease_token" not in first.json()["run"]
    assert "checkpoint" not in first.json()["run"]


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "shell", "payload": {}},
        {"kind": "research", "payload": {"question": "ok", "secret": 1}},
        {"kind": "support", "payload": {"message": "refund", "refund_cents": -20}},
        {"kind": "support", "payload": {"message": "refund", "order_id": "../../etc"}},
    ],
)
def test_invalid_input(client, settings, payload):
    assert client.post("/v1/runs", json=payload, headers=headers(settings)).status_code == 422


def test_body_limit(client, settings):
    assert (
        client.post("/v1/runs", content=b"a" * 100001, headers=headers(settings)).status_code == 413
    )


def test_approver_role_required(client, settings, store):
    row, _ = store.create("development", "someone", "support", {}, "key")
    assert (
        client.post(
            f"/v1/runs/{row['id']}/approval",
            headers=headers(settings),
            json={"decision": "approved", "reason": "Validated order"},
        ).status_code
        == 403
    )


def test_other_tenant_routes_hidden(client, settings, store):
    row, _ = store.create("another", "a", "support", {}, "key")
    for suffix in ("", "/events", "/traces"):
        assert (
            client.get(f"/v1/runs/{row['id']}" + suffix, headers=headers(settings)).status_code
            == 404
        )


def test_sse_replay_and_security_headers(client, settings, store):
    row, _ = store.create("development", "developer", "support", {}, "key")
    claimed = store.claim()
    store.finish(row["id"], claimed["lease_token"], {"ok": True})
    response = client.get(f"/v1/runs/{row['id']}/events", headers=headers(settings))
    assert response.status_code == 200
    assert "event: succeeded" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_health(client):
    assert client.get("/health/ready").status_code == 200


def test_approval_api_with_distinct_identity(client, store):
    row, _ = store.create("tenant", "requester", "support", {}, "key")
    claim = store.claim()
    store.finish(row["id"], claim["lease_token"], {}, waiting=True)
    client.app.dependency_overrides[client.app.state.auth] = lambda: Principal(
        "tenant", "approver", frozenset({"refund_approver"})
    )
    response = client.post(
        f"/v1/runs/{row['id']}/approval", json={"decision": "approved", "reason": "Validated order"}
    )
    assert response.status_code == 200
    assert store.get(row["id"])["status"] == "queued"
