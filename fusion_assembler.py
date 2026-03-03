#!/usr/bin/env python3
"""
fusion_assembler.py — Align raga arc with western genre arc and assemble.

This module produces a fused arc plan and assembles a track by reusing
the existing phrase assembly logic from assemble_track.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import soundfile as sf

from assemble_track import (
    assemble_final_track,
    load_phrase_library,
    select_phrases,
    select_phrases_from_plan,
)
from western_grammar import GENRE_TEMPLATES, GENRE_TO_TEMPLATE

PROJECT_ROOT = Path(__file__).resolve().parent
COMPAT_PATH = PROJECT_ROOT / "data" / "compatibility_map.json"


DEFAULT_ARC_PROFILE = {
    "opening_energy": 0.35,
    "peak_ceiling": 0.75,
    "peak_position_ratio": 0.65,
    "alap_ratio": 0.3,
}

ARC_SECTION_MAP = {
    "alap": {"alap_opening", "alap_upper"},
    "jod": {"jod"},
    "gat": {"vilambit_gat", "gat_development"},
    "peak": {"peak_taan"},
    "resolution": {"resolution"},
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


def _intent_score(phrase: dict, intent_tags: list[str]) -> float:
    """Score how well a phrase matches intent tags (density-based + tag overlap)."""
    if not intent_tags:
        return 0.5
    density = phrase.get("phrase_density")
    if density is None:
        notes = phrase.get("notes_detected") or []
        dur = max(phrase.get("duration"), 0.1)
        density = len(notes) / dur if dur else 5.0
    desired_density = "medium"
    for tag in intent_tags:
        if tag in INTENT_DENSITY:
            desired_density = INTENT_DENSITY[tag]
            break
    base = 0.6
    if desired_density == "sparse" and density < 4.0:
        base = 1.0
    elif desired_density == "sparse" and density > 8.0:
        base = 0.2
    elif desired_density == "dense" and density > 6.0:
        base = 1.0
    elif desired_density == "dense" and density < 3.0:
        base = 0.2
    # Bonus when phrase intent_tags overlap with request
    phrase_tags = set(phrase.get("intent_tags") or [])
    req_tags = set(intent_tags)
    overlap = len(phrase_tags & req_tags) / max(len(req_tags), 1)
    if overlap > 0:
        base = min(1.0, base + 0.15 * overlap)
    return base


def _load_compat() -> dict:
    if not COMPAT_PATH.exists():
        return {}
    with open(COMPAT_PATH) as f:
        return json.load(f)


MIX_DEFAULTS = {
    "alap": {"raga": 0.9, "harmony": 0.1, "rhythm": 0.0},
    "jod": {"raga": 0.8, "harmony": 0.15, "rhythm": 0.05},
    "gat": {"raga": 0.6, "harmony": 0.2, "rhythm": 0.2},
    "peak": {"raga": 0.5, "harmony": 0.25, "rhythm": 0.25},
    "resolution": {"raga": 0.7, "harmony": 0.2, "rhythm": 0.1},
}


def _western_peak_ratio(arc_shape: list) -> float | None:
    """Infer peak position from western arc_shape energy curve."""
    if not arc_shape:
        return None
    best_idx = max(range(len(arc_shape)), key=lambda i: arc_shape[i].get("energy", 0))
    return (best_idx + 0.5) / len(arc_shape)


def align_arcs(raga: str, genre: str, duration_sec: int, fusion_style: str = "balanced") -> dict:
    """
    Create a fused arc plan with section timings and mix ratios.
    Uses western_grammar genre templates for mix ratios and energy-based peak alignment.
    """
    compat = _load_compat().get("ragas", {}).get(raga, {})
    arc_profile = compat.get("arc_profile") or DEFAULT_ARC_PROFILE

    alap_ratio = arc_profile.get("alap_ratio", DEFAULT_ARC_PROFILE["alap_ratio"])
    peak_pos = arc_profile.get("peak_position_ratio", DEFAULT_ARC_PROFILE["peak_position_ratio"])

    template_name = GENRE_TO_TEMPLATE.get(genre, "lofi")
    template = GENRE_TEMPLATES.get(template_name, GENRE_TEMPLATES.get("lofi", {}))
    mix_ratios = template.get("mix_ratios") or MIX_DEFAULTS

    if fusion_style == "balanced" and template.get("arc_shape"):
        western_peak = _western_peak_ratio(template["arc_shape"])
        if western_peak is not None:
            peak_pos = 0.7 * peak_pos + 0.3 * western_peak

    sections = [
        {"name": "alap", "start": 0.0, "end": alap_ratio},
        {"name": "jod", "start": alap_ratio, "end": min(0.55, peak_pos - 0.15)},
        {"name": "gat", "start": min(0.55, peak_pos - 0.15), "end": peak_pos},
        {"name": "peak", "start": peak_pos, "end": min(0.85, peak_pos + 0.15)},
        {"name": "resolution", "start": min(0.85, peak_pos + 0.15), "end": 1.0},
    ]

    plan_sections = []
    for s in sections:
        mix = mix_ratios.get(s["name"]) or MIX_DEFAULTS.get(s["name"], MIX_DEFAULTS["gat"])
        plan_sections.append({
            "section": s["name"],
            "start_sec": round(s["start"] * duration_sec, 2),
            "end_sec": round(s["end"] * duration_sec, 2),
            "mix": mix,
        })

    return {
        "raga": raga,
        "genre": genre,
        "duration_sec": duration_sec,
        "fusion_style": fusion_style,
        "template": template_name,
        "sections": plan_sections,
    }


def assemble_fusion_track(plan: dict, phrase_library: Path, output_path: Path) -> Path:
    """
    Assemble a track from the phrase library using the plan's duration.
    """
    phrases = load_phrase_library(phrase_library)
    target_duration = plan.get("duration_sec", 60)
    sequence = plan.get("phrase_sequence")

    if not sequence and plan.get("sections"):
        intent_tags = plan.get("intent_tags") or []
        sequence = _build_sequence_from_sections(plan["sections"], phrases, intent_tags=intent_tags)
        if sequence:
            plan["phrase_sequence"] = sequence

    if sequence:
        selected = select_phrases_from_plan(sequence, phrases)
    else:
        selected = select_phrases(target_duration, phrases)

    if not selected:
        raise RuntimeError("No phrases selected for fusion assembly")

    sr = selected[0]["sr"]
    audio = assemble_final_track(selected, crossfade_dur=0.75, sr=sr)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), audio, sr)
    return output_path


def _build_sequence_from_sections(sections: list[dict], phrases: list[dict],
                                  intent_tags: list[str] | None = None) -> list[str]:
    by_id = {p["phrase_id"]: p for p in phrases}
    used = set()
    sequence: list[str] = []
    intent_tags = intent_tags or []

    for section in sections:
        name = section.get("section", "")
        start = section.get("start_sec", 0.0)
        end = section.get("end_sec", 0.0)
        target = max(0.0, end - start)
        if target <= 0:
            continue

        arc_targets = ARC_SECTION_MAP.get(name, set())
        candidates = [
            p for p in phrases
            if p["phrase_id"] not in used
            and (not arc_targets or p.get("arc_section") in arc_targets)
        ]
        if not candidates:
            candidates = [p for p in phrases if p["phrase_id"] not in used]

        # Sort by intent match (when intent_tags given) then quality
        if intent_tags:
            candidates.sort(key=lambda p: (
                -_intent_score(p, intent_tags),
                -p.get("quality_score", 0.0),
                p["phrase_id"],
            ))
        else:
            candidates.sort(key=lambda p: (-p.get("quality_score", 0.0), p["phrase_id"]))

        acc = 0.0
        for p in candidates:
            if acc >= target:
                break
            sequence.append(p["phrase_id"])
            used.add(p["phrase_id"])
            acc += max(p.get("duration", 0.0), 0.0)

    # Ensure no missing phrase IDs
    return [pid for pid in sequence if pid in by_id]
