#!/usr/bin/env python3
"""
build_library.py — Extract phrases from normalized sources and merge into raga libraries.

Reads normalized audio under data/sources/<raga>/<source_key>/normalized.wav
and builds/extends data/phrases/<raga>/ with merged metadata.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from extract_phrases import extract_phrases

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCES_ROOT = PROJECT_ROOT / "data" / "sources"
PHRASES_ROOT = PROJECT_ROOT / "data" / "phrases"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def _safe_copy(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        i = 1
        while dest.exists():
            dest = dest.with_name(f"{stem}_{i}{suffix}")
            i += 1
    shutil.copy2(src, dest)
    return dest


def merge_into_library(source_key: str, raga: str, staging_dir: Path, target_dir: Path,
                       source_meta: dict) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_meta_path = target_dir / "phrases_metadata.json"

    staging_meta_path = staging_dir / "phrases_metadata.json"
    staging_meta = _load_json(staging_meta_path, [])
    if not staging_meta:
        return 0

    existing = _load_json(target_meta_path, [])
    merged = list(existing)

    for entry in staging_meta:
        src_wav = staging_dir / entry["file"]
        dst_wav = _safe_copy(src_wav, target_dir / entry["file"])

        new_entry = dict(entry)
        new_entry["file"] = dst_wav.name
        new_entry["source_key"] = source_key
        new_entry["source_title"] = source_meta.get("title")
        new_entry["source_artist"] = source_meta.get("artist")
        new_entry["source_platform"] = source_meta.get("source_platform")
        new_entry["rights_status"] = source_meta.get("rights_status")
        new_entry["license_type"] = source_meta.get("license_type")
        new_entry["source_type"] = "library"
        new_entry["library_tier"] = new_entry.get("library_tier", "standard")
        merged.append(new_entry)

    with open(target_meta_path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return len(staging_meta)


def build_for_source(source_dir: Path, count: int, min_dur: float, max_dur: float,
                     staging_root: Path) -> int:
    raga = source_dir.parent.name
    source_key = source_dir.name
    normalized = source_dir / "normalized.wav"
    if not normalized.exists():
        print(f"  Missing normalized.wav for {source_key}")
        return 0

    staging_dir = staging_root / source_key
    staging_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{source_key}_phrase"

    extract_phrases(
        audio_path=str(normalized),
        output_dir=str(staging_dir),
        count=count,
        min_dur=min_dur,
        max_dur=max_dur,
        prefix=prefix,
    )

    source_manifest = _load_json(source_dir / "source_manifest.json", {})
    target_dir = PHRASES_ROOT / raga
    merged_count = merge_into_library(source_key, raga, staging_dir, target_dir, source_manifest)
    return merged_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch extract and merge phrase libraries.")
    parser.add_argument("--count", type=int, default=20, help="Phrases per source")
    parser.add_argument("--min-dur", type=float, default=3.0)
    parser.add_argument("--max-dur", type=float, default=7.0)
    parser.add_argument("--ragas", nargs="*", default=None, help="Limit to these ragas")
    parser.add_argument("--source-keys", nargs="*", default=None, help="Limit to these source keys")
    parser.add_argument("--staging", default=str(PHRASES_ROOT / "_staging"))
    parser.add_argument("--make-gold", action="store_true",
                        help="Create gold libraries after merge")
    parser.add_argument("--gold-count", type=int, default=100,
                        help="Number of phrases per gold library")
    args = parser.parse_args()

    staging_root = Path(args.staging)
    staging_root.mkdir(parents=True, exist_ok=True)

    total = 0
    for raga_dir in SOURCES_ROOT.iterdir():
        if not raga_dir.is_dir():
            continue
        raga = raga_dir.name
        if args.ragas and raga not in args.ragas:
            continue

        for source_dir in raga_dir.iterdir():
            if not source_dir.is_dir():
                continue
            source_key = source_dir.name
            if args.source_keys and source_key not in args.source_keys:
                continue

            print(f"\n[Extract] {raga}/{source_key}")
            merged = build_for_source(
                source_dir,
                count=args.count,
                min_dur=args.min_dur,
                max_dur=args.max_dur,
                staging_root=staging_root,
            )
            total += merged
            print(f"  Merged {merged} phrases.")

        if args.make_gold:
            meta_path = PHRASES_ROOT / raga / "phrases_metadata.json"
            if meta_path.exists():
                gold_dir = PHRASES_ROOT / f"{raga}_gold"
                cmd = [
                    sys.executable,
                    str(PROJECT_ROOT / "extract_phrases.py"),
                    str(meta_path),
                    "--gold",
                    "--source-meta",
                    str(meta_path),
                    "--count",
                    str(args.gold_count),
                    "--output",
                    str(gold_dir),
                ]
                print(f"\n[Gold] Building {raga}_gold library")
                subprocess.run(cmd, check=False)

    print(f"\nDone. Merged {total} phrases into libraries.")


if __name__ == "__main__":
    main()
