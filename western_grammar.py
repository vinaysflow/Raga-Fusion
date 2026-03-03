#!/usr/bin/env python3
"""
western_grammar.py — Genre templates for fusion planning.

Defines BPM ranges, feel, arc shapes, and section-aware mix ratios.
"""

GENRE_TEMPLATES = {
    "lofi": {
        "bpm_range": (70, 90),
        "feel": "straight",
        "arc_shape": [
            {"section": "intro", "energy": 0.3},
            {"section": "development", "energy": 0.35},
            {"section": "peak", "energy": 0.4},
            {"section": "outro", "energy": 0.3},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.95, "harmony": 0.03, "rhythm": 0.02},
            "jod": {"raga": 0.8, "harmony": 0.15, "rhythm": 0.05},
            "gat": {"raga": 0.6, "harmony": 0.2, "rhythm": 0.2},
            "peak": {"raga": 0.55, "harmony": 0.2, "rhythm": 0.25},
            "resolution": {"raga": 0.7, "harmony": 0.2, "rhythm": 0.1},
        },
    },
    "ambient": {
        "bpm_range": (0, 70),
        "feel": "beatless",
        "arc_shape": [
            {"section": "intro", "energy": 0.2},
            {"section": "development", "energy": 0.3},
            {"section": "peak", "energy": 0.35},
            {"section": "outro", "energy": 0.2},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.98, "harmony": 0.02, "rhythm": 0.0},
            "jod": {"raga": 0.85, "harmony": 0.15, "rhythm": 0.0},
            "gat": {"raga": 0.7, "harmony": 0.25, "rhythm": 0.05},
            "peak": {"raga": 0.6, "harmony": 0.35, "rhythm": 0.05},
            "resolution": {"raga": 0.8, "harmony": 0.2, "rhythm": 0.0},
        },
    },
    "jazz": {
        "bpm_range": (100, 180),
        "feel": "swing",
        "arc_shape": [
            {"section": "head", "energy": 0.4},
            {"section": "solo", "energy": 0.6},
            {"section": "peak", "energy": 0.75},
            {"section": "head_out", "energy": 0.4},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.9, "harmony": 0.1, "rhythm": 0.0},
            "jod": {"raga": 0.75, "harmony": 0.2, "rhythm": 0.05},
            "gat": {"raga": 0.55, "harmony": 0.25, "rhythm": 0.2},
            "peak": {"raga": 0.45, "harmony": 0.25, "rhythm": 0.3},
            "resolution": {"raga": 0.6, "harmony": 0.25, "rhythm": 0.15},
        },
    },
    "rock": {
        "bpm_range": (120, 160),
        "feel": "straight",
        "arc_shape": [
            {"section": "verse", "energy": 0.5},
            {"section": "chorus", "energy": 0.8},
            {"section": "bridge", "energy": 0.65},
            {"section": "chorus_out", "energy": 0.85},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.85, "harmony": 0.1, "rhythm": 0.05},
            "gat": {"raga": 0.55, "harmony": 0.25, "rhythm": 0.2},
            "peak": {"raga": 0.45, "harmony": 0.3, "rhythm": 0.25},
            "resolution": {"raga": 0.6, "harmony": 0.25, "rhythm": 0.15},
        },
    },
    "punk": {
        "bpm_range": (160, 220),
        "feel": "straight",
        "raga_arc_override": "peak_only",
        "arc_shape": [
            {"section": "attack", "energy": 0.9},
            {"section": "attack", "energy": 0.95},
        ],
        "mix_ratios": {
            "peak": {"raga": 0.4, "harmony": 0.35, "rhythm": 0.25},
        },
    },
    "cinematic": {
        "bpm_range": (60, 120),
        "feel": "rubato",
        "arc_shape": [
            {"section": "intro", "energy": 0.3},
            {"section": "build", "energy": 0.6},
            {"section": "climax", "energy": 0.9},
            {"section": "outro", "energy": 0.4},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.9, "harmony": 0.1, "rhythm": 0.0},
            "gat": {"raga": 0.6, "harmony": 0.25, "rhythm": 0.15},
            "peak": {"raga": 0.45, "harmony": 0.35, "rhythm": 0.2},
            "resolution": {"raga": 0.7, "harmony": 0.2, "rhythm": 0.1},
        },
    },
    "new_age": {
        "bpm_range": (50, 80),
        "feel": "gentle",
        "arc_shape": [
            {"section": "intro", "energy": 0.25},
            {"section": "development", "energy": 0.35},
            {"section": "outro", "energy": 0.25},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.98, "harmony": 0.02, "rhythm": 0.0},
            "gat": {"raga": 0.75, "harmony": 0.2, "rhythm": 0.05},
            "resolution": {"raga": 0.85, "harmony": 0.15, "rhythm": 0.0},
        },
    },
    "electronic": {
        "bpm_range": (120, 140),
        "feel": "four_on_floor",
        "arc_shape": [
            {"section": "build", "energy": 0.5},
            {"section": "drop", "energy": 0.9},
            {"section": "plateau", "energy": 0.8},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.8, "harmony": 0.1, "rhythm": 0.1},
            "gat": {"raga": 0.55, "harmony": 0.2, "rhythm": 0.25},
            "peak": {"raga": 0.4, "harmony": 0.25, "rhythm": 0.35},
        },
    },
    "downtempo": {
        "bpm_range": (85, 105),
        "feel": "organic",
        "arc_shape": [
            {"section": "intro", "energy": 0.3},
            {"section": "development", "energy": 0.4},
            {"section": "peak", "energy": 0.5},
            {"section": "outro", "energy": 0.35},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.92, "harmony": 0.05, "rhythm": 0.03},
            "jod": {"raga": 0.78, "harmony": 0.12, "rhythm": 0.10},
            "gat": {"raga": 0.62, "harmony": 0.20, "rhythm": 0.18},
            "peak": {"raga": 0.52, "harmony": 0.22, "rhythm": 0.26},
            "resolution": {"raga": 0.75, "harmony": 0.15, "rhythm": 0.10},
        },
    },
    "reggae_dub": {
        "bpm_range": (60, 80),
        "feel": "offbeat",
        "arc_shape": [
            {"section": "intro", "energy": 0.35},
            {"section": "riddim", "energy": 0.5},
            {"section": "breakdown", "energy": 0.4},
            {"section": "outro", "energy": 0.35},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.88, "harmony": 0.06, "rhythm": 0.06},
            "jod": {"raga": 0.72, "harmony": 0.14, "rhythm": 0.14},
            "gat": {"raga": 0.55, "harmony": 0.22, "rhythm": 0.23},
            "peak": {"raga": 0.48, "harmony": 0.24, "rhythm": 0.28},
            "resolution": {"raga": 0.68, "harmony": 0.18, "rhythm": 0.14},
        },
    },
    "chillhop": {
        "bpm_range": (75, 95),
        "feel": "swing",
        "arc_shape": [
            {"section": "intro", "energy": 0.35},
            {"section": "development", "energy": 0.42},
            {"section": "peak", "energy": 0.48},
            {"section": "outro", "energy": 0.38},
        ],
        "mix_ratios": {
            "alap": {"raga": 0.90, "harmony": 0.06, "rhythm": 0.04},
            "jod": {"raga": 0.75, "harmony": 0.15, "rhythm": 0.10},
            "gat": {"raga": 0.58, "harmony": 0.22, "rhythm": 0.20},
            "peak": {"raga": 0.50, "harmony": 0.24, "rhythm": 0.26},
            "resolution": {"raga": 0.72, "harmony": 0.18, "rhythm": 0.10},
        },
    },
}

GENRE_TO_TEMPLATE = {
    "lofi": "lofi",
    "ambient": "ambient",
    "jazz": "jazz",
    "rock": "rock",
    "punk": "punk",
    "cinematic": "cinematic",
    "new_age": "new_age",
    "electronic": "electronic",
    "downtempo": "downtempo",
    "reggae_dub": "reggae_dub",
    "chillhop": "chillhop",
    "calm": "lofi",
    "upbeat": "lofi",
    "jazz_fusion": "jazz",
    "trap": "electronic",
    "bass_house": "electronic",
    "psytrance": "electronic",
}
