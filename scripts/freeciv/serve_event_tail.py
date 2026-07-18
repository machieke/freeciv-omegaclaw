#!/usr/bin/env python3
"""Serve a canonical persisted event log over the read-only V5 protocol."""

import argparse
import asyncio
import json

from websockets import serve

from freeciv_agent.events import PersistedEventTail


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, help="append-only canonical JSONL path")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--poll-ms", type=float, default=50.0)
    parser.add_argument("--max-batch", type=int, default=256)
    return parser.parse_args()


async def run(args):
    tail = PersistedEventTail(
        args.events, args.game_id, poll_interval=args.poll_ms / 1000.0,
        max_batch=args.max_batch)
    async with serve(tail.handler, args.host, args.port, max_size=2 ** 22):
        print(json.dumps({
            "status": "ready", "endpoint": "ws://{}:{}".format(args.host, args.port),
            "events": tail.path, "game_id": tail.game_id,
            "schema_version": tail.schema_version, "persisted_first": True,
        }, sort_keys=True), flush=True)
        await asyncio.get_running_loop().create_future()


def main():
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
