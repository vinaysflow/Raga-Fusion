#!/usr/bin/env python3
"""
backfill_supabase.py — Backfill new Supabase fields from local manifests.

Updates recording_assets with raw checksums/sizes/warnings and uploads the latest
seeding QA report when present.
"""

import argparse
import json
import os
from pathlib import Path
from urllib import request, error, parse

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCES_ROOT = PROJECT_ROOT / "data" / "sources"
SEED_REPORT = PROJECT_ROOT / "data" / "seed_qa_report.json"


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


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


def _fetch_all(url: str, key: str, table: str, select: str) -> list[dict]:
    endpoint = f"{url}/rest/v1/{table}?select={parse.quote(select)}"
    status, body = _request_json("GET", endpoint, key)
    if status != 200:
        raise RuntimeError(f"Fetch failed for {table}: {status} {body}")
    return json.loads(body)


def _find_recording_asset_id(url: str, key: str, source_id: str, storage_path_wav: str) -> str | None:
    filters = (
        f"source_id=eq.{parse.quote(source_id)}"
        f"&storage_path_wav=eq.{parse.quote(storage_path_wav)}"
    )
    endpoint = f"{url}/rest/v1/recording_assets?select=id&{filters}"
    status, body = _request_json("GET", endpoint, key)
    if status != 200:
        raise RuntimeError(f"Fetch failed for recording_assets: {status} {body}")
    rows = json.loads(body)
    if not rows:
        return None
    return rows[0]["id"]


def backfill_recording_assets(url: str, key: str, dry_run: bool) -> tuple[int, int]:
    source_rows = _fetch_all(url, key, "recording_sources", "id,source_key,raga")
    source_map = {r["source_key"]: r for r in source_rows}

    updated = 0
    skipped = 0

    for manifest_path in SOURCES_ROOT.rglob("source_manifest.json"):
        manifest = json.loads(manifest_path.read_text())
        source_key = manifest.get("source_key")
        if not source_key:
            skipped += 1
            continue
        source_row = source_map.get(source_key)
        if not source_row:
            skipped += 1
            continue

        raga = manifest.get("raga", source_row.get("raga"))
        storage_path_wav = f"sources/{raga}/{source_key}/normalized.wav"

        asset_id = _find_recording_asset_id(url, key, source_row["id"], storage_path_wav)
        if not asset_id:
            skipped += 1
            continue

        payload = {
            "raw_checksum_sha256": manifest.get("raw_checksum_sha256"),
            "raw_size_mb": manifest.get("raw_size_mb"),
            "wav_size_mb": manifest.get("wav_size_mb"),
            "ingest_warnings": manifest.get("ingest_warnings", []),
        }

        if dry_run:
            updated += 1
            continue

        endpoint = f"{url}/rest/v1/recording_assets?id=eq.{asset_id}"
        status, body = _request_json(
            "PATCH",
            endpoint,
            key,
            payload=payload,
            headers={"Prefer": "return=minimal"},
        )
        if status not in (200, 204):
            raise RuntimeError(f"Patch failed for recording_assets: {status} {body}")
        updated += 1

    return updated, skipped


def upload_seed_report(url: str, key: str, dry_run: bool) -> bool:
    if not SEED_REPORT.exists():
        return False
    report = json.loads(SEED_REPORT.read_text())
    report_key = report.get("report_key")
    if not report_key:
        return False
    payload = {
        "report_key": report_key,
        "raga": None,
        "report": report,
    }
    if dry_run:
        return True
    endpoint = f"{url}/rest/v1/seeding_reports"
    status, body = _request_json(
        "POST",
        endpoint,
        key,
        payload=payload,
        headers={"Prefer": "return=minimal"},
    )
    if status not in (200, 201, 204):
        raise RuntimeError(f"Seeding report upload failed: {status} {body}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Supabase fields from local manifests.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase")
    args = parser.parse_args()

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")

    updated, skipped = backfill_recording_assets(url, key, args.dry_run)
    report_uploaded = upload_seed_report(url, key, args.dry_run)

    print(f"Recording assets updated: {updated}")
    print(f"Recording assets skipped: {skipped}")
    print(f"Seeding report uploaded: {report_uploaded}")


if __name__ == "__main__":
    main()
