#!/usr/bin/env python3
"""
extract_phrases.py — Melodic Phrase Extractor for Raga Recordings

Segments a raga recording into clean, individual melodic phrases using
onset detection, silence analysis, and pitch filtering.  Exports the
best segments as WAV files with per-phrase metadata JSON.

Usage:
    python extract_phrases.py recording.mp3
    python extract_phrases.py recording.mp3 --count 20 --output data/phrases/yaman/
    python extract_phrases.py recording.wav --sa D --min-dur 2 --max-dur 6

Examples:
    # Extract 20 best phrases from a Yaman performance
    python extract_phrases.py yaman_full.mp3 --count 20

    # Custom output directory and filename prefix
    python extract_phrases.py bhairav.mp3 --output data/phrases/bhairav/ --prefix bhairav_phrase

    # Override tonic detection
    python extract_phrases.py recording.wav --sa C#

Requires:
    pip install -r requirements.txt
    (librosa, numpy, soundfile; ffmpeg for MP3 support)
"""

import argparse
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

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

import shutil

from analyze_raga import (
    SAMPLE_RATE,
    HOP_LENGTH,
    FRAME_DURATION,
    DEGREE_TO_SVARA,
    DEGREE_INFO,
    NOTE_NAMES,
    SUPPORTED_FORMATS,
    load_audio,
    detect_sa,
)
from raga_scorer import RagaScorer


# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

MIN_ONSET_GAP = 0.3        # merge onsets closer than this (seconds)
SILENCE_THRESHOLD_PCT = 20  # percentile of RMS energy for silence detection
SILENCE_MIN_DUR = 0.15     # minimum silence duration to mark a boundary (seconds)
BOUNDARY_MERGE_TOL = 0.2   # merge boundaries within this tolerance (seconds)
MIN_VOICED_RATIO = 0.55    # stricter: at least 55% of frames must be voiced
ENERGY_FLOOR_PCT = 15      # stricter: reject segments below this percentile of global RMS
IDEAL_DURATION = 4.0       # aim for longer melodic arcs
MIN_DISTINCT_SVARAS = 3    # require at least 3 distinct svaras
MIN_SEQUENCE_LEN = 5       # require more melodic motion
PAKAD_BOOST = 0.25         # stronger pakad bonus
MIN_PAKAD_SCORE = 0.25     # drop phrases with pakad score below this


# ═══════════════════════════════════════════════════════════════════════
#  PHRASE BOUNDARY DETECTION
# ═══════════════════════════════════════════════════════════════════════

def detect_onset_boundaries(y, sr):
    """Find note-attack timestamps via librosa onset detection.

    Adjacent onsets closer than MIN_ONSET_GAP are merged to avoid
    splitting fast ornamental passages.

    Args:
        y:  Audio time-series.
        sr: Sample rate.

    Returns:
        np.ndarray: Onset times in seconds, de-duplicated.

    Example:
        >>> onsets = detect_onset_boundaries(y, sr)
        >>> print(f"{len(onsets)} onsets detected")
    """
    onsets = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=HOP_LENGTH,
        backtrack=True, units='time',
    )
    if len(onsets) == 0:
        return onsets

    merged = [onsets[0]]
    for t in onsets[1:]:
        if t - merged[-1] >= MIN_ONSET_GAP:
            merged.append(t)
    return np.array(merged)


def detect_silence_boundaries(y, sr):
    """Find phrase boundaries at silence or low-energy gaps.

    Computes frame-level RMS energy.  Consecutive frames below the
    SILENCE_THRESHOLD_PCT percentile lasting longer than SILENCE_MIN_DUR
    produce a boundary at the midpoint of each gap.

    Args:
        y:  Audio time-series.
        sr: Sample rate.

    Returns:
        tuple: (silence_boundaries, rms_values, energy_threshold)
            - silence_boundaries: np.ndarray of times in seconds
            - rms_values: full RMS array (frames)
            - energy_threshold: the computed silence threshold

    Example:
        >>> bounds, rms, thresh = detect_silence_boundaries(y, sr)
        >>> print(f"{len(bounds)} silence gaps found")
    """
    rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
    threshold = np.percentile(rms[rms > 0], SILENCE_THRESHOLD_PCT) if np.any(rms > 0) else 0

    is_silent = rms < threshold
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)
    min_frames = int(SILENCE_MIN_DUR / FRAME_DURATION)

    boundaries = []
    run_start = None
    for i, silent in enumerate(is_silent):
        if silent and run_start is None:
            run_start = i
        elif not silent and run_start is not None:
            if i - run_start >= min_frames:
                mid = (run_start + i) // 2
                boundaries.append(times[mid])
            run_start = None
    if run_start is not None and len(rms) - run_start >= min_frames:
        mid = (run_start + len(rms) - 1) // 2
        boundaries.append(times[mid])

    return np.array(boundaries), rms, threshold


