import asyncio
import time

from .telemetry import tracer


class BudgetExceeded(RuntimeError):
    pass


class Context:
    def __init__(self, store, row, model, search, sandbox, settings):
        self.store, self.row, self.model = store, row, model
        self.search, self.sandbox, self.settings = search, sandbox, settings
        self.id, self.token = row["id"], row["lease_token"]
        self.cache = dict(row["checkpoint"])
        self.lock = asyncio.Lock()

    async def step(self, name, fn):
        if name in self.cache:
            return self.cache[name]
        self.store.heartbeat(self.id, self.token, self.settings.lease_seconds)
        with tracer.start_as_current_span(name, attributes={"run.id": self.id}):
            started = time.perf_counter()
            result = await fn()
            self.store.checkpoint(self.id, self.token, name, result)
            self.cache[name] = result
            self.store.emit(
                self.id,
                self.token,
                "step",
                {"name": name, "duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )
            return result

    async def ask(self, name, system, data, schema):
        async def invoke():
            # Serialized reservations survive restart and are conservative if a worker dies pre-call.
            async with self.lock:
                calls = self.cache.get("_model_calls", 0) + 1
                if calls > self.settings.max_model_calls:
                    raise BudgetExceeded("Maximum model calls reached")
                self.store.checkpoint(self.id, self.token, "_model_calls", calls)
                self.cache["_model_calls"] = calls
            result, usage = await self.model.complete(system, data, schema)
            self.store.emit(self.id, self.token, "model_usage", {"step": name, **usage})
            return result

        return await self.step(name, invoke)

    def emit(self, kind, data):
        self.store.emit(self.id, self.token, kind, data)
