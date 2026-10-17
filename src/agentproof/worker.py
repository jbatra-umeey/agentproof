import asyncio
import logging
import signal

from .agents import WORKFLOWS
from .config import Settings
from .db import LostLease, Store
from .providers import Model, Search, TransientProviderError
from .runtime import Context
from .sandbox import DockerSandbox
from .telemetry import configure, tracer

logger = logging.getLogger("agentproof.worker")


async def execute(store, row, settings, model=None, search=None, sandbox=None):
    ctx = Context(
        store,
        row,
        model or Model(settings),
        search or Search(settings.tavily_key),
        sandbox or DockerSandbox(settings),
        settings,
    )

    async def work():
        with tracer.start_as_current_span(
            "agent.run", attributes={"run.id": row["id"], "agent.kind": row["kind"]}
        ):
            result = await WORKFLOWS[row["kind"]](ctx, row["payload"])
            waiting = result.pop("_waiting", False)
            store.finish(row["id"], row["lease_token"], result, waiting)

    async def heartbeat():
        while True:
            await asyncio.sleep(max(1, settings.lease_seconds // 3))
            store.heartbeat(row["id"], row["lease_token"], settings.lease_seconds)

    task, beat = asyncio.create_task(work()), asyncio.create_task(heartbeat())
    try:
        done, _ = await asyncio.wait(
            [task, beat], timeout=settings.run_timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            raise TimeoutError("Run deadline exceeded")
        for completed in done:
            completed.result()
    except LostLease:
        logger.info("Lease lost", extra={"run_id": row["id"]})
    except Exception as exc:
        try:
            store.fail(
                row["id"],
                row["lease_token"],
                type(exc).__name__,
                isinstance(exc, TransientProviderError),
                settings.max_attempts,
            )
        except LostLease:
            pass
        logger.warning("Run failed: %s", type(exc).__name__, extra={"run_id": row["id"]})
    finally:
        for pending in (task, beat):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, beat, return_exceptions=True)


async def serve(kinds):
    settings = Settings()
    settings.validate()
    configure()
    store = Store(settings.database_url)
    if not store.ready():
        raise RuntimeError("Run migrations before starting workers")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    model, search, sandbox = Model(settings), Search(settings.tavily_key), DockerSandbox(settings)
    while not stop.is_set():
        row = store.claim(settings.lease_seconds, settings.max_attempts, kinds)
        if row:
            await execute(store, row, settings, model, search, sandbox)
        else:
            try:
                await asyncio.wait_for(stop.wait(), 1)
            except TimeoutError:
                pass
    store.engine.dispose()
