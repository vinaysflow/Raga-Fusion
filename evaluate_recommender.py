#!/usr/bin/env python3
"""
evaluate_recommender.py — Batch evaluation of recommender constraints.

Writes a JSON report with per-raga constraint metrics and pass rates.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from recommender import Recommender

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "recommender_eval.json"


def _load_ragas() -> list[str]:
    rules_dir = PROJECT_ROOT / "data" / "raga_rules"
    if not rules_dir.exists():
        return ["yaman"]
    return sorted([p.stem for p in rules_dir.glob("*.json")])


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate recommender constraints across ragas.")
    parser.add_argument("--ragas", nargs="*", default=None, help="Ragas to evaluate")
    parser.add_argument("--style", default="lofi")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--source", default="library", choices=["library", "generated"])
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    ragas = args.ragas or _load_ragas()
    rec = Recommender()
    results = []
    passes = 0

    for raga in ragas:
        plan = rec.recommend_arrangement(
            raga=raga,
            style=args.style,
            duration=args.duration,
            source=args.source,
            intent_tags=[],
        )
        constraints = plan.get("constraints", {})
        passed = bool(constraints.get("passes"))
        if passed:
            passes += 1
        results.append({
            "raga": raga,
            "passes": passed,
            "score": constraints.get("score"),
            "metrics": constraints.get("metrics", {}),
            "violations": constraints.get("violations", []),
            "total_phrases": plan.get("total_phrases"),
            "avg_authenticity": plan.get("avg_authenticity"),
            "avg_recommendation_score": plan.get("avg_recommendation_score"),
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "style": args.style,
        "duration": args.duration,
        "source": args.source,
        "total_ragas": len(ragas),
        "passes": passes,
        "pass_rate": round(passes / max(len(ragas), 1), 3),
        "results": results,
    }

    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"Wrote evaluation report to {args.out}")


if __name__ == "__main__":
    main()