def merge_boundaries(onset_bounds, silence_bounds, duration):
    """Merge onset and silence boundaries into a single sorted list.

    Boundaries within BOUNDARY_MERGE_TOL of each other are de-duplicated
    (keep the earlier one).  Start (0.0) and end (duration) are always
    included so the full recording is covered.

    Args:
        onset_bounds:   Array of onset times.
        silence_bounds: Array of silence-gap times.
        duration:       Total recording length in seconds.

    Returns:
        np.ndarray: Sorted, de-duplicated boundary times.

    Example:
        >>> bounds = merge_boundaries(onsets, silences, 310.0)
        >>> print(f"{len(bounds)} total boundaries")
    """
    all_bounds = np.concatenate([
        [0.0],
        onset_bounds,
        silence_bounds,
        [duration],
    ])
    all_bounds = np.sort(np.unique(all_bounds))

    merged = [all_bounds[0]]
    for t in all_bounds[1:]:
        if t - merged[-1] >= BOUNDARY_MERGE_TOL:
            merged.append(t)
    if merged[-1] < duration - BOUNDARY_MERGE_TOL:
        merged.append(duration)
    return np.array(merged)


# ═══════════════════════════════════════════════════════════════════════
#  SEGMENT FILTERING AND RANKING
# ═══════════════════════════════════════════════════════════════════════

def build_candidate_segments(boundaries, min_dur, max_dur):
    """Generate candidate (start, end) pairs from boundary list.

    Args:
        boundaries: Sorted boundary times.
        min_dur:    Minimum segment duration.
        max_dur:    Maximum segment duration.

    Returns:
        list[tuple]: List of (start_sec, end_sec) pairs.

    Example:
        >>> segs = build_candidate_segments(bounds, 2.0, 5.0)
        >>> print(f"{len(segs)} candidates in duration range")
    """
    segments = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        dur = end - start
        if min_dur <= dur <= max_dur:
            segments.append((start, end))
    return segments


def compute_segment_rms(y, sr, start, end):
    """Compute mean RMS energy for an audio slice.

    Args:
        y:     Full audio array.
        sr:    Sample rate.
        start: Start time in seconds.
        end:   End time in seconds.

    Returns:
        float: Mean RMS energy of the segment.
    """
    s = int(start * sr)
    e = int(end * sr)
    segment = y[s:e]
    if len(segment) == 0:
        return 0.0
    rms = librosa.feature.rms(y=segment, hop_length=HOP_LENGTH)[0]
    return float(np.mean(rms))


def compute_voiced_ratio(y_seg, sr):
    """Run pyin on a segment and return the fraction of voiced frames.

    Args:
        y_seg: Audio segment array.
        sr:    Sample rate.

    Returns:
        tuple: (voiced_ratio, f0_array)
            - voiced_ratio: float 0.0-1.0
            - f0_array: raw f0 from pyin (with NaNs for unvoiced)
    """
    f0, voiced, _ = librosa.pyin(
        y_seg,
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C6'),
        sr=sr, hop_length=HOP_LENGTH,
    )
    if len(f0) == 0:
        return 0.0, f0
    valid = ~np.isnan(f0) & voiced
    ratio = float(np.sum(valid) / len(f0))
    return ratio, f0


def score_segment(voiced_ratio, norm_energy, duration, ideal=IDEAL_DURATION):
    """Compute a composite quality score for ranking phrases.

    Score = 0.5 * voiced_ratio + 0.3 * norm_energy + 0.2 * duration_score

    Duration score peaks at ``ideal`` seconds and falls off at edges.

    Args:
        voiced_ratio: Fraction of voiced frames (0-1).
        norm_energy:  Normalized RMS energy (0-1).
        duration:     Segment duration in seconds.
        ideal:        Ideal phrase duration for peak score.

    Returns:
        float: Quality score (0-1).

    Example:
        >>> score_segment(0.87, 0.5, 3.2)
        0.635
    """
    dur_score = max(0.0, 1.0 - abs(duration - ideal) / ideal)
    return 0.5 * voiced_ratio + 0.3 * norm_energy + 0.2 * dur_score


