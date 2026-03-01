#!/usr/bin/env python3
"""
seed_qa_report.py — Generate QA report for recording source seeding.

Summarizes coverage, rights status, missing metadata, and duplicates.
Optionally uploads the report to Supabase (seeding_reports table).
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error, parse

PROJECT_ROOT = Path(__file__).resolve().parent
CATALOG_PATH = PROJECT_ROOT / "data" / "recording_sources.json"
DEFAULT_JSON_OUT = PROJECT_ROOT / "data" / "seed_qa_report.json"
DEFAULT_MD_OUT = PROJECT_ROOT / "data" / "seed_qa_report.md"

INGESTIBLE_STATUSES = {
    "ingestible",
    "licensed",
    "public_domain",
    "cc_by",
    "cc0",
}


def _load_catalog(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _request_json(method: str, url: str, key: str, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        hdrs.update(headers)
    req = request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, body


def _summarize(catalog: list[dict]) -> dict:
    by_raga = defaultdict(int)
    by_rights = defaultdict(int)
    missing = Counter()
    ingestible_missing_download = 0
    duplicate_source_keys = []
    duplicate_links = []

    seen_source_keys = set()
    seen_links = set()
    for entry in catalog:
        raga = (entry.get("raga") or "unknown").lower()
        by_raga[raga] += 1

        rights = entry.get("rights_status", "reference_only")
        by_rights[rights] += 1

        if not entry.get("title"):
            missing["title"] += 1
        if not entry.get("link"):
            missing["link"] += 1
        if not entry.get("artist"):
            missing["artist"] += 1

        source_key = entry.get("source_key")
        if source_key:
            if source_key in seen_source_keys:
                duplicate_source_keys.append(source_key)
            else:
                seen_source_keys.add(source_key)

        link = (entry.get("link") or "").strip().lower()
        if link:
            if link in seen_links:
                duplicate_links.append(link)
            else:
                seen_links.add(link)

        if rights in INGESTIBLE_STATUSES and not entry.get("download_url"):
            ingestible_missing_download += 1

    return {
        "total_sources": len(catalog),
        "by_raga": dict(sorted(by_raga.items(), key=lambda x: x[0])),
        "by_rights_status": dict(sorted(by_rights.items(), key=lambda x: x[0])),
        "missing_fields": dict(missing),
        "ingestible_missing_download_url": ingestible_missing_download,
        "duplicates": {
            "source_key": duplicate_source_keys[:50],
            "link": duplicate_links[:50],
        },
    }


def _to_markdown(report: dict) -> str:
    lines = []
    lines.append("# Seeding QA Report")
    lines.append("")
    lines.append(f"- Generated: {report.get('generated_at')}")
    lines.append(f"- Total sources: {report.get('total_sources')}")
    lines.append(f"- Ingestible missing download_url: {report.get('ingestible_missing_download_url')}")
    lines.append("")
    lines.append("## Coverage by Raga")
    for raga, count in report.get("by_raga", {}).items():
        lines.append(f"- {raga}: {count}")
    lines.append("")
    lines.append("## Rights Status")
    for status, count in report.get("by_rights_status", {}).items():
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## Missing Fields")
    for field, count in report.get("missing_fields", {}).items():
        lines.append(f"- {field}: {count}")
    lines.append("")
    lines.append("## Duplicates (sample)")
    dups = report.get("duplicates", {})
    lines.append(f"- source_key: {len(dups.get('source_key', []))} shown")
    lines.append(f"- link: {len(dups.get('link', []))} shown")
    lines.append("")
    return "\n".join(lines)


def _upload_report(report: dict, report_key: str) -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY for upload.")
    endpoint = f"{url}/rest/v1/seeding_reports"
    payload = {
        "report_key": report_key,
        "raga": None,
        "report": report,
    }
    status, body = _request_json("POST", endpoint, key, payload=payload, headers={"Prefer": "return=minimal"})
    if status not in (200, 201, 204):
        raise RuntimeError(f"Seeding report upload failed: {status} {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a seeding QA report.")
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="Path to recording_sources.json")
    parser.add_argument("--out-json", default=str(DEFAULT_JSON_OUT), help="Output JSON path")
    parser.add_argument("--out-md", default=str(DEFAULT_MD_OUT), help="Output Markdown path")
    parser.add_argument("--upload", action="store_true", help="Upload report to Supabase")
    args = parser.parse_args()

    catalog = _load_catalog(Path(args.catalog))
    report = _summarize(catalog)
    report_key = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report["report_key"] = report_key
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    Path(args.out_json).write_text(json.dumps(report, indent=2))
    Path(args.out_md).write_text(_to_markdown(report))
    print(f"Wrote report to {args.out_json} and {args.out_md}")

    if args.upload:
        _upload_report(report, report_key)
        print("Uploaded seeding report to Supabase.")


if __name__ == "__main__":
    main()
