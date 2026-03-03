#!/usr/bin/env python3
"""
seed_rod_data.py — Ingest ROD dataset into phrase libraries.

Reads expert-annotated ROD audio segments, maps them to raga rule files,
extracts phrase metadata (notes, ornaments, arc section), and merges
the results into data/phrases/{raga}/.

Usage:
    python seed_rod_data.py --dataset "/Users/vinaytripathi/Downloads/DATA"
    python seed_rod_data.py --dataset "/Users/vinaytripathi/Downloads/DATA" --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import librosa
except ImportError:
    print("\n  ERROR: librosa is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

try:
    import soundfile as sf
except ImportError:
    print("\n  ERROR: soundfile is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

from analyze_raga import HOP_LENGTH, SAMPLE_RATE, detect_sa, load_audio
from extract_phrases import (
    ENERGY_FLOOR_PCT,
    IDEAL_DURATION,
    MIN_DISTINCT_SVARAS,
    MIN_SEQUENCE_LEN,
    MIN_VOICED_RATIO,
    analyze_phrase_notes,
    build_candidate_segments,
    compute_segment_rms,
    compute_voiced_ratio,
    detect_onset_boundaries,
    detect_silence_boundaries,
    merge_boundaries,
    score_segment,
)
from ornament_detector import detect_ornaments
from raga_arc_profiler import classify_arc_section, compute_note_density, infer_register, median_f0
from raga_scorer import RagaScorer

RAGA_ALIASES = {
    "bageshree": ["bageshree"],
    "bhairav": ["bhairav"],
    "bhoopali": ["bhoopali", "bhupali", "bhopali"],
    "darbari": ["darbari"],
}

ARC_HINTS = {
    "alaap": "alap_opening",
    "alap": "alap_opening",
    "sthai": "vilambit_gat",
    "antra": "gat_development",
    "chhoti_taan": "gat_development",
    "badi_taan": "peak_taan",
    "taan": "peak_taan",
    "alankar": "jod",
    "palta": "jod",
    "sargam": "jod",
    "pakad": "alap_opening",
    "aroh": "alap_opening",
    "avroh": "alap_opening",
}

ORNAMENT_MAP = {
    "K": "kan",
    "k": "kan",
    "H": "nyas_svar",
    "H1": "nyas_svar",
    "Me": "meend",
    "Me1": "meend",
    "G": "gamak",
    "Mu": "murki",
    "Mu1": "murki",
    "An": "andolan",
    "An1": "andolan",
}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _parse_teacher_id(name: str) -> str | None:
    match = re.match(r"^(\d{3})_", name)
    return match.group(1) if match else None


def _detect_raga_from_name(name: str) -> str | None:
    lower = name.lower()
    for canon, aliases in RAGA_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                return canon
    return None


def _parse_lesson_id(name: str, raga: str) -> int | None:
    lower = name.lower()
    # e.g. "001_bageshree_10_..." or "002_bhairav10_..."
    match = re.search(rf"{re.escape(raga)}[_-]?(\d+)", lower)
    if match:
        return int(match.group(1))
    return None


def _infer_arc_from_name(name: str) -> tuple[str, float, str | None]:
    lower = name.lower()
    for key, section in ARC_HINTS.items():
        if key in lower:
            return section, 0.9, key
    return "gat_development", 0.4, None


def _is_non_musical(name: str) -> bool:
    lower = name.lower()
    if "a#3_audio" in lower or "a#3 audio" in lower:
        return True
    if "silence" in lower or "puzzle" in lower or "odd" in lower:
        return True
    return False


def _load_metadata(path: Path) -> dict[tuple[str, int], dict]:
    mapping: dict[tuple[str, int], dict] = {}
    if not path.exists():
        return mapping
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lesson_id = row.get("lesson_id")
            teacher_id = row.get("teacher_id") or ""
            if not lesson_id or not teacher_id:
                continue
            try:
                lesson_id = int(lesson_id)
            except ValueError:
                continue
            teacher_digits = re.sub(r"\D", "", teacher_id)
            if not teacher_digits:
                continue
            mapping[(teacher_digits, lesson_id)] = row
    return mapping


def _build_label_index(labels_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for split in ("train", "test"):
        split_dir = labels_dir / split
        if not split_dir.exists():
            continue
        for p in split_dir.glob("*.txt"):
            index[p.stem] = p
    return index


def _load_labels(label_path: Path | None) -> list[dict]:
    if not label_path or not label_path.exists():
        return []
    results = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                start = float(parts[0])
                end = float(parts[1])
            except ValueError:
                continue
            raw = parts[2]
            ornament = ORNAMENT_MAP.get(raw, raw)
            results.append({
                "start_sec": round(start, 4),
                "end_sec": round(end, 4),
                "ornament": ornament,
            })
    return results


def _sa_from_metadata(row: dict | None) -> tuple[int, str, float] | None:
    if not row:
        return None
    sa_note = row.get("t_scale")
    if not sa_note:
        return None
    try:
        sa_hz = float(librosa.note_to_hz(sa_note))
        sa_midi = int(round(librosa.hz_to_midi(sa_hz)))
    except Exception:
        return None
    return sa_midi % 12, sa_note, sa_hz


def _detect_sa_from_audio(y: np.ndarray, sr: int) -> tuple[int, str, float]:
    f0, voiced, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C6"),
        sr=sr,
        hop_length=HOP_LENGTH,
    )
    valid = ~np.isnan(f0) & voiced
    if not np.any(valid):
        return 0, "C4", 261.63
    midi = np.round(librosa.hz_to_midi(f0[valid])).astype(int)
    pc_sample = midi % 12
    sa_pc, sa_note, sa_hz = detect_sa(pc_sample)
    return sa_pc, f"{sa_note}4", sa_hz


def _segment_phrases(y: np.ndarray, sr: int, duration: float,
                     min_dur: float, max_dur: float,
                     target_count: int) -> list[tuple]:
    onset_bounds = detect_onset_boundaries(y, sr)
    silence_bounds, rms_full, _ = detect_silence_boundaries(y, sr)
    boundaries = merge_boundaries(onset_bounds, silence_bounds, duration)
    candidates = build_candidate_segments(boundaries, min_dur, max_dur)
    if not candidates:
        return [(0.0, duration, None, 1.0, 1.0, None, 0.5)]

    global_rms_floor = float(np.percentile(rms_full[rms_full > 0], ENERGY_FLOOR_PCT)) \
        if np.any(rms_full > 0) else 0
    global_rms_max = float(np.max(rms_full)) if np.any(rms_full > 0) else 1.0

    scored = []
    for start, end in candidates:
        seg_rms = compute_segment_rms(y, sr, start, end)
        if seg_rms < global_rms_floor:
            continue
        norm_e = min(1.0, seg_rms / global_rms_max) if global_rms_max > 0 else 0.0
        s_idx = int(start * sr)
        e_idx = int(end * sr)
        y_seg = y[s_idx:e_idx]
        voiced_ratio, f0 = compute_voiced_ratio(y_seg, sr)
        if voiced_ratio < MIN_VOICED_RATIO:
            continue
        quality = score_segment(voiced_ratio, norm_e, end - start, ideal=IDEAL_DURATION)
        scored.append((quality, start, end, seg_rms, norm_e, voiced_ratio, f0))

    if not scored:
        return [(0.0, duration, None, 1.0, 1.0, None, 0.5)]

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[:target_count]
    return [(s, e, r, n, v, f0, q) for q, s, e, r, n, v, f0 in selected]


def _next_phrase_index(existing: Iterable[dict], prefix: str) -> int:
    max_idx = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for entry in existing:
        pid = entry.get("phrase_id", "")
        match = pattern.match(pid)
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def process_dataset(dataset_root: Path, output_root: Path,
                    min_dur: float, max_dur: float,
                    single_phrase_max: float,
                    max_phrases_per_clip: int,
                    dry_run: bool = False) -> dict:
    rod_root = dataset_root / "ROD"
    audio_dir = rod_root / "audio"
    expert_001 = rod_root / "Expert_001"
    expert_002 = rod_root / "Expert_002"

    metadata = {}
    metadata.update(_load_metadata(expert_001 / "metadata_001.csv"))
    metadata.update(_load_metadata(expert_002 / "metadata_002.csv"))

    labels_001 = _build_label_index(expert_001 / "labels")
    labels_002 = _build_label_index(expert_002 / "labels")
    label_index = {**labels_001, **labels_002}

    summary = {"processed": 0, "skipped": 0, "phrases_added": 0, "raga_counts": {}}

    for audio_path in sorted(audio_dir.glob("*.wav")):
        name = audio_path.name
        if _is_non_musical(name):
            summary["skipped"] += 1
            continue

        teacher_id = _parse_teacher_id(name)
        raga = _detect_raga_from_name(name)
        if not raga or not teacher_id:
            summary["skipped"] += 1
            continue

        lesson_id = _parse_lesson_id(name, raga)
        meta_row = metadata.get((teacher_id, lesson_id)) if lesson_id else None

        label_path = label_index.get(audio_path.stem)
        gt_ornaments = _load_labels(label_path)

        y, sr, duration = load_audio(audio_path)

        sa_info = _sa_from_metadata(meta_row)
        if sa_info:
            sa_pc, sa_note, sa_hz = sa_info
        else:
            sa_pc, sa_note, sa_hz = _detect_sa_from_audio(y, sr)

        tempo_confidence = 0.0
        try:
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            beat_count = len(beats) if hasattr(beats, "__len__") else 0
            tempo_confidence = min(1.0, beat_count / max(1.0, duration / 2))
        except Exception:
            tempo_confidence = 0.0

        out_dir = output_root / raga
        out_dir.mkdir(parents=True, exist_ok=True)
        meta_path = out_dir / "phrases_metadata.json"
        existing = []
        if meta_path.exists():
            with open(meta_path) as f:
                existing = json.load(f)

        existing_keys = {
            (e.get("source_file"), e.get("source_segment")) for e in existing
        }

        prefix = f"{raga}_phrase"
        next_idx = _next_phrase_index(existing, prefix)

        scorer = None
        rules_path = Path("data/raga_rules") / f"{raga}.json"
        if rules_path.exists():
            scorer = RagaScorer.from_rules_file(rules_path)

        if duration <= single_phrase_max:
            segments = [(0.0, duration, None, 1.0, 1.0, None, 0.5)]
        else:
            target_count = max(1, min(max_phrases_per_clip, int(duration / IDEAL_DURATION)))
            segments = _segment_phrases(y, sr, duration, min_dur, max_dur, target_count)

        for seg_idx, (start, end, seg_rms, norm_e, voiced_ratio, f0, quality) in enumerate(segments, 1):
            if (name, seg_idx) in existing_keys:
                continue

            s_idx = int(start * sr)
            e_idx = int(end * sr)
            y_seg = y[s_idx:e_idx]
            if len(y_seg) == 0:
                continue

            if f0 is None:
                voiced_ratio, f0 = compute_voiced_ratio(y_seg, sr)
                norm_e = 1.0 if norm_e is None else norm_e
                quality = score_segment(voiced_ratio, norm_e, end - start, ideal=IDEAL_DURATION)

            allowed = scorer.allowed_degrees if scorer else None
            note_info = analyze_phrase_notes(f0, sa_pc, allowed_degrees=allowed)
            if len(note_info["notes_detected"]) < MIN_DISTINCT_SVARAS or \
               len(note_info["notes_sequence"]) < MIN_SEQUENCE_LEN:
                continue

            note_density = compute_note_density(len(note_info["notes_sequence"]), end - start)
            register = infer_register(median_f0(f0), sa_hz)
            position_ratio = start / max(duration, 0.01)
            arc_section, arc_conf = classify_arc_section(
                norm_e if norm_e is not None else 0.5,
                note_density,
                tempo_confidence,
                register,
                position_ratio,
            )
            hint_section, hint_conf, hint_tag = _infer_arc_from_name(name)
            if hint_conf >= 0.8:
                arc_section = hint_section
                arc_conf = hint_conf

            ornaments = detect_ornaments(f0, ~np.isnan(f0), sr, HOP_LENGTH)

            phrase_id = f"{prefix}_{next_idx:03d}"
            wav_name = f"{phrase_id}.wav"
            wav_path = out_dir / wav_name

            if not dry_run:
                sf.write(str(wav_path), y_seg, sr)

            entry = {
                "phrase_id": phrase_id,
                "file": wav_name,
                "start_time": round(start, 2),
                "end_time": round(end, 2),
                "duration": round(end - start, 2),
                "source_duration": round(duration, 2),
                "position_ratio": round(position_ratio, 4),
                "notes_detected": note_info["notes_detected"],
                "notes_sequence": note_info["notes_sequence"],
                "dominant_note": note_info["dominant_note"],
                "starts_with": note_info["starts_with"],
                "ends_with": note_info["ends_with"],
                "voiced_ratio": round(float(voiced_ratio), 3),
                "energy_level": round(float(norm_e if norm_e is not None else 0.5), 3),
                "quality_score": round(float(quality), 3),
                "note_density": round(note_density, 3),
                "register": register,
                "arc_section": arc_section,
                "arc_confidence": round(float(arc_conf), 3),
                "arc_fraction": round(float(position_ratio), 3),
                "ornaments_detected": ornaments,
                "ground_truth_ornaments": gt_ornaments,
                "source_key": f"rod_{audio_path.stem}",
                "source_title": audio_path.stem,
                "source_artist": None,
                "source_platform": "rod_dataset",
                "rights_status": "open_dataset",
                "license_type": "CC-BY-4.0",
                "source_type": "rod_dataset",
                "library_tier": "standard",
                "source_file": name,
                "source_segment": seg_idx,
                "teacher_id": teacher_id,
                "lesson_id": lesson_id,
                "lesson_name": meta_row.get("lesson_name") if meta_row else None,
                "t_scale": meta_row.get("t_scale") if meta_row else None,
                "t_bpm": meta_row.get("t_bpm") if meta_row else None,
                "t_taal": meta_row.get("taal") if meta_row else None,
                "t_tanpura_file": meta_row.get("t_tanpura_file") if meta_row else None,
                "t_taal_file": meta_row.get("t_taal_file") if meta_row else None,
                "arc_hint": hint_tag,
            }

            if scorer:
                entry = scorer.score_phrase(entry)

            existing.append(entry)
            existing_keys.add((name, seg_idx))
            summary["phrases_added"] += 1
            summary["raga_counts"][raga] = summary["raga_counts"].get(raga, 0) + 1
            next_idx += 1

        if not dry_run:
            with open(meta_path, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

        summary["processed"] += 1

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the ROD dataset into raga phrase libraries."
    )
    parser.add_argument(
        "--dataset", type=str, required=True,
        help="Path to DATA directory containing ROD/ and PB/ folders",
    )
    parser.add_argument(
        "--output", type=str, default="data/phrases",
        help="Output phrase root directory (default: data/phrases)",
    )
    parser.add_argument(
        "--min-dur", type=float, default=2.0,
        help="Minimum phrase duration for segmentation (seconds)",
    )
    parser.add_argument(
        "--max-dur", type=float, default=6.0,
        help="Maximum phrase duration for segmentation (seconds)",
    )
    parser.add_argument(
        "--single-max", type=float, default=8.0,
        help="Treat clips <= this duration as single phrases",
    )
    parser.add_argument(
        "--max-per-clip", type=int, default=6,
        help="Max phrases to extract from a long clip",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and score, but do not write audio or metadata",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset)
    output_root = Path(args.output)
    if not dataset_root.exists():
        print(f"\n  ERROR: dataset path not found: {dataset_root}")
        sys.exit(1)

    print("\n  Seeding ROD dataset ...")
    summary = process_dataset(
        dataset_root=dataset_root,
        output_root=output_root,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
        single_phrase_max=args.single_max,
        max_phrases_per_clip=args.max_per_clip,
        dry_run=args.dry_run,
    )
    print("\n  Done.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
