#!/usr/bin/env python3
"""
backfill_intent_tags.py — Derive intent_tags for phrases from metadata.

Uses enhancement_config.json rules: phrase_density, contour_direction.
Tags: meditative, exploratory, energetic, dense, sparse, climax.
Populates phrase index at build time (phrase_indexer integrates this).
Can also write back to phrases_metadata.json for persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "data" / "enhancement_config.json"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def derive_intent_tags(phrase: dict) -> list[str]:
    """Derive intent tags from phrase metadata (density, contour)."""
    config = _load_config()
    rules = config.get("intent_derivation_rules") or {}
    tags = []
    density = phrase.get("phrase_density")
    if density is None:
        notes = phrase.get("notes_detected") or phrase.get("notes_sequence") or []
        dur = max(phrase.get("duration", 1.0), 0.1)
        density = len(notes) / dur if dur else 5.0
    contour = phrase.get("contour_direction", 0.0)

    if density <= 3.0 and -0.3 <= contour <= 0.3:
        tags.append("meditative")
    elif density <= 3.0:
        tags.append("sparse")
    elif density >= 6.0 and contour >= 0.2:
        tags.extend(["dense", "energetic"])
    elif density >= 6.0:
        tags.extend(["dense", "climax"])
    elif 2.0 <= density <= 5.0:
        tags.append("exploratory")

    if not tags:
        tags.append("exploratory" if density < 6 else "dense")
    return tags[:3]


if __name__ == "__main__":
    # Quick test
    p = {"phrase_density": 2.0, "contour_direction": 0.1}
    print("meditative-ish:", derive_intent_tags(p))
    p2 = {"phrase_density": 7.0, "contour_direction": 0.4}
    print("energetic-ish:", derive_intent_tags(p2))
