"""Inject lease expiry and demonstrate recovery/fencing without calling an LLM."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import update
from agentproof.db import Store, LostLease, runs


def main():
    timeline = []

    def record(event, **details):
        timeline.append({"at": datetime.now(timezone.utc).isoformat(), "event": event, **details})

    with tempfile.TemporaryDirectory() as directory:
        store = Store("sqlite:///" + directory + "/drill.db")
        store.migrate()
        job, _ = store.create(
            "drill", "operator", "research", {"question": "Lease recovery drill"}, "drill-001"
        )
        original = store.claim()
        store.checkpoint(
            job["id"], original["lease_token"], "retrieved", {"evidence": "Checkpoint survives"}
        )
        record("worker_A_checkpointed", run_id=job["id"])
        with store.tx() as c:
            c.execute(update(runs).where(runs.c.id == job["id"]).values(lease_until=0))
        record("fault_injected", action="Expired active lease to model missed heartbeat")
        recovered = store.claim()
        assert recovered["checkpoint"]["retrieved"]["evidence"] == "Checkpoint survives"
        record("worker_B_reclaimed", attempt=recovered["attempt"])
        try:
            store.finish(job["id"], original["lease_token"], {"stale": True})
            raise AssertionError("Stale worker unexpectedly committed")
        except LostLease:
            record("worker_A_fenced", stale_commit_rejected=True)
        store.finish(job["id"], recovered["lease_token"], {"recovered": True})
        record("recovery_complete", status=store.get(job["id"])["status"])
        evidence = {
            "type": "local_fault_injection_not_production_incident",
            "timeline": timeline,
            "events": store.event_list(job["id"]),
        }
        store.engine.dispose()
    path = Path("evals/results/incident-drill.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"recovered": True, "stale_commit_rejected": True, "artifact": str(path)}))


if __name__ == "__main__":
    main()
