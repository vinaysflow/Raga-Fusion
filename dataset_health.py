#!/usr/bin/env python3
"""
dataset_health.py — Dataset coverage and quality summary.

Builds a JSON report with phrase counts per raga, gold library sizes,
and the latest ornament calibration summary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def build_report(data_dir: Path) -> dict:
    phrases_dir = data_dir / "phrases"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phrase_counts": {},
        "gold_counts": {},
        "rod_phrase_counts": {},
        "ragas": [],
    }

    for raga_dir in sorted(phrases_dir.iterdir()):
        if not raga_dir.is_dir():
            continue
        name = raga_dir.name
        if name.startswith("_") or name.endswith("_generated") or name.endswith("_gold"):
            continue

        meta_path = raga_dir / "phrases_metadata.json"
        meta = _load_json(meta_path) or []
        report["phrase_counts"][name] = len(meta)
        report["ragas"].append(name)

        rod_count = 0
        for entry in meta:
            if entry.get("source_type") == "rod_dataset":
                rod_count += 1
        if rod_count:
            report["rod_phrase_counts"][name] = rod_count

        gold_dir = phrases_dir / f"{name}_gold"
        gold_meta = _load_json(gold_dir / "phrases_metadata.json")
        if gold_meta is not None:
            report["gold_counts"][name] = len(gold_meta)

    # Ornament calibration summary
    ornament_report = _load_json(data_dir / "ornament_calibration_report.json")
    if ornament_report:
        summary = {
            "overall": ornament_report.get("overall"),
            "low_f1_types": ornament_report.get("review_recommendations", {}).get("low_f1_types", []),
            "pb_integration": ornament_report.get("pb_integration"),
        }
        report["ornament_calibration_summary"] = summary

    return report


def main() -> None:
    data_dir = Path("data")
    report = build_report(data_dir)
    out_path = data_dir / "dataset_health_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Wrote {out_path}")


if __name__ == "__main__":
    main()
