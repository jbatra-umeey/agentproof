import json
import time
from types import SimpleNamespace
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from agentproof.auth import authenticator
from agentproof.providers import Model, ProviderError, TransientProviderError
from agentproof.schemas import Grounding


@pytest.fixture
def oidc(settings, monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.jwks_url = "https://identity.example/jwks"
    settings.jwt_issuer = "https://identity.example"
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, token: SimpleNamespace(key=private.public_key()),
    )
    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "roles": ["refund_approver"],
    }
    return authenticator(settings), private, claims


def credential(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_real_rsa_signature_and_claims(oidc):
    auth, private, claims = oidc
    principal = auth(credential(jwt.encode(claims, private, algorithm="RS256")))
    assert principal.tenant == "tenant-1" and "refund_approver" in principal.roles


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"aud": "wrong"},
        {"iss": "wrong"},
        {"tenant_id": "../other"},
        {"roles": "operator"},
    ],
)
def test_oidc_rejects_invalid_claims(oidc, changes):
    auth, private, claims = oidc
    with pytest.raises(HTTPException) as error:
        auth(credential(jwt.encode(claims | changes, private, algorithm="RS256")))
    assert error.value.status_code == 401


def test_oidc_rejects_wrong_signature_and_algorithm(oidc):
    auth, _, claims = oidc
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for key, algorithm in ((other, "RS256"), ("a-test-secret-at-least-thirty-two-bytes", "HS256")):
        with pytest.raises(HTTPException):
            auth(credential(jwt.encode(claims, key, algorithm=algorithm)))


def mock_http(monkeypatch, status, body):
    real = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real(transport=transport, **kwargs))


async def test_live_adapter_usage_and_schema(settings, monkeypatch):
    settings.llm_key, settings.llm_model = "test-key", "test-model"
    settings.input_price, settings.output_price = 2, 8
    mock_http(
        monkeypatch,
        200,
        {
            "choices": [
                {"message": {"content": json.dumps({"supported": True, "reason": "Matches quote"})}}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )
    result, usage = await Model(settings).complete("Check", {}, Grounding)
    assert result["supported"]
    assert usage["estimated_usd"] == pytest.approx(0.00036)


@pytest.mark.parametrize(
    "status,error",
    [(429, TransientProviderError), (500, TransientProviderError), (401, ProviderError)],
)
async def test_provider_error_classification(settings, monkeypatch, status, error):
    settings.llm_key, settings.llm_model = "test", "model"
    mock_http(monkeypatch, status, {})
    with pytest.raises(error):
        await Model(settings).complete("Check", {}, Grounding)


async def test_invalid_model_schema_rejected(settings, monkeypatch):
    settings.llm_key, settings.llm_model = "test", "model"
    mock_http(monkeypatch, 200, {"choices": [{"message": {"content": '{"admin":true}'}}]})
    with pytest.raises(ProviderError):
        await Model(settings).complete("Check", {}, Grounding)
