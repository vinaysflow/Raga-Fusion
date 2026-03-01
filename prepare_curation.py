#!/usr/bin/env python3
"""
prepare_curation.py — Create per-raga candidate CSVs for manual curation.

Heuristically scores expanded playlist items for classical raga likelihood
and produces sorted CSVs to help select top-50 ingestible sources.
"""

import argparse
import csv
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
EXPANDED_PATH = PROJECT_ROOT / "data" / "recording_sources_expanded.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "curation"

POSITIVE_KEYWORDS = {
    "raag": 2,
    "raga": 2,
    "raagas": 2,
    "alap": 2,
    "alaap": 2,
    "khayal": 2,
    "dhrupad": 2,
    "thumri": 1,
    "bandish": 2,
    "vilambit": 1,
    "drut": 1,
    "bansuri": 2,
    "sitar": 2,
    "sarod": 2,
    "sarangi": 2,
    "shehnai": 2,
    "rudra": 2,
    "veena": 2,
    "violin": 1,
    "flute": 1,
    "tabla": 1,
    "tanpura": 1,
    "ustad": 1,
    "pandit": 1,
    "pt.": 1,
    "vidushi": 1,
    "live": 1,
    "festival": 1,
    "classical": 2,
    "hindustani": 2,
}

NEGATIVE_KEYWORDS = {
    "lyrical": -3,
    "song": -1,
    "songs": -1,
    "movie": -3,
    "film": -3,
    "bollywood": -3,
    "soundtrack": -3,
    "t-series": -3,
    "remix": -3,
    "cover": -2,
    "karaoke": -3,
    "lofi": -2,
    "trap": -2,
    "bass": -1,
    "house": -2,
    "psytrance": -2,
    "beats": -1,
    "dj": -2,
    "mix": -1,
}


def _load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _score_title(title: str) -> tuple[int, list[str]]:
    if not title:
        return 0, []
    text = title.lower()
    score = 0
    hits = []

    for key, val in POSITIVE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(key)}\b", text):
            score += val
            hits.append(f"+{key}")

    for key, val in NEGATIVE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(key)}\b", text):
            score += val
            hits.append(f"{val}{key}")

    return score, hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare candidate CSVs for curation.")
    parser.add_argument("--expanded", default=str(EXPANDED_PATH))
    parser.add_argument("--out-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--min-score", type=int, default=-2,
                        help="Minimum score to keep in output")
    args = parser.parse_args()

    expanded = _load_json(Path(args.expanded))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict]] = {}
    for entry in expanded:
        title = entry.get("title", "")
        score, hits = _score_title(title)
        if score < args.min_score:
            continue

        enriched = dict(entry)
        enriched["score"] = score
        enriched["score_hits"] = ", ".join(hits)
        enriched["rights_status"] = enriched.get("rights_status", "reference_only")
        enriched["license_type"] = enriched.get("license_type", "unknown")
        enriched["download_url"] = enriched.get("download_url", "")
        grouped.setdefault(enriched.get("raga", "unknown"), []).append(enriched)

    fields = [
        "source_key",
        "raga",
        "title",
        "artist",
        "performance_type",
        "link",
        "score",
        "score_hits",
        "rights_status",
        "license_type",
        "download_url",
        "notes",
    ]

    all_rows: list[dict] = []
    for raga, rows in grouped.items():
        rows.sort(key=lambda r: r.get("score", 0), reverse=True)
        out_path = out_dir / f"{raga}_candidates.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                row.setdefault("notes", "")
                writer.writerow({k: row.get(k) for k in fields})
                all_rows.append({k: row.get(k) for k in fields})

    with open(out_dir / "all_candidates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in sorted(all_rows, key=lambda r: (r.get("raga") or "", -int(r.get("score") or 0))):
            writer.writerow(row)

    print(f"Wrote curation CSVs to {out_dir}/")


if __name__ == "__main__":
    main()
