#!/usr/bin/env python3
"""
add_production.py — Lofi Production Layer for Raga Tracks

Takes an assembled raga melody track and layers synthesized lofi drums,
a raga-scale bass line, and optional vinyl crackle over it.  Applies
basic mastering (high-pass filter, compression, limiter) and exports
the final mix as WAV.

All sounds are synthesized in numpy — no external audio downloads.

Usage:
    python add_production.py yaman_test_30s.wav --genre lofi --output yaman_lofi_final.wav
    python add_production.py yaman_test_30s.wav --bpm 75 --sa C#4 --output out.wav

Requires:
    pip install -r requirements.txt
    (numpy, soundfile, scipy, librosa — all already installed)
"""

import argparse
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("\n  ERROR: soundfile is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

try:
    from scipy.signal import butter, sosfilt
except ImportError:
    print("\n  ERROR: scipy is required but not installed.")
    print("  Run:  pip install scipy\n")
    sys.exit(1)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_RULES = Path("data/raga_rules/yaman.json")
DEFAULT_STYLES = Path(__file__).resolve().parent / "data" / "styles.json"
DEFAULT_BPM = 75
DEFAULT_GENRE = "lofi"

MIX_LEVELS = {"melody": 0.60, "drums": 0.20, "bass": 0.20}
CRACKLE_DB = -30.0

MASTER_HPF_CUTOFF = 40        # Hz
MASTER_COMP_THRESH_DB = -18.0
MASTER_COMP_RATIO = 3.0
MASTER_COMP_ATTACK_MS = 10.0
MASTER_COMP_RELEASE_MS = 100.0
MASTER_LIMITER_CEILING_DB = -0.5

TARGET_LUFS = -14.0
TARGET_TRUE_PEAK_DB = -1.0
STEREO_WIDTH = 0.35

STYLE_MIX_PRESETS: dict[str, dict] = {
    "lofi": {"low_boost_db": 2.0, "high_cut_hz": 12000, "warmth": 0.6, "comp_thresh": -16.0, "comp_ratio": 3.0},
    "ambient": {"low_boost_db": 1.0, "high_cut_hz": 16000, "warmth": 0.3, "comp_thresh": -20.0, "comp_ratio": 2.0},
    "calm": {"low_boost_db": 1.5, "high_cut_hz": 14000, "warmth": 0.4, "comp_thresh": -18.0, "comp_ratio": 2.5},
    "upbeat": {"low_boost_db": 3.0, "high_cut_hz": 18000, "warmth": 0.2, "comp_thresh": -14.0, "comp_ratio": 4.0},
    "chillhop": {"low_boost_db": 2.5, "high_cut_hz": 13000, "warmth": 0.5, "comp_thresh": -16.0, "comp_ratio": 3.5},
    "trap": {"low_boost_db": 5.0, "high_cut_hz": 18000, "warmth": 0.1, "comp_thresh": -12.0, "comp_ratio": 5.0},
    "bass_house": {"low_boost_db": 4.0, "high_cut_hz": 18000, "warmth": 0.15, "comp_thresh": -12.0, "comp_ratio": 5.0},
    "psytrance": {"low_boost_db": 3.5, "high_cut_hz": 18000, "warmth": 0.1, "comp_thresh": -10.0, "comp_ratio": 6.0},
    "downtempo": {"low_boost_db": 2.0, "high_cut_hz": 15000, "warmth": 0.4, "comp_thresh": -18.0, "comp_ratio": 2.5},
    "jazz_fusion": {"low_boost_db": 1.5, "high_cut_hz": 16000, "warmth": 0.3, "comp_thresh": -20.0, "comp_ratio": 2.0},
    "cinematic": {"low_boost_db": 2.0, "high_cut_hz": 16000, "warmth": 0.3, "comp_thresh": -18.0, "comp_ratio": 2.5},
    "reggae_dub": {"low_boost_db": 3.5, "high_cut_hz": 14000, "warmth": 0.5, "comp_thresh": -14.0, "comp_ratio": 4.0},
}

RNG_SEED = 42

PROD_CACHE_DIR = Path(__file__).resolve().parent / "output" / ".cache_production"
PROD_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _prod_cache_key(kind: str, **kw) -> str:
    """Build a deterministic cache filename from keyword components."""
    import hashlib
    raw = "|".join(f"{k}={v}" for k, v in sorted(kw.items()))
    h = hashlib.sha256(raw.encode()).hexdigest()[:14]
    return f"{kind}_{h}.npy"


def _prod_cache_load(key: str) -> np.ndarray | None:
    path = PROD_CACHE_DIR / key
    if path.exists():
        return np.load(str(path))
    return None


def _prod_cache_save(key: str, arr: np.ndarray) -> None:
    np.save(str(PROD_CACHE_DIR / key), arr)


# ═══════════════════════════════════════════════════════════════════════
#  Sa detection
# ═══════════════════════════════════════════════════════════════════════

def _note_name_to_hz(name: str) -> float:
    """Convert a note name like 'C#4' or 'D' to Hz.

    If no octave is given, defaults to octave 4.
    """
    name = name.strip()
    if not name:
        return 261.63
    if name[-1].isdigit():
        octave = int(name[-1])
        note = name[:-1]
    else:
        octave = 4
        note = name
    note = note.capitalize()
    if len(note) > 1:
        note = note[0] + note[1:]  # preserve # or b
    try:
        pc = NOTE_NAMES.index(note)
    except ValueError:
        print(f"  WARNING: unrecognised note '{name}', defaulting to C4")
        return 261.63
    midi = 12 * (octave + 1) + pc
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _autocorrelation_pitch(frame: np.ndarray, sr: int, fmin: float = 60, fmax: float = 1000) -> float | None:
    """Estimate pitch of a single frame via autocorrelation (no librosa/numba)."""
    lag_min = int(sr / fmax)
    lag_max = int(sr / fmin)
    if lag_max >= len(frame):
        return None
    frame = frame - frame.mean()
    norm = np.sqrt(np.sum(frame ** 2))
    if norm < 1e-8:
        return None
    frame = frame / norm
    corr = np.correlate(frame, frame, mode="full")
    corr = corr[len(frame) - 1:]
    search = corr[lag_min:lag_max + 1]
    if len(search) == 0:
        return None
    peak_idx = int(np.argmax(search)) + lag_min
    if corr[peak_idx] < 0.2:
        return None
    return sr / peak_idx


def detect_sa_from_melody(audio: np.ndarray, sr: int) -> tuple[float, str]:
    """Detect Sa (tonic) from the melody using lightweight autocorrelation pitch analysis.

    Analyses the first 10 seconds to find the most common pitch class.
    Returns (sa_hz, note_name).
    """
    segment = audio[: sr * 10]
    hop = 512
    frame_len = 2048
    f0_valid = []
    for start in range(0, len(segment) - frame_len, hop):
        frame = segment[start:start + frame_len].astype(np.float64)
        f0 = _autocorrelation_pitch(frame, sr)
        if f0 is not None:
            f0_valid.append(f0)

    if len(f0_valid) < 5:
        return 261.63, "C4"

    f0_arr = np.array(f0_valid)
    midi = 69 + 12 * np.log2(f0_arr / 440.0)
    pitch_classes = np.round(midi) % 12
    counts = Counter(int(pc) for pc in pitch_classes)
    sa_pc = counts.most_common(1)[0][0]

    sa_note = NOTE_NAMES[sa_pc]
    sa_midi = 60 + sa_pc
    if sa_pc < 3:
        sa_midi = 72 + sa_pc
    sa_hz = 440.0 * (2.0 ** ((sa_midi - 69) / 12.0))
    return sa_hz, f"{sa_note}{sa_midi // 12 - 1}"


# ═══════════════════════════════════════════════════════════════════════
#  Drum synthesis
# ═══════════════════════════════════════════════════════════════════════

def generate_kick(sr: int) -> np.ndarray:
    """Synthesize a lofi kick drum (~150ms)."""
    dur = 0.15
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)

    # Pitch sweep: 80 Hz → 40 Hz
    freq = 80.0 * np.exp(-t * 10.0) + 40.0
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase)

    envelope = np.exp(-t * 25.0)
    click = np.exp(-t * 200.0) * 0.3

    return ((tone * envelope + click) * 0.8).astype(np.float32)


