#!/usr/bin/env python3
"""
Smoke test: generation pipeline via API.

Usage:
  python tests/smoke_generate_flow.py --raga yaman --genre lofi --duration 30
"""

from __future__ import annotations

import argparse
import json
import time
from urllib import request


def request_json(method: str, url: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=headers)
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generation smoke test.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--raga", default="yaman")
    parser.add_argument("--genre", default="lofi")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--source", default="library")
    parser.add_argument("--prompt", default="Calm evening meditation")
    args = parser.parse_args()

    payload = {
        "raga": args.raga,
        "genre": args.genre,
        "duration": args.duration,
        "source": args.source,
        "prompt": args.prompt,
    }
    resp = request_json("POST", f"{args.base_url}/api/generate", payload)
    track_id = resp.get("track_id")
    if not track_id:
        raise SystemExit("No track_id returned")

    for _ in range(60):
        status = request_json("GET", f"{args.base_url}/api/status/{track_id}")
        if status.get("status") == "complete":
            print("Generated:", track_id)
            return
        if status.get("status") == "error":
            raise SystemExit(status.get("error") or "Generation failed")
        time.sleep(2)

    raise SystemExit("Generation did not complete in time")


if __name__ == "__main__":
    main()
