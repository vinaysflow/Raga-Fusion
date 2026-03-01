#!/usr/bin/env python3
"""
quality_metrics.py — Commercial-grade quality and authenticity evaluation.

Measures both production polish (LUFS, dynamic range, spectral balance,
true peak, noise floor) and raga authenticity (pakad, vadi, scale compliance,
forbidden notes) for generated tracks.

Usage (CLI):
    python quality_metrics.py output/track.wav --rules data/raga_rules/yaman.json
    python quality_metrics.py output/ --all-tracks

Usage (as module):
    from quality_metrics import evaluate_track, evaluate_all
    report = evaluate_track("output/track.wav", "data/raga_rules/yaman.json")
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("ERROR: soundfile required")
    sys.exit(1)

try:
    from scipy.signal import welch
except ImportError:
    print("ERROR: scipy required")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent


def _native(val):
    """Convert numpy scalars/booleans to Python native types for JSON serialization."""
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return round(float(val), 4)
    return val

# ═══════════════════════════════════════════════════════════════════════
#  Thresholds
# ═══════════════════════════════════════════════════════════════════════

THRESHOLDS = {
    "lufs_min": -16.0,
    "lufs_max": -10.0,
    "dynamic_range_min": 4.0,
    "dynamic_range_max": 14.0,
    "true_peak_max_db": -0.5,
    "noise_floor_max_db": -50.0,
    "bass_energy_min_pct": 5.0,
    "mid_energy_min_pct": 40.0,
    "high_energy_min_pct": 2.0,
    "auth_min": 0.3,
    "pakad_min": 0.1,
    "forbidden_max": 0.15,
    "scale_compliance_min": 0.5,
}


# ═══════════════════════════════════════════════════════════════════════
#  Polish metrics
# ═══════════════════════════════════════════════════════════════════════

def measure_lufs(audio: np.ndarray, sr: int) -> float:
    """Approximate integrated LUFS (mono, ITU-R BS.1770 approximation)."""
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
    if rms < 1e-10:
        return -100.0
    return round(20.0 * np.log10(rms) - 0.691, 2)


def measure_true_peak(audio: np.ndarray) -> float:
    """True peak in dBFS."""
    if audio.ndim == 2:
        peak = np.max(np.abs(audio))
    else:
        peak = np.max(np.abs(audio))
    if peak < 1e-10:
        return -100.0
    return round(20.0 * np.log10(peak), 2)


def measure_dynamic_range(audio: np.ndarray, sr: int) -> float:
    """Dynamic range: difference between loudest and softest RMS segments."""
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    seg_len = int(0.5 * sr)
    n_segs = max(len(audio) // seg_len, 1)
    rms_values = []
    for i in range(n_segs):
        chunk = audio[i * seg_len:(i + 1) * seg_len]
        if len(chunk) > 0:
            rms = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
            if rms > 1e-10:
                rms_values.append(20.0 * np.log10(rms))
    if len(rms_values) < 2:
        return 0.0
    return round(max(rms_values) - min(rms_values), 2)


def measure_noise_floor(audio: np.ndarray, sr: int) -> float:
    """Estimate noise floor from quietest 10% of segments."""
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    seg_len = int(0.1 * sr)
    n_segs = max(len(audio) // seg_len, 1)
    rms_values = []
    for i in range(n_segs):
        chunk = audio[i * seg_len:(i + 1) * seg_len]
        if len(chunk) > 0:
            rms = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
            rms_values.append(rms)
    if not rms_values:
        return -100.0
    rms_values.sort()
    bottom_10 = rms_values[:max(1, len(rms_values) // 10)]
    avg_floor = np.mean(bottom_10)
    if avg_floor < 1e-10:
        return -100.0
    return round(20.0 * np.log10(avg_floor), 2)


def measure_spectral_balance(audio: np.ndarray, sr: int) -> dict:
    """Spectral energy distribution across bass/mid/high bands."""
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    freqs, psd = welch(audio.astype(np.float64), fs=sr, nperseg=min(4096, len(audio)))
    total = np.sum(psd) + 1e-12

    bass_mask = (freqs >= 20) & (freqs < 200)
    mid_mask = (freqs >= 200) & (freqs < 4000)
    high_mask = (freqs >= 4000) & (freqs <= sr / 2)

    bass_pct = round(100.0 * np.sum(psd[bass_mask]) / total, 2)
    mid_pct = round(100.0 * np.sum(psd[mid_mask]) / total, 2)
    high_pct = round(100.0 * np.sum(psd[high_mask]) / total, 2)

    return {"bass_pct": bass_pct, "mid_pct": mid_pct, "high_pct": high_pct}


def evaluate_polish(audio: np.ndarray, sr: int) -> dict:
    """Evaluate production polish metrics."""
    lufs = measure_lufs(audio, sr)
    true_peak = measure_true_peak(audio)
    dr = measure_dynamic_range(audio, sr)
    noise_floor = measure_noise_floor(audio, sr)
    spectral = measure_spectral_balance(audio, sr)

    checks = []
    checks.append({
        "metric": "LUFS",
        "value": _native(lufs),
        "target": f"{THRESHOLDS['lufs_min']} to {THRESHOLDS['lufs_max']}",
        "pass": bool(THRESHOLDS["lufs_min"] <= lufs <= THRESHOLDS["lufs_max"]),
    })
    checks.append({
        "metric": "True Peak",
        "value": _native(true_peak),
        "target": f"< {THRESHOLDS['true_peak_max_db']} dBFS",
        "pass": bool(true_peak <= THRESHOLDS["true_peak_max_db"]),
    })
    checks.append({
        "metric": "Dynamic Range",
        "value": _native(dr),
        "target": f"{THRESHOLDS['dynamic_range_min']} - {THRESHOLDS['dynamic_range_max']} dB",
        "pass": bool(THRESHOLDS["dynamic_range_min"] <= dr <= THRESHOLDS["dynamic_range_max"]),
    })
    checks.append({
        "metric": "Noise Floor",
        "value": _native(noise_floor),
        "target": f"< {THRESHOLDS['noise_floor_max_db']} dBFS",
        "pass": bool(noise_floor <= THRESHOLDS["noise_floor_max_db"]),
    })
    checks.append({
        "metric": "Bass Energy",
        "value": _native(spectral["bass_pct"]),
        "target": f"> {THRESHOLDS['bass_energy_min_pct']}%",
        "pass": bool(spectral["bass_pct"] >= THRESHOLDS["bass_energy_min_pct"]),
    })
    checks.append({
        "metric": "Mid Energy",
        "value": _native(spectral["mid_pct"]),
        "target": f"> {THRESHOLDS['mid_energy_min_pct']}%",
        "pass": bool(spectral["mid_pct"] >= THRESHOLDS["mid_energy_min_pct"]),
    })
    checks.append({
        "metric": "High Energy",
        "value": _native(spectral["high_pct"]),
        "target": f"> {THRESHOLDS['high_energy_min_pct']}%",
        "pass": bool(spectral["high_pct"] >= THRESHOLDS["high_energy_min_pct"]),
    })

    passed = sum(1 for c in checks if c["pass"])
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "score": round(passed / len(checks), 3),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Authenticity metrics (uses raga_scorer on track-level analysis)
# ═══════════════════════════════════════════════════════════════════════

def evaluate_authenticity(wav_path: str, rules_path: str | None = None) -> dict:
    """Evaluate raga authenticity of a rendered track."""
    try:
        from analyze_raga import (
            load_audio, detect_pitches, detect_sa,
            analyze_note_distribution, identify_thaat, identify_raga,
        )
        from raga_scorer import RagaScorer
    except ImportError:
        return {"error": "analysis modules not available", "score": 0.0}

    y, sr, duration = load_audio(wav_path)
    analysis_seconds = min(duration, 30)
    y = y[:int(analysis_seconds * sr)]

    times, freqs, midi_notes, pitch_classes = detect_pitches(y, sr)
    if len(times) == 0:
        return {"error": "no pitched content", "score": 0.0}

    sa_pc, sa_note, sa_hz = detect_sa(pitch_classes)
    distribution = analyze_note_distribution(pitch_classes, midi_notes, times, sa_pc)
    thaat_matches = identify_thaat(distribution)
    raga_matches = identify_raga(thaat_matches, distribution)

    notes_detected = [d.get("svara", "Sa") for d in distribution if d.get("percentage", 0) > 2.0]

    fake_phrase = {
        "notes_detected": notes_detected,
        "duration": duration,
        "quality_score": 0.7,
    }

    scorer = None
    if rules_path and Path(rules_path).exists():
        scorer = RagaScorer.from_rules_file(rules_path)
    else:
        rules_dir = PROJECT_ROOT / "data" / "raga_rules"
        if raga_matches:
            best_raga = raga_matches[0]
            raga_name = best_raga[0] if isinstance(best_raga, tuple) else "yaman"
            rp = rules_dir / f"{raga_name.lower()}.json"
            if rp.exists():
                scorer = RagaScorer.from_rules_file(rp)

    if scorer is None:
        default_rules = rules_dir / "yaman.json"
        if default_rules.exists():
            scorer = RagaScorer.from_rules_file(default_rules)

    if scorer is None:
        return {"error": "no raga rules available", "score": 0.0}

    enriched = scorer.score_phrase(fake_phrase)

    checks = []
    checks.append({
        "metric": "Authenticity Score",
        "value": _native(enriched.get("authenticity_score", 0)),
        "target": f"> {THRESHOLDS['auth_min']}",
        "pass": bool(enriched.get("authenticity_score", 0) >= THRESHOLDS["auth_min"]),
    })
    checks.append({
        "metric": "Pakad Match",
        "value": _native(enriched.get("pakad_match_score", 0)),
        "target": f"> {THRESHOLDS['pakad_min']}",
        "pass": bool(enriched.get("pakad_match_score", 0) >= THRESHOLDS["pakad_min"]),
    })
    checks.append({
        "metric": "Forbidden Notes",
        "value": _native(enriched.get("forbidden_note_ratio", 0)),
        "target": f"< {THRESHOLDS['forbidden_max']}",
        "pass": bool(enriched.get("forbidden_note_ratio", 0) <= THRESHOLDS["forbidden_max"]),
    })
    checks.append({
        "metric": "Scale Compliance",
        "value": _native(enriched.get("scale_compliance", 0)),
        "target": f"> {THRESHOLDS['scale_compliance_min']}",
        "pass": bool(enriched.get("scale_compliance", 0) >= THRESHOLDS["scale_compliance_min"]),
    })

    passed = sum(1 for c in checks if c["pass"])

    detected_raga = "unknown"
    if raga_matches and isinstance(raga_matches[0], tuple):
        raga_obj = raga_matches[0][0]
        detected_raga = getattr(raga_obj, "name", str(raga_obj))
    detected_thaat = "unknown"
    if thaat_matches:
        thaat_val = thaat_matches[0][0] if isinstance(thaat_matches[0], tuple) else thaat_matches[0]
        detected_thaat = str(thaat_val)

    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "score": round(passed / len(checks), 3),
        "detected_raga": detected_raga,
        "detected_thaat": detected_thaat,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Combined evaluation
# ═══════════════════════════════════════════════════════════════════════

def evaluate_track(wav_path: str, rules_path: str | None = None) -> dict:
    """Full quality evaluation: polish + authenticity."""
    audio, sr = sf.read(wav_path, dtype="float32")
    duration = len(audio) / sr if audio.ndim == 1 else len(audio) / sr

    polish = evaluate_polish(audio, sr)
    auth = evaluate_authenticity(wav_path, rules_path)

    overall_score = (polish["score"] * 0.5 + auth.get("score", 0) * 0.5)

    return {
        "file": wav_path,
        "duration": round(duration, 2),
        "polish": polish,
        "authenticity": auth,
        "overall_score": round(overall_score, 3),
        "commercial_ready": polish["score"] >= 0.7 and auth.get("score", 0) >= 0.5,
    }


def evaluate_all(directory: str | Path, rules_dir: str | Path | None = None) -> list[dict]:
    """Evaluate all WAV tracks in a directory."""
    directory = Path(directory)
    rules_dir = Path(rules_dir) if rules_dir else PROJECT_ROOT / "data" / "raga_rules"
    results = []

    for wav_path in sorted(directory.glob("*.wav")):
        if wav_path.name.startswith("."):
            continue

        meta_path = wav_path.with_suffix(".json")
        raga = "yaman"
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                raga = meta.get("raga", "yaman")
            except Exception:
                pass

        rp = rules_dir / f"{raga}.json"
        rules_path = str(rp) if rp.exists() else None

        try:
            result = evaluate_track(str(wav_path), rules_path)
            results.append(result)
        except Exception as e:
            results.append({"file": str(wav_path), "error": str(e)})

    return results


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Evaluate track quality and authenticity.")
    parser.add_argument("path", type=str, help="WAV file or directory")
    parser.add_argument("--rules", type=str, default=None, help="Raga rules JSON path")
    parser.add_argument("--all-tracks", action="store_true", help="Evaluate all tracks in dir")
    args = parser.parse_args()

    path = Path(args.path)

    if args.all_tracks or path.is_dir():
        results = evaluate_all(str(path))
        print(f"\n{'='*68}")
        print("  QUALITY EVALUATION REPORT")
        print(f"{'='*68}\n")

        for r in results:
            if "error" in r and isinstance(r.get("error"), str):
                print(f"  {Path(r['file']).name}: ERROR — {r['error']}")
                continue

            p = r.get("polish", {})
            a = r.get("authenticity", {})
            status = "PASS" if r.get("commercial_ready") else "NEEDS WORK"
            print(f"  {Path(r['file']).name}")
            print(f"    Polish: {p.get('passed', 0)}/{p.get('total', 0)}  "
                  f"Auth: {a.get('passed', 0)}/{a.get('total', 0)}  "
                  f"Overall: {r.get('overall_score', 0):.0%}  [{status}]")

        print(f"\n{'='*68}\n")
    else:
        result = evaluate_track(str(path), args.rules)
        print(f"\n{'='*68}")
        print(f"  QUALITY REPORT: {path.name}")
        print(f"{'='*68}\n")

        print("  PRODUCTION POLISH")
        print(f"  {'─'*60}")
        for c in result.get("polish", {}).get("checks", []):
            status = "PASS" if c["pass"] else "FAIL"
            print(f"    {c['metric']:<20s}  {c['value']:>8}  target: {c['target']:<20s}  [{status}]")

        print(f"\n  RAGA AUTHENTICITY")
        print(f"  {'─'*60}")
        for c in result.get("authenticity", {}).get("checks", []):
            status = "PASS" if c["pass"] else "FAIL"
            val = c["value"]
            if isinstance(val, float):
                val = f"{val:.3f}"
            print(f"    {c['metric']:<20s}  {val:>8}  target: {c['target']:<20s}  [{status}]")

        overall = result.get("overall_score", 0)
        ready = result.get("commercial_ready", False)
        print(f"\n  Overall: {overall:.0%}  {'COMMERCIAL READY' if ready else 'NEEDS WORK'}")
        print(f"\n{'='*68}\n")


if __name__ == "__main__":
    main()