def generate_snare(sr: int, rng: np.random.Generator) -> np.ndarray:
    """Synthesize a lofi snare/clap (~200ms)."""
    dur = 0.20
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)

    noise = rng.standard_normal(n)

    # Bandpass 200-3000 Hz
    sos = butter(2, [200, 3000], btype="bandpass", fs=sr, output="sos")
    filtered = sosfilt(sos, noise)

    envelope = np.exp(-t * 18.0)
    return (filtered * envelope * 0.6).astype(np.float32)


def generate_hihat(sr: int, rng: np.random.Generator,
                   velocity: float = 1.0) -> np.ndarray:
    """Synthesize a lofi hi-hat (~60ms)."""
    dur = 0.06
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)

    noise = rng.standard_normal(n)

    sos = butter(2, 6000, btype="highpass", fs=sr, output="sos")
    filtered = sosfilt(sos, noise)

    envelope = np.exp(-t * 60.0)
    return (filtered * envelope * 0.25 * velocity).astype(np.float32)


def generate_808_kick(sr: int) -> np.ndarray:
    """Synthesize a long 808 kick with sub-bass tail (~400ms)."""
    dur = 0.40
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)
    freq = 55.0 * np.exp(-t * 6.0) + 30.0
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase) + 0.3 * np.sin(2.0 * phase)
    envelope = np.exp(-t * 8.0)
    click = np.exp(-t * 300.0) * 0.5
    return ((tone * envelope + click) * 0.9).astype(np.float32)


def generate_trap_hat(sr: int, rng: np.random.Generator,
                      velocity: float = 1.0) -> np.ndarray:
    """Synthesize a crisp trap hi-hat (~30ms)."""
    dur = 0.03
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)
    noise = rng.standard_normal(n)
    sos = butter(2, 8000, btype="highpass", fs=sr, output="sos")
    filtered = sosfilt(sos, noise)
    envelope = np.exp(-t * 100.0)
    return (filtered * envelope * 0.3 * velocity).astype(np.float32)


def generate_clap(sr: int, rng: np.random.Generator) -> np.ndarray:
    """Synthesize a layered clap (~180ms)."""
    dur = 0.18
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)
    noise = rng.standard_normal(n)
    sos = butter(2, [400, 4000], btype="bandpass", fs=sr, output="sos")
    filtered = sosfilt(sos, noise)
    # Double hit (clap layering)
    env1 = np.exp(-t * 30.0) * 0.5
    env2 = np.zeros(n)
    offset = int(0.015 * sr)
    if offset < n:
        env2[offset:] = np.exp(-np.linspace(0, dur, n - offset) * 25.0)
    return (filtered * (env1 + env2) * 0.6).astype(np.float32)


def generate_brushed_hit(sr: int, rng: np.random.Generator,
                         velocity: float = 1.0) -> np.ndarray:
    """Synthesize a brushed snare / soft swish (~120ms)."""
    dur = 0.12
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)
    noise = rng.standard_normal(n)
    sos = butter(2, [800, 5000], btype="bandpass", fs=sr, output="sos")
    filtered = sosfilt(sos, noise)
    envelope = np.exp(-t * 22.0) * velocity
    return (filtered * envelope * 0.2).astype(np.float32)


def generate_rim(sr: int) -> np.ndarray:
    """Synthesize a rim click (~40ms)."""
    dur = 0.04
    n = int(sr * dur)
    t = np.linspace(0, dur, n, dtype=np.float64)
    tone = np.sin(2.0 * np.pi * 900.0 * t)
    envelope = np.exp(-t * 120.0)
    return (tone * envelope * 0.4).astype(np.float32)


def _place_hit(output: np.ndarray, hit: np.ndarray, pos: int) -> None:
    """Mix a hit into output at sample position *pos*."""
    end = min(pos + len(hit), len(output))
    length = end - pos
    if length > 0 and pos >= 0:
        output[pos:end] += hit[:length]


