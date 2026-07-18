#!/usr/bin/env python3
"""Phase 0 transport/turn smoke test.

``--mode fixture`` is deterministic and requires no services. ``--mode live``
uses the established live runner and the environment contract documented under
``docs/freeciv``.
"""

import argparse
import asyncio
import json
import os
import sys


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_BENCH = os.path.join(_REPO, "benchmarks")
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)


async def fixture_smoke():
    from freeciv import client, turncycle
    from freeciv.turn_cycle_fixtures import MockProxyWS

    ws = MockProxyWS(start_turn=1)
    before = await turncycle.get_state(ws)
    current = turncycle.turn_of(before)
    await turncycle.send_end_turn(ws)
    after = await turncycle.await_turn_advance(ws, current, timeout=2)
    result = {
        "mode": "fixture",
        "connect_shape": client.FreecivClient(
            "http://proxy", "ws://proxy/llmsocket/8002", "redacted", "smoke", 1
        ).connect_message(),
        "end_turn_shape": client.end_turn_message(),
        "turn_before": current,
        "turn_after": after,
        "advanced": after is not None and after > current,
    }
    result["connect_shape"]["api_token"] = "REDACTED"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    args = parser.parse_args(argv)
    if args.mode == "live":
        from freeciv import live_play
        return live_play.main()
    result = asyncio.run(fixture_smoke())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["advanced"] else 1


if __name__ == "__main__":
    sys.exit(main())

