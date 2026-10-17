import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .auth import authenticator
from .config import Settings
from .db import Capacity, Conflict, Store
from .schemas import Approval, CreateRun

REQUESTS = Counter("agentproof_http_requests_total", "HTTP requests", ["method", "status"])
LATENCY = Histogram("agentproof_http_duration_seconds", "HTTP latency")


def public_run(row):
    return {
        k: v
        for k, v in row.items()
        if k not in ("lease_token", "checkpoint", "payload_hash", "idem_key")
    }


def create_app(settings=None, store=None):
    settings = settings or Settings()
    settings.validate()
    store = store or Store(settings.database_url)
    app = FastAPI(title="AgentProof", version="0.1.0")
    auth = authenticator(settings)
    app.state.store, app.state.auth = store, auth

    @app.middleware("http")
    async def boundaries(request, call_next):
        # Read and cap actual bytes, including requests with no Content-Length.
        if request.method in ("POST", "PUT", "PATCH"):
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 100000:
                    return Response("Request too large", status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        started = time.perf_counter()
        response = await call_next(request)
        REQUESTS.labels(request.method, str(response.status_code)).inc()
        LATENCY.observe(time.perf_counter() - started)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
        )
        return response

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            if store.ready():
                return {"status": "ready"}
        except Exception:
            pass
        raise HTTPException(503, "Database schema unavailable")

    @app.get("/metrics")
    def metrics(principal=Depends(auth)):
        if "operator" not in principal.roles:
            raise HTTPException(403, "Operator role required")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/runs", status_code=202)
    def create(
        body: CreateRun,
        idempotency_key: str = Header(min_length=8, max_length=128),
        principal=Depends(auth),
    ):
        try:
            row, created = store.create(
                principal.tenant,
                principal.subject,
                body.kind,
                body.payload,
                idempotency_key,
                settings.max_active_per_tenant,
            )
            return {"run": public_run(row), "created": created}
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except Capacity as exc:
            raise HTTPException(429, str(exc)) from None

    @app.get("/v1/runs")
    def list_runs(principal=Depends(auth)):
        return [public_run(row) for row in store.list(principal.tenant)]

    def owned(run_id, principal):
        row = store.get(run_id, principal.tenant)
        if not row:
            raise HTTPException(404, "Run not found")
        return row

    @app.get("/v1/runs/{run_id}")
    def get(run_id: str, principal=Depends(auth)):
        return public_run(owned(run_id, principal))

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel(run_id: str, principal=Depends(auth)):
        owned(run_id, principal)
        try:
            store.cancel(run_id, principal.tenant)
            return {"status": "cancelled"}
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/v1/runs/{run_id}/approval")
    def approve(run_id: str, body: Approval, principal=Depends(auth)):
        if "refund_approver" not in principal.roles:
            raise HTTPException(403, "Refund approver role required")
        owned(run_id, principal)
        try:
            store.decide(run_id, principal.tenant, principal.subject, body.decision, body.reason)
            return {"status": "queued"}
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/v1/runs/{run_id}/traces")
    def trace(run_id: str, after: int = 0, principal=Depends(auth)):
        owned(run_id, principal)
        return {
            "events": store.event_list(run_id, after),
            "pagination": "Use last event id as after",
        }

    @app.get("/v1/runs/{run_id}/events")
    async def stream(
        run_id: str,
        request: Request,
        after: int = 0,
        last_event_id: int | None = Header(default=None),
        principal=Depends(auth),
    ):
        owned(run_id, principal)

        async def generate():
            cursor, deadline = max(after, last_event_id or 0), time.monotonic() + 60
            while time.monotonic() < deadline and not await request.is_disconnected():
                batch = store.event_list(run_id, cursor)
                for e in batch:
                    cursor = e["id"]
                    yield f"id: {cursor}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
                row = store.get(run_id, principal.tenant)
                if not batch and row["status"] in ("succeeded", "failed", "cancelled", "waiting"):
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    web = Path(os.getenv("WEB_DIR", "web"))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web / "index.html")

    @app.get("/app.js", include_in_schema=False)
    def js():
        return FileResponse(web / "app.js", media_type="text/javascript")

    @app.get("/style.css", include_in_schema=False)
    def css():
        return FileResponse(web / "style.css", media_type="text/css")

    return app