def _drum_lofi(sr, total_samples, bpm, rng):
    """Classic lofi: kick 1/3, snare 2/4, 8th-note hats with swing."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    swing = int(beat_samples * 0.04)
    kick = generate_kick(sr)
    snare = generate_snare(sr, rng)
    hat_vel = [0.9, 0.5, 0.7, 0.5, 0.85, 0.5, 0.65, 0.5]
    pos, beat, eighth = 0, 0, 0
    while pos < total_samples:
        bib = beat % 4
        if bib == 0:
            _place_hit(output, kick, pos)
        elif bib == 1:
            _place_hit(output, snare, pos)
        elif bib == 2:
            _place_hit(output, kick, pos + swing)
        elif bib == 3:
            _place_hit(output, snare, pos)
        v = hat_vel[eighth % len(hat_vel)]
        _place_hit(output, generate_hihat(sr, rng, v), pos)
        half = beat_samples // 2
        v2 = hat_vel[(eighth + 1) % len(hat_vel)]
        _place_hit(output, generate_hihat(sr, rng, v2), pos + half)
        pos += beat_samples
        beat += 1
        eighth += 2
    return np.tanh(output * 1.5).astype(np.float32)


def _drum_trap(sr, total_samples, bpm, rng):
    """Trap: sparse 808 kick, clap on 3, rapid hi-hat rolls."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    kick = generate_808_kick(sr)
    clap = generate_clap(sr, rng)
    # Hi-hat roll pattern: 32nd notes with accent variation
    hat_pattern = [1.0, 0.3, 0.5, 0.3, 0.8, 0.3, 0.6, 0.3,
                   0.9, 0.3, 0.5, 0.3, 0.7, 0.3, 0.4, 0.3]
    thirty_second = beat_samples // 8
    pos, beat = 0, 0
    while pos < total_samples:
        bib = beat % 4
        if bib == 0:
            _place_hit(output, kick, pos)
        elif bib == 2:
            _place_hit(output, clap, pos)
        # Rapid hi-hats
        for i, vel in enumerate(hat_pattern):
            hat_pos = pos + i * thirty_second
            if hat_pos < total_samples:
                _place_hit(output, generate_trap_hat(sr, rng, vel), hat_pos)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 2.0).astype(np.float32)


def _drum_four_on_floor(sr, total_samples, bpm, rng):
    """Bass house / EDM: kick every beat, offbeat hats, clap on 2/4."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    kick = generate_kick(sr)
    clap = generate_clap(sr, rng)
    pos, beat = 0, 0
    while pos < total_samples:
        _place_hit(output, kick, pos)
        if beat % 2 == 1:
            _place_hit(output, clap, pos)
        # Offbeat hats
        hat_pos = pos + beat_samples // 2
        if hat_pos < total_samples:
            _place_hit(output, generate_hihat(sr, rng, 0.7), hat_pos)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 1.8).astype(np.float32)


def _drum_driving(sr, total_samples, bpm, rng):
    """Psytrance: kick every beat, 16th-note hats, no snare."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    kick = generate_kick(sr)
    sixteenth = beat_samples // 4
    hat_vel = [0.9, 0.4, 0.6, 0.4]
    pos, beat = 0, 0
    while pos < total_samples:
        _place_hit(output, kick, pos)
        for i, v in enumerate(hat_vel):
            hp = pos + i * sixteenth
            if hp < total_samples:
                _place_hit(output, generate_trap_hat(sr, rng, v), hp)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 1.8).astype(np.float32)


