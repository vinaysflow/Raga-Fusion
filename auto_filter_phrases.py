#!/usr/bin/env python3
"""
auto_filter_phrases.py — Remove weak phrases and rebuild gold libraries.

Filters phrases by:
  - forbidden_note_ratio <= max_forbidden
  - authenticity_score   >= min_auth

Rebuilds gold libraries using the filtered metadata.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from raga_scorer import RagaScorer

PROJECT_ROOT = Path(__file__).resolve().parent
PHRASES_ROOT = PROJECT_ROOT / "data" / "phrases"
RULES_ROOT = PROJECT_ROOT / "data" / "raga_rules"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def filter_library(raga: str, min_auth: float, max_forbidden: float) -> dict:
    lib_dir = PHRASES_ROOT / raga
    meta_path = lib_dir / "phrases_metadata.json"
    if not meta_path.exists():
        return {"raga": raga, "kept": 0, "removed": 0, "total": 0}

    rules_path = RULES_ROOT / f"{raga}.json"
    scorer = RagaScorer.from_rules_file(rules_path) if rules_path.exists() else None

    phrases = _load_json(meta_path, [])
    total = len(phrases)
    if total == 0:
        return {"raga": raga, "kept": 0, "removed": 0, "total": 0}

    filtered = []
    for p in phrases:
        if scorer and "authenticity_score" not in p:
            p = scorer.score_phrase(p)
        auth = float(p.get("authenticity_score", 0.0))
        forbidden = float(p.get("forbidden_note_ratio", 0.0))
        if auth >= min_auth and forbidden <= max_forbidden:
            filtered.append(p)

    # Backup original once
    backup = meta_path.with_suffix(".json.bak")
    if not backup.exists():
        shutil.copy2(meta_path, backup)

    with open(meta_path, "w") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    return {"raga": raga, "kept": len(filtered), "removed": total - len(filtered), "total": total}


def rebuild_gold(raga: str, count: int) -> None:
    meta_path = PHRASES_ROOT / raga / "phrases_metadata.json"
    if not meta_path.exists():
        return
    gold_dir = PHRASES_ROOT / f"{raga}_gold"
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "extract_phrases.py"),
        str(meta_path),
        "--gold",
        "--source-meta",
        str(meta_path),
        "--count",
        str(count),
        "--output",
        str(gold_dir),
    ]
    subprocess.run(cmd, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter weak phrases and rebuild gold libraries.")
    parser.add_argument("--ragas", nargs="*", default=None,
                        help="Limit to these ragas (default: all libraries)")
    parser.add_argument("--min-auth", type=float, default=0.35)
    parser.add_argument("--max-forbidden", type=float, default=0.15)
    parser.add_argument("--gold-count", type=int, default=100)
    args = parser.parse_args()

    ragas = args.ragas
    if not ragas:
        ragas = [p.name for p in PHRASES_ROOT.iterdir() if p.is_dir() and not p.name.startswith("_")]
        ragas = [r.replace("_gold", "").replace("_generated", "") for r in ragas]
        ragas = sorted(set(ragas))

    results = []
    for r in ragas:
        res = filter_library(r, args.min_auth, args.max_forbidden)
        results.append(res)
        rebuild_gold(r, args.gold_count)

    print("\nFilter summary:")
    for r in results:
        print(f"  {r['raga']}: kept={r['kept']} removed={r['removed']} total={r['total']}")


if __name__ == "__main__":
    main()
