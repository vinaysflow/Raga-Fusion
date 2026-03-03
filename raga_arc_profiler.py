#!/usr/bin/env python3
"""
raga_arc_profiler.py — Heuristic arc section classifier for raga phrases.

Classifies a phrase into arc sections based on energy, density, tempo
confidence, register, and position in the full performance.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def infer_register(median_hz: float, sa_hz: float) -> str:
    """
    Infer register from median pitch relative to Sa.
    Returns: 'lower', 'middle', or 'upper'
    """
    if sa_hz <= 0:
        return "middle"
    ratio = median_hz / sa_hz
    if ratio < 0.75:
        return "lower"
    if ratio > 1.5:
        return "upper"
    return "middle"


def classify_arc_section(
    energy_level: float,
    note_density: float,
    tempo_confidence: float,
    register: str,
    position_ratio: float,
) -> Tuple[str, float]:
    """
    Return (arc_section, confidence).

    Sections:
      alap_opening, alap_upper, jod, vilambit_gat, gat_development,
      peak_taan, resolution
    """
    # Early alap
    if position_ratio <= 0.15 and energy_level <= 0.25 and tempo_confidence < 0.2:
        return "alap_opening", 0.75
    if position_ratio <= 0.35 and tempo_confidence < 0.25 and register == "upper":
        return "alap_upper", 0.7

    # Jod / Gat transitions
    if tempo_confidence >= 0.3 and tempo_confidence < 0.55 and note_density < 6:
        return "jod", 0.6
    if tempo_confidence >= 0.55 and note_density < 6:
        return "vilambit_gat", 0.6

    # Peak / resolution
    if note_density >= 6 and energy_level >= 0.5:
        return "peak_taan", 0.65
    if position_ratio >= 0.8:
        return "resolution", 0.6

    return "gat_development", 0.5


def compute_note_density(note_count: int, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    return float(note_count) / duration_sec


def median_f0(f0: np.ndarray) -> float:
    f0 = np.asarray(f0, dtype=float)
    f0 = f0[~np.isnan(f0)]
    if len(f0) == 0:
        return 0.0
    return float(np.median(f0))
