#!/usr/bin/env python3
"""
quality_gate.py — Gold standard comparison utilities for provider uploads.

Used to compare a new phrase library's average authenticity to the
current gold library for the same raga.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
PHRASES_DIR = PROJECT_ROOT / "data" / "phrases"


def _load_phrase_scores(meta_path: Path) -> list[float]:
    if not meta_path.exists():
        return []
    try:
        with meta_path.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    scores: list[float] = []
    for item in data:
        score = item.get("authenticity_score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    return scores


def _average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def get_gold_ceiling(raga: str) -> float:
    """
    Return the average authenticity score of the gold library for a raga.
    If no gold library exists or scores are missing, returns 0.0.
    """
    gold_dir = PHRASES_DIR / f"{raga}_gold"
    meta_path = gold_dir / "phrases_metadata.json"
    return _average(_load_phrase_scores(meta_path))


def compute_library_avg(meta_path: Path) -> float:
    """
    Return average authenticity_score for a phrase metadata JSON file.
    """
    return _average(_load_phrase_scores(meta_path))


def compare_to_gold(raga: str, new_avg: float, threshold_exceeds: float = 0.05) -> dict:
    """
    Compare new library avg authenticity against the gold ceiling.

    Returns:
      {
        "status": "no_gold_baseline" | "exceeds_gold" | "above_gold" | "standard_tier",
        "current_gold_avg": float,
        "new_avg": float,
        "delta": float,
        "action": str
      }
    """
    current_gold_avg = get_gold_ceiling(raga)
    if current_gold_avg <= 0.0:
        return {
            "status": "no_gold_baseline",
            "current_gold_avg": 0.0,
            "new_avg": new_avg,
            "delta": new_avg,
            "action": "set_as_first_gold",
        }

    delta = new_avg - current_gold_avg
    if delta >= threshold_exceeds:
        status = "exceeds_gold"
        action = "flag_for_recalibration"
    elif delta > 0:
        status = "above_gold"
        action = "add_to_gold"
    else:
        status = "standard_tier"
        action = "add_to_standard"

    return {
        "status": status,
        "current_gold_avg": current_gold_avg,
        "new_avg": new_avg,
        "delta": delta,
        "action": action,
    }


def trigger_recalibration(raga: str, upload_id: str, new_phrases_dir: Path,
                          max_gold_count: int = 200) -> dict:
    """
    Rebuild the gold library for a raga using existing gold phrases plus
    new phrases from a provider upload. Keeps top N by authenticity_score.
    """
    gold_dir = PHRASES_DIR / f"{raga}_gold"
    new_meta = new_phrases_dir / "phrases_metadata.json"
    if not new_meta.exists():
        return {"status": "error", "error": "new phrases metadata missing"}

    def _load_with_source(meta_path: Path, source_dir: Path) -> list[dict]:
        items = []
        with meta_path.open() as f:
            raw = json.load(f)
        for entry in raw:
            entry = dict(entry)
            entry["_source_dir"] = str(source_dir)
            items.append(entry)
        return items

    new_phrases = _load_with_source(new_meta, new_phrases_dir)
    existing_phrases = []
    if gold_dir.exists():
        gold_meta = gold_dir / "phrases_metadata.json"
        if gold_meta.exists():
            existing_phrases = _load_with_source(gold_meta, gold_dir)

    combined = existing_phrases + new_phrases
    combined.sort(key=lambda p: p.get("authenticity_score", 0.0), reverse=True)
    selected = combined[:max_gold_count]

    if gold_dir.exists():
        shutil.rmtree(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    final_meta = []
    for entry in selected:
        source_dir = Path(entry.pop("_source_dir", str(new_phrases_dir)))
        src = source_dir / entry.get("file", "")
        if src.exists():
            shutil.copy2(src, gold_dir / src.name)
        entry["library_tier"] = "gold"
        entry["source_type"] = "library"
        final_meta.append(entry)

    with (gold_dir / "phrases_metadata.json").open("w") as f:
        json.dump(final_meta, f, indent=2)

    return {
        "status": "ok",
        "raga": raga,
        "upload_id": upload_id,
        "gold_count": len(final_meta),
        "gold_dir": str(gold_dir),
    }
