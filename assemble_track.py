#!/usr/bin/env python3
"""
assemble_track.py — Raga Phrase Assembler

Loads a library of extracted melodic phrases and assembles them into a
coherent musical track with crossfade transitions, volume normalisation,
and a musically structured arc (opening → ascending → development →
peak → resolution).

Usage:
    python assemble_track.py --duration 30 --output yaman_test_30s.wav
    python assemble_track.py --library data/phrases/yaman/ --duration 30 --output out.wav
    python assemble_track.py --duration 15 --count 5 --output short.wav

Requires:
    pip install -r requirements.txt
    (librosa, numpy, soundfile)
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    import soundfile as sf
except ImportError:
    print("\n  ERROR: soundfile is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

from analyze_raga import SAMPLE_RATE


# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_LIBRARY = Path("data/phrases/yaman")
DEFAULT_CROSSFADE = 0.75          # seconds
MAX_CROSSFADE_RATIO = 0.40        # never crossfade more than 40% of shorter phrase
TARGET_DBFS = -1.0                # peak-normalise target

PHASE_NAMES = ["opening", "ascending", "development", "peak", "resolution"]

# Svara register ordering (lower octave → upper octave) used for
# note-connectivity scoring.  Base names (case-insensitive first letter)
# map to a simple ordinal so we can measure melodic distance.
SVARA_ORDER = {
    "Sa": 0, "re": 1, "Re": 2, "ga": 3, "Ga": 4,
    "ma": 5, "Ma": 6, "Ma'": 6,
    "Pa": 7, "dha": 8, "Dha": 9, "ni": 10, "Ni": 11,
}


# ═══════════════════════════════════════════════════════════════════════
#  Phrase library loading
# ═══════════════════════════════════════════════════════════════════════

def load_phrase_library(library_dir: Path) -> list[dict]:
    """Read phrases_metadata.json and load each WAV into memory.

    Returns a list of dicts — each is the original metadata enriched
    with an ``"audio"`` key holding a 1-D float32 numpy array and an
    ``"sr"`` key with the sample rate.
    """
    meta_path = library_dir / "phrases_metadata.json"
    if not meta_path.exists():
        print(f"\n  ERROR: metadata file not found: {meta_path}")
        sys.exit(1)

    with open(meta_path) as f:
        metadata = json.load(f)

    phrases: list[dict] = []
    for entry in metadata:
        wav_path = library_dir / entry["file"]
        if not wav_path.exists():
            print(f"  WARNING: skipping missing file {wav_path}")
            continue
        audio, sr = sf.read(str(wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        entry = dict(entry)
        entry["audio"] = audio
        entry["sr"] = sr
        phrases.append(entry)

    if not phrases:
        print(f"\n  ERROR: no valid phrases found in {library_dir}")
        sys.exit(1)

    # Stable sort by quality_score descending for deterministic ordering
    phrases.sort(key=lambda p: (-p["quality_score"], p["phrase_id"]))
    return phrases


# ═══════════════════════════════════════════════════════════════════════
#  Phase categorisation
# ═══════════════════════════════════════════════════════════════════════

def _note_set(phrase: dict) -> set[str]:
    """Return the set of base svara names in a phrase (case-preserved)."""
    return set(phrase.get("notes_detected", []))


def _has_any(phrase: dict, targets: set[str]) -> bool:
    return bool(_note_set(phrase) & targets)


def categorize_phrases(phrases: list[dict]) -> dict[str, list[dict]]:
    """Assign each phrase to a musical phase.

    Categories (in arc order):
      opening     — tonic-centred, calm (Sa dominant, low energy; or Ni→Sa)
      ascending   — upward melodic motion through Re / Ga
      development — rich phrases with many notes and higher energy
      peak        — upper register (Pa, Dha dominant) or highest energy
      resolution  — resolves to Sa, calm energy

    A phrase is placed in exactly one category.  Ambiguous phrases are
    resolved by priority: development > ascending > peak > opening >
    resolution (to ensure the middle phases get enough material).
    """
    energies = [p["energy_level"] for p in phrases]
    median_energy = float(np.median(energies))

    phases: dict[str, list[dict]] = {name: [] for name in PHASE_NAMES}
    assigned: set[str] = set()

    arc_phase_map = {
        "alap_opening": "opening",
        "alap_upper": "opening",
        "jod": "ascending",
        "vilambit_gat": "development",
        "gat_development": "development",
        "peak_taan": "peak",
        "resolution": "resolution",
    }

    for p in phrases:
        pid = p["phrase_id"]
        arc_section = p.get("arc_section")
        if arc_section in arc_phase_map and pid not in assigned:
            phases[arc_phase_map[arc_section]].append(p)
            assigned.add(pid)
            continue
        dom = p["dominant_note"]
        starts = p["starts_with"]
        ends = p["ends_with"]
        energy = p["energy_level"]
        notes = _note_set(p)
        n_notes = len(notes)

        # --- Development: rich phrases, 3+ notes, above-median energy ---
        if n_notes >= 3 and energy >= median_energy and pid not in assigned:
            phases["development"].append(p)
            assigned.add(pid)
            continue

        # --- Ascending: contains Re or Ga, movement upward ---
        if _has_any(p, {"Re", "Ga", "ga", "re"}) and pid not in assigned:
            phases["ascending"].append(p)
            assigned.add(pid)
            continue

        # --- Peak: Pa or Dha dominant, or upper-register exploration ---
        if dom in ("Pa", "Dha", "dha") and pid not in assigned:
            phases["peak"].append(p)
            assigned.add(pid)
            continue
        if _has_any(p, {"Pa", "dha"}) and pid not in assigned:
            phases["peak"].append(p)
            assigned.add(pid)
            continue

        # --- Opening: Sa-dominant low energy, or Ni→Sa approach ---
        if (starts == "Ni" and ends == "Sa") and pid not in assigned:
            phases["opening"].append(p)
            assigned.add(pid)
            continue
        if dom == "Sa" and energy <= median_energy and pid not in assigned:
            phases["opening"].append(p)
            assigned.add(pid)
            continue

        # --- Resolution: ends on Sa, calm ---
        if ends == "Sa" and energy <= median_energy and pid not in assigned:
            phases["resolution"].append(p)
            assigned.add(pid)
            continue

        # Fallback: phrases dominated by Ni/Dha go to peak; Sa to resolution
        if pid not in assigned:
            if dom in ("Ni", "ni", "Dha"):
                phases["peak"].append(p)
            else:
                phases["resolution"].append(p)
            assigned.add(pid)

    # Within each phase, sort by quality_score descending (stable)
    for name in PHASE_NAMES:
        phases[name].sort(key=lambda p: (-p["quality_score"], p["phrase_id"]))

    return phases


# ═══════════════════════════════════════════════════════════════════════
#  Phrase selection
# ═══════════════════════════════════════════════════════════════════════

def _svara_distance(note_a: str, note_b: str) -> int:
    """Melodic distance between two svaras (0 = same note)."""
    oa = SVARA_ORDER.get(note_a, -1)
    ob = SVARA_ORDER.get(note_b, -1)
    if oa < 0 or ob < 0:
        return 6  # unknown → treat as large distance
    return abs(oa - ob)


def _pick_best_continuation(candidates: list[dict],
                            prev_end_note: str,
                            used_ids: set[str]) -> dict | None:
    """From *candidates*, pick the unused phrase whose start note best
    connects to *prev_end_note*.  Ties broken by quality_score."""
    best, best_key = None, (999, -1.0, "")
    for c in candidates:
        if c["phrase_id"] in used_ids:
            continue
        dist = _svara_distance(prev_end_note, c["starts_with"])
        key = (dist, -c["quality_score"], c["phrase_id"])
        if key < best_key:
            best, best_key = c, key
    return best


def select_phrases(target_duration: float,
                   phrases: list[dict],
                   crossfade_dur: float,
                   count: int | None = None) -> list[dict]:
    """Select and sequence phrases to fill *target_duration* seconds.

    The selection follows a 5-phase musical arc.  Time is distributed
    proportionally across phases (opening 15%, ascending 20%,
    development 30%, peak 20%, resolution 15%).  Within each phase,
    phrases are ordered for melodic continuity.

    If *count* is given, exactly that many phrases are selected instead
    of duration-based filling.
    """
    categorized = categorize_phrases(phrases)

    phase_weights = {
        "opening":     0.15,
        "ascending":   0.20,
        "development": 0.30,
        "peak":        0.20,
        "resolution":  0.15,
    }

    selected: list[dict] = []
    used_ids: set[str] = set()
    accumulated_dur = 0.0

    if count is not None:
        # Fixed-count mode: distribute count across phases proportionally
        phase_counts = {}
        remaining = count
        for i, name in enumerate(PHASE_NAMES):
            if i == len(PHASE_NAMES) - 1:
                phase_counts[name] = remaining
            else:
                n = max(1, round(count * phase_weights[name]))
                n = min(n, remaining)
                phase_counts[name] = n
                remaining -= n
    else:
        phase_counts = None

    for phase_name in PHASE_NAMES:
        pool = categorized[phase_name]
        if not pool:
            continue

        if phase_counts is not None:
            budget_n = phase_counts[phase_name]
        else:
            phase_budget = target_duration * phase_weights[phase_name]
            budget_n = len(pool)  # unlimited; duration controls

        added_in_phase = 0
        while added_in_phase < budget_n:
            prev_end = selected[-1]["ends_with"] if selected else "Sa"
            pick = _pick_best_continuation(pool, prev_end, used_ids)
            if pick is None:
                break

            # Duration check (skip if we'd overshoot by more than one phrase)
            if phase_counts is None:
                new_total = (accumulated_dur + pick["duration"]
                             - crossfade_dur * (1 if selected else 0))
                if new_total > target_duration * 1.15 and accumulated_dur > 0:
                    break

            used_ids.add(pick["phrase_id"])
            if selected:
                accumulated_dur += pick["duration"] - crossfade_dur
            else:
                accumulated_dur += pick["duration"]
            selected.append(pick)
            added_in_phase += 1

            if phase_counts is None and accumulated_dur >= target_duration:
                break

        if phase_counts is None and accumulated_dur >= target_duration:
            break

    # If we haven't filled the target yet, do a second pass over unused
    # phrases regardless of category.
    if phase_counts is None and accumulated_dur < target_duration:
        unused = [p for p in phrases if p["phrase_id"] not in used_ids]
        unused.sort(key=lambda p: (-p["quality_score"], p["phrase_id"]))
        for p in unused:
            prev_end = selected[-1]["ends_with"] if selected else "Sa"
            pick = _pick_best_continuation(unused, prev_end, used_ids)
            if pick is None:
                pick = p
                if pick["phrase_id"] in used_ids:
                    continue
            used_ids.add(pick["phrase_id"])
            accumulated_dur += pick["duration"] - crossfade_dur
            selected.append(pick)
            if accumulated_dur >= target_duration:
                break

    return selected


def select_phrases_from_plan(
    plan_sequence: Sequence[str],
    phrases: list[dict],
) -> list[dict]:
    """Select and order phrases according to a pre-computed recommendation plan.

    *plan_sequence* is an ordered list of phrase_ids produced by the
    recommender.  This replaces the heuristic phase-based selection when
    an intelligent plan is available.
    """
    by_id = {p["phrase_id"]: p for p in phrases}
    selected = []
    for pid in plan_sequence:
        if pid in by_id:
            selected.append(by_id[pid])
    return selected


def _load_plan_sequence(plan_path: Path) -> list[str]:
    """Load a recommender plan JSON and return the ordered phrase_id list."""
    if not plan_path.exists():
        print(f"\n  ERROR: plan file not found: {plan_path}")
        sys.exit(1)
    try:
        with open(plan_path) as f:
            data = json.load(f)
    except Exception as exc:
        print(f"\n  ERROR: could not read plan file: {exc}")
        sys.exit(1)

    if isinstance(data, dict):
        if "phrase_sequence" in data and isinstance(data["phrase_sequence"], list):
            return [str(p) for p in data["phrase_sequence"]]
        if "phrases" in data and isinstance(data["phrases"], list):
            return [p.get("phrase_id") for p in data["phrases"] if isinstance(p, dict)]

    print("\n  ERROR: plan file missing 'phrase_sequence' list.")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
#  Crossfade & assembly
# ═══════════════════════════════════════════════════════════════════════

def apply_crossfade(audio1: np.ndarray,
                    audio2: np.ndarray,
                    duration: float,
                    sr: int) -> np.ndarray:
    """Blend the tail of *audio1* into the head of *audio2* using
    logarithmic fade curves over *duration* seconds.

    Returns a single contiguous array: [audio1_body | crossfade | audio2_body].
    """
    n_samples = int(duration * sr)
    # Cap at MAX_CROSSFADE_RATIO of the shorter segment
    max_allowed = int(MAX_CROSSFADE_RATIO * min(len(audio1), len(audio2)))
    n_samples = min(n_samples, max_allowed)

    if n_samples <= 0 or len(audio1) < n_samples or len(audio2) < n_samples:
        return np.concatenate([audio1, audio2])

    t = np.linspace(0.0, 1.0, n_samples, dtype=np.float64)
    fade_in = np.log2(1.0 + t)       # 0 → 1
    fade_out = 1.0 - np.log2(1.0 + t)  # 1 → 0

    tail = audio1[-n_samples:].astype(np.float64)
    head = audio2[:n_samples].astype(np.float64)

    blended = (tail * fade_out + head * fade_in).astype(np.float32)

    return np.concatenate([
        audio1[:-n_samples],
        blended,
        audio2[n_samples:],
    ])


def normalize_audio(audio: np.ndarray,
                    target_dbfs: float = TARGET_DBFS) -> np.ndarray:
    """Peak-normalise *audio* so the loudest sample reaches *target_dbfs*."""
    peak = np.max(np.abs(audio))
    if peak < 1e-8:
        return audio
    target_linear = 10.0 ** (target_dbfs / 20.0)
    return audio * (target_linear / peak)


def assemble_final_track(phrase_list: list[dict],
                         crossfade_dur: float,
                         sr: int) -> np.ndarray:
    """Chain all phrases with crossfade transitions and normalise."""
    if not phrase_list:
        return np.array([], dtype=np.float32)

    result = phrase_list[0]["audio"].copy()
    for phrase in phrase_list[1:]:
        result = apply_crossfade(result, phrase["audio"], crossfade_dur, sr)

    result = normalize_audio(result)
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Reporting
# ═══════════════════════════════════════════════════════════════════════

def _phase_label(phrase: dict, categorized: dict[str, list[dict]]) -> str:
    """Return the phase name a phrase was assigned to."""
    pid = phrase["phrase_id"]
    for name, members in categorized.items():
        if any(m["phrase_id"] == pid for m in members):
            return name
    return "unknown"


def print_report(selected: list[dict],
                 categorized: dict[str, list[dict]],
                 total_phrases: int,
                 crossfade_dur: float,
                 output_path: str,
                 final_dur: float) -> None:
    """Print a structured assembly report."""
    sep = "═" * 68
    print(f"\n{sep}")
    print("  RAGA PHRASE ASSEMBLER — Track Report")
    print(sep)

    print(f"\n  Phrase library : {total_phrases} phrases available")
    print(f"  Selected       : {len(selected)} phrases")
    print(f"  Crossfade      : {crossfade_dur:.2f}s (logarithmic curves)")
    print(f"  Final duration : {final_dur:.2f}s")
    print(f"  Output         : {output_path}")

    # Phase distribution
    print(f"\n{'─' * 68}")
    print("  PHASE DISTRIBUTION")
    print(f"{'─' * 68}")
    for name in PHASE_NAMES:
        members = categorized[name]
        print(f"    {name.capitalize():14s}: {len(members):2d} phrases in pool")

    # Sequence detail
    print(f"\n{'─' * 68}")
    print("  ASSEMBLY SEQUENCE")
    print(f"{'─' * 68}")
    print(f"  {'#':>3s}  {'Phase':<14s}  {'Phrase ID':<20s}  "
          f"{'Dur':>5s}  {'Notes':<30s}  {'Connection'}")
    print(f"  {'─'*3}  {'─'*14}  {'─'*20}  {'─'*5}  {'─'*30}  {'─'*20}")

    for i, p in enumerate(selected):
        phase = _phase_label(p, categorized)
        notes_str = ", ".join(p["notes_detected"][:5])
        if len(p["notes_detected"]) > 5:
            notes_str += "…"

        if i == 0:
            conn = "(start)"
        else:
            prev = selected[i - 1]
            prev_end = prev["ends_with"]
            cur_start = p["starts_with"]
            dist = _svara_distance(prev_end, cur_start)
            if dist == 0:
                conn = f"{prev_end} → {cur_start} (same)"
            elif dist <= 2:
                conn = f"{prev_end} → {cur_start} (step)"
            else:
                conn = f"{prev_end} → {cur_start} (leap:{dist})"

        print(f"  {i+1:3d}  {phase:<14s}  {p['phrase_id']:<20s}  "
              f"{p['duration']:5.2f}  {notes_str:<30s}  {conn}")

    # Energy profile
    print(f"\n{'─' * 68}")
    print("  ENERGY PROFILE")
    print(f"{'─' * 68}")
    max_bar = 40
    max_energy = max(p["energy_level"] for p in selected) if selected else 1.0
    for i, p in enumerate(selected):
        bar_len = int((p["energy_level"] / max_energy) * max_bar)
        bar = "█" * bar_len
        print(f"  {i+1:3d}  {bar:<{max_bar}s}  {p['energy_level']:.3f}")

    print(f"\n{sep}\n")


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble extracted raga phrases into a musical track.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python assemble_track.py --duration 30 --output yaman_test_30s.wav
              python assemble_track.py --library data/phrases/yaman/ --duration 30 --output out.wav
              python assemble_track.py --duration 15 --count 5 --output short.wav
        """),
    )
    parser.add_argument(
        "--library", type=Path, default=DEFAULT_LIBRARY,
        help="Directory containing phrase WAVs and phrases_metadata.json "
             "(default: data/phrases/yaman/)",
    )
    parser.add_argument(
        "--duration", type=float, default=30.0,
        help="Target track duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--crossfade", type=float, default=DEFAULT_CROSSFADE,
        help=f"Crossfade duration in seconds (default: {DEFAULT_CROSSFADE})",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Force exactly N phrases (overrides duration-based selection)",
    )
    parser.add_argument(
        "--plan", type=Path, default=None,
        help="Optional recommendation plan JSON (uses its phrase sequence)",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output WAV file path",
    )

    args = parser.parse_args()

    # ── Load ──────────────────────────────────────────────────────────
    print(f"\n  Loading phrase library from {args.library} …")
    phrases = load_phrase_library(args.library)
    print(f"  Loaded {len(phrases)} phrases.\n")

    # ── Select & sequence ─────────────────────────────────────────────
    print("  Selecting phrases …")
    if args.plan is not None:
        plan_sequence = _load_plan_sequence(args.plan)
        selected = select_phrases_from_plan(plan_sequence, phrases)
    else:
        selected = select_phrases(
            target_duration=args.duration,
            phrases=phrases,
            crossfade_dur=args.crossfade,
            count=args.count,
        )

    # ── Categorise (for reporting) ────────────────────────────────────
    categorized = categorize_phrases(phrases)

    if not selected:
        print("\n  ERROR: no phrases could be selected.")
        sys.exit(1)

    # ── Assemble ──────────────────────────────────────────────────────
    sr = selected[0]["sr"]
    print(f"  Assembling {len(selected)} phrases with {args.crossfade:.2f}s crossfades …")
    track = assemble_final_track(selected, args.crossfade, sr)

    final_dur = len(track) / sr

    # ── Export ─────────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), track, sr)

    # ── Report ────────────────────────────────────────────────────────
    print_report(
        selected=selected,
        categorized=categorized,
        total_phrases=len(phrases),
        crossfade_dur=args.crossfade,
        output_path=str(out_path),
        final_dur=final_dur,
    )

    print(f"  Done — wrote {out_path} ({final_dur:.2f}s)")


if __name__ == "__main__":
    main()
