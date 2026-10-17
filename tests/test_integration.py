import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentproof.db import Store
from agentproof.sandbox import DockerSandbox


@pytest.mark.postgres
def test_postgres_concurrent_claims():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    store = Store(url)
    store.migrate()
    tenant = "test-" + uuid.uuid4().hex
    for index in range(10):
        store.create(tenant, "test", "support", {}, str(index))
    with ThreadPoolExecutor(max_workers=5) as pool:
        claimed = list(pool.map(lambda _: store.claim(), range(10)))
    assert len({row["id"] for row in claimed}) == 10
    store.engine.dispose()


@pytest.mark.docker
async def test_real_sandbox(settings):
    if not shutil.which("docker") or os.getenv("RUN_DOCKER_TESTS") != "1":
        pytest.skip("Docker sandbox integration not enabled")
    settings.sandbox_enabled = True
    sandbox = DockerSandbox(settings)
    result = await sandbox.run(
        "def add(a,b): return a+b",
        "import unittest\nfrom solution import add\nclass T(unittest.TestCase):\n def test_sum(self): self.assertEqual(add(2,3),5)\n",
    )
    assert result["passed"]
