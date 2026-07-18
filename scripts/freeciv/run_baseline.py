#!/usr/bin/env python3
"""Run M7 condition (a), the existing plain-LLM FreeCiv agent, with a manifest.

The runner deliberately delegates game behavior to ``freeciv.ab_sim``.  It adds
reproducibility and artifact lifecycle without changing the proven transport,
prompt, action validation, or turn-cycle behavior.
"""

import argparse
import asyncio
import json
import os
import sys
import time


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_SRC = os.path.join(_REPO, "src")
_BENCH = os.path.join(_REPO, "benchmarks")
for _path in (_SRC, _BENCH):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from freeciv_agent.manifest import (  # noqa: E402
    build_manifest, external_git_commit, write_manifest,
)
import provider_config  # noqa: E402


def _atomic_json(path, value):
    tmp = path + ".tmp.{}".format(os.getpid())
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(tmp, path)


def _dependency_identity(args):
    discovered = external_git_commit(args.freeciv_llm_root)
    freeciv_commit = args.freeciv_commit or discovered
    proxy_commit = args.proxy_commit or discovered
    if not ((freeciv_commit and proxy_commit) or args.engine_image_digest):
        raise ValueError(
            "baseline runs require pinned FreeCiv/proxy commits or --engine-image-digest; "
            "set FREECIV_LLM_ROOT for source discovery")
    return freeciv_commit, proxy_commit


def prepare_run(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    if os.path.exists(os.path.join(out, "manifest.json")) and not args.resume:
        raise ValueError("run already has a manifest; pass --resume or choose a new --out")
    freeciv_commit, proxy_commit = _dependency_identity(args)
    provider = provider_config.provider_entry(args.provider)
    manifest = build_manifest(
        condition_id="a_stock_llm",
        game_id=args.game_id,
        seed=args.seed,
        ruleset=args.ruleset,
        turn_limit=args.max_turns,
        provider=args.provider,
        model=provider["model"],
        base_url=provider["base_url"],
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        opponent=args.opponent,
        difficulty=args.difficulty,
        freeciv_commit=freeciv_commit,
        proxy_commit=proxy_commit,
        engine_image_digest=args.engine_image_digest,
    )
    write_manifest(os.path.join(out, "manifest.json"), manifest)
    _atomic_json(os.path.join(out, "run_status.json"), {
        "status": "prepared",
        "condition": "a_stock_llm",
        "manifest_identity": manifest["manifest_identity"],
    })
    return out, manifest


async def _run_live(args, out):
    os.environ["FREECIV_GAME_ID"] = args.game_id
    from freeciv import ab_sim
    return await ab_sim.run("plain", args.seed, args.hours, args.max_turns, out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="run the reproducible stock FreeCiv baseline")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("--ruleset", default="civ2civ3")
    parser.add_argument("--provider", default=os.environ.get("FREECIV_PROVIDER", "Ollama-local"))
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--opponent", default="builtin-ai")
    parser.add_argument("--difficulty", default="normal")
    parser.add_argument("--freeciv-llm-root", default=os.environ.get("FREECIV_LLM_ROOT"))
    parser.add_argument("--freeciv-commit")
    parser.add_argument("--proxy-commit")
    parser.add_argument("--engine-image-digest")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--prepare-only", action="store_true",
                        help="write and validate the manifest without connecting to a game")
    args = parser.parse_args(argv)

    try:
        out, manifest = prepare_run(args)
    except Exception as exc:  # noqa: BLE001 - CLI emits a concise structured failure
        print("baseline preparation failed: {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "out": out,
                          "manifest_identity": manifest["manifest_identity"]}, sort_keys=True))
        return 0

    started = time.time()
    try:
        rc = asyncio.run(_run_live(args, out))
        status = "completed" if rc == 0 else "failed"
    except Exception as exc:  # noqa: BLE001
        rc = 1
        status = "failed"
        _atomic_json(os.path.join(out, "failure.json"), {
            "type": type(exc).__name__, "message": str(exc)[:1000],
        })
    _atomic_json(os.path.join(out, "run_status.json"), {
        "status": status,
        "condition": "a_stock_llm",
        "manifest_identity": manifest["manifest_identity"],
        "elapsed_seconds": round(time.time() - started, 3),
        "exit_code": rc,
    })
    return rc


if __name__ == "__main__":
    sys.exit(main())

