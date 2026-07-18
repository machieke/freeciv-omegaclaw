#!/usr/bin/env python3
"""Live smoke for the configured Ollama constrained-JSON transport."""

import argparse
import json
import os
import sys
import urllib.request


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for path in (os.path.join(REPO, "src"),):
    if path not in sys.path:
        sys.path.insert(0, path)

import provider_config  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="Ollama-local")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    provider = provider_config.provider_entry(args.provider)
    if not provider:
        raise SystemExit("unknown provider")
    payload = {
        "model": provider["model"], "temperature": 0,
        "messages": [{"role": "user", "content": (
            "Return only this JSON object with no markdown: "
            "{\"schema_version\":\"1.0\",\"status\":\"ok\"}")}],
    }
    request = urllib.request.Request(
        provider["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"})
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        value = json.load(response)
    content = value["choices"][0]["message"]["content"].strip()
    parsed = json.loads(content)
    if parsed != {"schema_version": "1.0", "status": "ok"}:
        raise SystemExit("unexpected model response: {}".format(content[:500]))
    print(json.dumps({"model": provider["model"], "response": parsed, "valid": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
