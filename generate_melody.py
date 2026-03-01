#!/usr/bin/env python3
"""
generate_melody.py — Rule-based raga melody generator

Generates phrase WAVs and metadata from raga rules (e.g. yaman.json)
so Assemble and Add production can run without a source recording.
Output matches extract_phrases format: phrases_metadata.json + yaman_phrase_001.wav, etc.

Usage:
    python generate_melody.py --rules data/raga_rules/yaman.json --output data/phrases/yaman_generated --count 20
    python generate_melody.py --duration 30 --output data/phrases/yaman_generated

Requires: numpy, soundfile (from requirements.txt).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("\n  ERROR: soundfile is required. Run: pip install -r requirements.txt\n")
    sys.exit(1)

from analyze_raga import SAMPLE_RATE

# Full degree→display-name map covering all thaat svaras
DEGREE_TO_NAME = {
    0: "Sa", 1: "re", 2: "Re", 3: "ga", 4: "Ga",
    5: "ma", 6: "Ma'", 7: "Pa", 8: "dha", 9: "Dha",
    10: "ni", 11: "Ni", 12: "Sa'",
}

# Svara string → semitone degree (handles shuddh, komal, and tivra)
SVARA_DEGREE_MAP = {
    "S": 0, "S'": 12,
    "r": 1, "R": 2,
    "g": 3, "G": 4,
    "m": 5, "M": 5, "M'": 6,
    "P": 7,
    "d": 8, "D": 9,
    "n": 10, "N": 11,
}

SR = SAMPLE_RATE
SA_HZ = 261.63  # C4
RNG_SEED = 42

# Harmonic profile: sitar/sarangi-like timbre
# (harmonic number, relative amplitude)
HARMONICS = [(1, 1.0), (2, 0.45), (3, 0.25), (4, 0.15), (5, 0.08), (6, 0.05)]

VIBRATO_RATE = 5.0     # Hz — natural vocal/string vibrato speed
VIBRATO_DEPTH = 0.004  # semitones as fraction — subtle pitch wobble
PORTAMENTO_SEC = 0.06  # glide time between notes


def _degree_to_hz(degree: int, sa_hz: float = SA_HZ) -> float:
    """Convert scale degree (0–12) to frequency in Hz."""
    return sa_hz * (2.0 ** (degree / 12.0))


def _render_note(
    degree: int,
    duration_sec: float,
    sa_hz: float,
    prev_degree: int | None = None,
) -> np.ndarray:
    """Render a note with harmonics, vibrato, and optional portamento from prev note."""
    n = int(SR * duration_sec)
    t = np.arange(n, dtype=np.float64) / SR
    freq = _degree_to_hz(degree, sa_hz)

    # Portamento: glide from previous note's frequency
    if prev_degree is not None and prev_degree != degree:
        prev_freq = _degree_to_hz(prev_degree, sa_hz)
        glide_n = min(int(PORTAMENTO_SEC * SR), n // 3)
        freq_curve = np.full(n, freq, dtype=np.float64)
        if glide_n > 0:
            freq_curve[:glide_n] = np.linspace(prev_freq, freq, glide_n)
    else:
        freq_curve = np.full(n, freq, dtype=np.float64)

    # Vibrato: sinusoidal pitch modulation (increases after attack)
    vibrato_env = np.clip(t / 0.15, 0.0, 1.0)  # ramp in over 150ms
    vibrato = 1.0 + VIBRATO_DEPTH * vibrato_env * np.sin(2.0 * np.pi * VIBRATO_RATE * t)
    inst_freq = freq_curve * vibrato

    # Phase accumulation for FM-like synthesis
    phase = np.cumsum(inst_freq / SR) * 2.0 * np.pi

    # Multi-harmonic tone
    tone = np.zeros(n, dtype=np.float64)
    for h_num, h_amp in HARMONICS:
        tone += h_amp * np.sin(h_num * phase)
    # Normalize harmonics sum
    tone /= sum(a for _, a in HARMONICS)

    # ADSR envelope: attack-decay-sustain-release
    attack = min(int(0.05 * SR), n // 4)
    decay = min(int(0.08 * SR), n // 4)
    release = min(int(0.12 * SR), n // 3)
    sustain_level = 0.7
    env = np.ones(n) * sustain_level
    if attack > 0:
        env[:attack] = np.linspace(0, 1, attack)
    if decay > 0 and attack + decay < n:
        env[attack:attack + decay] = np.linspace(1, sustain_level, decay)
    if release > 0:
        env[-release:] = np.linspace(env[-release - 1] if release < n else sustain_level, 0, release)

    return (tone * env * 0.55).astype(np.float32)


def _render_tanpura(duration_sec: float, sa_hz: float, use_pa: bool = True) -> np.ndarray:
    """Render a continuous tanpura drone as background texture.

    Standard tuning: Sa + Pa + low Sa.
    For ragas without Pa (e.g. Malkauns): Sa + Ma + low Sa.
    """
    n = int(SR * duration_sec)
    t = np.arange(n, dtype=np.float64) / SR
    drone = np.zeros(n, dtype=np.float64)

    fifth_ratio = 1.5 if use_pa else (2.0 ** (5 / 12.0))  # Pa or Ma
    drone_notes = [
        (sa_hz, 1.0),                # Sa
        (sa_hz * fifth_ratio, 0.5),  # Pa (or Ma for Pa-less ragas)
        (sa_hz * 0.5, 0.6),          # low Sa (octave below)
    ]
    for freq, amp in drone_notes:
        # Each string has slow amplitude beating + harmonics
        beat = 1.0 + 0.15 * np.sin(2.0 * np.pi * 0.3 * t + freq)
        tone = amp * beat * (
            np.sin(2.0 * np.pi * freq * t)
            + 0.3 * np.sin(2.0 * np.pi * 2 * freq * t)
            + 0.1 * np.sin(2.0 * np.pi * 3 * freq * t)
        )
        drone += tone

    # Normalize and apply gentle fade-in/out
    drone /= np.max(np.abs(drone)) + 1e-9
    fade_in = min(int(0.5 * SR), n // 4)
    fade_out = min(int(0.3 * SR), n // 4)
    if fade_in > 0:
        drone[:fade_in] *= np.linspace(0, 1, fade_in)
    if fade_out > 0:
        drone[-fade_out:] *= np.linspace(1, 0, fade_out)

    return (drone * 0.12).astype(np.float32)  # low level — background texture


def _render_gamak(
    degree: int,
    neighbor_degree: int,
    duration_sec: float,
    sa_hz: float,
    oscillations: int = 6,
) -> np.ndarray:
    """Render a gamak: rapid oscillation between a note and its neighbor."""
    n = int(SR * duration_sec)
    t = np.arange(n, dtype=np.float64) / SR
    freq_main = _degree_to_hz(degree, sa_hz)
    freq_neighbor = _degree_to_hz(neighbor_degree, sa_hz)

    osc_rate = oscillations / duration_sec
    # Smooth sinusoidal interpolation between the two pitches
    blend = 0.5 + 0.5 * np.sin(2.0 * np.pi * osc_rate * t)
    inst_freq = freq_main * (1.0 - blend) + freq_neighbor * blend

    phase = np.cumsum(inst_freq / SR) * 2.0 * np.pi
    tone = np.zeros(n, dtype=np.float64)
    for h_num, h_amp in HARMONICS:
        tone += h_amp * np.sin(h_num * phase)
    tone /= sum(a for _, a in HARMONICS)

    # Envelope with gentle attack/release
    attack = min(int(0.04 * SR), n // 4)
    release = min(int(0.08 * SR), n // 3)
    env = np.ones(n) * 0.75
    if attack > 0:
        env[:attack] = np.linspace(0, 0.75, attack)
    if release > 0:
        env[-release:] = np.linspace(0.75, 0, release)

    return (tone * env * 0.55).astype(np.float32)


def _parse_pakad(pakad_strings: list[str]) -> list[list[int]]:
    """Convert pakad strings like ["N R G", "g m d P"] to lists of degree ints."""
    pakad_degrees = []
    for p in pakad_strings:
        parts = p.replace("\u2019", "'").replace("\u2018", "'").split()
        seg = []
        for x in parts:
            tok = x.strip()
            if tok in SVARA_DEGREE_MAP:
                seg.append(SVARA_DEGREE_MAP[tok])
            elif tok and tok[0] in SVARA_DEGREE_MAP:
                seg.append(SVARA_DEGREE_MAP[tok[0]])
        if seg:
            pakad_degrees.append(seg)
    return pakad_degrees


def _phrase_degrees_from_rules(
    rules: dict, rng: np.random.Generator,
) -> tuple[list[tuple[int, float]], str]:
    """Build one phrase as (degree, duration_sec) list from raga rules.

    Returns (notes, template_name) where template_name is one of:
    pakad, aroha, avaroha, walk, alap, gamak, taan.
    """
    scale = rules.get("scale", {})
    movement = rules.get("movement", {})
    emphasis = rules.get("emphasis", {})
    degrees = scale.get("degrees", [0, 2, 4, 6, 7, 9, 11])
    aroha_d = movement.get("aroha_degrees", [0, 2, 4, 6, 7, 9, 11, 12])
    avaroha_d = movement.get("avaroha_degrees", [12, 11, 9, 7, 6, 4, 2, 0])
    pakad = movement.get("pakad", [])
    pakad_degrees = _parse_pakad(pakad)

    vadi_deg = emphasis.get("vadi", {}).get("degree", degrees[len(degrees) // 2])
    samvadi_deg = emphasis.get("samvadi", {}).get("degree", degrees[0])

    # 7 template types weighted by musical variety
    templates = ["pakad", "aroha", "avaroha", "walk", "alap", "gamak", "taan"]
    weights = np.array([2.0, 1.5, 1.5, 1.0, 2.0, 1.5, 1.0])
    if not pakad_degrees:
        weights[0] = 0.0
    weights /= weights.sum()
    template = rng.choice(templates, p=weights)

    if template == "alap":
        # Slow meditative exploration: 3-5 long notes centered on vadi/samvadi
        n_notes = int(rng.integers(3, 6))
        total_dur = float(rng.uniform(3.5, 6.0))
        important = [vadi_deg, samvadi_deg, 0]  # vadi, samvadi, Sa
        pool = important + degrees[:3]  # lower register focus
        seg = [pool[rng.integers(0, len(pool))] for _ in range(n_notes)]
        # Ensure we start near Sa and end on vadi or Sa
        seg[0] = 0
        seg[-1] = rng.choice([vadi_deg, 0])
        note_durs = np.random.dirichlet(np.ones(n_notes) * 0.3)
        note_durs = (note_durs * total_dur).tolist()
        return list(zip(seg, note_durs)), "alap"

    if template == "gamak":
        # Oscillation on vadi/important note + its neighbor
        target = rng.choice([vadi_deg, samvadi_deg])
        idx = degrees.index(target) if target in degrees else 0
        neighbor_idx = min(idx + 1, len(degrees) - 1) if rng.random() > 0.5 else max(idx - 1, 0)
        neighbor = degrees[neighbor_idx]
        n_osc = int(rng.integers(4, 8))
        total_dur = float(rng.uniform(1.5, 3.0))

        # Build as alternating notes
        seg = []
        for i in range(n_osc * 2):
            seg.append(target if i % 2 == 0 else neighbor)
        note_durs = [total_dur / len(seg)] * len(seg)
        return list(zip(seg, note_durs)), "gamak"

    if template == "taan":
        # Fast scalar run: full aroha or avaroha at rapid pace
        direction = rng.choice(["up", "down", "up_down"])
        if direction == "up":
            seg = list(aroha_d)
        elif direction == "down":
            seg = list(avaroha_d)
        else:
            seg = list(aroha_d) + list(avaroha_d[1:])  # up then back down
        # Optionally repeat for longer taans
        if len(seg) < 10 and rng.random() > 0.5:
            seg = seg + seg
        n_notes = len(seg)
        per_note = float(rng.uniform(0.08, 0.13))
        note_durs = [per_note] * n_notes
        return list(zip(seg, note_durs)), "taan"

    # Original templates
    n_notes = int(rng.integers(4, 11))
    total_dur = float(rng.uniform(2.2, 4.0))
    note_durs = np.random.dirichlet(np.ones(n_notes))
    note_durs = (note_durs * total_dur).tolist()

    if template == "pakad" and pakad_degrees:
        seg = pakad_degrees[rng.integers(0, len(pakad_degrees))]
        seg = seg * (n_notes // len(seg) + 1)
        seg = seg[:n_notes]
    elif template == "aroha":
        idx = rng.integers(0, max(1, len(aroha_d) - n_notes))
        seg = aroha_d[idx : idx + n_notes]
        if len(seg) < n_notes:
            seg = seg + [aroha_d[-1]] * (n_notes - len(seg))
    elif template == "avaroha":
        idx = rng.integers(0, max(1, len(avaroha_d) - n_notes))
        seg = avaroha_d[idx : idx + n_notes]
        if len(seg) < n_notes:
            seg = seg + [avaroha_d[-1]] * (n_notes - len(seg))
    else:
        seg = [degrees[rng.integers(0, len(degrees))] for _ in range(n_notes)]

    return list(zip(seg, note_durs)), template


def generate_phrases(
    rules_path: Path,
    output_dir: Path,
    count: int = 20,
    sa_hz: float = SA_HZ,
    seed: int = RNG_SEED,
) -> list[dict]:
    """Generate *count* phrase WAVs and metadata. Returns list of metadata dicts."""
    with open(rules_path) as f:
        rules = json.load(f)
    raga_name = rules.get("raga", {}).get("name", "yaman").lower()
    prefix = raga_name + "_phrase_"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    metadata_list = []
    start_time = 0.0

    # Check if raga has Pa (for tanpura tuning)
    scale_degrees = rules.get("scale", {}).get("degrees", [0, 2, 4, 6, 7, 9, 11])
    has_pa = 7 in scale_degrees

    for i in range(count):
        phrase_id = f"{prefix}{i + 1:03d}"
        degree_durs, tmpl = _phrase_degrees_from_rules(rules, rng)
        chunks = []
        prev_deg = None
        for deg, dur in degree_durs:
            if tmpl == "gamak" and prev_deg is not None and prev_deg != deg:
                chunks.append(_render_gamak(prev_deg, deg, dur, sa_hz))
            else:
                chunks.append(_render_note(deg, dur, sa_hz, prev_degree=prev_deg))
            prev_deg = deg
        melody = np.concatenate(chunks)

        # Tanpura drone — use Ma instead of Pa for ragas like Malkauns that omit Pa
        drone = _render_tanpura(len(melody) / SR, sa_hz, use_pa=has_pa)
        if len(drone) > len(melody):
            drone = drone[: len(melody)]
        elif len(drone) < len(melody):
            drone = np.pad(drone, (0, len(melody) - len(drone)))
        audio = melody + drone

        duration = len(audio) / SR
        end_time = start_time + duration

        notes_detected = [DEGREE_TO_NAME.get(d, "Sa") for d, _ in degree_durs]
        from collections import Counter
        cnt = Counter(notes_detected)
        dominant_note = cnt.most_common(1)[0][0] if cnt else "Sa"
        starts_with = notes_detected[0] if notes_detected else "Sa"
        ends_with = notes_detected[-1] if notes_detected else "Sa"

        file_name = f"{phrase_id}.wav"
        wav_path = output_dir / file_name
        sf.write(str(wav_path), audio, SR)

        meta = {
            "phrase_id": phrase_id,
            "file": file_name,
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
            "duration": round(duration, 2),
            "notes_detected": notes_detected,
            "dominant_note": dominant_note,
            "starts_with": starts_with,
            "ends_with": ends_with,
            "voiced_ratio": 1.0,
            "energy_level": round(float(rng.uniform(0.18, 0.28)), 3),
            "quality_score": round(float(rng.uniform(0.68, 0.82)), 3),
        }
        metadata_list.append(meta)
        start_time = end_time

    meta_path = output_dir / "phrases_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata_list, f, indent=2)

    return metadata_list


def main():
    parser = argparse.ArgumentParser(description="Generate raga phrase WAVs from rules.")
    parser.add_argument("--rules", type=Path, default=Path("data/raga_rules/yaman.json"))
    parser.add_argument("--output", type=Path, default=Path("data/phrases/yaman_generated"))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--sa", type=float, default=SA_HZ, help="Sa frequency in Hz")
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    args = parser.parse_args()

    if not args.rules.exists():
        print(f"  ERROR: rules file not found: {args.rules}")
        sys.exit(1)

    print(f"\n  Generating {args.count} phrases from {args.rules} …")
    meta = generate_phrases(args.rules, args.output, args.count, args.sa, args.seed)
    print(f"  Wrote {len(meta)} phrases to {args.output}")
    print(f"  Metadata: {args.output / 'phrases_metadata.json'}\n")


if __name__ == "__main__":
    main()
