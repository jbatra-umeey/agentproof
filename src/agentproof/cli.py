import argparse
import asyncio
import json

from .config import Settings
from .db import Store


def main():
    parser = argparse.ArgumentParser(prog="agentproof")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("api")
    worker = sub.add_parser("worker")
    worker.add_argument(
        "--kinds",
        nargs="+",
        choices=["research", "codefix", "support", "reports"],
        default=["research", "support", "reports"],
    )
    export = sub.add_parser("export")
    export.add_argument("run_id")
    args = parser.parse_args()
    if args.command == "migrate":
        Store(Settings().database_url).migrate()
    elif args.command == "api":
        import uvicorn

        uvicorn.run("agentproof.api:create_app", factory=True, host="0.0.0.0", port=8000)
    elif args.command == "worker":
        from .worker import serve

        asyncio.run(serve(args.kinds))
    else:
        store = Store(Settings().database_url)
        row = store.get(args.run_id)
        if row is None:
            raise SystemExit("Unknown run")
        cursor, trace = 0, []
        while batch := store.event_list(args.run_id, cursor):
            trace.extend(batch)
            cursor = batch[-1]["id"]
        print(
            json.dumps(
                {"run": {k: v for k, v in row.items() if k != "lease_token"}, "events": trace},
                indent=2,
            )
        )