# ═══════════════════════════════════════════════════════════════════════
#  PER-PHRASE PITCH ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def analyze_phrase_notes(f0, sa_pc, allowed_degrees: set[int] | None = None):
    """Extract svara information from a phrase's f0 contour.

    Args:
        f0:    Fundamental frequency array (with NaNs for unvoiced).
        sa_pc: Pitch class of Sa (0-11).

    Returns:
        dict with keys:
            notes_detected: list of unique svara abbreviations (order of appearance)
            notes_sequence: compacted svara sequence (order preserved, repeats collapsed)
            dominant_note:  svara with longest total duration
            starts_with:    svara of the first stable pitched frame
            ends_with:      svara of the last stable pitched frame

    Example:
        >>> info = analyze_phrase_notes(f0_array, sa_pc=2)
        >>> print(info['notes_detected'])
        ['Ni', 'Re', 'Ga']
    """
    valid_mask = ~np.isnan(f0)
    if not np.any(valid_mask):
        return {
            'notes_detected': [],
            'notes_sequence': [],
            'dominant_note': None,
            'starts_with': None,
            'ends_with': None,
        }

    valid_f0 = f0[valid_mask]
    midi = np.round(librosa.hz_to_midi(valid_f0)).astype(int)
    degrees = (midi % 12 - sa_pc) % 12
    if allowed_degrees:
        snapped = []
        for d in degrees:
            d = int(d)
            nearest = min(allowed_degrees, key=lambda x: min((x - d) % 12, (d - x) % 12))
            snapped.append(nearest)
        degrees = np.array(snapped, dtype=int)

    seen_order = []
    seen_set = set()
    duration_count = Counter()
    sequence = []
    last_seq = None
    for deg in degrees:
        deg = int(deg)
        svara = DEGREE_TO_SVARA[deg]
        if svara not in seen_set:
            seen_order.append(svara)
            seen_set.add(svara)
        duration_count[svara] += 1
        if svara != last_seq:
            sequence.append(svara)
            last_seq = svara

    # Map single-char abbreviations (from DEGREE_TO_SVARA) to readable names (from DEGREE_INFO)
    readable = {DEGREE_TO_SVARA[d]: DEGREE_INFO[d][0] for d in range(12)}
    notes_readable = [readable.get(s, s) for s in seen_order]
    sequence_readable = [readable.get(s, s) for s in sequence]

    dominant = duration_count.most_common(1)[0][0] if duration_count else None
    first_svara = DEGREE_TO_SVARA[int(degrees[0])]
    last_svara = DEGREE_TO_SVARA[int(degrees[-1])]

    return {
        'notes_detected': notes_readable,
        'notes_sequence': sequence_readable,
        'dominant_note': readable.get(dominant, dominant),
        'starts_with': readable.get(first_svara, first_svara),
        'ends_with': readable.get(last_svara, last_svara),
    }


# ═══════════════════════════════════════════════════════════════════════
#  EXPORT
# ═══════════════════════════════════════════════════════════════════════

def export_phrase(y, sr, start, end, filepath):
    """Write a segment of audio to a WAV file.

    Args:
        y:        Full audio array.
        sr:       Sample rate.
        start:    Start time in seconds.
        end:      End time in seconds.
        filepath: Output path (.wav).

    Example:
        >>> export_phrase(y, 22050, 12.4, 15.6, "phrase_001.wav")
    """
    s = int(start * sr)
    e = int(end * sr)
    sf.write(str(filepath), y[s:e], sr)


def export_existing_phrase(source_dir: Path, entry: dict, output_dir: Path, prefix: str, idx: int) -> dict:
    """Copy an existing phrase WAV and rewrite metadata entry with new id."""
    wav_name = f"{prefix}_{idx:03d}.wav"
    src_wav = source_dir / entry["file"]
    dst_wav = output_dir / wav_name
    shutil.copy2(src_wav, dst_wav)
    new_entry = dict(entry)
    new_entry["phrase_id"] = f"{prefix}_{idx:03d}"
    new_entry["file"] = wav_name
    return new_entry


# ═══════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════

