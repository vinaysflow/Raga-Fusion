#!/usr/bin/env python3
"""
evaluate_recommendations.py — compare baseline vs recommender quality.

Runs a simple replay evaluation: for each raga library, it builds a baseline
phrase selection using the heuristic assembler and compares it to the new
recommendation engine. Outputs an educational, formatted report with average
authenticity and rule-compliance metrics.

Usage:
    python evaluate_recommendations.py
    python evaluate_recommendations.py --duration 60 --ragas yaman bhairavi
"""

import argparse
from pathlib import Path

from assemble_track import load_phrase_library, select_phrases
from phrase_indexer import load_index
from raga_scorer import RagaScorer
from recommender import Recommender

PROJECT_ROOT = Path(__file__).resolve().parent
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"
PHRASES_DIR = PROJECT_ROOT / "data" / "phrases"


def _score_selection(phrases: list[dict], scorer: RagaScorer) -> dict:
    if not phrases:
        return {"avg_auth": 0.0, "avg_forbid": 0.0, "avg_pakad": 0.0}
    enriched = [scorer.score_phrase(p) for p in phrases]
    avg_auth = sum(p["authenticity_score"] for p in enriched) / len(enriched)
    avg_forbid = sum(p["forbidden_note_ratio"] for p in enriched) / len(enriched)
    avg_pakad = sum(p["pakad_match_score"] for p in enriched) / len(enriched)
    return {
        "avg_auth": avg_auth,
        "avg_forbid": avg_forbid,
        "avg_pakad": avg_pakad,
    }


def evaluate(duration: float, ragas: list[str] | None = None) -> None:
    index = load_index()
    rec = Recommender(index=index)

    ragas_to_run = ragas or sorted(index.get("ragas", {}).keys())

    print("\n══════════════════════════════════════════════════════════════")
    print("  RAGA INTELLIGENCE — EVALUATION REPORT")
    print("══════════════════════════════════════════════════════════════\n")
    print(f"  Target duration per raga: {duration:.1f}s\n")

    for raga in ragas_to_run:
        rules_path = RULES_DIR / f"{raga}.json"
        if not rules_path.exists():
            print(f"  Skipping {raga}: no rules file")
            continue

        # Prefer real library if available
        lib_path = PHRASES_DIR / raga
        if not (lib_path / "phrases_metadata.json").exists():
            lib_path = PHRASES_DIR / f"{raga}_generated"

        if not (lib_path / "phrases_metadata.json").exists():
            print(f"  Skipping {raga}: no phrase library")
            continue

        scorer = RagaScorer.from_rules_file(rules_path)
        phrases = load_phrase_library(lib_path)

        baseline = select_phrases(duration, phrases, crossfade_dur=0.75)
        base_scores = _score_selection(baseline, scorer)

        rec_phrases = rec.recommend_phrases(
            raga=raga,
            style="lofi",
            duration=duration,
            source="library" if lib_path.name == raga else "generated",
        )
        rec_scores = {
            "avg_auth": (sum(p["authenticity_score"] for p in rec_phrases) / len(rec_phrases))
            if rec_phrases else 0.0,
            "avg_forbid": (sum(p["forbidden_note_ratio"] for p in rec_phrases) / len(rec_phrases))
            if rec_phrases else 0.0,
            "avg_pakad": (sum(p["pakad_match_score"] for p in rec_phrases) / len(rec_phrases))
            if rec_phrases else 0.0,
        }

        print(f"  Raga: {raga.capitalize()}  ({lib_path.name})")
        print(f"  ─ Baseline:     auth={base_scores['avg_auth']:.3f}  "
              f"forbid={base_scores['avg_forbid']:.3f}  "
              f"pakad={base_scores['avg_pakad']:.3f}")
        print(f"  ─ Recommended:  auth={rec_scores['avg_auth']:.3f}  "
              f"forbid={rec_scores['avg_forbid']:.3f}  "
              f"pakad={rec_scores['avg_pakad']:.3f}")
        print()

    print("══════════════════════════════════════════════════════════════")
    print("  Done.")
    print("══════════════════════════════════════════════════════════════\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline vs recommendation quality.")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="Target duration per raga (seconds)")
    parser.add_argument("--ragas", nargs="*", default=None,
                        help="Optional list of ragas to evaluate")
    args = parser.parse_args()
    evaluate(args.duration, args.ragas)


if __name__ == "__main__":
    main()
