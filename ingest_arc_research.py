#!/usr/bin/env python3
"""
ingest_arc_research.py — Ingest OpenAI/Grok arc research JSON into raga rules.

Reads research metadata (arc_profile, genre_compatibility_additions, fusion_notes)
and merges it into data/raga_rules/*.json. Then runs build_compatibility_map
and phrase_indexer to refresh downstream data.

Usage:
    python ingest_arc_research.py research.json
    python ingest_arc_research.py grok_output.json openai_output.json
    python ingest_arc_research.py research.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"

# Map research raga names to rule file stems (e.g. darbari_kanada -> darbari)
RAGA_NAME_MAP = {
    "darbari_kanada": "darbari",
}


def _raga_to_rules_stem(raga_name: str) -> str:
    """Map research raga_name to raga_rules filename stem."""
    key = raga_name.lower().strip().replace(" ", "_")
    return RAGA_NAME_MAP.get(key, key)


def _normalize_fusion_notes(raw) -> list[str]:
    """Handle fusion_notes as string or array."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(".") if s.strip()]
    if isinstance(raw, list):
        out = []
        for x in raw:
            if isinstance(x, str):
                out.append(x.strip())
            else:
                out.append(str(x))
        return [x for x in out if x]
    return []


def merge_into_rules(rules: dict, entry: dict) -> dict:
    """Merge research entry into raga rules dict. Returns modified copy."""
    out = dict(rules)

    # arc_profile: merge keys, research wins
    arc = entry.get("arc_profile")
    if arc and isinstance(arc, dict):
        existing = out.get("arc_profile") or {}
        out["arc_profile"] = {**existing, **arc}

    # genre_compatibility: merge genre_compatibility_additions
    additions = entry.get("genre_compatibility_additions")
    if additions and isinstance(additions, dict):
        existing = out.get("genre_compatibility") or {}
        for genre, val in additions.items():
            if isinstance(val, dict) and "score" in val:
                existing[genre] = {"score": float(val["score"]), "notes": val.get("notes", "")}
            elif isinstance(val, (int, float)):
                existing[genre] = {"score": float(val), "notes": ""}
        out["genre_compatibility"] = existing

    # fusion_notes: add as top-level if present
    notes = _normalize_fusion_notes(entry.get("fusion_notes"))
    if notes:
        out["fusion_notes"] = notes

    return out


def ingest_file(path: Path, rules_cache: dict, dry_run: bool) -> int:
    """Ingest one research JSON file. Returns count of ragas updated."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    updated = 0
    for entry in data:
        raga_name = entry.get("raga_name")
        if not raga_name:
            continue
        stem = _raga_to_rules_stem(raga_name)
        rules_path = RULES_DIR / f"{stem}.json"
        if not rules_path.exists():
            print(f"  SKIP {raga_name}: no rules file {rules_path.name}")
            continue
        if stem not in rules_cache:
            with open(rules_path) as rf:
                rules_cache[stem] = json.load(rf)
        merged = merge_into_rules(rules_cache[stem], entry)
        rules_cache[stem] = merged
        if not dry_run:
            with open(rules_path, "w") as rf:
                json.dump(merged, rf, indent=2, ensure_ascii=False)
        print(f"  {raga_name} -> {rules_path.name}")
        updated += 1
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest arc research JSON (OpenAI/Grok) into raga rules."
    )
    parser.add_argument("files", nargs="+", type=Path, help="Research JSON file(s)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--no-rebuild", action="store_true", help="Skip build_compatibility_map and phrase_indexer")
    args = parser.parse_args()

    RULES_DIR.mkdir(parents=True, exist_ok=True)
    rules_cache: dict[str, dict] = {}

    total = 0
    for p in args.files:
        if not p.exists():
            print(f"ERROR: file not found: {p}")
            return 1
        print(f"\nIngesting {p.name}:")
        total += ingest_file(p, rules_cache, args.dry_run)

    if total == 0:
        print("\nNo ragas updated.")
        return 0

    if args.dry_run:
        print(f"\n[DRY RUN] Would update {total} raga rule(s). Run without --dry-run to apply.")
        return 0

    if not args.no_rebuild:
        print("\nRebuilding compatibility map...")
        r1 = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "build_compatibility_map.py")],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if r1.returncode != 0:
            print(f"  WARNING: build_compatibility_map failed: {r1.stderr}")
        else:
            print("  OK")

        print("Rebuilding phrase index...")
        r2 = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "phrase_indexer.py"), "--force"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if r2.returncode != 0:
            print(f"  WARNING: phrase_indexer failed: {r2.stderr}")
        else:
            print("  OK")

    print(f"\nDone. Updated {total} raga rule(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
