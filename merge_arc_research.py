#!/usr/bin/env python3
"""
merge_arc_research.py — Combine Grok and OpenAI arc research, picking best from both.

For each raga:
  - arc_profile: average numeric values (balanced consensus)
  - genre_compatibility: take higher score; use notes from source with higher score
  - fusion_notes: merge both, dedupe similar content

Usage:
    python merge_arc_research.py data/arc_research_grok.json data/arc_research_openai.json -o data/arc_research_merged.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ARC_KEYS = ("alap_ratio", "peak_position_ratio", "peak_ceiling", "opening_energy")


def _to_list(val) -> list[str]:
    """Normalize fusion_notes to list of strings."""
    if val is None:
        return []
    if isinstance(val, str):
        return [s.strip() for s in re.split(r"[.;]+\s*", val) if s.strip()]
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


def _similar(a: str, b: str) -> bool:
    """Rough similarity: share significant words."""
    aw = set(re.findall(r"\w{4,}", a.lower()))
    bw = set(re.findall(r"\w{4,}", b.lower()))
    overlap = len(aw & bw) / max(len(aw | bw), 1)
    return overlap > 0.5


def _build_index(data: list[dict]) -> dict[str, dict]:
    """Index by raga_name (lowercase)."""
    out = {}
    for entry in data:
        name = (entry.get("raga_name") or "").lower().strip()
        if name:
            out[name] = entry
    return out


def merge_arc_profile(grok: dict, openai: dict) -> dict:
    """Average numeric arc_profile values."""
    result = {}
    for k in ARC_KEYS:
        g = grok.get(k)
        o = openai.get(k)
        vals = [v for v in (g, o) if isinstance(v, (int, float))]
        if vals:
            result[k] = round(sum(vals) / len(vals), 2)
        elif g is not None:
            result[k] = g
        elif o is not None:
            result[k] = o
    return result


def merge_genre_compat(grok: dict, openai: dict) -> dict:
    """Per genre: take higher score; use notes from higher-scoring source."""
    all_genres = set(
        (grok or {}).keys() | (openai or {}).keys()
    )
    result = {}
    for genre in sorted(all_genres):
        g_ent = (grok or {}).get(genre)
        o_ent = (openai or {}).get(genre)
        g_score = g_ent.get("score", 0) if isinstance(g_ent, dict) else 0
        o_score = o_ent.get("score", 0) if isinstance(o_ent, dict) else 0
        if g_score >= o_score and g_ent:
            result[genre] = {"score": float(g_score), "notes": g_ent.get("notes", "")}
        elif o_ent:
            result[genre] = {"score": float(o_score), "notes": o_ent.get("notes", "")}
    return result


def merge_fusion_notes(grok_list: list[str], openai_list: list[str]) -> list[str]:
    """Merge both lists, dedupe by similarity."""
    combined = grok_list + openai_list
    seen = []
    for s in combined:
        if not s or len(s) < 10:
            continue
        if any(_similar(s, t) for t in seen):
            continue
        seen.append(s)
    return seen


def merge_entry(raga_name: str, grok: dict | None, openai: dict | None) -> dict:
    """Merge one raga from both sources."""
    grok = grok or {}
    openai = openai or {}
    g_arc = grok.get("arc_profile") or {}
    o_arc = openai.get("arc_profile") or {}
    g_genre = grok.get("genre_compatibility_additions") or {}
    o_genre = openai.get("genre_compatibility_additions") or {}
    g_notes = _to_list(grok.get("fusion_notes"))
    o_notes = _to_list(openai.get("fusion_notes"))
    return {
        "raga_name": raga_name,
        "arc_profile": merge_arc_profile(g_arc, o_arc),
        "genre_compatibility_additions": merge_genre_compat(g_genre, o_genre),
        "fusion_notes": merge_fusion_notes(g_notes, o_notes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge Grok and OpenAI arc research.")
    parser.add_argument("grok", type=Path, help="Grok research JSON")
    parser.add_argument("openai", type=Path, help="OpenAI research JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output merged JSON")
    args = parser.parse_args()

    with open(args.grok) as f:
        grok_data = json.load(f)
    with open(args.openai) as f:
        openai_data = json.load(f)

    if not isinstance(grok_data, list):
        grok_data = [grok_data]
    if not isinstance(openai_data, list):
        openai_data = [openai_data]

    grok_idx = _build_index(grok_data)
    openai_idx = _build_index(openai_data)
    all_ragas = sorted(set(grok_idx.keys()) | set(openai_idx.keys()))

    merged = []
    for raga in all_ragas:
        entry = merge_entry(raga, grok_idx.get(raga), openai_idx.get(raga))
        merged.append(entry)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.output} ({len(merged)} ragas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