def extract_phrases(audio_path, output_dir, count=20, sa_override=None,
                    min_dur=2.0, max_dur=5.0, prefix=None):
    """Full extraction pipeline: load, segment, filter, rank, export.

    Args:
        audio_path:  Path to input audio file.
        output_dir:  Directory for output WAV + metadata.
        count:       Number of phrases to extract.
        sa_override: Optional Sa note name override.
        min_dur:     Minimum phrase duration (seconds).
        max_dur:     Maximum phrase duration (seconds).
        prefix:      Filename prefix for exported WAVs.

    Returns:
        list[dict]: Metadata for all exported phrases.

    Example:
        >>> results = extract_phrases("yaman.mp3", "data/phrases/yaman/", count=20)
        >>> len(results)
        20
    """
    # 1. Load audio
    print(f"\n  Loading: {audio_path} ...")
    y, sr, duration = load_audio(audio_path)
    print(f"  Loaded {duration:.1f}s of audio.")

    # 2. Detect boundaries
    print("  Detecting onsets and energy envelope ...")
    onset_bounds = detect_onset_boundaries(y, sr)
    silence_bounds, rms_full, energy_thresh = detect_silence_boundaries(y, sr)
    boundaries = merge_boundaries(onset_bounds, silence_bounds, duration)
    print(f"  Found {len(onset_bounds)} onsets, {len(silence_bounds)} silence gaps "
          f"-> {len(boundaries) - 1} boundary intervals")

    # 3. Build candidates
    candidates = build_candidate_segments(boundaries, min_dur, max_dur)
    print(f"  {len(candidates)} candidates in {min_dur}-{max_dur}s duration range")

    if not candidates:
        print("  WARNING: No candidates found. Try adjusting --min-dur / --max-dur.")
        return []

    # 4. Compute global energy floor for filtering
    global_rms_floor = float(np.percentile(rms_full[rms_full > 0], ENERGY_FLOOR_PCT)) \
        if np.any(rms_full > 0) else 0
    global_rms_max = float(np.max(rms_full)) if np.any(rms_full > 0) else 1.0

    # 5. Quick filter by energy (no pyin needed — fast)
    energy_filtered = []
    for start, end in candidates:
        seg_rms = compute_segment_rms(y, sr, start, end)
        if seg_rms >= global_rms_floor:
            norm_e = min(1.0, seg_rms / global_rms_max) if global_rms_max > 0 else 0
            energy_filtered.append((start, end, seg_rms, norm_e))

    print(f"  {len(energy_filtered)} candidates above energy floor")

    if not energy_filtered:
        print("  WARNING: All candidates below energy threshold.")
        return []

    # 6. Score by energy + duration (pre-rank before expensive pyin)
    pre_scored = []
    for start, end, seg_rms, norm_e in energy_filtered:
        dur = end - start
        pre_score = 0.3 * norm_e + 0.2 * max(0.0, 1.0 - abs(dur - IDEAL_DURATION) / IDEAL_DURATION)
        pre_scored.append((start, end, seg_rms, norm_e, pre_score))
    pre_scored.sort(key=lambda x: x[4], reverse=True)

    # Take top 3x candidates for pyin analysis (pyin is expensive)
    pyin_pool_size = min(len(pre_scored), count * 3)
    pyin_pool = pre_scored[:pyin_pool_size]

    print(f"  Running pitch analysis on top {len(pyin_pool)} candidates ...")

    # 7. Voiced ratio filter + full scoring
    scored = []
    for i, (start, end, seg_rms, norm_e, _) in enumerate(pyin_pool):
        s_idx = int(start * sr)
        e_idx = int(end * sr)
        y_seg = y[s_idx:e_idx]
        if len(y_seg) == 0:
            continue

        voiced_ratio, f0 = compute_voiced_ratio(y_seg, sr)
        if voiced_ratio < MIN_VOICED_RATIO:
            continue

        dur = end - start
        quality = score_segment(voiced_ratio, norm_e, dur)
        scored.append((start, end, seg_rms, norm_e, voiced_ratio, f0, quality))

    print(f"  {len(scored)} candidates passed voicing filter (>={MIN_VOICED_RATIO:.0%})")

    if not scored:
        print("  WARNING: No candidates with sufficient voiced content.")
        return []

    # 8. Detect Sa from a sample of the full recording for svara mapping
    print("  Detecting Sa for svara mapping ...")
    sample_len = min(len(y), sr * 60)
    f0_sample, voiced_sample, _ = librosa.pyin(
        y[:sample_len],
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C6'),
        sr=sr, hop_length=HOP_LENGTH,
    )
    valid_sample = ~np.isnan(f0_sample) & voiced_sample
    if np.any(valid_sample):
        midi_sample = np.round(librosa.hz_to_midi(f0_sample[valid_sample])).astype(int)
        pc_sample = midi_sample % 12
        sa_pc, sa_note, sa_hz = detect_sa(pc_sample, sa_override=sa_override)
    else:
        sa_pc, sa_note, sa_hz = 0, 'C', 261.6

    print(f"  Sa = {sa_note} ({'user-specified' if sa_override else 'auto-detected'})")

    # 9. Rank and select top N (apply melody richness + optional pakad boost)
    try:
        raga_name = Path(output_dir).name
        rules_path = Path("data/raga_rules") / f"{raga_name}.json"
        scorer = RagaScorer.from_rules_file(rules_path) if rules_path.exists() else None
    except Exception:
        scorer = None

    def _rank_candidates(min_distinct, min_seq, min_pakad):
        ranked = []
        for (start, end, seg_rms, norm_e, voiced_ratio, f0, quality) in scored:
            allowed = scorer.allowed_degrees if scorer else None
            note_info = analyze_phrase_notes(f0, sa_pc, allowed_degrees=allowed)
            distinct = len(note_info["notes_detected"])
            seq_len = len(note_info["notes_sequence"])
            if distinct < min_distinct or seq_len < min_seq:
                continue
            pakad_score = scorer.pakad_match_score(note_info["notes_sequence"]) if scorer else 0.0
            if scorer and pakad_score < min_pakad:
                continue
            rank_score = quality + (PAKAD_BOOST * pakad_score)
            ranked.append((rank_score, start, end, seg_rms, norm_e, voiced_ratio, f0, quality))
        return ranked

    enriched_scored = _rank_candidates(MIN_DISTINCT_SVARAS, MIN_SEQUENCE_LEN, MIN_PAKAD_SCORE)
    if not enriched_scored:
        print("  WARNING: No candidates met strict melody/pakad thresholds — relaxing filters.")
        enriched_scored = _rank_candidates(2, 3, 0.2)
    if len(enriched_scored) < count:
        print("  INFO: Fewer than requested phrases — widening filters to fill.")
        extra = _rank_candidates(2, 3, 0.0)
        # Merge while preserving best score per segment
        seen = {}
        for item in enriched_scored + extra:
            key = (item[1], item[2])
            if key not in seen or item[0] > seen[key][0]:
                seen[key] = item
        enriched_scored = list(seen.values())

    enriched_scored.sort(key=lambda x: x[0], reverse=True)
    selected = [(s, e, r, n, v, f, q) for _, s, e, r, n, v, f, q in enriched_scored[:count]]
    print(f"  {len(selected)} candidates after melody richness + pakad boost")

    # 10. Prepare output directory
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if prefix is None:
        prefix = Path(audio_path).stem.split('_')[0] + '_phrase'

    # 11. Export phrases and build metadata
    print(f"\n  Exporting {len(selected)} phrases to {out}/ ...")
    metadata = []
    for idx, (start, end, seg_rms, norm_e, voiced_ratio, f0, quality) in enumerate(selected, 1):
        phrase_id = f"{prefix}_{idx:03d}"
        wav_name = f"{phrase_id}.wav"
        wav_path = out / wav_name

        export_phrase(y, sr, start, end, wav_path)

        allowed = scorer.allowed_degrees if scorer else None
        note_info = analyze_phrase_notes(f0, sa_pc, allowed_degrees=allowed)
        dur = end - start

        entry = {
            'phrase_id': phrase_id,
            'file': wav_name,
            'start_time': round(start, 2),
            'end_time': round(end, 2),
            'duration': round(dur, 2),
            'notes_detected': note_info['notes_detected'],
            'notes_sequence': note_info['notes_sequence'],
            'dominant_note': note_info['dominant_note'],
            'starts_with': note_info['starts_with'],
            'ends_with': note_info['ends_with'],
            'voiced_ratio': round(voiced_ratio, 3),
            'energy_level': round(norm_e, 3),
            'quality_score': round(quality, 3),
        }
        metadata.append(entry)

        notes_str = ' '.join(note_info['notes_detected'][:6])
        print(f"    [{idx:>{len(str(count))}}/{count}] "
              f"{start:>7.1f}s-{end:<7.1f}s  {notes_str:<25} (score: {quality:.2f})")

    # 12. Write metadata JSON
    meta_path = out / 'phrases_metadata.json'
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n  Exported {len(metadata)} phrases to {out}/")
    print(f"  Metadata written to {meta_path}")
    print()
    return metadata


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def build_parser():
    """Create the command-line argument parser.

    Returns:
        argparse.ArgumentParser

    Example:
        >>> parser = build_parser()
        >>> args = parser.parse_args(['alaap.mp3', '--count', '10'])
        >>> args.count
        10
    """
    parser = argparse.ArgumentParser(
        prog='extract_phrases',
        description='Extract melodic phrases from raga recordings.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python extract_phrases.py yaman_full.mp3 --count 20
              python extract_phrases.py recording.wav --sa D --output data/phrases/yaman/
              python extract_phrases.py bhairav.mp3 --min-dur 1.5 --max-dur 6
        """),
    )
    parser.add_argument(
        'audio_file',
        help='Path to audio file (MP3, WAV, FLAC, OGG, M4A)',
    )
    parser.add_argument(
        '--output', '-o', metavar='DIR',
        default=None,
        help='Output directory (default: data/phrases/<name>/)',
    )
    parser.add_argument(
        '--count', '-n', type=int, default=20,
        help='Number of phrases to extract (default: 20)',
    )
    parser.add_argument(
        '--sa', metavar='NOTE', default=None,
        help='Override auto-detected Sa (tonic), e.g. --sa D',
    )
    parser.add_argument(
        '--min-dur', type=float, default=3.0,
        help='Minimum phrase duration in seconds (default: 3.0)',
    )
    parser.add_argument(
        '--max-dur', type=float, default=7.0,
        help='Maximum phrase duration in seconds (default: 7.0)',
    )
    parser.add_argument(
        '--gold', action='store_true',
        help='Create a curated gold library from existing metadata (no re-extraction)',
    )
    parser.add_argument(
        '--source-meta', type=str, default=None,
        help='Path to an existing phrases_metadata.json for gold selection',
    )
    parser.add_argument(
        '--prefix', default=None,
        help='Filename prefix for exported WAVs (default: derived from input)',
    )
    return parser


def main():
    """Entry point: parse arguments and run the extraction pipeline.

    Exit codes:
        0 — success
        1 — user error (bad file, no results)
        130 — interrupted (Ctrl-C)
    """
    parser = build_parser()
    args = parser.parse_args()

    output_dir = args.output
    if output_dir is None:
        stem = Path(args.audio_file).stem.split('_')[0]
        output_dir = f"data/phrases/{stem}/"

    try:
        if args.gold:
            source_meta = Path(args.source_meta) if args.source_meta else Path(output_dir) / "phrases_metadata.json"
            if not source_meta.exists():
                raise FileNotFoundError(f"gold source metadata not found: {source_meta}")
            source_dir = source_meta.parent
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            prefix = args.prefix or f"{source_dir.name}_gold"

            with open(source_meta) as f:
                phrases = json.load(f)
            rules_path = Path("data/raga_rules") / f"{source_dir.name.replace('_generated', '')}.json"
            scorer = RagaScorer.from_rules_file(rules_path) if rules_path.exists() else None
            scored_phrases = []
            for p in phrases:
                if scorer and "authenticity_score" not in p:
                    p = scorer.score_phrase(p)
                scored_phrases.append(p)
            scored = sorted(scored_phrases, key=lambda p: p.get("authenticity_score", 0.0), reverse=True)
            selected = scored[:args.count]

            gold_meta = []
            for idx, entry in enumerate(selected, 1):
                gold_entry = export_existing_phrase(source_dir, entry, out, prefix, idx)
                gold_entry["source_type"] = "library"
                gold_entry["library_tier"] = "gold"
                gold_meta.append(gold_entry)

            meta_path = out / "phrases_metadata.json"
            with open(meta_path, "w") as f:
                json.dump(gold_meta, f, indent=2, ensure_ascii=False)

            print(f"\n  Exported {len(gold_meta)} gold phrases to {out}/")
            print(f"  Metadata written to {meta_path}\n")
            return

        results = extract_phrases(
            audio_path=args.audio_file,
            output_dir=output_dir,
            count=args.count,
            sa_override=args.sa,
            min_dur=args.min_dur,
            max_dur=args.max_dur,
            prefix=args.prefix,
        )
        if not results:
            print("  No phrases extracted. Try different duration or energy settings.\n")
            sys.exit(1)

    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"\n  ERROR: {exc}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(130)


if __name__ == '__main__':
    main()
