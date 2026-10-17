import pytest

from agentproof.config import Settings
from agentproof.db import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url="sqlite:///" + str(tmp_path / "test.db"),
        dev_token="test-token-not-for-deployment",
    )


@pytest.fixture
def store(settings):
    result = Store(settings.database_url)
    result.migrate()
    yield result
    result.engine.dispose()


class ScriptedModel:
    """Explicit deterministic test double; never imported by application code."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, system, data, schema):
        self.calls.append((system, data, schema))
        result = self.responses.pop(0)
        return schema.model_validate(result).model_dump(), {
            "provider": "test_double",
            "model": "scripted",
            "input_tokens": None,
            "output_tokens": None,
            "estimated_usd": None,
            "duration_ms": 0,
        }


class FakeSandbox:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    async def run(self, source, tests):
        self.calls.append((source, tests))
        passed = next(self.outcomes)
        return {
            "passed": passed,
            "exit_code": 0 if passed else 1,
            "log": "ok" if passed else "AssertionError: expected 5",
        }
