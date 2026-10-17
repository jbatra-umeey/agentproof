import hmac
import re
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant: str
    subject: str
    roles: frozenset[str]


def authenticator(settings):
    jwks = (
        jwt.PyJWKClient(settings.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)
        if settings.jwks_url
        else None
    )

    def auth(credential: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credential is None:
            raise HTTPException(401, "Bearer token required")
        token = credential.credentials
        if (
            settings.environment != "production"
            and settings.dev_token
            and hmac.compare_digest(token, settings.dev_token)
        ):
            return Principal("development", "developer", frozenset({"operator"}))
        if jwks is None:
            raise HTTPException(401, "Invalid token")
        try:
            key = jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                options={"require": ["exp", "iat", "sub", "tenant_id"]},
            )
            tenant, subject = claims["tenant_id"], claims["sub"]
            roles = claims.get("roles", [])
            if not isinstance(tenant, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", tenant):
                raise ValueError("Invalid tenant")
            if not isinstance(subject, str) or not 1 <= len(subject) <= 128:
                raise ValueError("Invalid subject")
            if not isinstance(roles, list) or any(not isinstance(x, str) for x in roles):
                raise ValueError("Invalid roles")
            return Principal(tenant, subject, frozenset(roles))
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise HTTPException(401, "Invalid token") from None

    return auth
