#!/usr/bin/env python3
"""
audio_analyzer.py — Consumer input analysis pipeline.

Analyzes an uploaded audio file (MP3/WAV) and returns structured intelligence:
raga likelihoods, tonal center, energy/density profile, motif hints, and
derived intent tags. This powers the consumer flow: "here's my song, find me
the best fusion."

Usage (as module):
    from audio_analyzer import analyze_upload
    result = analyze_upload("/path/to/song.mp3")

Usage (CLI):
    python audio_analyzer.py /path/to/song.mp3
"""

import json
import sys
from pathlib import Path

import numpy as np

try:
    import librosa
except ImportError:
    print("ERROR: librosa required. pip install librosa")
    sys.exit(1)

try:
    import soundfile as sf
except ImportError:
    print("ERROR: soundfile required. pip install soundfile")
    sys.exit(1)

from analyze_raga import (
    SAMPLE_RATE, HOP_LENGTH, FRAME_DURATION,
    DEGREE_TO_SVARA, DEGREE_INFO,
    load_audio, detect_pitches, detect_sa,
    analyze_note_distribution, identify_thaat, identify_raga,
)

PROJECT_ROOT = Path(__file__).resolve().parent
RULES_DIR = PROJECT_ROOT / "data" / "raga_rules"


# ═══════════════════════════════════════════════════════════════════════
#  Energy / density helpers
# ═══════════════════════════════════════════════════════════════════════

def _compute_energy_profile(y: np.ndarray, sr: int, n_segments: int = 10) -> dict:
    """Split audio into segments and compute RMS energy per segment."""
    seg_len = len(y) // n_segments
    energies = []
    for i in range(n_segments):
        chunk = y[i * seg_len:(i + 1) * seg_len]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        energies.append(round(rms, 4))
    avg = float(np.mean(energies))
    peak_idx = int(np.argmax(energies))
    return {
        "segment_energies": energies,
        "avg_energy": round(avg, 4),
        "peak_segment": peak_idx,
        "dynamic_range_db": round(
            20 * np.log10(max(energies) / max(min(energies), 1e-8)), 2
        ),
    }


def _compute_density(times: np.ndarray, duration: float) -> dict:
    """Compute note density (pitched frames per second)."""
    if duration <= 0:
        return {"notes_per_second": 0.0, "density_label": "silent"}
    nps = len(times) * FRAME_DURATION / duration * (1 / FRAME_DURATION)
    nps = len(times) / (duration / FRAME_DURATION) if duration > 0 else 0
    nps = float(len(times)) / max(duration, 0.1)
    if nps < 3:
        label = "sparse"
    elif nps < 8:
        label = "medium"
    else:
        label = "dense"
    return {"notes_per_second": round(nps, 2), "density_label": label}


def _compute_tempo_estimate(y: np.ndarray, sr: int) -> dict:
    """Estimate tempo from onset strength."""
    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, '__len__'):
            tempo = float(tempo[0])
        return {"estimated_bpm": round(float(tempo), 1), "beat_count": len(beats)}
    except Exception:
        return {"estimated_bpm": 0.0, "beat_count": 0}


def _derive_intent_tags(density: dict, energy: dict, raga_matches: list,
                        tempo: dict) -> list[str]:
    """Derive intent tags from analysis results."""
    tags = []
    d_label = density.get("density_label", "medium")
    if d_label == "sparse":
        tags.append("meditative")
    elif d_label == "dense":
        tags.append("energetic")

    if energy.get("avg_energy", 0) < 0.05:
        tags.append("calm")
    elif energy.get("avg_energy", 0) > 0.15:
        tags.append("intense")

    bpm = tempo.get("estimated_bpm", 0)
    if bpm > 0 and bpm < 80:
        tags.append("contemplative")
    elif bpm > 120:
        tags.append("vibrant")

    if raga_matches:
        best = raga_matches[0]
        mood = best.get("mood", [])
        for m in mood:
            ml = m.lower()
            if ml in ("serene", "devotional", "romantic"):
                tags.append("meditative")
            elif ml in ("majestic", "serious"):
                tags.append("intense")

    return list(set(tags))


def _load_raga_rules(raga_name: str) -> dict | None:
    path = RULES_DIR / f"{raga_name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


# ═══════════════════════════════════════════════════════════════════════
#  Main analysis
# ═══════════════════════════════════════════════════════════════════════

