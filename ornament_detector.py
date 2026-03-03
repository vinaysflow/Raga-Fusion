#!/usr/bin/env python3
"""
ornament_detector.py — Rule-based ornament detection from f0 contours.

Detects common Hindustani ornaments using duration + oscillation heuristics.
Thresholds are guided by the 2025 ROD dataset annotation rules.

Confidence floor: Only events with confidence >= CONFIDENCE_FLOOR are emitted.
This reduces false positives (F1 was 0.011) that actively degraded scoring.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

import numpy as np

CONFIDENCE_FLOOR = float(os.environ.get("RF_ORNAMENT_CONFIDENCE_FLOOR", "0.5"))

ROD_RULES = {
    "kan": {"max_sec": 0.25, "min_amp": 0.7, "max_reversals": 2},
    "meend": {"min_sec": 0.50, "max_sec": 2.00, "min_amp": 2.0, "max_reversals": 2},
    "murki": {"min_sec": 0.25, "max_sec": 0.80, "min_reversals": 5, "max_amp": 3.0},
    "nyas_svar": {"min_sec": 0.80, "max_std": 0.12, "max_amp": 0.8},
    "andolan": {"min_sec": 1.00, "max_sec": 4.00, "max_amp": 0.9, "max_reversals": 4},
    "gamak": {"min_sec": 0.40, "max_sec": 2.00, "min_amp": 2.5, "min_reversals": 8},
}


@dataclass
class OrnamentEvent:
    ornament: str
    start_sec: float
    end_sec: float
    duration_sec: float
    amplitude_semitones: float
    reversals: int
    confidence: float

    def to_dict(self) -> dict:
        return {
            "ornament": self.ornament,
            "start_sec": round(self.start_sec, 3),
            "end_sec": round(self.end_sec, 3),
            "duration_sec": round(self.duration_sec, 3),
            "amplitude_semitones": round(self.amplitude_semitones, 3),
            "reversals": int(self.reversals),
            "confidence": round(self.confidence, 2),
        }


def _hz_to_semitones(hz: np.ndarray) -> np.ndarray:
    hz = np.asarray(hz, dtype=float)
    hz = np.where(hz <= 0, np.nan, hz)
    return 12 * np.log2(hz / 440.0) + 69


def _voiced_segments(voiced: np.ndarray) -> list[tuple[int, int]]:
    segments = []
    start = None
    for i, v in enumerate(voiced):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segments.append((start, i))
            start = None
    if start is not None:
        segments.append((start, len(voiced)))
    return segments


def _count_reversals(values: np.ndarray) -> int:
    if len(values) < 3:
        return 0
    diff = np.diff(values)
    signs = np.sign(diff)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0
    return int(np.sum(signs[:-1] * signs[1:] < 0))


def _classify_segment(duration: float, amp: float, reversals: int, std: float) -> str | None:
    if (
        duration >= ROD_RULES["nyas_svar"]["min_sec"]
        and amp <= ROD_RULES["nyas_svar"]["max_amp"]
        and std <= ROD_RULES["nyas_svar"]["max_std"]
    ):
        return "nyas_svar"
    if (
        duration >= ROD_RULES["gamak"]["min_sec"]
        and duration <= ROD_RULES["gamak"]["max_sec"]
        and amp >= ROD_RULES["gamak"]["min_amp"]
        and reversals >= ROD_RULES["gamak"]["min_reversals"]
    ):
        return "gamak"
    if (
        duration >= ROD_RULES["andolan"]["min_sec"]
        and duration <= ROD_RULES["andolan"]["max_sec"]
        and amp <= ROD_RULES["andolan"]["max_amp"]
        and reversals <= ROD_RULES["andolan"]["max_reversals"]
    ):
        return "andolan"
    if (
        duration >= ROD_RULES["meend"]["min_sec"]
        and duration <= ROD_RULES["meend"]["max_sec"]
        and amp >= ROD_RULES["meend"]["min_amp"]
        and reversals <= ROD_RULES["meend"]["max_reversals"]
    ):
        return "meend"
    if (
        duration >= ROD_RULES["murki"]["min_sec"]
        and duration <= ROD_RULES["murki"]["max_sec"]
        and reversals >= ROD_RULES["murki"]["min_reversals"]
        and amp <= ROD_RULES["murki"]["max_amp"]
    ):
        return "murki"
    if (
        duration <= ROD_RULES["kan"]["max_sec"]
        and amp >= ROD_RULES["kan"]["min_amp"]
        and reversals <= ROD_RULES["kan"]["max_reversals"]
    ):
        return "kan"
    return None


def detect_ornaments(f0: Iterable[float], voiced: Iterable[bool], sr: int, hop_length: int) -> list[dict]:
    """
    Detect ornaments from an f0 contour and voiced mask.

    Returns a list of ornament dicts with start/end seconds and features.
    """
    f0 = np.asarray(f0, dtype=float)
    voiced = np.asarray(voiced, dtype=bool)
    segments = _voiced_segments(voiced)
    ornaments: list[OrnamentEvent] = []

    for start, end in segments:
        seg_f0 = f0[start:end]
        seg_f0 = seg_f0[~np.isnan(seg_f0)]
        if len(seg_f0) < 3:
            continue
        seg_st = start * hop_length / sr
        seg_et = end * hop_length / sr
        duration = seg_et - seg_st

        semitones = _hz_to_semitones(seg_f0)
        semitones = semitones[~np.isnan(semitones)]
        if len(semitones) < 3:
            continue
        amp = float(np.nanmax(semitones) - np.nanmin(semitones))
        reversals = _count_reversals(semitones)
        std = float(np.nanstd(semitones))

        ornament = _classify_segment(duration, amp, reversals, std)
        if ornament:
            confidence = min(1.0, 0.4 + (amp / 4.0))
            if confidence >= CONFIDENCE_FLOOR:
                ornaments.append(
                    OrnamentEvent(
                        ornament=ornament,
                        start_sec=seg_st,
                        end_sec=seg_et,
                        duration_sec=duration,
                        amplitude_semitones=amp,
                        reversals=reversals,
                        confidence=confidence,
                    )
                )

    return [o.to_dict() for o in ornaments]
