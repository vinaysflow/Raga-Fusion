#!/usr/bin/env python3
"""
merge_curation.py — Merge curated CSV into recording_sources.json.

By default, marks all rows as ingestible and updates/creates entries keyed by source_key.
"""

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "curation" / "all_candidates.csv"
CATALOG_PATH = PROJECT_ROOT / "data" / "recording_sources.json"


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge curated candidates into recording_sources.json")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--catalog", default=str(CATALOG_PATH))
    parser.add_argument("--rights", default="ingestible",
                        help="rights_status to set for all rows")
    parser.add_argument("--license", default="unknown",
                        help="license_type to set if missing")
    args = parser.parse_args()

    catalog = _load_json(Path(args.catalog))
    by_key = {c.get("source_key"): c for c in catalog if c.get("source_key")}

    with open(args.csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_key = row.get("source_key")
            if not source_key:
                continue
            entry = by_key.get(source_key, {})
            entry.update({
                "source_key": source_key,
                "raga": row.get("raga") or entry.get("raga"),
                "artist": row.get("artist") or entry.get("artist"),
                "title": row.get("title") or entry.get("title"),
                "performance_type": row.get("performance_type") or entry.get("performance_type"),
                "link": row.get("link") or entry.get("link"),
                "source_platform": entry.get("source_platform") or "youtube",
                "license_type": row.get("license_type") or entry.get("license_type") or args.license,
                "rights_status": args.rights,
                "collection_key": entry.get("collection_key") or row.get("collection_key"),
                "rank": entry.get("rank"),
                "tags": entry.get("tags", []),
                "download_url": row.get("download_url") or entry.get("download_url", ""),
            })
            by_key[source_key] = entry

    merged = list(by_key.values())
    merged.sort(key=lambda x: (x.get("raga") or "", x.get("source_key") or ""))
    _save_json(Path(args.catalog), merged)
    print(f"Merged {len(merged)} entries into {args.catalog}")


if __name__ == "__main__":
    main()
