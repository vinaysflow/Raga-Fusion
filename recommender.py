#!/usr/bin/env python3
"""
recommender.py — Raga phrase recommendation engine.

Given a request (raga, style, duration, source preference, intent tags),
returns a ranked phrase plan: ordered list of phrases optimised for
raga authenticity, style fit, transition smoothness, and novelty.

The engine consumes the phrase index built by phrase_indexer.py and the
grammar scorer from raga_scorer.py.

Usage (as module):
    from recommender import Recommender
    rec = Recommender()
    plan = rec.recommend_phrases("yaman", "lofi", duration=120, source="library")
    plan = rec.recommend_arrangement("yaman", "lofi", duration=120,
                                      intent_tags=["meditative"])

Usage (CLI):
    python recommender.py --raga yaman --style lofi --duration 60
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
INDEX_PATH = PROJECT_ROOT / "data" / "phrase_index.json"

DEFAULT_WEIGHTS = {
    "w_auth": 0.30,
    "w_trans": 0.20,
    "w_style": 0.15,
    "w_quality": 0.15,
    "w_novelty": 0.10,
    "w_intent": 0.10,
}

PLAN_CONSTRAINTS = {
    "min_pakad_usage": 0.3,
    "min_vadi_emphasis": 0.05,
    "max_forbidden_ratio": 0.1,
    "min_scale_compliance": 0.6,
}

SVARA_ORDER = {
    "Sa": 0, "re": 1, "Re": 2, "ga": 3, "Ga": 4,
    "ma": 5, "Ma": 5, "Ma'": 6,
    "Pa": 7, "dha": 8, "Dha": 9, "ni": 10, "Ni": 11,
    "Sa'": 12,
}

INTENT_DENSITY = {
    "meditative": "sparse",
    "energetic": "dense",
    "minimal": "sparse",
    "dense": "dense",
    "contemplative": "sparse",
    "vibrant": "dense",
    "calm": "sparse",
    "intense": "dense",
}

PHASE_NAMES = ["opening", "ascending", "development", "peak", "resolution"]
PHASE_WEIGHTS = {
    "opening": 0.15,
    "ascending": 0.20,
    "development": 0.30,
    "peak": 0.20,
    "resolution": 0.15,
}

PHASE_CRITERIA = {
    "opening": {"contour_target": (-0.3, 0.3), "density_pref": "sparse", "vadi_bonus": False},
    "ascending": {"contour_target": (0.0, 1.0), "density_pref": "medium", "vadi_bonus": True},
    "development": {"contour_target": (-0.5, 0.5), "density_pref": "dense", "vadi_bonus": True},
    "peak": {"contour_target": (-1.0, 1.0), "density_pref": "dense", "vadi_bonus": False},
    "resolution": {"contour_target": (-0.5, 0.0), "density_pref": "sparse", "vadi_bonus": False},
}


class Recommender:
    """Weighted ranking engine for phrase selection and arrangement."""

    def __init__(self, index: dict | None = None, weights: dict | None = None):
        if index is None:
            index = self._load_index()
        self.index = index
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        allow_blend = os.getenv("ALLOW_LIBRARY_BLEND_RAGAS", "")
        self.allow_blend_ragas = {
            r.strip().lower() for r in allow_blend.split(",") if r.strip()
        }
        self.min_gold_count = int(os.getenv("MIN_GOLD_COUNT", "30"))

    @staticmethod
    def _load_index() -> dict:
        from phrase_indexer import load_index
        return load_index()

    def _get_candidates(self, raga: str, source: str | None = None) -> list[dict]:
        raga_data = self.index.get("ragas", {}).get(raga)
        if not raga_data:
            return []
        phrases = raga_data.get("phrases", [])
        if source:
            phrases = [p for p in phrases if p.get("source_type") == source]
            if source == "library":
                gold = [p for p in phrases if p.get("library_tier") == "gold"]
                if gold:
                    if raga in self.allow_blend_ragas and len(gold) < self.min_gold_count:
                        return phrases
                    return gold
        return phrases

    @staticmethod
    def _transition_score(prev_phrase: dict | None, candidate: dict) -> float:
        """Score melodic transition quality between consecutive phrases (0-1)."""
        if prev_phrase is None:
            start = candidate.get("starts_with", "Sa")
            return 1.0 if start == "Sa" else 0.7

        prev_end = prev_phrase.get("ends_with", "Sa")
        curr_start = candidate.get("starts_with", "Sa")

        prev_ord = SVARA_ORDER.get(prev_end, 0)
        curr_ord = SVARA_ORDER.get(curr_start, 0)
        dist = abs(prev_ord - curr_ord)

        if dist == 0:
            return 1.0
        elif dist <= 2:
            return 0.85
        elif dist <= 4:
            return 0.6
        else:
            return max(0.1, 1.0 - dist * 0.08)

    @staticmethod
    def _novelty_score(candidate: dict, selected_ids: set[str],
                       selected_notes_hist: list[float]) -> float:
        """Anti-repetition score: penalise re-used phrases and overused pitch classes."""
        if candidate.get("phrase_id") in selected_ids:
            return 0.0

        phrase_hist = candidate.get("pitch_histogram", [0.0] * 12)
        if not selected_notes_hist or all(h == 0 for h in selected_notes_hist):
            return 1.0

        overlap = sum(min(a, b) for a, b in zip(phrase_hist, selected_notes_hist))
        return max(0.0, 1.0 - overlap)

    @staticmethod
    def _intent_score(candidate: dict, intent_tags: list[str]) -> float:
        """Score how well a phrase matches intent tags."""
        if not intent_tags:
            return 0.5

        density = candidate.get("phrase_density", 5.0)
        desired_density = "medium"
        for tag in intent_tags:
            if tag in INTENT_DENSITY:
                desired_density = INTENT_DENSITY[tag]
                break

        if desired_density == "sparse" and density < 4.0:
            return 1.0
        elif desired_density == "sparse" and density > 8.0:
            return 0.2
        elif desired_density == "dense" and density > 6.0:
            return 1.0
        elif desired_density == "dense" and density < 3.0:
            return 0.2
        return 0.6

    def _score_candidate(self, candidate: dict, style: str,
                         prev_phrase: dict | None, selected_ids: set[str],
                         selected_hist: list[float],
                         intent_tags: list[str],
                         phase: str | None = None) -> float:
        """Compute composite ranking score for a candidate phrase."""
        w = self.weights

        auth = candidate.get("authenticity_score", 0.5)
        trans = self._transition_score(prev_phrase, candidate)
        style_aff = candidate.get("style_affinities", {}).get(style, 0.5)
        quality = candidate.get("quality_score", 0.5)
        novelty = self._novelty_score(candidate, selected_ids, selected_hist)
        intent = self._intent_score(candidate, intent_tags)

        score = (
            w["w_auth"] * auth
            + w["w_trans"] * trans
            + w["w_style"] * style_aff
            + w["w_quality"] * quality
            + w["w_novelty"] * novelty
            + w["w_intent"] * intent
        )

        if phase:
            criteria = PHASE_CRITERIA.get(phase, {})
            contour = candidate.get("contour_direction", 0.0)
            lo, hi = criteria.get("contour_target", (-1.0, 1.0))
            if lo <= contour <= hi:
                score += 0.05
            if criteria.get("vadi_bonus") and candidate.get("vadi_emphasis", 0) > 0.15:
                score += 0.03

        return score

    def recommend_phrases(self, raga: str, style: str,
                          duration: float = 120.0,
                          source: str | None = None,
                          intent_tags: list[str] | None = None,
                          crossfade_dur: float = 0.75,
                          min_auth: float | None = None) -> list[dict]:
        """Return a ranked, ordered list of phrases to fill the target duration.

        Each returned phrase dict includes the original metadata plus a
        'recommendation_score' field.
        """
        candidates = self._get_candidates(raga, source)
        if not candidates:
            return []
        if min_auth is not None:
            filtered = [c for c in candidates if c.get("authenticity_score", 0.0) >= min_auth]
            if filtered:
                candidates = filtered

        intent_tags = intent_tags or []
        selected: list[dict] = []
        selected_ids: set[str] = set()
        selected_hist = [0.0] * 12
        accumulated_dur = 0.0

        phase_idx = 0
        phase_budget = duration * PHASE_WEIGHTS[PHASE_NAMES[0]]
        phase_dur = 0.0

        while accumulated_dur < duration and len(selected) < len(candidates):
            current_phase = PHASE_NAMES[min(phase_idx, len(PHASE_NAMES) - 1)]
            prev = selected[-1] if selected else None

            scored = []
            for c in candidates:
                if c["phrase_id"] in selected_ids:
                    continue
                s = self._score_candidate(
                    c, style, prev, selected_ids, selected_hist,
                    intent_tags, current_phase,
                )
                scored.append((s, c))

            if not scored:
                break

            scored.sort(key=lambda x: -x[0])
            best_score, best = scored[0]

            best_out = {k: v for k, v in best.items()
                        if k not in ("audio",)}
            best_out["recommendation_score"] = round(best_score, 4)
            best_out["assigned_phase"] = current_phase

            selected.append(best_out)
            selected_ids.add(best["phrase_id"])

            ph = best.get("pitch_histogram", [0.0] * 12)
            n = len(selected)
            selected_hist = [
                selected_hist[i] * (n - 1) / n + ph[i] / n
                for i in range(12)
            ]

            phrase_dur = best.get("duration", 3.0)
            if selected_ids:
                accumulated_dur += phrase_dur - (crossfade_dur if len(selected) > 1 else 0)
            phase_dur += phrase_dur

            if phase_dur >= phase_budget:
                phase_idx += 1
                if phase_idx < len(PHASE_NAMES):
                    phase_budget = duration * PHASE_WEIGHTS[PHASE_NAMES[phase_idx]]
                    phase_dur = 0.0
                else:
                    phase_budget = duration

        return selected

    @staticmethod
    def _check_constraints(phrases: list[dict]) -> dict:
        """Validate the recommended plan against quality constraints."""
        if not phrases:
            return {"passes": False, "violations": ["No phrases selected"], "score": 0.0}

        violations = []
        n = len(phrases)

        avg_pakad = sum(p.get("pakad_match_score", 0) for p in phrases) / n
        avg_vadi = sum(p.get("vadi_emphasis", 0) for p in phrases) / n
        avg_forbidden = sum(p.get("forbidden_note_ratio", 0) for p in phrases) / n
        avg_scale = sum(p.get("scale_compliance", 0) for p in phrases) / n

        if avg_pakad < PLAN_CONSTRAINTS["min_pakad_usage"]:
            violations.append(
                f"Low pakad usage ({avg_pakad:.2f} < {PLAN_CONSTRAINTS['min_pakad_usage']}): "
                "characteristic phrases underrepresented"
            )
        if avg_vadi < PLAN_CONSTRAINTS["min_vadi_emphasis"]:
            violations.append(
                f"Low vadi emphasis ({avg_vadi:.2f} < {PLAN_CONSTRAINTS['min_vadi_emphasis']}): "
                "king note needs more presence"
            )
        if avg_forbidden > PLAN_CONSTRAINTS["max_forbidden_ratio"]:
            violations.append(
                f"High forbidden notes ({avg_forbidden:.2f} > {PLAN_CONSTRAINTS['max_forbidden_ratio']}): "
                "raga purity at risk"
            )
        if avg_scale < PLAN_CONSTRAINTS["min_scale_compliance"]:
            violations.append(
                f"Low scale compliance ({avg_scale:.2f} < {PLAN_CONSTRAINTS['min_scale_compliance']}): "
                "too many out-of-scale notes"
            )

        constraint_score = (
            min(avg_pakad / PLAN_CONSTRAINTS["min_pakad_usage"], 1.0) * 0.3
            + min(avg_vadi / max(PLAN_CONSTRAINTS["min_vadi_emphasis"], 0.01), 1.0) * 0.2
            + max(0, 1.0 - avg_forbidden / max(PLAN_CONSTRAINTS["max_forbidden_ratio"], 0.01)) * 0.25
            + min(avg_scale / max(PLAN_CONSTRAINTS["min_scale_compliance"], 0.01), 1.0) * 0.25
        )

        return {
            "passes": len(violations) == 0,
            "violations": violations,
            "score": round(constraint_score, 4),
            "metrics": {
                "avg_pakad_match": round(avg_pakad, 4),
                "avg_vadi_emphasis": round(avg_vadi, 4),
                "avg_forbidden_ratio": round(avg_forbidden, 4),
                "avg_scale_compliance": round(avg_scale, 4),
            },
        }

    @staticmethod
    def _generate_explanations(phrases: list[dict], raga: str, style: str,
                                intent_tags: list[str]) -> list[str]:
        """Generate human-readable explanations of why this plan was chosen."""
        explanations = []
        if not phrases:
            return ["No phrases available for this raga/source combination."]

        n = len(phrases)
        avg_auth = sum(p.get("authenticity_score", 0) for p in phrases) / n
        avg_rec = sum(p.get("recommendation_score", 0) for p in phrases) / n

        explanations.append(
            f"Selected {n} phrases for raga {raga.capitalize()} in {style} style"
        )

        if avg_auth > 0.5:
            explanations.append(
                f"High raga authenticity ({avg_auth:.0%}) — strong adherence to "
                f"{raga.capitalize()} grammar and characteristic phrases"
            )
        elif avg_auth > 0.3:
            explanations.append(
                f"Moderate raga authenticity ({avg_auth:.0%}) — recognizable "
                f"{raga.capitalize()} identity with some creative freedom"
            )
        else:
            explanations.append(
                f"Exploratory raga treatment ({avg_auth:.0%}) — fusion-forward "
                "with looser adherence to traditional grammar"
            )

        phases_used = set(p.get("assigned_phase", "") for p in phrases)
        if len(phases_used) >= 4:
            explanations.append(
                "Full musical arc: opening → ascending → development → peak → resolution"
            )

        if intent_tags:
            explanations.append(
                f"Optimized for intent: {', '.join(intent_tags)}"
            )

        sources = set(p.get("source_type", "unknown") for p in phrases)
        if "library" in sources:
            explanations.append("Uses real recorded phrases for authentic timbre")
        if "generated" in sources:
            explanations.append("Includes synthesized phrases for tonal consistency")

        return explanations

    def recommend_arrangement(self, raga: str, style: str,
                               duration: float = 120.0,
                               source: str | None = None,
                               intent_tags: list[str] | None = None) -> dict:
        """Return a full arrangement plan with ranked phrases, constraints, and explanations."""
        intent_tags = intent_tags or []
        phrases = self.recommend_phrases(
            raga, style, duration, source, intent_tags
        )

        constraints = self._check_constraints(phrases)
        fallbacks = []
        if not constraints.get("passes", False):
            min_needed = max(6, int(duration / 3.0))
            for threshold in (0.6, 0.7):
                alt = self.recommend_phrases(
                    raga, style, duration, source, intent_tags, min_auth=threshold
                )
                alt_constraints = self._check_constraints(alt)
                fallbacks.append({
                    "min_auth": threshold,
                    "passes": alt_constraints.get("passes", False),
                    "metrics": alt_constraints.get("metrics", {}),
                    "phrase_count": len(alt),
                })
                if alt_constraints.get("passes", False) and len(alt) >= min_needed:
                    phrases = alt
                    constraints = alt_constraints
                    break

        arrangement: dict[str, list[dict]] = {name: [] for name in PHASE_NAMES}
        for p in phrases:
            phase = p.get("assigned_phase", "development")
            arrangement[phase].append(p)

        avg_auth = (
            sum(p.get("authenticity_score", 0) for p in phrases) / len(phrases)
            if phrases else 0
        )
        avg_rec = (
            sum(p.get("recommendation_score", 0) for p in phrases) / len(phrases)
            if phrases else 0
        )

        explanations = self._generate_explanations(phrases, raga, style, intent_tags)

        result = {
            "raga": raga,
            "style": style,
            "duration": duration,
            "total_phrases": len(phrases),
            "avg_authenticity": round(avg_auth, 4),
            "avg_recommendation_score": round(avg_rec, 4),
            "constraints": constraints,
            "fallbacks": fallbacks,
            "explanations": explanations,
            "phases": arrangement,
            "phrase_sequence": [p["phrase_id"] for p in phrases],
        }

        try:
            from raga_ai import ai_explain_plan
            ai_explanation = ai_explain_plan(result)
            if ai_explanation:
                result["ai_explanation"] = ai_explanation
        except Exception:
            pass

        return result


def main():
    parser = argparse.ArgumentParser(description="Recommend phrases for a raga+style request.")
    parser.add_argument("--raga", default="yaman")
    parser.add_argument("--style", default="lofi")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--source", default=None, choices=["library", "generated"])
    parser.add_argument("--intent", nargs="*", default=[])
    args = parser.parse_args()

    rec = Recommender()
    plan = rec.recommend_arrangement(
        args.raga, args.style, args.duration, args.source, args.intent
    )

    print(f"\n  Arrangement plan for {args.raga} / {args.style} ({args.duration}s)")
    print(f"  Total phrases: {plan['total_phrases']}")
    print(f"  Avg authenticity: {plan['avg_authenticity']:.3f}")
    print(f"  Avg recommendation: {plan['avg_recommendation_score']:.3f}")
    print()

    for phase_name in PHASE_NAMES:
        phase_phrases = plan["phases"][phase_name]
        print(f"  [{phase_name.upper()}] — {len(phase_phrases)} phrases")
        for p in phase_phrases:
            notes = " ".join(p.get("notes_detected", [])[:5])
            print(f"    {p['phrase_id']:>25s}  "
                  f"auth={p.get('authenticity_score', 0):.3f}  "
                  f"rec={p.get('recommendation_score', 0):.3f}  "
                  f"src={p.get('source_type', '?'):>9s}  "
                  f"{notes}")
        print()


if __name__ == "__main__":
    main()