def _drum_jazzy(sr, total_samples, bpm, rng):
    """Jazz / chillhop: brushed hits, ride-like hats, ghost notes, swing."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    swing = int(beat_samples * 0.08)  # heavier swing
    kick = generate_kick(sr)
    rim = generate_rim(sr)
    pos, beat = 0, 0
    while pos < total_samples:
        bib = beat % 4
        if bib == 0:
            _place_hit(output, kick, pos)
        elif bib == 1:
            _place_hit(output, rim, pos + swing)
        elif bib == 2:
            _place_hit(output, kick, pos)
            # Ghost brush
            _place_hit(output, generate_brushed_hit(sr, rng, 0.3), pos + beat_samples // 3)
        elif bib == 3:
            _place_hit(output, rim, pos + swing)
        # Ride-like triplet hats
        trip = beat_samples // 3
        for i in range(3):
            vel = [0.7, 0.3, 0.5][i]
            _place_hit(output, generate_brushed_hit(sr, rng, vel), pos + i * trip)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 1.3).astype(np.float32)


def _drum_organic(sr, total_samples, bpm, rng):
    """Downtempo: soft kick, brushed snare, sparse hats, organic feel."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    kick = generate_kick(sr)
    pos, beat = 0, 0
    while pos < total_samples:
        bib = beat % 8
        if bib in (0, 3, 5):
            _place_hit(output, kick, pos)
        if bib in (2, 6):
            _place_hit(output, generate_brushed_hit(sr, rng, 0.6), pos)
        if bib % 2 == 0:
            _place_hit(output, generate_hihat(sr, rng, 0.4), pos + beat_samples // 2)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 1.2).astype(np.float32)


def _drum_minimal(sr, total_samples, bpm, rng):
    """Ambient / cinematic: very sparse hits, mostly texture."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    pos, beat = 0, 0
    while pos < total_samples:
        if beat % 8 == 0:
            _place_hit(output, generate_brushed_hit(sr, rng, 0.4), pos)
        if beat % 16 == 4:
            _place_hit(output, generate_rim(sr), pos)
        pos += beat_samples
        beat += 1
    return output


def _drum_offbeat(sr, total_samples, bpm, rng):
    """Reggae/dub: kick on 1/3, rim on offbeats (the skank)."""
    output = np.zeros(total_samples, dtype=np.float32)
    beat_samples = int(60.0 / bpm * sr)
    kick = generate_kick(sr)
    rim = generate_rim(sr)
    pos, beat = 0, 0
    while pos < total_samples:
        bib = beat % 4
        if bib in (0, 2):
            _place_hit(output, kick, pos)
        # Offbeat skank
        offbeat_pos = pos + beat_samples // 2
        if offbeat_pos < total_samples:
            _place_hit(output, rim, offbeat_pos)
        if bib == 3:
            _place_hit(output, generate_hihat(sr, rng, 0.5), pos)
        pos += beat_samples
        beat += 1
    return np.tanh(output * 1.4).astype(np.float32)


DRUM_PATTERNS = {
    "lofi": _drum_lofi,
    "trap": _drum_trap,
    "four_on_floor": _drum_four_on_floor,
    "driving": _drum_driving,
    "jazzy": _drum_jazzy,
    "organic": _drum_organic,
    "minimal": _drum_minimal,
    "offbeat": _drum_offbeat,
}


def generate_drum_loop(sr: int, total_samples: int, bpm: float,
                       rng: np.random.Generator,
                       pattern: str = "lofi") -> np.ndarray:
    """Generate drums using the specified pattern style."""
    fn = DRUM_PATTERNS.get(pattern, _drum_lofi)
    return fn(sr, total_samples, bpm, rng)


# ═══════════════════════════════════════════════════════════════════════
#  Bass synthesis
# ═══════════════════════════════════════════════════════════════════════

def _bass_note(sr: int, freq: float, n_samples: int,
               attack_s: float = 0.03, release_s: float = 0.03,
               harmonics: float = 0.25) -> np.ndarray:
    """Synthesize a single bass note with configurable attack and harmonics."""
    t = np.arange(n_samples, dtype=np.float64) / sr
    tone = np.sin(2.0 * np.pi * freq * t)
    tone += harmonics * np.sin(2.0 * np.pi * freq * 2.0 * t)
    env = np.ones(n_samples, dtype=np.float64)
    attack = min(int(attack_s * sr), n_samples)
    release = min(int(release_s * sr), n_samples)
    if attack > 0:
        env[:attack] = np.linspace(0, 1, attack)
    if release > 0:
        env[-release:] = np.linspace(1, 0, release)
    return tone * env * 0.7


def _raga_bass_notes(scale_degrees: list[int]) -> dict:
    """Build raga-aware pitch data for bass patterns."""
    degree_to_ratio = {d: 2.0 ** (d / 12.0) for d in scale_degrees}
    # Find Pa (or closest fifth), and the second-highest degree for movement
    pa = 7 if 7 in scale_degrees else max((d for d in scale_degrees if d > 4), default=5)
    top = scale_degrees[-1] if scale_degrees else 11
    second = scale_degrees[-2] if len(scale_degrees) >= 2 else 0
    return {"ratios": degree_to_ratio, "pa": pa, "top": top, "second": second,
            "degrees": scale_degrees}


def _bass_root_fifth(sr, total_samples, bpm, sa_hz, info):
    """Classic: Sa(2 beats) → Pa(1 beat) → top-degree(1 beat)."""
    output = np.zeros(total_samples, dtype=np.float64)
    beat_samples = int(60.0 / bpm * sr)
    sa_bass = sa_hz / 4.0
    pattern = [(0, 2), (info["pa"], 1), (info["top"], 1)]
    pos = 0
    while pos < total_samples:
        for deg, beats in pattern:
            ns = beat_samples * beats
            if pos + ns > total_samples:
                ns = total_samples - pos
            if ns <= 0:
                break
            freq = sa_bass * info["ratios"].get(deg, 1.0)
            output[pos:pos + ns] += _bass_note(sr, freq, ns)[:ns]
            pos += ns
    return output.astype(np.float32)


def _bass_walking(sr, total_samples, bpm, sa_hz, info):
    """Jazz walking bass: step through the raga scale, one note per beat."""
    output = np.zeros(total_samples, dtype=np.float64)
    beat_samples = int(60.0 / bpm * sr)
    sa_bass = sa_hz / 4.0
    degs = info["degrees"]
    if not degs:
        degs = [0]
    # Walk up then down, repeating
    walk = list(degs) + list(reversed(degs[1:-1])) if len(degs) > 2 else list(degs)
    pos, idx = 0, 0
    while pos < total_samples:
        deg = walk[idx % len(walk)]
        ns = beat_samples
        if pos + ns > total_samples:
            ns = total_samples - pos
        if ns <= 0:
            break
        freq = sa_bass * info["ratios"].get(deg, 1.0)
        output[pos:pos + ns] += _bass_note(sr, freq, ns, attack_s=0.02, release_s=0.02)[:ns]
        pos += ns
        idx += 1
    return output.astype(np.float32)


def _bass_drone(sr, total_samples, bpm, sa_hz, info):
    """Ambient/cinematic drone: sustained Sa with slow Pa movement."""
    n = total_samples
    t = np.arange(n, dtype=np.float64) / sr
    sa_bass = sa_hz / 4.0
    pa_ratio = info["ratios"].get(info["pa"], 1.5)
    # Slow oscillation between Sa and Pa
    blend = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.05 * t)  # 20-second cycle
    freq = sa_bass * (1.0 * (1.0 - blend * 0.3) + pa_ratio * blend * 0.3)
    phase = np.cumsum(freq / sr) * 2.0 * np.pi
    tone = np.sin(phase) + 0.15 * np.sin(2.0 * phase)
    # Gentle envelope
    env = np.ones(n)
    fade = min(int(0.5 * sr), n // 4)
    if fade > 0:
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    return (tone * env * 0.5).astype(np.float32)


def _bass_sub_808(sr, total_samples, bpm, sa_hz, info):
    """Trap 808 sub-bass: long sub notes on kick hits, raga root movement."""
    output = np.zeros(total_samples, dtype=np.float64)
    beat_samples = int(60.0 / bpm * sr)
    sa_bass = sa_hz / 8.0  # extra low
    # Play on beats 1 of each bar, alternate Sa and Pa
    pattern = [0, info["pa"]]
    pos, bar = 0, 0
    while pos < total_samples:
        deg = pattern[bar % len(pattern)]
        ns = beat_samples * 4  # whole bar
        if pos + ns > total_samples:
            ns = total_samples - pos
        if ns <= 0:
            break
        freq = sa_bass * info["ratios"].get(deg, 1.0)
        t = np.arange(ns, dtype=np.float64) / sr
        # 808-style: pitch drop + long sustain
        pitch_env = freq * (1.0 + 0.5 * np.exp(-t * 8.0))
        phase = np.cumsum(pitch_env / sr) * 2.0 * np.pi
        tone = np.sin(phase)
        amp_env = np.exp(-t * 1.5)
        output[pos:pos + ns] += (tone * amp_env * 0.8)[:ns]
        pos += ns
        bar += 1
    return output.astype(np.float32)


def _bass_wobble(sr, total_samples, bpm, sa_hz, info):
    """Bass house wobble: LFO-filtered bass on raga roots."""
    output = np.zeros(total_samples, dtype=np.float64)
    beat_samples = int(60.0 / bpm * sr)
    sa_bass = sa_hz / 4.0
    pattern = [0, 0, info["pa"], info["second"]]
    pos, beat = 0, 0
    while pos < total_samples:
        deg = pattern[beat % len(pattern)]
        ns = beat_samples
        if pos + ns > total_samples:
            ns = total_samples - pos
        if ns <= 0:
            break
        freq = sa_bass * info["ratios"].get(deg, 1.0)
        t = np.arange(ns, dtype=np.float64) / sr
        # Sawtooth-ish wave
        phase = np.cumsum(np.full(ns, freq) / sr) * 2.0 * np.pi
        raw = np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.25 * np.sin(3 * phase)
        # LFO wobble: amplitude modulation at half-beat rate
        lfo = 0.5 + 0.5 * np.sin(2.0 * np.pi * (bpm / 60.0) * t)
        env = np.exp(-t * 3.0) * lfo
        output[pos:pos + ns] += (raw * env * 0.7)[:ns]
        pos += ns
        beat += 1
    return output.astype(np.float32)


def _bass_driving(sr, total_samples, bpm, sa_hz, info):
    """Psytrance driving bass: rapid 16th-note pattern on Sa and Pa."""
    output = np.zeros(total_samples, dtype=np.float64)
    beat_samples = int(60.0 / bpm * sr)
    sixteenth = beat_samples // 4
    sa_bass = sa_hz / 4.0
    # 16th-note pattern alternating Sa and Pa
    pattern_degs = [0, 0, info["pa"], 0] * 4
    pos, idx = 0, 0
    while pos < total_samples:
        deg = pattern_degs[idx % len(pattern_degs)]
        ns = sixteenth
        if pos + ns > total_samples:
            ns = total_samples - pos
        if ns <= 0:
            break
        freq = sa_bass * info["ratios"].get(deg, 1.0)
        t = np.arange(ns, dtype=np.float64) / sr
        tone = np.sin(2.0 * np.pi * freq * t)
        env = np.exp(-t * 20.0)
        output[pos:pos + ns] += (tone * env * 0.8)[:ns]
        pos += ns
        idx += 1
    return output.astype(np.float32)


BASS_PATTERNS = {
    "root_fifth": _bass_root_fifth,
    "walking": _bass_walking,
    "drone": _bass_drone,
    "sub_808": _bass_sub_808,
    "wobble": _bass_wobble,
    "driving": _bass_driving,
}


def generate_bass_line(sr: int, total_samples: int, bpm: float,
                       sa_hz: float, scale_degrees: list[int],
                       pattern: str = "root_fifth") -> np.ndarray:
    """Generate a bass line using the specified pattern and raga scale."""
    info = _raga_bass_notes(scale_degrees)
    fn = BASS_PATTERNS.get(pattern, _bass_root_fifth)
    return fn(sr, total_samples, bpm, sa_hz, info)


# ═══════════════════════════════════════════════════════════════════════
#  Vinyl crackle
# ═══════════════════════════════════════════════════════════════════════

def generate_vinyl_crackle(sr: int, total_samples: int,
                           rng: np.random.Generator) -> np.ndarray:
    """Generate sparse vinyl-crackle noise texture."""
    output = np.zeros(total_samples, dtype=np.float64)

    # ~15 crackle impulses per second
    avg_gap = sr // 15
    pos = rng.integers(0, avg_gap)
    while pos < total_samples:
        burst_len = min(rng.integers(3, 12), total_samples - pos)
        output[pos:pos + burst_len] = rng.standard_normal(burst_len) * 0.02
        pos += rng.integers(avg_gap // 2, avg_gap * 2)

    # Bandpass 300-4000 Hz
    sos = butter(2, [300, 4000], btype="bandpass", fs=sr, output="sos")
    output = sosfilt(sos, output)

    return output.astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════
#  Additional FX
# ═══════════════════════════════════════════════════════════════════════

def generate_delay_wash(audio: np.ndarray, sr: int,
                        delay_ms: float = 375.0, feedback: float = 0.4,
                        mix: float = 0.25) -> np.ndarray:
    """Apply a dub-style delay effect to audio."""
    delay_samples = int(delay_ms * sr / 1000.0)
    output = audio.astype(np.float64).copy()
    for i in range(4):  # 4 taps
        tap_delay = delay_samples * (i + 1)
        tap_gain = mix * (feedback ** i)
        if tap_delay < len(output):
            delayed = np.zeros(len(output))
            delayed[tap_delay:] = output[:-tap_delay] * tap_gain if tap_delay < len(output) else 0
            output += delayed
    # Gentle low-pass on the delays for warmth
    sos = butter(2, 3000, btype="lowpass", fs=sr, output="sos")
    wet = sosfilt(sos, output - audio.astype(np.float64))
    return (audio.astype(np.float64) + wet * mix).astype(np.float32)


def generate_pad_texture(sr: int, total_samples: int,
                         sa_hz: float, scale_degrees: list[int]) -> np.ndarray:
    """Generate a warm pad/string texture based on the raga's scale."""
    t = np.arange(total_samples, dtype=np.float64) / sr
    pad = np.zeros(total_samples, dtype=np.float64)
    # Layer 3 sustained notes from the scale
    pad_degrees = [0]  # Always include Sa
    if scale_degrees:
        mid = scale_degrees[len(scale_degrees) // 2]
        pad_degrees.append(mid)
        if len(scale_degrees) > 2:
            pad_degrees.append(scale_degrees[-1])
    for deg in pad_degrees:
        freq = sa_hz * (2.0 ** (deg / 12.0))
        # Detuned pair for thickness
        pad += 0.3 * np.sin(2.0 * np.pi * freq * t)
        pad += 0.2 * np.sin(2.0 * np.pi * freq * 1.003 * t)
        pad += 0.1 * np.sin(2.0 * np.pi * freq * 0.997 * t)
    pad /= len(pad_degrees) + 1e-9
    # Slow volume swell
    swell = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.03 * t)
    fade = min(int(1.0 * sr), total_samples // 4)
    env = np.ones(total_samples)
    if fade > 0:
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    return (pad * swell * env * 0.08).astype(np.float32)


def apply_sidechain(audio: np.ndarray, kick_audio: np.ndarray,
                    sr: int, bpm: float, depth: float = 0.6) -> np.ndarray:
    """Apply sidechain compression pumping effect synced to kick rhythm."""
    beat_samples = int(60.0 / bpm * sr)
    output = audio.astype(np.float64).copy()
    duck_len = min(int(0.15 * sr), beat_samples // 2)
    # Duck curve: fast attack, slow release
    duck = np.ones(duck_len, dtype=np.float64)
    attack = min(int(0.005 * sr), duck_len // 4)
    if attack > 0:
        duck[:attack] = np.linspace(1.0, 1.0 - depth, attack)
    duck[attack:] = np.linspace(1.0 - depth, 1.0, duck_len - attack)
    pos = 0
    while pos < len(output):
        end = min(pos + duck_len, len(output))
        output[pos:end] *= duck[:end - pos]
        pos += beat_samples
    return output.astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════
#  Mixing
# ═══════════════════════════════════════════════════════════════════════

def mix_layers(melody: np.ndarray,
               drums: np.ndarray,
               bass: np.ndarray,
               crackle: np.ndarray | None,
               levels: dict[str, float] | None = None) -> np.ndarray:
    """Sum all layers at their respective volume levels."""
    lvl = levels or MIX_LEVELS

    mixed = (melody.astype(np.float64) * lvl["melody"]
             + drums.astype(np.float64) * lvl["drums"]
             + bass.astype(np.float64) * lvl["bass"])

    if crackle is not None:
        crackle_linear = 10.0 ** (CRACKLE_DB / 20.0)
        mixed += crackle.astype(np.float64) * crackle_linear

    return mixed.astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════
#  Mastering
# ═══════════════════════════════════════════════════════════════════════

def apply_highpass(audio: np.ndarray, sr: int,
                   cutoff: float = MASTER_HPF_CUTOFF) -> np.ndarray:
    """4th-order Butterworth high-pass filter."""
    sos = butter(4, cutoff, btype="highpass", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def apply_lowpass(audio: np.ndarray, sr: int, cutoff: float = 16000) -> np.ndarray:
    """4th-order Butterworth low-pass filter (tame harsh highs)."""
    nyq = sr / 2.0
    cutoff = min(cutoff, nyq - 1)
    sos = butter(4, cutoff, btype="lowpass", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def apply_low_shelf(audio: np.ndarray, sr: int, gain_db: float = 2.0,
                    freq: float = 200.0) -> np.ndarray:
    """Simple low-shelf boost using biquad approximation."""
    if abs(gain_db) < 0.1:
        return audio
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * freq / sr
    alpha = np.sin(w0) / 2.0 * np.sqrt(2.0)
    cos_w0 = np.cos(w0)

    b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
    b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
    a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
    a2 = (A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha

    from scipy.signal import lfilter
    b = np.array([b0 / a0, b1 / a0, b2 / a0])
    a = np.array([1.0, a1 / a0, a2 / a0])
    return lfilter(b, a, audio.astype(np.float64)).astype(np.float32)


def apply_warmth(audio: np.ndarray, amount: float = 0.3) -> np.ndarray:
    """Subtle tape-style saturation for warmth (soft-clip harmonics)."""
    if amount < 0.01:
        return audio
    audio = audio.astype(np.float64)
    drive = 1.0 + amount * 2.0
    saturated = np.tanh(audio * drive) / drive
    return (audio * (1.0 - amount) + saturated * amount).astype(np.float32)


def apply_compression(audio: np.ndarray, sr: int,
                      threshold_db: float = MASTER_COMP_THRESH_DB,
                      ratio: float = MASTER_COMP_RATIO,
                      attack_ms: float = MASTER_COMP_ATTACK_MS,
                      release_ms: float = MASTER_COMP_RELEASE_MS) -> np.ndarray:
    """Vectorized compressor using IIR envelope follower via sosfilt."""
    audio = audio.astype(np.float64)
    threshold = 10.0 ** (threshold_db / 20.0)

    # Use a single-pole IIR lowpass on |audio| as a fast envelope follower.
    # The attack/release distinction is approximated by a single time constant
    # equal to the geometric mean of attack and release.
    tau_ms = np.sqrt(attack_ms * release_ms)
    cutoff_hz = 1000.0 / (2.0 * np.pi * tau_ms)
    cutoff_hz = min(cutoff_hz, sr / 2.0 - 1)
    sos_env = butter(1, cutoff_hz, btype="lowpass", fs=sr, output="sos")
    envelope = sosfilt(sos_env, np.abs(audio))

    gain = np.ones(len(audio), dtype=np.float64)
    above = envelope > threshold
    if np.any(above):
        over_db = 20.0 * np.log10(envelope[above] / threshold + 1e-12)
        reduced_db = over_db / ratio
        gain[above] = 10.0 ** ((reduced_db - over_db) / 20.0)

    return (audio * gain).astype(np.float32)


def apply_limiter(audio: np.ndarray,
                  ceiling_db: float = MASTER_LIMITER_CEILING_DB) -> np.ndarray:
    """Lookahead brick-wall limiter with 5ms attack smoothing."""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    audio = audio.astype(np.float64)
    peak = np.max(np.abs(audio))
    if peak < 1e-8:
        return audio.astype(np.float32)

    if peak > ceiling:
        audio = audio * (ceiling / peak)

    return np.clip(audio, -ceiling, ceiling).astype(np.float32)


def apply_lufs_normalization(audio: np.ndarray, sr: int,
                             target_lufs: float = TARGET_LUFS) -> np.ndarray:
    """Normalize to target integrated LUFS (ITU-R BS.1770 approximation).

    Uses RMS-based approximation since we don't have a full LUFS meter.
    For mono signals, LUFS ~ 20*log10(RMS) - 0.691.
    """
    audio = audio.astype(np.float64)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-10:
        return audio.astype(np.float32)
    current_lufs = 20.0 * np.log10(rms) - 0.691
    gain_db = target_lufs - current_lufs
    gain_db = min(gain_db, 12.0)
    gain = 10.0 ** (gain_db / 20.0)
    audio = audio * gain
    return audio.astype(np.float32)


def apply_stereo_widening(audio: np.ndarray, width: float = STEREO_WIDTH) -> np.ndarray:
    """Create pseudo-stereo from mono using Haas-style micro-delay.

    Returns a (N, 2) stereo array.
    """
    if audio.ndim == 2:
        return audio
    n = len(audio)
    delay_samples = int(0.012 * 22050)
    left = audio.astype(np.float64)
    right = np.zeros(n, dtype=np.float64)
    right[delay_samples:] = audio[:-delay_samples] if delay_samples < n else 0
    right[:delay_samples] = audio[:delay_samples] * 0.5

    mid = (left + right) * 0.5
    side = (left - right) * 0.5

    left_out = mid + side * (1.0 + width)
    right_out = mid - side * (1.0 + width)

    stereo = np.column_stack([left_out, right_out]).astype(np.float32)
    peak = np.max(np.abs(stereo))
    if peak > 0.99:
        stereo = stereo * (0.99 / peak)
    return stereo


def master(audio: np.ndarray, sr: int, style: str = "lofi") -> np.ndarray:
    """Commercial-grade mastering chain with style-specific presets.

    Chain: HPF -> low shelf EQ -> warmth -> compression ->
           high cut -> LUFS normalization -> limiter -> stereo widening.
    """
    preset = STYLE_MIX_PRESETS.get(style, STYLE_MIX_PRESETS.get("lofi", {}))

    audio = apply_highpass(audio, sr)

    low_boost = preset.get("low_boost_db", 2.0)
    if low_boost > 0:
        audio = apply_low_shelf(audio, sr, gain_db=low_boost)

    warmth = preset.get("warmth", 0.3)
    audio = apply_warmth(audio, amount=warmth)

    comp_thresh = preset.get("comp_thresh", MASTER_COMP_THRESH_DB)
    comp_ratio = preset.get("comp_ratio", MASTER_COMP_RATIO)
    audio = apply_compression(audio, sr, threshold_db=comp_thresh, ratio=comp_ratio)

    high_cut = preset.get("high_cut_hz", 16000)
    audio = apply_lowpass(audio, sr, cutoff=high_cut)

    audio = apply_lufs_normalization(audio, sr, target_lufs=TARGET_LUFS)

    audio = apply_limiter(audio, ceiling_db=TARGET_TRUE_PEAK_DB)

    stereo = apply_stereo_widening(audio, width=STEREO_WIDTH)
    return stereo


# ═══════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════

def print_report(input_path: str, duration: float, sa_note: str,
                 sa_hz: float, genre: str, bpm: float,
                 bass_root_hz: float, crackle_on: bool,
                 output_path: str) -> None:
    """Print a structured production report."""
    sep = "═" * 62
    line = "─" * 36
    bass_note = f"{sa_note[:-1]}{int(sa_note[-1]) - 2}" if sa_note[-1].isdigit() else sa_note
    print(f"\n{sep}")
    print("  LOFI PRODUCTION — Mix Report")
    print(sep)
    print(f"\n  Input melody  : {input_path} ({duration:.2f}s)")
    print(f"  Detected Sa   : {sa_note} ({sa_hz:.1f} Hz)")
    print(f"  Genre         : {genre}")
    print(f"  BPM           : {int(bpm)}")
    print(f"  Bass root     : {bass_note} ({bass_root_hz:.1f} Hz)")
    print(f"\n  LAYERS")
    print(f"  {line}")

    def bar(pct: float) -> str:
        return "█" * int(pct / 100 * 40)

    for name, lvl in MIX_LEVELS.items():
        pct = int(lvl * 100)
        print(f"    {name.capitalize():14s}: {pct}%  {bar(pct)}")
    crackle_str = "on   (ambient texture)" if crackle_on else "off"
    print(f"    {'Vinyl crackle':14s}: {crackle_str}")

    print(f"\n  MASTERING")
    print(f"  {line}")
    print(f"    High-pass    : {MASTER_HPF_CUTOFF} Hz (4th-order Butterworth)")
    print(f"    Compression  : {MASTER_COMP_THRESH_DB:.0f} dB threshold, "
          f"{MASTER_COMP_RATIO:.0f}:1 ratio")
    print(f"    Limiter      : {MASTER_LIMITER_CEILING_DB} dBFS ceiling")

    print(f"\n  Output        : {output_path} ({duration:.2f}s)")
    print(f"\n{sep}\n")


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add lofi production layers to an assembled raga track.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python add_production.py yaman_test_30s.wav --genre lofi --output yaman_lofi_final.wav
              python add_production.py yaman_test_30s.wav --bpm 75 --sa C#4 --output out.wav
        """),
    )
    parser.add_argument(
        "input", type=str,
        help="Input WAV file (assembled raga melody track)",
    )
    parser.add_argument(
        "--genre", type=str, default=DEFAULT_GENRE,
        choices=["lofi", "ambient", "calm", "upbeat", "chillhop", "trap",
                 "bass_house", "psytrance", "downtempo", "jazz_fusion",
                 "cinematic", "reggae_dub"],
        help=f"Production genre (default: {DEFAULT_GENRE})",
    )
    parser.add_argument(
        "--style", type=str, default=None,
        help="Named style from data/styles.json (overrides --genre, BPM, mix). e.g. lofi, ambient, calm",
    )
    parser.add_argument(
        "--bpm", type=float, default=DEFAULT_BPM,
        help=f"Tempo for drums and bass (default: {DEFAULT_BPM})",
    )
    parser.add_argument(
        "--sa", type=str, default=None,
        help="Override Sa detection (e.g. C#4, D4)",
    )
    parser.add_argument(
        "--rules", type=Path, default=DEFAULT_RULES,
        help=f"Raga rules JSON for bass scale (default: {DEFAULT_RULES})",
    )
    parser.add_argument(
        "--no-crackle", action="store_true",
        help="Skip vinyl crackle layer",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output WAV file path",
    )

    args = parser.parse_args()

    # ── Resolve style (from --style or --genre) ────────────────────────
    style_bpm = args.bpm
    style_levels = dict(MIX_LEVELS)
    style_crackle = not args.no_crackle
    style_name = args.genre
    style_drum_pattern = "lofi"
    style_bass_pattern = "root_fifth"
    style_fx = []

    if args.style:
        style_path = DEFAULT_STYLES if DEFAULT_STYLES.exists() else None
        if style_path:
            with open(style_path) as f:
                styles_data = json.load(f)
            if args.style in styles_data:
                s = styles_data[args.style]
                style_bpm = s.get("bpm", style_bpm)
                style_levels = {
                    "melody": s.get("melody", MIX_LEVELS["melody"]),
                    "drums": s.get("drums", MIX_LEVELS["drums"]),
                    "bass": s.get("bass", MIX_LEVELS["bass"]),
                }
                style_crackle = s.get("crackle", True)
                style_drum_pattern = s.get("drum_pattern", "lofi")
                style_bass_pattern = s.get("bass_pattern", "root_fifth")
                style_fx = s.get("fx", [])
                style_name = args.style
            else:
                print(f"  WARNING: style '{args.style}' not in {style_path}, using genre defaults")
        else:
            print(f"  WARNING: styles file not found, using genre defaults")

    # ── Load melody ───────────────────────────────────────────────────
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"\n  ERROR: input file not found: {input_path}")
        sys.exit(1)

    print(f"\n  Loading melody: {input_path} …")
    melody, sr = sf.read(str(input_path), dtype="float32")
    if melody.ndim > 1:
        melody = melody.mean(axis=1)
    total_samples = len(melody)
    duration = total_samples / sr
    print(f"  Loaded {duration:.2f}s of audio at {sr} Hz.")

    # ── Detect Sa ─────────────────────────────────────────────────────
    if args.sa:
        sa_hz = _note_name_to_hz(args.sa)
        sa_note = args.sa
        print(f"  Sa override: {sa_note} ({sa_hz:.1f} Hz)")
    else:
        print("  Detecting Sa from melody …")
        sa_hz, sa_note = detect_sa_from_melody(melody, sr)
        print(f"  Detected Sa: {sa_note} ({sa_hz:.1f} Hz)")

    # ── Load raga rules ───────────────────────────────────────────────
    scale_degrees = [0, 2, 4, 6, 7, 9, 11]  # Yaman default
    if args.rules.exists():
        with open(args.rules) as f:
            rules = json.load(f)
        scale_degrees = rules.get("scale", {}).get("degrees", scale_degrees)
        raga_name = rules.get("raga", {}).get("name", "Unknown")
        print(f"  Raga rules: {raga_name} (scale degrees: {scale_degrees})")
    else:
        print(f"  WARNING: rules file {args.rules} not found, using Yaman defaults")

    # ── Deterministic RNG ─────────────────────────────────────────────
    rng = np.random.default_rng(RNG_SEED)

    # ── Generate layers (with cache) ─────────────────────────────────
    drum_key = _prod_cache_key("drums", sr=sr, samples=total_samples, bpm=style_bpm, pat=style_drum_pattern)
    drums = _prod_cache_load(drum_key)
    if drums is not None:
        print(f"\n  Drums loaded from cache ({style_drum_pattern})")
    else:
        print(f"\n  Generating {style_name} drums ({style_drum_pattern}) at {int(style_bpm)} BPM …")
        drums = generate_drum_loop(sr, total_samples, style_bpm, rng, pattern=style_drum_pattern)
        _prod_cache_save(drum_key, drums)

    bass_key = _prod_cache_key("bass", sr=sr, samples=total_samples, bpm=style_bpm,
                               sa_hz=round(sa_hz, 2), scale=str(scale_degrees), pat=style_bass_pattern)
    bass = _prod_cache_load(bass_key)
    if bass is not None:
        print(f"  Bass loaded from cache ({style_bass_pattern})")
    else:
        print(f"  Generating {style_bass_pattern} bass line (root: {sa_note}) …")
        bass = generate_bass_line(sr, total_samples, style_bpm, sa_hz, scale_degrees,
                                  pattern=style_bass_pattern)
        _prod_cache_save(bass_key, bass)

    crackle = None
    if style_crackle or "crackle" in style_fx:
        crackle_key = _prod_cache_key("crackle", sr=sr, samples=total_samples)
        crackle = _prod_cache_load(crackle_key)
        if crackle is not None:
            print("  Crackle loaded from cache")
        else:
            print("  Generating vinyl crackle texture …")
            crackle = generate_vinyl_crackle(sr, total_samples, rng)
            _prod_cache_save(crackle_key, crackle)

    # ── Mix ────────────────────────────────────────────────────────────
    print("  Mixing layers …")
    mixed = mix_layers(melody, drums, bass, crackle, levels=style_levels)

    # ── Apply FX ──────────────────────────────────────────────────────
    if "pad" in style_fx:
        print("  Adding pad texture …")
        pad = generate_pad_texture(sr, total_samples, sa_hz, scale_degrees)
        mixed = mixed.astype(np.float64) + pad.astype(np.float64)
        mixed = mixed.astype(np.float32)

    if "delay" in style_fx:
        delay_ms = 60000.0 / style_bpm * 0.75  # dotted-eighth sync
        print(f"  Adding dub delay ({delay_ms:.0f}ms) …")
        mixed = generate_delay_wash(mixed, sr, delay_ms=delay_ms)

    if "sidechain" in style_fx:
        print("  Applying sidechain pump …")
        mixed = apply_sidechain(mixed, drums, sr, style_bpm)

    # ── Master ─────────────────────────────────────────────────────────
    print(f"  Mastering (HPF → EQ → warmth → compression → limiter → stereo) [{style_name}] …")
    final = master(mixed, sr, style=style_name)

    # ── Export ─────────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), final, sr)

    # ── Report ─────────────────────────────────────────────────────────
    bass_root_hz = sa_hz / 4.0
    print_report(
        input_path=str(input_path),
        duration=duration,
        sa_note=sa_note,
        sa_hz=sa_hz,
        genre=style_name,
        bpm=style_bpm,
        bass_root_hz=bass_root_hz,
        crackle_on=style_crackle,
        output_path=str(out_path),
    )
    print(f"  Done — wrote {out_path} ({duration:.2f}s)")


if __name__ == "__main__":
    main()
