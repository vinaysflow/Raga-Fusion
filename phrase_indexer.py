#!/usr/bin/env python3
"""
phrase_indexer.py — Offline phrase index builder.

Scans all phrase libraries under data/phrases/, scores each phrase against
its raga's rules using RagaScorer, and produces a global index file
(data/phrase_index.json) that the recommendation engine consumes.

The index contains enriched phrase metadata with authenticity scores,
feature vectors, and style affinity priors.

Usage:
    python phrase_indexer.py                          # build full index
    python phrase_indexer.py --ragas yaman bhairavi   # index only these ragas
    python phrase_indexer.py --force                  # rebuild even if up-to-date

This is meant to run offline (or on server startup when stale).
"""

import argparse
import json
import sys
import time
from pathlib import Path

from raga_scorer import RagaScorer

try:
    from backfill_intent_tags import derive_intent_tags
except ImportError:
    def derive_intent_tags(_: dict) -> list:
        return []

PROJECT_ROOT = Path(__file__).resolve().parent
PHRASES_DIR = PROJECT_ROOT / "data" / "phrases"
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"
STYLES_PATH = PROJECT_ROOT / "data" / "styles.json"
INDEX_PATH = PROJECT_ROOT / "data" / "phrase_index.json"


def _detect_source_type(lib_name: str) -> str:
    return "generated" if lib_name.endswith("_generated") else "library"


def _raga_from_lib_name(lib_name: str) -> str:
    name = lib_name.replace("_generated", "")
    if name.endswith("_gold"):
        name = name[: -len("_gold")]
    return name


def _load_styles() -> dict:
    try:
        with open(STYLES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def build_index(ragas: list[str] | None = None, force: bool = False) -> dict:
    """Build the global phrase index.

    Returns the index dict with structure:
    {
        "built_at": <iso timestamp>,
        "ragas": {
            "<raga>": {
                "rules_file": "...",
                "phrases": [ { ...enriched metadata... }, ... ]
            }
        },
        "stats": { "total_phrases": N, "ragas_indexed": M }
    }
    """
    if not force and INDEX_PATH.exists():
        with open(INDEX_PATH) as f:
            existing = json.load(f)
        stale = _check_staleness(existing)
        if not stale:
            print("  Index is up-to-date. Use --force to rebuild.")
            return existing

    styles = _load_styles()
    style_names = list(styles.keys())

    index: dict = {"built_at": "", "ragas": {}, "stats": {}}
    total_phrases = 0

    lib_dirs = sorted(PHRASES_DIR.iterdir()) if PHRASES_DIR.exists() else []

    for lib_dir in lib_dirs:
        if not lib_dir.is_dir():
            continue
        meta_path = lib_dir / "phrases_metadata.json"
        if not meta_path.exists():
            continue

        raga = _raga_from_lib_name(lib_dir.name)
        source_type = _detect_source_type(lib_dir.name)

        if ragas and raga not in ragas:
            continue

        rules_path = RULES_DIR / f"{raga}.json"
        if not rules_path.exists():
            print(f"  WARNING: no rules for raga '{raga}', skipping {lib_dir.name}")
            continue

        scorer = RagaScorer.from_rules_file(rules_path)

        with open(meta_path) as f:
            phrases_raw = json.load(f)

        if raga not in index["ragas"]:
            index["ragas"][raga] = {
                "rules_file": str(rules_path.relative_to(PROJECT_ROOT)),
                "phrases": [],
            }

        for p in phrases_raw:
            enriched = scorer.score_phrase(p)

            raw_source = p.get("source_type", "")
            if raw_source == "rod_dataset":
                enriched["source_type"] = "rod_dataset"
            else:
                enriched["source_type"] = source_type

            enriched["library_dir"] = str(lib_dir.relative_to(PROJECT_ROOT))

            if raw_source == "rod_dataset" and p.get("ground_truth_ornaments"):
                enriched["ornaments_source"] = "ground_truth"
            else:
                enriched["ornaments_source"] = "heuristic"

            style_affinities = {}
            for sname in style_names:
                style_affinities[sname] = round(scorer.style_affinity(sname), 3)
            enriched["style_affinities"] = style_affinities

            if "intent_tags" not in enriched or not enriched["intent_tags"]:
                enriched["intent_tags"] = derive_intent_tags(enriched)

            index["ragas"][raga]["phrases"].append(enriched)
            total_phrases += 1

    index["built_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    index["stats"] = {
        "total_phrases": total_phrases,
        "ragas_indexed": len(index["ragas"]),
    }

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)

    print(f"\n  Built phrase index: {total_phrases} phrases across {len(index['ragas'])} ragas")
    print(f"  Saved to {INDEX_PATH}\n")
    return index


def _check_staleness(existing: dict) -> bool:
    """Check if the existing index is stale (newer metadata files exist)."""
    built_at = existing.get("built_at", "")
    if not built_at:
        return True
    try:
        import datetime
        idx_time = datetime.datetime.fromisoformat(built_at)
    except Exception:
        return True

    if not PHRASES_DIR.exists():
        return True

    for lib_dir in PHRASES_DIR.iterdir():
        if not lib_dir.is_dir():
            continue
        meta_path = lib_dir / "phrases_metadata.json"
        if meta_path.exists():
            import datetime
            mod_time = datetime.datetime.fromtimestamp(meta_path.stat().st_mtime)
            if mod_time > idx_time:
                return True
    return False


def load_index() -> dict:
    """Load the phrase index, building it if needed."""
    if not INDEX_PATH.exists():
        return build_index()
    with open(INDEX_PATH) as f:
        idx = json.load(f)
    if _check_staleness(idx):
        return build_index()
    return idx


def main():
    parser = argparse.ArgumentParser(description="Build the global phrase index.")
    parser.add_argument("--ragas", nargs="*", default=None,
                        help="Only index these ragas (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Force rebuild even if up-to-date")
    args = parser.parse_args()

    build_index(ragas=args.ragas, force=args.force)


if __name__ == "__main__":
    main()
