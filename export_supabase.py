#!/usr/bin/env python3
"""
export_supabase.py — Export catalog JSON to Supabase-ready CSV.
"""

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
COLLECTIONS_PATH = PROJECT_ROOT / "data" / "source_collections.json"
SOURCES_PATH = PROJECT_ROOT / "data" / "recording_sources.json"


def _load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def export_collections(out_path: Path, collections: list[dict]) -> None:
    fields = [
        "source_key",
        "raga",
        "title",
        "url",
        "source_platform",
        "license_type",
        "rights_status",
        "expected_count",
        "notes",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for c in collections:
            writer.writerow({k: c.get(k) for k in fields})


def export_sources(out_path: Path, sources: list[dict]) -> None:
    fields = [
        "source_key",
        "raga",
        "artist",
        "title",
        "performance_type",
        "link",
        "source_platform",
        "duration_sec",
        "license_type",
        "rights_status",
        "collection_id",
        "rank",
        "tags",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in sources:
            tags = {}
            if isinstance(s.get("tags"), list):
                tags = {"tags": s.get("tags")}
            elif isinstance(s.get("tags"), dict):
                tags = s.get("tags", {})
            if s.get("collection_key"):
                tags["collection_key"] = s.get("collection_key")
            row = {k: s.get(k) for k in fields}
            row["collection_id"] = ""
            row["tags"] = json.dumps(tags, ensure_ascii=False)
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export source catalogs to CSV for Supabase.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data"),
                        help="Output directory for CSV files")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    collections = _load_json(COLLECTIONS_PATH)
    sources = _load_json(SOURCES_PATH)

    export_collections(out_dir / "supabase_source_collections.csv", collections)
    export_sources(out_dir / "supabase_recording_sources.csv", sources)

    print("Exported:")
    print(f"  {out_dir / 'supabase_source_collections.csv'}")
    print(f"  {out_dir / 'supabase_recording_sources.csv'}")


if __name__ == "__main__":
    main()
