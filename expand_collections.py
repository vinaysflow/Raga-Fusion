#!/usr/bin/env python3
"""
expand_collections.py — Expand playlist/collection URLs into candidate recordings.

Uses yt-dlp to list items for collection URLs in data/source_collections.json.
Outputs a JSON list that can be curated into recording_sources.json.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
COLLECTIONS_PATH = PROJECT_ROOT / "data" / "source_collections.json"


def _load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _yt_dlp_dump(url: str) -> list[dict]:
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", url]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: yt-dlp not found. Install with: pip install yt-dlp")
        return []
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: yt-dlp failed for {url}: {exc.stderr.strip()}")
        return []

    entries = []
    for line in proc.stdout.splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def expand_collection(collection: dict, limit: int | None = None) -> list[dict]:
    url = collection.get("url")
    if not url:
        return []
    raw_entries = _yt_dlp_dump(url)
    if limit:
        raw_entries = raw_entries[:limit]

    results = []
    for entry in raw_entries:
        vid = entry.get("id")
        title = entry.get("title")
        if not vid or not title:
            continue
        results.append({
            "source_key": f"{collection.get('source_key')}_{vid}",
            "raga": collection.get("raga"),
            "artist": None,
            "title": title,
            "performance_type": None,
            "link": f"https://www.youtube.com/watch?v={vid}",
            "source_platform": "youtube",
            "license_type": "unknown",
            "rights_status": "reference_only",
            "collection_key": collection.get("source_key"),
            "rank": None,
            "tags": ["playlist_expanded"],
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand collections to candidate recordings.")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "data" / "recording_sources_expanded.json"))
    parser.add_argument("--limit", type=int, default=50, help="Limit per collection")
    parser.add_argument("--collections", nargs="*", default=None, help="Limit to these source_key values")
    args = parser.parse_args()

    collections = _load_json(COLLECTIONS_PATH)
    expanded = []
    for c in collections:
        if args.collections and c.get("source_key") not in args.collections:
            continue
        print(f"Expanding {c.get('source_key')} — {c.get('title')}")
        expanded.extend(expand_collection(c, limit=args.limit))

    with open(args.out, "w") as f:
        json.dump(expanded, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(expanded)} entries to {args.out}")


if __name__ == "__main__":
    main()
