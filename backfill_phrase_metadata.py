#!/usr/bin/env python3
"""
backfill_phrase_metadata.py — Tier 0 data backfill.

1. Arc section backfill: Run raga_arc_profiler on all phrases; write arc_section,
   arc_confidence to each phrases_metadata.json.

2. Generated metadata enrichment: For *_generated libraries, add phrase_density,
   contour_direction, authenticity_score, pitch_histogram, and other RagaScorer
   fields that are missing.

Usage:
    python backfill_phrase_metadata.py                    # all libraries
    python backfill_phrase_metadata.py --ragas yaman      # specific ragas
    python backfill_phrase_metadata.py --dry-run         # no writes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PHRASES_DIR = PROJECT_ROOT / "data" / "phrases"
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"


def _raga_from_lib_name(lib_name: str) -> str:
    """Extract raga from library dir name. Raga is always the first segment."""
    parts = lib_name.split("_")
    if not parts:
        return "yaman"  # fallback
    return parts[0]


def _infer_register_from_histogram(pitch_histogram: list[float]) -> str:
    """Infer register from 12-bin pitch class histogram. Lower tetrachord vs upper."""
    if not pitch_histogram or len(pitch_histogram) != 12:
        return "middle"
    total = sum(pitch_histogram)
    if total <= 0:
        return "middle"
    weighted_degree = sum(i * h for i, h in enumerate(pitch_histogram)) / total
    if weighted_degree < 4:
        return "lower"
    if weighted_degree > 7:
        return "upper"
    return "middle"


def _tempo_confidence_from_density(phrase_density: float) -> float:
    """Map phrase_density (notes/sec) to tempo_confidence for arc classifier."""
    if phrase_density < 2:
        return 0.1
    if phrase_density < 4:
        return 0.25
    if phrase_density < 6:
        return 0.45
    return 0.65


def backfill_library(lib_dir: Path, rules_path: Path, dry_run: bool) -> int:
    """Backfill one phrase library. Returns count of phrases updated."""
    meta_path = lib_dir / "phrases_metadata.json"
    if not meta_path.exists():
        return 0

    with open(meta_path) as f:
        phrases = json.load(f)

    if not phrases:
        return 0

    raga = _raga_from_lib_name(lib_dir.name)
    is_generated = lib_dir.name.endswith("_generated")

    from raga_scorer import RagaScorer
    from raga_arc_profiler import classify_arc_section, compute_note_density

    scorer = RagaScorer.from_rules_file(rules_path)

    # Source duration: prefer source_duration from phrases, else max(end_time)
    source_duration = max(p.get("source_duration", 0) for p in phrases) if phrases else 0
    max_end = max(
        p.get("end_time", p.get("start_time", 0) + p.get("duration", 0))
        for p in phrases
    ) if phrases else 1.0
    if source_duration > 0:
        max_end = source_duration
    elif max_end <= 0:
        max_end = sum(p.get("duration", 0) for p in phrases) or 1.0

    updated = 0
    for p in phrases:
        orig = dict(p)

        # 1. Enrich generated phrases with RagaScorer fields
        notes = p.get("notes_sequence") or p.get("notes_detected", [])
        dur = p.get("duration", 1.0)

        if is_generated and (
            "phrase_density" not in p
            or "contour_direction" not in p
            or "authenticity_score" not in p
            or "pitch_histogram" not in p
        ):
            enriched = scorer.score_phrase(p)
            for key in (
                "phrase_density",
                "contour_direction",
                "authenticity_score",
                "pitch_histogram",
                "forbidden_note_ratio",
                "scale_compliance",
                "pakad_match_score",
                "aroha_compliance",
                "avaroha_compliance",
                "vadi_emphasis",
                "samvadi_emphasis",
            ):
                if key in enriched and key not in p:
                    p[key] = enriched[key]

        # 2. Compute note_density if missing (for arc classifier)
        note_density = p.get("note_density")
        if note_density is None:
            note_count = len(notes)
            note_density = compute_note_density(note_count, dur)
            p["note_density"] = round(note_density, 3)

        phrase_density = p.get("phrase_density", note_density)
        energy_level = p.get("energy_level", 0.3)
        register = p.get("register")
        if register is None:
            hist = p.get("pitch_histogram")
            if hist:
                register = _infer_register_from_histogram(hist)
            else:
                register = "middle"
            p["register"] = register

        position_ratio = p.get("position_ratio")
        if position_ratio is None:
            position_ratio = p.get("start_time", 0) / max_end if max_end > 0 else 0.5
        position_ratio = min(1.0, max(0.0, float(position_ratio)))
        p["position_ratio"] = round(position_ratio, 4)

        tempo_confidence = _tempo_confidence_from_density(phrase_density)

        arc_section, arc_confidence = classify_arc_section(
            energy_level=energy_level,
            note_density=note_density,
            tempo_confidence=tempo_confidence,
            register=register,
            position_ratio=position_ratio,
        )

        p["arc_section"] = arc_section
        p["arc_confidence"] = round(arc_confidence, 3)
        updated += 1

    if not dry_run and updated > 0:
        with open(meta_path, "w") as f:
            json.dump(phrases, f, indent=2)

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill arc_section and enrich generated phrase metadata.")
    parser.add_argument("--ragas", nargs="*", default=None, help="Only process these ragas")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    args = parser.parse_args()

    if not PHRASES_DIR.exists():
        print("  ERROR: data/phrases/ not found")
        sys.exit(1)

    lib_dirs = sorted(d for d in PHRASES_DIR.iterdir() if d.is_dir())
    total_phrases = 0
    libs_processed = 0

    for lib_dir in lib_dirs:
        raga = _raga_from_lib_name(lib_dir.name)
        if not raga or raga.startswith("_"):
            continue
        rules_path = RULES_DIR / f"{raga}.json"

        if args.ragas and raga not in args.ragas:
            continue
        if not rules_path.exists():
            print(f"  SKIP {lib_dir.name}: no rules for {raga}")
            continue

        n = backfill_library(lib_dir, rules_path, args.dry_run)
        if n > 0:
            libs_processed += 1
            total_phrases += n
            mode = "(dry-run)" if args.dry_run else ""
            print(f"  {lib_dir.name}: {n} phrases {mode}")

    print(f"\n  Done: {total_phrases} phrases in {libs_processed} libraries")
    if args.dry_run:
        print("  Run without --dry-run to write changes.\n")


if __name__ == "__main__":
    main()
