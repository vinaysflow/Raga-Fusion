#!/usr/bin/env python3
"""
calibrate_ornaments.py — Evaluate ornament detector against expert labels.

Compares detected ornaments from ornament_detector.py with expert-annotated
labels from the ROD dataset. Outputs precision/recall/F1 per ornament type
and a summary report.

Usage:
    python calibrate_ornaments.py --dataset "/Users/vinaytripathi/Downloads/DATA"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import librosa
except ImportError:
    print("\n  ERROR: librosa is required but not installed.")
    print("  Run:  pip install -r requirements.txt\n")
    sys.exit(1)

from analyze_raga import HOP_LENGTH, SAMPLE_RATE, load_audio
from ornament_detector import detect_ornaments

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


def _load_labels(label_path: Path) -> list[dict]:
    labels = []
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
            labels.append({
                "start_sec": start,
                "end_sec": end,
                "ornament": ORNAMENT_MAP.get(raw, raw),
            })
    return labels


def _iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    if inter <= 0:
        return 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    return inter / union if union > 0 else 0.0


def _match_events(gt: list[dict], pred: list[dict], iou_thresh: float) -> tuple[int, int, int]:
    used_pred = set()
    tp = 0
    for i, g in enumerate(gt):
        best_j = None
        best_iou = 0.0
        for j, p in enumerate(pred):
            if j in used_pred or p["ornament"] != g["ornament"]:
                continue
            ov = _iou(g["start_sec"], g["end_sec"], p["start_sec"], p["end_sec"])
            if ov > best_iou:
                best_iou = ov
                best_j = j
        if best_j is not None and best_iou >= iou_thresh:
            used_pred.add(best_j)
            tp += 1
    fp = len(pred) - len(used_pred)
    fn = len(gt) - tp
    return tp, fp, fn


def _compute_metrics(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _collect_label_files(labels_dir: Path) -> list[Path]:
    files = []
    for split in ("train", "test"):
        split_dir = labels_dir / split
        if split_dir.exists():
            files.extend(sorted(split_dir.glob("*.txt")))
    return files


def _count_pb_labels(pb_root: Path) -> dict:
    labels_dir = pb_root / "labels"
    spect_dir = pb_root / "spectrograms"
    label_files = sorted(labels_dir.glob("*.txt")) if labels_dir.exists() else []
    counts: dict[str, int] = {}
    for lf in label_files:
        for row in _load_labels(lf):
            counts[row["ornament"]] = counts.get(row["ornament"], 0) + 1
    spec_count = len(list(spect_dir.glob("*.npy"))) if spect_dir.exists() else 0
    return {
        "label_files": len(label_files),
        "label_counts": counts,
        "spectrograms": spec_count,
        "scored": False,
        "note": "PB provides labels + spectrograms only; no audio to score ornaments yet."
    }


def calibrate(dataset_root: Path, iou_thresh: float) -> dict:
    rod_root = dataset_root / "ROD"
    audio_dir = rod_root / "audio"
    expert_001 = rod_root / "Expert_001"
    expert_002 = rod_root / "Expert_002"

    label_files = _collect_label_files(expert_001 / "labels") + _collect_label_files(expert_002 / "labels")
    by_type = {}
    overall = {"tp": 0, "fp": 0, "fn": 0}

    for label_path in label_files:
        stem = label_path.stem
        audio_path = audio_dir / f"{stem}.wav"
        if not audio_path.exists():
            continue

        labels = _load_labels(label_path)
        if not labels:
            continue

        y, sr, _ = load_audio(audio_path)
        f0, voiced, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C6"),
            sr=sr,
            hop_length=HOP_LENGTH,
        )
        pred = detect_ornaments(f0, ~np.isnan(f0), sr, HOP_LENGTH)

        # Group by ornament type for per-type metrics
        types = sorted({g["ornament"] for g in labels} | {p["ornament"] for p in pred})
        for t in types:
            gt_t = [g for g in labels if g["ornament"] == t]
            pr_t = [p for p in pred if p["ornament"] == t]
            tp, fp, fn = _match_events(gt_t, pr_t, iou_thresh)
            if t not in by_type:
                by_type[t] = {"tp": 0, "fp": 0, "fn": 0}
            by_type[t]["tp"] += tp
            by_type[t]["fp"] += fp
            by_type[t]["fn"] += fn
            overall["tp"] += tp
            overall["fp"] += fp
            overall["fn"] += fn

    report = {"by_type": {}, "overall": {}}
    for t, counts in by_type.items():
        report["by_type"][t] = _compute_metrics(counts["tp"], counts["fp"], counts["fn"])
    report["overall"] = _compute_metrics(overall["tp"], overall["fp"], overall["fn"])
    report["iou_threshold"] = iou_thresh

    low_f1 = [t for t, m in report["by_type"].items() if m["f1"] < 0.5]
    report["review_recommendations"] = {
        "low_f1_types": low_f1,
        "note": "Review ornament detector thresholds for low-F1 types."
    }

    pb_root = dataset_root / "PB"
    if pb_root.exists():
        report["pb_integration"] = _count_pb_labels(pb_root)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate ornament detector against ROD labels.")
    parser.add_argument(
        "--dataset", type=str, required=True,
        help="Path to DATA directory containing ROD/ folder",
    )
    parser.add_argument(
        "--iou", type=float, default=0.3,
        help="IoU threshold to count a detected ornament as correct",
    )
    parser.add_argument(
        "--output", type=str, default="data/ornament_calibration_report.json",
        help="Path for calibration report JSON",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset)
    if not dataset_root.exists():
        print(f"\n  ERROR: dataset path not found: {dataset_root}")
        sys.exit(1)

    report = calibrate(dataset_root, args.iou)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print("\n  Ornament calibration complete.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
