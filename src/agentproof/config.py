import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///agentproof.db")
    )
    dev_token: str = field(default_factory=lambda: os.getenv("DEV_API_TOKEN", ""))
    jwt_issuer: str = field(default_factory=lambda: os.getenv("JWT_ISSUER", ""))
    jwt_audience: str = field(default_factory=lambda: os.getenv("JWT_AUDIENCE", "agentproof"))
    jwks_url: str = field(default_factory=lambda: os.getenv("JWKS_URL", ""))
    llm_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    llm_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    tavily_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    input_price: float | None = field(default_factory=lambda: _price("LLM_INPUT_USD_PER_MILLION"))
    output_price: float | None = field(default_factory=lambda: _price("LLM_OUTPUT_USD_PER_MILLION"))
    lease_seconds: int = 120
    max_attempts: int = 3
    max_active_per_tenant: int = 20
    max_model_calls: int = 24
    run_timeout: int = 600
    sandbox_image: str = field(
        default_factory=lambda: os.getenv("SANDBOX_IMAGE", "python:3.12-slim")
    )
    sandbox_enabled: bool = field(default_factory=lambda: os.getenv("SANDBOX_ENABLED") == "true")

    def validate(self):
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if self.dev_token or not self.jwt_issuer or not self.jwks_url.startswith("https://"):
                raise ValueError("Production requires OIDC/JWKS and disables development tokens")
            if not self.llm_url.startswith("https://"):
                raise ValueError("Production model endpoint requires HTTPS")
        elif not self.dev_token and not self.jwks_url:
            raise ValueError("Set a random DEV_API_TOKEN or configure OIDC")


def _price(key):
    value = os.getenv(key)
    if value is None:
        return None
    price = float(value)
    if price < 0:
        raise ValueError("Token prices must be non-negative")
    return price
