#!/usr/bin/env python3
"""
validate_track.py — Automated Track Validation

Runs 5 automated checks against a produced raga-fusion track:

  1. Coherence     — energy consistency, no clicks/pops
  2. Raga identity — thaat and raga detection via analyze_raga.py
  3. Transitions   — no amplitude jumps or silence gaps
  4. Fusion balance — bass / mid / high spectral energy present
  5. Duration      — within target range, no leading/trailing silence

Usage:
    python validate_track.py yaman_lofi_final.wav
    python validate_track.py yaman_lofi_final.wav --melody yaman_test_30s.wav

Requires:
    pip install -r requirements.txt
    (numpy, soundfile, scipy, librosa)
"""

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("\n  ERROR: soundfile is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

try:
    from scipy.signal import welch
except ImportError:
    print("\n  ERROR: scipy is required but not installed.\n")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
#  Thresholds (tune as needed)
# ═══════════════════════════════════════════════════════════════════════

ENERGY_CV_MAX = 0.80
CLICK_COUNT_MAX = 5
CLICK_ZCR_MULTIPLIER = 3.0

RAGA_MIN_CONFIDENCE = 0.40
EXPECTED_THAAT = "Kalyan"
EXPECTED_RAGA = "Yaman"

MAX_AMPLITUDE_JUMP = 0.15
MAX_SILENCE_GAP_SEC = 0.20
SILENCE_THRESHOLD_DB = -40.0

BASS_MIN_PCT = 5.0       # 20-200 Hz
MID_MIN_PCT = 40.0       # 200-4000 Hz
HIGH_MIN_PCT = 2.0        # 4000-Nyquist

DURATION_MIN = 28.0
DURATION_MAX = 35.0
MAX_EDGE_SILENCE = 0.5

RMS_WINDOW = 0.5          # seconds for energy CV computation


# ═══════════════════════════════════════════════════════════════════════
#  Check 1: Coherence
# ═══════════════════════════════════════════════════════════════════════

def check_coherence(audio: np.ndarray, sr: int) -> list[dict]:
    """Energy consistency and click/pop detection."""
    results = []

    # --- Energy CV ---
    win = int(RMS_WINDOW * sr)
    hop = win // 2
    rms_vals = []
    for start in range(0, len(audio) - win, hop):
        chunk = audio[start:start + win]
        rms_vals.append(np.sqrt(np.mean(chunk ** 2)))
    rms_arr = np.array(rms_vals)
    mean_rms = np.mean(rms_arr)
    cv = float(np.std(rms_arr) / mean_rms) if mean_rms > 1e-8 else 999.0
    results.append({
        "name": "Energy consistency (CV)",
        "value": f"{cv:.2f}",
        "threshold": f"< {ENERGY_CV_MAX:.2f}",
        "passed": cv < ENERGY_CV_MAX,
    })

    # --- Click/pop count via ZCR spikes ---
    frame_len = int(0.01 * sr)  # 10ms
    zcr_vals = []
    for start in range(0, len(audio) - frame_len, frame_len):
        chunk = audio[start:start + frame_len]
        crossings = np.sum(np.abs(np.diff(np.sign(chunk))) > 0)
        zcr_vals.append(crossings)
    zcr_arr = np.array(zcr_vals, dtype=np.float64)
    median_zcr = np.median(zcr_arr)
    click_count = int(np.sum(zcr_arr > CLICK_ZCR_MULTIPLIER * median_zcr))
    results.append({
        "name": "Click/pop count",
        "value": str(click_count),
        "threshold": f"< {CLICK_COUNT_MAX}",
        "passed": click_count < CLICK_COUNT_MAX,
    })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Check 2: Raga Identity
# ═══════════════════════════════════════════════════════════════════════

def check_raga_identity(audio_path: str) -> list[dict]:
    """Run analyze_raga.py and parse its output."""
    results = []

    try:
        proc = subprocess.run(
            [sys.executable, "analyze_raga.py", audio_path],
            capture_output=True, text=True, timeout=300,
        )
        output = proc.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        results.append({
            "name": "Raga analysis",
            "value": f"ERROR: {e}",
            "threshold": "",
            "passed": False,
        })
        return results

    # Parse thaat
    thaat_match = re.search(r"Thaat:\s+(\w+)", output)
    detected_thaat = thaat_match.group(1) if thaat_match else "unknown"
    results.append({
        "name": "Detected thaat",
        "value": detected_thaat,
        "threshold": EXPECTED_THAAT,
        "passed": detected_thaat.lower() == EXPECTED_THAAT.lower(),
    })

    # Parse raga and confidence
    raga_match = re.search(
        r"Best Match:\s+Raga\s+(\w+)\s+\(Confidence:\s+(\d+)%\)", output
    )
    if raga_match:
        raga_name = raga_match.group(1)
        confidence = int(raga_match.group(2)) / 100.0
        results.append({
            "name": "Top raga match",
            "value": f"{raga_name} ({confidence:.0%})",
            "threshold": f"{EXPECTED_RAGA} >= {RAGA_MIN_CONFIDENCE:.0%}",
            "passed": (raga_name.lower() == EXPECTED_RAGA.lower()
                       and confidence >= RAGA_MIN_CONFIDENCE),
        })
    else:
        results.append({
            "name": "Top raga match",
            "value": "not detected",
            "threshold": f"{EXPECTED_RAGA} >= {RAGA_MIN_CONFIDENCE:.0%}",
            "passed": False,
        })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Check 3: Smooth Transitions
# ═══════════════════════════════════════════════════════════════════════

def check_transitions(audio: np.ndarray, sr: int) -> list[dict]:
    """Amplitude discontinuities and silence gaps."""
    results = []

    # --- Max sample-to-sample jump ---
    diffs = np.abs(np.diff(audio.astype(np.float64)))
    max_jump = float(np.max(diffs)) if len(diffs) > 0 else 0.0
    results.append({
        "name": "Max amplitude jump",
        "value": f"{max_jump:.3f}",
        "threshold": f"< {MAX_AMPLITUDE_JUMP:.2f}",
        "passed": max_jump < MAX_AMPLITUDE_JUMP,
    })

    # --- Longest silence gap ---
    silence_lin = 10.0 ** (SILENCE_THRESHOLD_DB / 20.0)
    frame_len = int(0.01 * sr)  # 10ms frames
    consecutive_silent = 0
    max_silent_frames = 0
    for start in range(0, len(audio) - frame_len, frame_len):
        rms = np.sqrt(np.mean(audio[start:start + frame_len] ** 2))
        if rms < silence_lin:
            consecutive_silent += 1
            max_silent_frames = max(max_silent_frames, consecutive_silent)
        else:
            consecutive_silent = 0
    longest_gap = max_silent_frames * 0.01
    results.append({
        "name": "Longest silence gap",
        "value": f"{longest_gap:.2f}s",
        "threshold": f"< {MAX_SILENCE_GAP_SEC:.2f}s",
        "passed": longest_gap < MAX_SILENCE_GAP_SEC,
    })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Check 4: Fusion Balance
# ═══════════════════════════════════════════════════════════════════════

def check_fusion_balance(audio: np.ndarray, sr: int) -> list[dict]:
    """Spectral band energy distribution."""
    results = []

    freqs, psd = welch(audio.astype(np.float64), fs=sr, nperseg=4096)

    _integrate = getattr(np, "trapezoid", getattr(np, "trapz", None))
    total_energy = _integrate(psd, freqs)
    if total_energy < 1e-12:
        for name in ["Bass", "Mid", "High"]:
            results.append({
                "name": f"{name} energy", "value": "0.0%",
                "threshold": "> 0%", "passed": False,
            })
        return results

    bands = [
        ("Bass energy  (20-200Hz)", 20, 200, BASS_MIN_PCT),
        ("Mid energy   (200-4kHz)", 200, 4000, MID_MIN_PCT),
        ("High energy  (4k-11kHz)", 4000, sr // 2, HIGH_MIN_PCT),
    ]
    for name, lo, hi, min_pct in bands:
        mask = (freqs >= lo) & (freqs < hi)
        band_energy = _integrate(psd[mask], freqs[mask]) if np.any(mask) else 0.0
        pct = 100.0 * band_energy / total_energy
        results.append({
            "name": name,
            "value": f"{pct:.1f}%",
            "threshold": f"> {min_pct:.0f}%",
            "passed": pct > min_pct,
        })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Check 5: Duration
# ═══════════════════════════════════════════════════════════════════════

def _edge_silence(audio: np.ndarray, sr: int, from_end: bool = False) -> float:
    """Measure silence duration at the start (or end) of audio."""
    silence_lin = 10.0 ** (SILENCE_THRESHOLD_DB / 20.0)
    frame_len = int(0.01 * sr)
    data = np.flip(audio) if from_end else audio
    silent_frames = 0
    for start in range(0, len(data) - frame_len, frame_len):
        rms = np.sqrt(np.mean(data[start:start + frame_len] ** 2))
        if rms < silence_lin:
            silent_frames += 1
        else:
            break
    return silent_frames * 0.01


def check_duration(audio: np.ndarray, sr: int) -> list[dict]:
    """Track length and edge silence."""
    results = []
    duration = len(audio) / sr

    results.append({
        "name": "Track length",
        "value": f"{duration:.2f}s",
        "threshold": f"{DURATION_MIN:.0f}-{DURATION_MAX:.0f}s",
        "passed": DURATION_MIN <= duration <= DURATION_MAX,
    })

    leading = _edge_silence(audio, sr, from_end=False)
    results.append({
        "name": "Leading silence",
        "value": f"{leading:.2f}s",
        "threshold": f"< {MAX_EDGE_SILENCE:.1f}s",
        "passed": leading < MAX_EDGE_SILENCE,
    })

    trailing = _edge_silence(audio, sr, from_end=True)
    results.append({
        "name": "Trailing silence",
        "value": f"{trailing:.2f}s",
        "threshold": f"< {MAX_EDGE_SILENCE:.1f}s",
        "passed": trailing < MAX_EDGE_SILENCE,
    })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════

def print_report(audio_path: str, duration: float, sr: int,
                 sections: list[tuple[str, list[dict]]]) -> int:
    """Print the validation report. Returns number of failed checks."""
    sep = "═" * 62
    line = "─" * 58

    print(f"\n{sep}")
    print("  TRACK VALIDATION REPORT")
    print(sep)
    print(f"\n  File: {audio_path} ({duration:.2f}s, {sr} Hz)")

    total = 0
    passed = 0

    for i, (title, checks) in enumerate(sections, 1):
        print(f"\n  {i}. {title}")
        for c in checks:
            total += 1
            tag = "PASS" if c["passed"] else "FAIL"
            if c["passed"]:
                passed += 1
            print(f"     {c['name']:<26s}: {c['value']:<8s} "
                  f"({c['threshold']})  {' ' * 4}{tag}")

    failed = total - passed
    overall = "PASS" if failed == 0 else "FAIL"
    print(f"\n  {line}")
    print(f"  OVERALL: {passed}/{total} checks passed"
          f"{'':>26s}{overall}")
    print(f"{sep}\n")

    return failed


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a produced raga-fusion track.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python validate_track.py yaman_lofi_final.wav
              python validate_track.py yaman_lofi_final.wav --melody yaman_test_30s.wav
        """),
    )
    parser.add_argument(
        "input", type=str,
        help="Final mix WAV file to validate",
    )
    parser.add_argument(
        "--melody", type=str, default=None,
        help="Pre-production melody WAV (used for transition check; "
             "defaults to the input file)",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"\n  ERROR: file not found: {input_path}")
        sys.exit(1)

    # ── Load audio ────────────────────────────────────────────────────
    print(f"\n  Loading {input_path} …")
    audio, sr = sf.read(str(input_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    duration = len(audio) / sr
    print(f"  Loaded {duration:.2f}s at {sr} Hz.\n")

    melody_path = args.melody or str(input_path)
    if args.melody and Path(args.melody).exists():
        melody_audio, _ = sf.read(args.melody, dtype="float32")
        if melody_audio.ndim > 1:
            melody_audio = melody_audio.mean(axis=1)
    else:
        melody_audio = audio

    # ── Run checks ────────────────────────────────────────────────────
    sections: list[tuple[str, list[dict]]] = []

    print("  Running check 1/5: Coherence …")
    sections.append(("COHERENCE (not robotic)", check_coherence(audio, sr)))

    print("  Running check 2/5: Raga identity (this may take a moment) …")
    sections.append(("RAGA IDENTITY", check_raga_identity(str(input_path))))

    print("  Running check 3/5: Smooth transitions …")
    sections.append(("SMOOTH TRANSITIONS",
                     check_transitions(melody_audio, sr)))

    print("  Running check 4/5: Fusion balance …")
    sections.append(("FUSION BALANCE", check_fusion_balance(audio, sr)))

    print("  Running check 5/5: Duration …")
    sections.append(("DURATION", check_duration(audio, sr)))

    # ── Report ────────────────────────────────────────────────────────
    failed = print_report(str(input_path), duration, sr, sections)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
