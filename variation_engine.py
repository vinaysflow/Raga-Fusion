#!/usr/bin/env python3
"""
variation_engine.py — Phrase variation generator.

Creates musical variations from existing phrase libraries while preserving
raga grammar. Supports tempo scaling, density shifting, motif amplification,
and harmonic coloring.

Usage (as module):
    from variation_engine import create_variation_library
    create_variation_library("data/phrases/yaman", "output/var_lib", "tempo", 0.2)

Usage (CLI):
    python variation_engine.py --source data/phrases/yaman --output output/var --type tempo --amount 0.2
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("ERROR: soundfile required. pip install soundfile")
    sys.exit(1)

try:
    from scipy.signal import resample
except ImportError:
    print("ERROR: scipy required. pip install scipy")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
#  Variation functions
# ═══════════════════════════════════════════════════════════════════════

def tempo_scale(audio: np.ndarray, factor: float) -> np.ndarray:
    """Time-stretch audio by resampling (changes pitch + tempo together).

    factor > 1.0 = faster, factor < 1.0 = slower.
    """
    if abs(factor - 1.0) < 0.01:
        return audio
    new_len = int(len(audio) / factor)
    if new_len < 10:
        return audio
    return resample(audio, new_len).astype(np.float32)


def pitch_shift_simple(audio: np.ndarray, semitones: float) -> np.ndarray:
    """Shift pitch by resampling then time-correcting (basic, artifact-prone)."""
    if abs(semitones) < 0.1:
        return audio
    factor = 2.0 ** (semitones / 12.0)
    resampled = resample(audio, int(len(audio) / factor)).astype(np.float32)
    if len(resampled) > len(audio):
        return resampled[:len(audio)]
    elif len(resampled) < len(audio):
        return np.pad(resampled, (0, len(audio) - len(resampled)))
    return resampled


def density_shift(audio: np.ndarray, factor: float) -> np.ndarray:
    """Adjust phrase density: chop or stretch internal segments.

    factor > 1.0 = denser (faster attack, shorter sustain)
    factor < 1.0 = sparser (longer sustain, gentler transitions)
    """
    if abs(factor - 1.0) < 0.05:
        return audio

    n = len(audio)
    if factor > 1.0:
        attack_fade = min(int(n * 0.05), int(0.02 * 22050))
        release_fade = min(int(n * 0.1), int(0.05 * 22050))
        env = np.ones(n, dtype=np.float32)
        if attack_fade > 0:
            env[:attack_fade] = np.linspace(0.3, 1.0, attack_fade)
        if release_fade > 0:
            env[-release_fade:] = np.linspace(1.0, 0.2, release_fade)
        audio = audio * env
        trim = int(n * min(factor - 1.0, 0.4))
        if trim > 0 and n - trim > 100:
            audio = audio[:n - trim]
    else:
        stretch_factor = 1.0 / factor
        new_len = int(n * min(stretch_factor, 2.0))
        audio = resample(audio.astype(np.float64), new_len).astype(np.float32)
        fade_in = min(int(new_len * 0.03), int(0.02 * 22050))
        if fade_in > 0:
            audio[:fade_in] *= np.linspace(0.5, 1.0, fade_in).astype(np.float32)

    return audio


def motif_amplify(audio: np.ndarray, amount: float = 0.3) -> np.ndarray:
    """Emphasize the core motif by boosting the loudest segment and fading edges."""
    n = len(audio)
    seg_size = max(n // 5, 100)

    energies = []
    for i in range(0, n, seg_size):
        chunk = audio[i:i + seg_size]
        energies.append(float(np.sqrt(np.mean(chunk ** 2))))

    if not energies:
        return audio

    peak_seg = int(np.argmax(energies))
    env = np.ones(n, dtype=np.float32)
    for i in range(len(energies)):
        start = i * seg_size
        end = min(start + seg_size, n)
        if i == peak_seg:
            env[start:end] = 1.0 + amount * 0.5
        else:
            dist = abs(i - peak_seg)
            env[start:end] = max(0.5, 1.0 - amount * dist * 0.15)

    result = audio * env
    peak = np.max(np.abs(result))
    if peak > 0.99:
        result = result * (0.99 / peak)
    return result


def harmonic_color(audio: np.ndarray, sr: int, color_amount: float = 0.2) -> np.ndarray:
    """Add harmonic coloring: subtle octave shimmer + filtered presence boost."""
    n = len(audio)
    audio = audio.astype(np.float64)

    octave_up = resample(audio, n // 2) if n > 100 else audio
    if len(octave_up) < n:
        octave_up = np.pad(octave_up, (0, n - len(octave_up)))
    else:
        octave_up = octave_up[:n]

    t = np.arange(n, dtype=np.float64) / sr
    shimmer_env = 0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t)
    octave_layer = octave_up * shimmer_env * color_amount * 0.3

    result = audio + octave_layer
    peak = np.max(np.abs(result))
    if peak > 0.99:
        result = result * (0.99 / peak)
    return result.astype(np.float32)


VARIATION_FUNCTIONS = {
    "tempo": lambda audio, sr, amt: tempo_scale(audio, 1.0 + amt),
    "pitch": lambda audio, sr, amt: pitch_shift_simple(audio, amt * 2),
    "density": lambda audio, sr, amt: density_shift(audio, 1.0 + amt),
    "motif": lambda audio, sr, amt: motif_amplify(audio, amt),
    "harmonic": lambda audio, sr, amt: harmonic_color(audio, sr, amt),
}

PRESET_PROFILES: dict[str, list[tuple[str, float]]] = {
    "pure": [("tempo", 0.03), ("density", 0.04), ("motif", 0.08)],
    "balanced": [("tempo", 0.06), ("density", 0.08), ("motif", 0.12), ("harmonic", 0.08)],
    "fusion": [("tempo", 0.1), ("density", 0.12), ("motif", 0.14), ("harmonic", 0.15)],
    "experimental": [("tempo", 0.14), ("density", 0.18), ("motif", 0.2), ("harmonic", 0.2)],
}

PRESET_FALLBACK = {
    "experimental": "fusion",
    "fusion": "balanced",
    "balanced": "pure",
}


def resolve_variation_ops(variation_type: str, amount: float, preset: str | None = None) -> tuple[str, list[tuple[str, float]]]:
    if preset:
        profile = PRESET_PROFILES.get(preset)
        if profile is None:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESET_PROFILES.keys())}")
        return preset, profile
    if variation_type not in VARIATION_FUNCTIONS:
        raise ValueError(f"Unknown variation type: {variation_type}. Available: {list(VARIATION_FUNCTIONS.keys())}")
    return "custom", [(variation_type, amount)]


def apply_variation_pipeline(audio: np.ndarray, sr: int, ops: list[tuple[str, float]]) -> np.ndarray:
    varied = audio
    for op_type, amt in ops:
        var_fn = VARIATION_FUNCTIONS.get(op_type)
        if var_fn is None:
            continue
        varied = var_fn(varied, sr, amt)
    return varied


# ═══════════════════════════════════════════════════════════════════════
#  Library-level variation
# ═══════════════════════════════════════════════════════════════════════

def create_variation_library(
    source_dir: str | Path,
    output_dir: str | Path,
    variation_type: str = "tempo",
    amount: float = 0.2,
    preset: str | None = None,
) -> Path:
    """Create a variation of an entire phrase library.

    Reads all phrases from source_dir, applies the variation, writes to output_dir.
    Returns the output_dir Path.
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    meta_path = source_dir / "phrases_metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No phrases_metadata.json in {source_dir}")

    with open(meta_path) as f:
        metadata = json.load(f)

    preset_name, ops = resolve_variation_ops(variation_type, amount, preset)

    new_metadata = []
    for entry in metadata:
        wav_path = source_dir / entry["file"]
        if not wav_path.exists():
            continue

        audio, sr = sf.read(str(wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        varied = apply_variation_pipeline(audio, sr, ops)

        out_wav = output_dir / entry["file"]
        sf.write(str(out_wav), varied, sr)

        new_entry = dict(entry)
        new_entry["duration"] = round(len(varied) / sr, 2)
        new_entry["variation_type"] = variation_type
        new_entry["variation_amount"] = amount
        new_entry["variation_preset"] = preset_name if preset else None
        new_entry["variation_ops"] = [{"type": t, "amount": a} for t, a in ops]
        new_metadata.append(new_entry)

    out_meta = output_dir / "phrases_metadata.json"
    with open(out_meta, "w") as f:
        json.dump(new_metadata, f, indent=2)

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Generate phrase library variations.")
    parser.add_argument("--source", type=Path, required=True, help="Source phrase library dir")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--type", default="tempo",
                        choices=list(VARIATION_FUNCTIONS.keys()),
                        help="Variation type")
    parser.add_argument("--preset", default=None,
                        choices=list(PRESET_PROFILES.keys()),
                        help="Preset variation profile")
    parser.add_argument("--amount", type=float, default=0.2,
                        help="Variation amount (0.0-1.0)")
    args = parser.parse_args()

    label = args.preset or args.type
    print(f"\n  Creating {label} variation (amount={args.amount}) from {args.source}")
    out = create_variation_library(args.source, args.output, args.type, args.amount, args.preset)
    print(f"  Wrote variation library to {out}\n")


if __name__ == "__main__":
    main()
