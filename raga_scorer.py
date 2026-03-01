#!/usr/bin/env python3
"""
raga_scorer.py — Raga grammar validator and authenticity scoring.

Scores phrases against raga rules: forbidden-note penalties, pakad similarity,
aroha/avaroha compliance, vadi/samvadi emphasis.  Used by the phrase indexer
and recommendation engine.

Usage (as module):
    from raga_scorer import RagaScorer
    scorer = RagaScorer.from_rules_file("data/raga_rules/yaman.json")
    enriched = scorer.score_phrase(phrase_metadata)

Usage (CLI — score all phrases in a library):
    python raga_scorer.py --raga yaman --library data/phrases/yaman/
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
#  Svara name normalisation
# ═══════════════════════════════════════════════════════════════════════

SVARA_TO_DEGREE = {
    "Sa": 0, "Sa'": 12,
    "S": 0,
    "re": 1, "Re": 2,
    "r": 1, "R": 2,
    "ga": 3, "Ga": 4,
    "g": 3, "G": 4,
    "ma": 5, "Ma": 5, "Ma'": 6,
    "m": 5, "M": 5,
    "Pa": 7, "P": 7,
    "dha": 8, "Dha": 9,
    "d": 8, "D": 9,
    "ni": 10, "Ni": 11,
    "n": 10, "N": 11,
}

DEGREE_TO_SVARA_FULL = {
    0: "Sa", 1: "re", 2: "Re", 3: "ga", 4: "Ga",
    5: "ma", 6: "Ma'", 7: "Pa", 8: "dha", 9: "Dha",
    10: "ni", 11: "Ni", 12: "Sa'",
}


def _svara_name_to_degree(name: str) -> int | None:
    if name in SVARA_TO_DEGREE:
        return SVARA_TO_DEGREE[name]
    clean = name.replace("'", "'").replace("\u2019", "'").strip()
    if clean in SVARA_TO_DEGREE:
        return SVARA_TO_DEGREE[clean]
    return None


# ═══════════════════════════════════════════════════════════════════════
#  RagaScorer
# ═══════════════════════════════════════════════════════════════════════

class RagaScorer:
    """Scores phrases against a raga's grammatical rules."""

    def __init__(self, rules: dict):
        self.rules = rules
        self.raga_name = rules.get("raga", {}).get("name", "unknown")

        scale = rules.get("scale", {})
        self.allowed_degrees = set(scale.get("degrees", []))
        self.forbidden_degrees = set()
        for entry in scale.get("forbidden", []):
            self.forbidden_degrees.add(entry["degree"])

        movement = rules.get("movement", {})
        self.aroha_degrees = movement.get("aroha_degrees", [])
        self.avaroha_degrees = movement.get("avaroha_degrees", [])

        self.pakad_strings = movement.get("pakad", [])
        self.pakad_degree_seqs = self._parse_pakad_strings(self.pakad_strings)

        emphasis = rules.get("emphasis", {})
        self.vadi_degree = emphasis.get("vadi", {}).get("degree")
        self.samvadi_degree = emphasis.get("samvadi", {}).get("degree")
        self.important_notes = emphasis.get("important_notes", [])
        self.resting_notes = emphasis.get("resting_notes", [])

        self.genre_compat = rules.get("genre_compatibility", {})
        self.mood = rules.get("context", {}).get("mood", [])

    @classmethod
    def from_rules_file(cls, path: str | Path) -> "RagaScorer":
        with open(path) as f:
            return cls(json.load(f))

    def _parse_pakad_strings(self, pakad_list: list[str]) -> list[list[int]]:
        result = []
        for p in pakad_list:
            parts = p.replace("\u2019", "'").replace("\u2018", "'").split()
            seq = []
            for tok in parts:
                deg = _svara_name_to_degree(tok)
                if deg is not None:
                    seq.append(deg % 12)
                elif tok and tok[0] in SVARA_TO_DEGREE:
                    seq.append(SVARA_TO_DEGREE[tok[0]] % 12)
            if seq:
                result.append(seq)
        return result

    # ── Scoring components ─────────────────────────────────────────────

    def forbidden_note_ratio(self, notes: list[str]) -> float:
        """Fraction of detected notes that are forbidden in this raga."""
        if not notes:
            return 0.0
        violations = 0
        for n in notes:
            deg = _svara_name_to_degree(n)
            if deg is not None and (deg % 12) in self.forbidden_degrees:
                violations += 1
        return violations / len(notes)

    def scale_compliance(self, notes: list[str]) -> float:
        """Fraction of notes that belong to the raga's scale."""
        if not notes:
            return 1.0
        in_scale = 0
        for n in notes:
            deg = _svara_name_to_degree(n)
            if deg is not None and (deg % 12) in self.allowed_degrees:
                in_scale += 1
        return in_scale / len(notes)

    def pakad_match_score(self, notes: list[str]) -> float:
        """Best subsequence match against any pakad pattern (0-1)."""
        if not self.pakad_degree_seqs or not notes:
            return 0.0
        note_degs = []
        for n in notes:
            d = _svara_name_to_degree(n)
            if d is not None:
                note_degs.append(d % 12)
        if not note_degs:
            return 0.0

        best = 0.0
        for pakad in self.pakad_degree_seqs:
            if not pakad:
                continue
            matched = self._longest_common_subseq_len(note_degs, pakad)
            score = matched / len(pakad)
            best = max(best, score)
        return min(best, 1.0)

    @staticmethod
    def _longest_common_subseq_len(a: list[int], b: list[int]) -> int:
        m, n = len(a), len(b)
        if m == 0 or n == 0:
            return 0
        prev = [0] * (n + 1)
        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(curr[j - 1], prev[j])
            prev = curr
        return prev[n]

    def aroha_compliance(self, notes: list[str]) -> float:
        """How well the phrase's ascending fragments follow the aroha pattern."""
        return self._directional_compliance(notes, self.aroha_degrees, ascending=True)

    def avaroha_compliance(self, notes: list[str]) -> float:
        """How well the phrase's descending fragments follow the avaroha pattern."""
        return self._directional_compliance(notes, self.avaroha_degrees, ascending=False)

    def _directional_compliance(self, notes: list[str], pattern_degrees: list[int],
                                ascending: bool) -> float:
        degs = [_svara_name_to_degree(n) for n in notes]
        degs = [d % 12 for d in degs if d is not None]
        if len(degs) < 2:
            return 1.0

        legal_transitions = 0
        total_transitions = 0
        pattern_set = set(pattern_degrees)
        for i in range(len(degs) - 1):
            if ascending and degs[i + 1] > degs[i]:
                total_transitions += 1
                if degs[i] in pattern_set and degs[i + 1] in pattern_set:
                    legal_transitions += 1
            elif not ascending and degs[i + 1] < degs[i]:
                total_transitions += 1
                if degs[i] in pattern_set and degs[i + 1] in pattern_set:
                    legal_transitions += 1
        if total_transitions == 0:
            return 1.0
        return legal_transitions / total_transitions

    def vadi_emphasis(self, notes: list[str]) -> float:
        """How much the vadi note is emphasised (fraction of note occurrences)."""
        if self.vadi_degree is None or not notes:
            return 0.0
        cnt = Counter()
        for n in notes:
            d = _svara_name_to_degree(n)
            if d is not None:
                cnt[d % 12] += 1
        total = sum(cnt.values())
        return cnt.get(self.vadi_degree, 0) / total if total > 0 else 0.0

    def samvadi_emphasis(self, notes: list[str]) -> float:
        """How much the samvadi note is emphasised."""
        if self.samvadi_degree is None or not notes:
            return 0.0
        cnt = Counter()
        for n in notes:
            d = _svara_name_to_degree(n)
            if d is not None:
                cnt[d % 12] += 1
        total = sum(cnt.values())
        return cnt.get(self.samvadi_degree, 0) / total if total > 0 else 0.0

    def pitch_histogram(self, notes: list[str]) -> list[float]:
        """12-bin histogram of pitch class usage (normalised to sum=1)."""
        hist = [0.0] * 12
        for n in notes:
            d = _svara_name_to_degree(n)
            if d is not None:
                hist[d % 12] += 1.0
        total = sum(hist)
        if total > 0:
            hist = [h / total for h in hist]
        return hist

    def phrase_density(self, notes: list[str], duration: float) -> float:
        """Notes per second — characterises fast taan vs slow alap."""
        if duration <= 0:
            return 0.0
        return len(notes) / duration

    def contour_direction(self, notes: list[str]) -> float:
        """Net melodic direction: +1 = pure ascending, -1 = pure descending, 0 = static."""
        degs = [_svara_name_to_degree(n) for n in notes]
        degs = [d for d in degs if d is not None]
        if len(degs) < 2:
            return 0.0
        ups = sum(1 for i in range(len(degs) - 1) if degs[i + 1] > degs[i])
        downs = sum(1 for i in range(len(degs) - 1) if degs[i + 1] < degs[i])
        total = ups + downs
        if total == 0:
            return 0.0
        return (ups - downs) / total

    def style_affinity(self, style: str) -> float:
        """Compatibility score for a given style from the raga rules (0-1)."""
        entry = self.genre_compat.get(style, {})
        if isinstance(entry, dict):
            return entry.get("score", 0.5)
        return 0.5

    # ── Composite scoring ──────────────────────────────────────────────

    def score_phrase(self, phrase: dict) -> dict:
        """Compute all intelligence features for a phrase and return enriched dict.

        Adds new fields without removing existing ones. The `authenticity_score`
        is the weighted composite of raga-grammar metrics.
        """
        notes = phrase.get("notes_sequence") or phrase.get("notes_detected", [])
        dur = phrase.get("duration", 1.0)

        forbidden = self.forbidden_note_ratio(notes)
        scale_comp = self.scale_compliance(notes)
        pakad = self.pakad_match_score(notes)
        aroha = self.aroha_compliance(notes)
        avaroha = self.avaroha_compliance(notes)
        vadi = self.vadi_emphasis(notes)
        samvadi = self.samvadi_emphasis(notes)
        p_hist = self.pitch_histogram(notes)
        density = self.phrase_density(notes, dur)
        contour = self.contour_direction(notes)

        authenticity = (
            0.25 * scale_comp
            + 0.20 * pakad
            + 0.15 * aroha
            + 0.15 * avaroha
            + 0.10 * vadi
            + 0.05 * samvadi
            - 0.40 * forbidden
        )
        authenticity = max(0.0, min(1.0, authenticity))

        enriched = dict(phrase)
        enriched.update({
            "forbidden_note_ratio": round(forbidden, 4),
            "scale_compliance": round(scale_comp, 4),
            "pakad_match_score": round(pakad, 4),
            "aroha_compliance": round(aroha, 4),
            "avaroha_compliance": round(avaroha, 4),
            "vadi_emphasis": round(vadi, 4),
            "samvadi_emphasis": round(samvadi, 4),
            "pitch_histogram": [round(h, 4) for h in p_hist],
            "phrase_density": round(density, 3),
            "contour_direction": round(contour, 3),
            "authenticity_score": round(authenticity, 4),
        })
        return enriched


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Score phrase library against raga rules.")
    parser.add_argument("--raga", type=str, default="yaman")
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--rules-dir", type=Path, default=Path("data/raga_rules"))
    args = parser.parse_args()

    rules_path = args.rules_dir / f"{args.raga}.json"
    if not rules_path.exists():
        print(f"  ERROR: rules not found: {rules_path}")
        sys.exit(1)

    scorer = RagaScorer.from_rules_file(rules_path)

    lib_dir = args.library or Path(f"data/phrases/{args.raga}")
    meta_path = lib_dir / "phrases_metadata.json"
    if not meta_path.exists():
        print(f"  ERROR: metadata not found: {meta_path}")
        sys.exit(1)

    with open(meta_path) as f:
        phrases = json.load(f)

    print(f"\n  Scoring {len(phrases)} phrases from {lib_dir} against {args.raga} rules\n")
    print(f"  {'ID':>25s}  {'Auth':>5s}  {'Scale':>5s}  {'Pakad':>5s}  {'Forbid':>6s}  {'Vadi':>5s}  {'Density':>7s}  Notes")
    print(f"  {'─'*25}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*6}  {'─'*5}  {'─'*7}  {'─'*30}")

    scored = []
    for p in phrases:
        enriched = scorer.score_phrase(p)
        scored.append(enriched)
        notes_str = " ".join(enriched["notes_detected"][:6])
        print(f"  {enriched['phrase_id']:>25s}"
              f"  {enriched['authenticity_score']:5.3f}"
              f"  {enriched['scale_compliance']:5.3f}"
              f"  {enriched['pakad_match_score']:5.3f}"
              f"  {enriched['forbidden_note_ratio']:6.3f}"
              f"  {enriched['vadi_emphasis']:5.3f}"
              f"  {enriched['phrase_density']:7.2f}"
              f"  {notes_str}")

    avg_auth = sum(s["authenticity_score"] for s in scored) / len(scored) if scored else 0
    avg_forbid = sum(s["forbidden_note_ratio"] for s in scored) / len(scored) if scored else 0
    print(f"\n  Average authenticity: {avg_auth:.3f}")
    print(f"  Average forbidden-note ratio: {avg_forbid:.3f}\n")


if __name__ == "__main__":
    main()