def analyze_upload(filepath: str, sa_override: str | None = None,
                   max_analysis_seconds: float = 120.0) -> dict:
    """Analyze an uploaded audio file and return structured intelligence.

    Returns a dict with:
        raga: best raga match info
        raga_candidates: top 3 raga matches
        tonal_center: detected Sa info
        energy_profile: segment-level energy analysis
        density: note density analysis
        tempo: BPM estimate
        intent_tags: derived intent tags for the recommender
        thaat: best thaat match
        scale_degrees: detected degrees present
        confidence: overall confidence score
    """
    y, sr, duration = load_audio(filepath)

    if duration > max_analysis_seconds:
        samples_to_keep = int(max_analysis_seconds * sr)
        y = y[:samples_to_keep]
        duration = max_analysis_seconds

    times, freqs, midi_notes, pitch_classes = detect_pitches(y, sr)

    if len(times) == 0:
        return {
            "error": "No pitched content detected",
            "raga": None,
            "raga_candidates": [],
            "tonal_center": None,
            "intent_tags": ["ambient"],
        }

    sa_pc, sa_note, sa_hz = detect_sa(pitch_classes, sa_override=sa_override)

    distribution = analyze_note_distribution(pitch_classes, midi_notes, times, sa_pc)
    thaat_matches = identify_thaat(distribution)
    raga_matches = identify_raga(thaat_matches, distribution)

    energy = _compute_energy_profile(y, sr)
    density = _compute_density(times, duration)
    tempo = _compute_tempo_estimate(y, sr)

    raga_candidates = []
    for rm in raga_matches[:3]:
        entry = {
            "raga": rm.name if hasattr(rm, 'name') else str(rm),
            "confidence": 0.0,
        }
        if isinstance(rm, tuple) and len(rm) >= 2:
            entry["raga"] = rm[0]
            entry["confidence"] = round(rm[1], 3)
        elif hasattr(rm, 'name') and hasattr(rm, 'score'):
            entry["raga"] = rm.name
            entry["confidence"] = round(rm.score, 3)
        raga_candidates.append(entry)

    best_raga = raga_candidates[0]["raga"] if raga_candidates else "yaman"
    best_confidence = raga_candidates[0]["confidence"] if raga_candidates else 0.0

    best_thaat = thaat_matches[0][0] if thaat_matches else "bilaval"
    best_thaat_score = round(thaat_matches[0][1], 3) if thaat_matches else 0.0

    detected_degrees = sorted(set(d["degree"] for d in distribution if d.get("degree") is not None))

    rules = _load_raga_rules(best_raga.lower() if isinstance(best_raga, str) else "yaman")
    raga_info = {}
    if rules:
        raga_info = {
            "name": rules.get("raga", {}).get("name", best_raga),
            "thaat": rules.get("raga", {}).get("thaat", ""),
            "mood": rules.get("context", {}).get("mood", []),
            "time": rules.get("context", {}).get("time", {}).get("window", ""),
            "description": rules.get("raga", {}).get("description", ""),
        }

    intent_tags = _derive_intent_tags(density, energy, [raga_info] if raga_info else [], tempo)

    return {
        "filepath": str(filepath),
        "duration": round(duration, 2),
        "raga": {
            "best_match": best_raga,
            "confidence": best_confidence,
            "info": raga_info,
        },
        "raga_candidates": raga_candidates,
        "tonal_center": {
            "sa_note": sa_note,
            "sa_hz": round(sa_hz, 2),
            "sa_pitch_class": int(sa_pc),
        },
        "thaat": {
            "name": best_thaat,
            "score": best_thaat_score,
        },
        "scale_degrees": detected_degrees,
        "energy_profile": energy,
        "density": density,
        "tempo": tempo,
        "intent_tags": intent_tags,
        "confidence": round(best_confidence, 3),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python audio_analyzer.py <audio_file> [--sa NOTE]")
        sys.exit(1)

    filepath = sys.argv[1]
    sa = None
    if "--sa" in sys.argv:
        idx = sys.argv.index("--sa")
        if idx + 1 < len(sys.argv):
            sa = sys.argv[idx + 1]

    print(f"\n  Analyzing: {filepath}")
    result = analyze_upload(filepath, sa_override=sa)

    print(f"\n  Duration: {result['duration']}s")
    if result.get("raga"):
        r = result["raga"]
        print(f"  Best raga: {r['best_match']} ({r['confidence']*100:.0f}% confidence)")
    if result.get("tonal_center"):
        tc = result["tonal_center"]
        print(f"  Tonal center (Sa): {tc['sa_note']} ({tc['sa_hz']} Hz)")
    if result.get("thaat"):
        print(f"  Thaat: {result['thaat']['name']} (score: {result['thaat']['score']})")
    if result.get("density"):
        d = result["density"]
        print(f"  Density: {d['density_label']} ({d['notes_per_second']} notes/s)")
    if result.get("tempo"):
        t = result["tempo"]
        print(f"  Tempo: ~{t['estimated_bpm']} BPM")
    if result.get("intent_tags"):
        print(f"  Intent tags: {', '.join(result['intent_tags'])}")
    print()


if __name__ == "__main__":
    main()
