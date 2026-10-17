"""SQL-backed queue, fencing leases and atomic business state transitions."""

import hashlib
import json
import time
import uuid
from contextlib import contextmanager

from sqlalchemy import (
    JSON,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("tenant", String(128), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("idem_key", String(128), nullable=False),
    Column("status", String(20), nullable=False),
    Column("created", Float, nullable=False),
    Column("updated", Float, nullable=False),
    Column("available", Float, nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("lease_token", String(36)),
    Column("attempt", Integer, nullable=False),
    Column("checkpoint", JSON, nullable=False),
    Column("result", JSON),
    Column("error", String(100)),
    UniqueConstraint("tenant", "idem_key", name="uq_runs_idempotency"),
)
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("created", Float, nullable=False),
    Column("type", String(40), nullable=False),
    Column("data", JSON, nullable=False),
)
approvals = Table(
    "approvals",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("actor", String(128), nullable=False),
    Column("decision", String(10), nullable=False),
    Column("reason", String(500), nullable=False),
    Column("created", Float, nullable=False),
)
refunds = Table(
    "refunds",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("tenant", String(128), nullable=False),
    Column("order_id", String(80), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("status", String(40), nullable=False),
    Column("created", Float, nullable=False),
)
tenants = Table("tenant_locks", metadata, Column("id", String(128), primary_key=True))
versions = Table("schema_versions", metadata, Column("version", Integer, primary_key=True))
Index("ix_runs_claim", runs.c.status, runs.c.available, runs.c.created)
Index("ix_runs_tenant", runs.c.tenant, runs.c.created)


class LostLease(RuntimeError):
    pass


class Conflict(ValueError):
    pass


class Capacity(ValueError):
    pass


class Store:
    def __init__(self, url):
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
        )
        self.sqlite = self.engine.dialect.name == "sqlite"
        if self.sqlite:

            @event.listens_for(self.engine, "connect")
            def configure(dbapi_connection, _):
                dbapi_connection.execute("PRAGMA journal_mode=WAL")

    def migrate(self):
        # Initial migration only. Later schema changes must use versioned migration scripts.
        metadata.create_all(self.engine)
        with self.tx() as c:
            if c.execute(select(versions.c.version)).first() is None:
                c.execute(versions.insert().values(version=1))

    def ready(self):
        with self.engine.connect() as c:
            return c.execute(select(versions.c.version)).scalar_one() == 1

    @contextmanager
    def tx(self):
        with self.engine.connect() as c:
            if self.sqlite:
                c.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                c.begin()
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def _event(self, c, run_id, kind, data):
        c.execute(events.insert().values(run_id=run_id, created=time.time(), type=kind, data=data))

    def create(self, tenant, actor, kind, payload, key, limit=20):
        digest = hashlib.sha256(json.dumps([kind, payload], sort_keys=True).encode()).hexdigest()
        # Insert tenant sentinel independently so a unique collision cannot abort the main tx.
        try:
            with self.tx() as c:
                c.execute(tenants.insert().values(id=tenant))
        except IntegrityError:
            pass
        with self.tx() as c:
            c.execute(select(tenants).where(tenants.c.id == tenant).with_for_update()).first()
            prior = (
                c.execute(select(runs).where(runs.c.tenant == tenant, runs.c.idem_key == key))
                .mappings()
                .first()
            )
            if prior:
                if prior["payload_hash"] != digest:
                    raise Conflict("Idempotency key used for a different request")
                return dict(prior), False
            active = c.execute(
                select(runs.c.id).where(
                    runs.c.tenant == tenant, runs.c.status.in_(["queued", "running", "waiting"])
                )
            ).all()
            if len(active) >= limit:
                raise Capacity("Tenant active-run capacity reached")
            now = time.time()
            row = dict(
                id=str(uuid.uuid4()),
                tenant=tenant,
                actor=actor,
                kind=kind,
                payload=payload,
                payload_hash=digest,
                idem_key=key,
                status="queued",
                created=now,
                updated=now,
                available=now,
                lease_until=0,
                lease_token=None,
                attempt=0,
                checkpoint={},
                result=None,
                error=None,
            )
            c.execute(runs.insert().values(**row))
            self._event(c, row["id"], "queued", {"kind": kind})
            return row, True

    def get(self, run_id, tenant=None):
        q = select(runs).where(runs.c.id == run_id)
        if tenant is not None:
            q = q.where(runs.c.tenant == tenant)
        with self.engine.connect() as c:
            row = c.execute(q).mappings().first()
            return dict(row) if row else None

    def list(self, tenant):
        with self.engine.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(runs)
                    .where(runs.c.tenant == tenant)
                    .order_by(runs.c.created.desc())
                    .limit(100)
                ).mappings()
            ]

    def claim(self, lease_seconds=120, max_attempts=3, kinds=None):
        now = time.time()
        with self.tx() as c:
            eligible = or_(
                (runs.c.status == "queued") & (runs.c.available <= now),
                (runs.c.status == "running") & (runs.c.lease_until < now),
            )
            q = (
                select(runs)
                .where(eligible)
                .order_by(runs.c.created)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if kinds:
                q = q.where(runs.c.kind.in_(kinds))
            row = c.execute(q).mappings().first()
            if not row:
                return None
            if row["attempt"] >= max_attempts:
                c.execute(
                    update(runs)
                    .where(runs.c.id == row["id"])
                    .values(status="failed", error="AttemptsExhausted", updated=now)
                )
                self._event(c, row["id"], "failed", {"code": "AttemptsExhausted"})
                return None
            token = str(uuid.uuid4())
            values = dict(
                status="running",
                lease_token=token,
                lease_until=now + lease_seconds,
                attempt=row["attempt"] + 1,
                updated=now,
            )
            c.execute(update(runs).where(runs.c.id == row["id"]).values(**values))
            self._event(c, row["id"], "claimed", {"attempt": values["attempt"]})
            return dict(row) | values

    def _owned(self, c, run_id, token):
        row = c.execute(select(runs).where(runs.c.id == run_id).with_for_update()).mappings().one()
        if (
            row["status"] != "running"
            or row["lease_token"] != token
            or row["lease_until"] < time.time()
        ):
            raise LostLease(run_id)
        return row

    def heartbeat(self, run_id, token, lease_seconds):
        with self.tx() as c:
            self._owned(c, run_id, token)
            c.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(lease_until=time.time() + lease_seconds)
            )

    def checkpoint(self, run_id, token, key, value):
        with self.tx() as c:
            row = self._owned(c, run_id, token)
            cp = dict(row["checkpoint"])
            cp[key] = value
            c.execute(
                update(runs).where(runs.c.id == run_id).values(checkpoint=cp, updated=time.time())
            )
            self._event(c, run_id, "checkpoint", {"step": key})

    def emit(self, run_id, token, kind, data):
        with self.tx() as c:
            self._owned(c, run_id, token)
            self._event(c, run_id, kind, data)

    def finish(self, run_id, token, result, waiting=False):
        with self.tx() as c:
            self._owned(c, run_id, token)
            status = "waiting" if waiting else "succeeded"
            c.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    status=status,
                    result=result,
                    lease_token=None,
                    lease_until=0,
                    updated=time.time(),
                    error=None,
                )
            )
            self._event(c, run_id, status, {"status": status})

    def fail(self, run_id, token, error_code, retry=False, max_attempts=3):
        with self.tx() as c:
            row = self._owned(c, run_id, token)
            status = "queued" if retry and row["attempt"] < max_attempts else "failed"
            c.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    status=status,
                    error=error_code,
                    lease_token=None,
                    lease_until=0,
                    available=time.time() + 2 ** row["attempt"],
                    updated=time.time(),
                )
            )
            self._event(c, run_id, status, {"code": error_code})

    def decide(self, run_id, tenant, actor, decision, reason):
        with self.tx() as c:
            row = (
                c.execute(
                    select(runs)
                    .where(runs.c.id == run_id, runs.c.tenant == tenant)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row:
                raise KeyError(run_id)
            if row["status"] != "waiting" or row["kind"] != "support":
                raise Conflict("Run is not awaiting approval")
            if row["actor"] == actor:
                raise Conflict("Refund requester cannot approve their own request")
            c.execute(
                approvals.insert().values(
                    run_id=run_id,
                    actor=actor,
                    decision=decision,
                    reason=reason,
                    created=time.time(),
                )
            )
            c.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(status="queued", attempt=0, available=time.time(), updated=time.time())
            )
            self._event(c, run_id, "approval", {"decision": decision, "actor": actor})

    def approval(self, run_id):
        with self.engine.connect() as c:
            row = (
                c.execute(select(approvals).where(approvals.c.run_id == run_id)).mappings().first()
            )
            return dict(row) if row else None

    def record_refund(self, run_id, token):
        # Local ledger only: no payment provider is called, and status never says money moved.
        with self.tx() as c:
            row = self._owned(c, run_id, token)
            approval = (
                c.execute(select(approvals).where(approvals.c.run_id == run_id)).mappings().first()
            )
            if not approval or approval["decision"] != "approved":
                raise Conflict("Approved human decision required")
            existing = (
                c.execute(select(refunds).where(refunds.c.run_id == run_id)).mappings().first()
            )
            if existing:
                return dict(existing)
            payload = row["payload"]
            if not payload.get("order_id") or not payload.get("refund_cents"):
                raise Conflict("Refund order and amount required")
            entry = dict(
                run_id=run_id,
                tenant=row["tenant"],
                order_id=payload["order_id"],
                amount_cents=payload["refund_cents"],
                status="approved_pending_payment_integration",
                created=time.time(),
            )
            c.execute(refunds.insert().values(**entry))
            self._event(c, run_id, "refund_recorded", {"status": entry["status"]})
            return entry

    def event_list(self, run_id, after=0):
        with self.engine.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    select(events)
                    .where(events.c.run_id == run_id, events.c.id > after)
                    .order_by(events.c.id)
                    .limit(500)
                ).mappings()
            ]

    def cancel(self, run_id, tenant):
        with self.tx() as c:
            row = (
                c.execute(
                    select(runs)
                    .where(runs.c.id == run_id, runs.c.tenant == tenant)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row:
                raise KeyError(run_id)
            if row["status"] not in ("queued", "running", "waiting"):
                raise Conflict("Run already terminal")
            c.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(status="cancelled", lease_token=None, lease_until=0, updated=time.time())
            )
            self._event(c, run_id, "cancelled", {})
