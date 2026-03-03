#!/usr/bin/env python3
"""
build_compatibility_map.py — Build raga/genre compatibility map from raga rules.

Reads data/raga_rules/*.json and writes data/compatibility_map.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"
OUT_PATH = PROJECT_ROOT / "data" / "compatibility_map.json"


def build_map() -> dict:
    ragas = {}
    for p in sorted(RULES_DIR.glob("*.json")):
        with open(p) as f:
            data = json.load(f)
        raga_id = p.stem
        western_mode = data.get("western_equivalent", {}).get("mode")
        genre_compat = data.get("genre_compatibility", {})
        arc_profile = data.get("arc_profile") or {}
        tempo_limits = data.get("tempo_limits") or {}
        ragas[raga_id] = {
            "western_mode": western_mode,
            "arc_profile": arc_profile,
            "compatible_genres": genre_compat,
            "tempo_limits": tempo_limits,
        }
    cross_raga = {"same_thaat": 0.9, "shared_vadi": 0.7}
    return {
        "generated_at": datetime.now().isoformat(),
        "ragas": ragas,
        "cross_raga": cross_raga,
    }


def main():
    payload = build_map()
    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
