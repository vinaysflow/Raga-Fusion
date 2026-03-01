#!/usr/bin/env python3
"""
ingest_sources.py — Download + normalize licensed recordings.

Reads data/recording_sources.json and downloads only sources whose
rights_status is ingestible (or explicitly requested). Normalizes to
mono 44.1kHz WAV for downstream phrase extraction.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlretrieve

import librosa
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parent
CATALOG_PATH = PROJECT_ROOT / "data" / "recording_sources.json"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "sources"
MIN_DURATION_SEC = 30.0
MAX_DURATION_SEC = 3600.0

INGESTIBLE_STATUSES = {
    "ingestible",
    "licensed",
    "public_domain",
    "cc_by",
    "cc0",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 2)


def _download_url(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading: {url}")
    urlretrieve(url, dest)
    return dest


def _download_yt_dlp(url: str, dest_dir: Path) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "-o",
        str(dest_dir / "%(title).200s.%(ext)s"),
        url,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("  ERROR: yt-dlp not found. Install with: pip install yt-dlp")
        return None
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: yt-dlp failed: {exc.stderr.strip()}")
        return None

    files = sorted(dest_dir.glob("*"))
    return files[-1] if files else None


def _normalize_audio(src_path: Path, dest_path: Path, target_sr: int = 44100) -> tuple[float, int, int]:
    y, sr = librosa.load(str(src_path), sr=target_sr, mono=True)
    sf.write(str(dest_path), y, target_sr)
    duration = float(len(y) / target_sr) if target_sr > 0 else 0.0
    return duration, target_sr, 1


def load_catalog(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def ingest_source(entry: dict, use_yt_dlp: bool = False) -> dict | None:
    source_key = entry.get("source_key")
    raga = entry.get("raga")
    if not source_key or not raga:
        print("  Skipping entry with missing source_key or raga.")
        return None

    out_dir = OUTPUT_ROOT / raga / source_key
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    raw_path = None
    if entry.get("download_url"):
        filename = Path(entry["download_url"]).name or "source_audio"
        raw_path = _download_url(entry["download_url"], raw_dir / filename)
    elif use_yt_dlp:
        raw_path = _download_yt_dlp(entry["link"], raw_dir)
    else:
        print(f"  No download_url for {source_key}; skipping download.")
        return None

    if raw_path is None or not raw_path.exists():
        return None

    normalized_path = out_dir / "normalized.wav"
    duration, sample_rate, channels = _normalize_audio(raw_path, normalized_path)
    checksum = _sha256(normalized_path)
    raw_checksum = _sha256(raw_path)
    raw_size_mb = _size_mb(raw_path)
    wav_size_mb = _size_mb(normalized_path)
    warnings = []
    if duration and duration < MIN_DURATION_SEC:
        warnings.append("duration_below_min")
    if duration and duration > MAX_DURATION_SEC:
        warnings.append("duration_above_max")

    manifest = {
        "source_key": source_key,
        "raga": raga,
        "title": entry.get("title"),
        "artist": entry.get("artist"),
        "link": entry.get("link"),
        "raw_path": str(raw_path.relative_to(PROJECT_ROOT)),
        "normalized_path": str(normalized_path.relative_to(PROJECT_ROOT)),
        "duration_sec": round(duration, 2),
        "sample_rate": sample_rate,
        "channels": channels,
        "checksum_sha256": checksum,
        "raw_checksum_sha256": raw_checksum,
        "raw_size_mb": raw_size_mb,
        "wav_size_mb": wav_size_mb,
        "ingest_warnings": warnings,
        "license_type": entry.get("license_type"),
        "rights_status": entry.get("rights_status"),
    }

    with open(out_dir / "source_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  Saved normalized audio: {normalized_path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and normalize licensed raga recordings.")
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="Path to recording_sources.json")
    parser.add_argument("--use-yt-dlp", action="store_true", help="Use yt-dlp for non-direct links")
    parser.add_argument("--include-reference", action="store_true",
                        help="Include reference_only sources (not recommended)")
    parser.add_argument("--source-keys", nargs="*", default=None,
                        help="Only ingest these source_key values")
    parser.add_argument("--max", type=int, default=None, help="Max number of sources to ingest")
    args = parser.parse_args()

    catalog = load_catalog(Path(args.catalog))
    ingested = 0

    for entry in catalog:
        rights = entry.get("rights_status", "reference_only")
        if args.source_keys and entry.get("source_key") not in args.source_keys:
            continue
        if rights not in INGESTIBLE_STATUSES and not args.include_reference:
            continue

        print(f"\n[Ingest] {entry.get('source_key')} — {entry.get('title')}")
        manifest = ingest_source(entry, use_yt_dlp=args.use_yt_dlp)
        if manifest:
            ingested += 1
        if args.max and ingested >= args.max:
            break

    print(f"\nDone. Ingested {ingested} sources.")


if __name__ == "__main__":
    main()
