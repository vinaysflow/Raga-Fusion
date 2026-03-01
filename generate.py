#!/usr/bin/env python3
"""
generate.py — One-command raga track generator

Runs the full pipeline: generate melody → assemble → add production.
Prints a concise summary on success.

Usage:
    python generate.py --raga yaman --genre lofi --duration 120
    python generate.py --genre ambient --duration 60
    python generate.py --source library --duration 30
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

GENRE_DISPLAY = {
    "lofi": "Lofi beats",
    "ambient": "Ambient",
    "calm": "Calm",
    "upbeat": "Upbeat",
}

TIME_WINDOW_TO_LABEL = {
    "PM": "evening",
    "AM": "morning",
}


def _load_styles() -> list[str]:
    styles_path = PROJECT_ROOT / "data" / "styles.json"
    try:
        with open(styles_path) as f:
            return list(json.load(f).keys())
    except Exception:
        return list(GENRE_DISPLAY.keys())


def _next_sequence(output_dir: Path, raga: str, genre: str, year: int) -> int:
    """Find next available sequence number for the naming pattern."""
    pattern = re.compile(rf"^{re.escape(raga)}_{re.escape(genre)}_{year}_(\d{{3}})\.wav$")
    max_seq = 0
    if output_dir.exists():
        for f in output_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    return max_seq + 1


def _raga_display(rules_path: Path, raga_name: str) -> str:
    """Build display string like 'Yaman (evening, romantic)'."""
    try:
        with open(rules_path) as f:
            rules = json.load(f)
    except Exception:
        return raga_name.capitalize()

    display_name = rules.get("raga", {}).get("name", raga_name.capitalize())
    context = rules.get("context", {})

    time_info = context.get("time", {})
    window = time_info.get("window", "")
    time_label = ""
    for key, label in TIME_WINDOW_TO_LABEL.items():
        if key in window:
            time_label = label
            break
    if not time_label:
        prahar = time_info.get("prahar", "")
        if "night" in prahar.lower():
            time_label = "evening"
        elif "morning" in prahar.lower():
            time_label = "morning"

    moods = context.get("mood", [])
    mood_label = moods[0].lower() if moods else ""

    parts = [p for p in [time_label, mood_label] if p]
    if parts:
        return f"{display_name} ({', '.join(parts)})"
    return display_name


def _genre_display(genre: str) -> str:
    return GENRE_DISPLAY.get(genre, genre.capitalize())


def _format_duration(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _read_wav_duration(path: Path) -> float | None:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return info.duration
    except Exception:
        return None


def _run_step(args: list[str], label: str, verbose: bool) -> int:
    """Run a subprocess step. Returns exit code."""
    if verbose:
        print(f"\n  [{label}]")
        proc = subprocess.run(args, cwd=PROJECT_ROOT, text=True)
    else:
        proc = subprocess.run(
            args, cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
    if proc.returncode != 0:
        print(f"\n  ERROR in {label} (exit {proc.returncode})")
        if not verbose and proc.stderr:
            print(proc.stderr)
        if not verbose and proc.stdout:
            print(proc.stdout)
    return proc.returncode


def main():
    available_styles = _load_styles()

    parser = argparse.ArgumentParser(
        description="Generate a raga-fusion track in one command.",
    )
    parser.add_argument(
        "--raga", type=str, default="yaman",
        help="Raga name (default: yaman). Must have data/raga_rules/<raga>.json.",
    )
    parser.add_argument(
        "--genre", type=str, default="lofi",
        choices=available_styles,
        help=f"Style/genre (default: lofi). One of: {', '.join(available_styles)}.",
    )
    parser.add_argument(
        "--duration", type=int, default=120,
        help="Target duration in seconds (default: 120).",
    )
    parser.add_argument(
        "--source", type=str, default="generated",
        choices=["generated", "library"],
        help="Phrase source: 'generated' (rule-based, no recording needed) or 'library' (existing phrase lib).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Directory for final WAV (default: project root).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show full output from each pipeline step.",
    )
    args = parser.parse_args()

    raga = args.raga.lower()
    genre = args.genre.lower()
    duration = args.duration
    output_dir = args.output_dir or PROJECT_ROOT
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rules_path = PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"
    lib_generated = PROJECT_ROOT / "data" / "phrases" / f"{raga}_generated"
    lib_existing = PROJECT_ROOT / "data" / "phrases" / raga

    if args.source == "generated":
        lib_path = lib_generated
    else:
        lib_path = lib_existing

    # Step 1: Generate melody (if source == generated)
    if args.source == "generated":
        if not rules_path.exists():
            print(f"  ERROR: Raga rules not found: {rules_path}")
            sys.exit(1)
        lib_path.mkdir(parents=True, exist_ok=True)
        rc = _run_step(
            [
                sys.executable,
                str(PROJECT_ROOT / "generate_melody.py"),
                "--rules", str(rules_path),
                "--output", str(lib_path),
                "--count", "20",
            ],
            "Generate melody",
            args.verbose,
        )
        if rc != 0:
            sys.exit(rc)

    # Verify phrase library exists
    meta_file = lib_path / "phrases_metadata.json"
    if not meta_file.exists():
        print(f"  ERROR: Phrase library not found: {meta_file}")
        print("  Run with --source generated, or provide a valid phrase library.")
        sys.exit(1)

    # Step 2: Assemble track
    temp_assembled = PROJECT_ROOT / f".tmp_{raga}_assembled.wav"
    rc = _run_step(
        [
            sys.executable,
            str(PROJECT_ROOT / "assemble_track.py"),
            "--library", str(lib_path),
            "--duration", str(duration),
            "--output", str(temp_assembled),
        ],
        "Assemble track",
        args.verbose,
    )
    if rc != 0:
        sys.exit(rc)

    # Step 3: Add production
    year = datetime.now().year
    seq = _next_sequence(output_dir, raga, genre, year)
    final_name = f"{raga}_{genre}_{year}_{seq:03d}.wav"
    final_path = output_dir / final_name

    rc = _run_step(
        [
            sys.executable,
            str(PROJECT_ROOT / "add_production.py"),
            str(temp_assembled),
            "--style", genre,
            "--output", str(final_path),
        ],
        "Add production",
        args.verbose,
    )

    # Clean up temp file
    if temp_assembled.exists():
        temp_assembled.unlink()

    if rc != 0:
        sys.exit(rc)

    # Read actual duration from the final WAV
    actual_dur = _read_wav_duration(final_path)
    dur_display = _format_duration(actual_dur) if actual_dur else _format_duration(duration)

    raga_info = _raga_display(rules_path, raga)
    genre_info = _genre_display(genre)

    print(f"\n✓ Generated: {final_name}")
    print(f"✓ Duration: {dur_display}")
    print(f"✓ Raga: {raga_info}")
    print(f"✓ Genre: {genre_info}")
    print()


if __name__ == "__main__":
    main()
