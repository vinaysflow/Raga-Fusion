#!/usr/bin/env python3
"""
supabase_load.py — Upload assets + load catalog data into Supabase.

Reads Supabase connection info from environment:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_BUCKET

Optional:
  RAGA_LIMIT="todi,bhairavi,bilawal,yaman,desh"
"""

import csv
import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from urllib import request, error, parse

PROJECT_ROOT = Path(__file__).resolve().parent

COLLECTIONS_CSV = PROJECT_ROOT / "data" / "supabase_source_collections.csv"
SOURCES_CSV = PROJECT_ROOT / "data" / "supabase_recording_sources.csv"

SOURCES_ROOT = PROJECT_ROOT / "data" / "sources"
PHRASES_ROOT = PROJECT_ROOT / "data" / "phrases"


def env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _headers_json(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request_json(method: str, url: str, key: str, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = _headers_json(key)
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


def ensure_bucket(url: str, key: str, bucket: str) -> None:
    endpoint = f"{url}/storage/v1/bucket"
    status, body = _request_json(
        "POST",
        endpoint,
        key,
        payload={"id": bucket, "name": bucket, "public": False},
    )
    if status in (200, 201):
        print(f"Created bucket: {bucket}")
        return
    if status == 409:
        print(f"Bucket exists: {bucket}")
        return
    print(f"Bucket create response: {status} {body}")


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upsert_rows(url: str, key: str, table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows:
        return
    endpoint = f"{url}/rest/v1/{table}?on_conflict={parse.quote(on_conflict)}"
    headers = {"Prefer": "resolution=merge-duplicates"}
    for batch in chunked(rows, 200):
        status, body = _request_json("POST", endpoint, key, payload=batch, headers=headers)
        if status not in (200, 201, 204):
            raise RuntimeError(f"Upsert failed for {table}: {status} {body}")


def _to_int(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if v == "":
            return None
        try:
            return int(float(v))
        except ValueError:
            return None
    return None


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        if v == "":
            return None
        try:
            return float(v)
        except ValueError:
            return None
    return None


def fetch_mapping(url: str, key: str, table: str, fields: str) -> list[dict]:
    endpoint = f"{url}/rest/v1/{table}?select={parse.quote(fields)}"
    req = request.Request(endpoint, headers=_headers_json(key), method="GET")
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_file(url: str, key: str, bucket: str, local_path: Path, remote_path: str,
                max_mb: float | None = None) -> bool:
    if max_mb is not None:
        size_mb = local_path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            return False
    mime, _ = mimetypes.guess_type(str(local_path))
    mime = mime or "application/octet-stream"
    endpoint = f"{url}/storage/v1/object/{bucket}/{remote_path}"
    cmd = [
        "curl",
        "-s",
        "-X",
        "PUT",
        "-H",
        f"Authorization: Bearer {key}",
        "-H",
        f"apikey: {key}",
        "-H",
        "x-upsert: true",
        "-H",
        f"Content-Type: {mime}",
        "--upload-file",
        str(local_path),
        endpoint,
    ]
    subprocess.run(cmd, check=False)
    return True


def main() -> None:
    supabase_url = env("SUPABASE_URL").rstrip("/")
    supabase_key = env("SUPABASE_SERVICE_ROLE_KEY")
    bucket = env("SUPABASE_BUCKET")
    raga_limit = os.getenv("RAGA_LIMIT")
    limit = set(r.strip() for r in raga_limit.split(",")) if raga_limit else None
    max_upload_mb = os.getenv("MAX_UPLOAD_MB")
    max_upload_mb = float(max_upload_mb) if max_upload_mb else 45.0
    upload_mode = os.getenv("UPLOAD_MODE", "all").lower()

    ensure_bucket(supabase_url, supabase_key, bucket)

    # Load catalog tables
    collections = load_csv(COLLECTIONS_CSV)
    for c in collections:
        c["expected_count"] = _to_int(c.get("expected_count"))
    upsert_rows(supabase_url, supabase_key, "source_collections", collections, "source_key")

    collection_rows = fetch_mapping(supabase_url, supabase_key, "source_collections", "id,source_key")
    collection_map = {r["source_key"]: r["id"] for r in collection_rows}

    sources_rows = load_csv(SOURCES_CSV)
    normalized_sources = []
    for row in sources_rows:
        tags = {}
        if row.get("tags"):
            try:
                tags = json.loads(row["tags"])
            except json.JSONDecodeError:
                tags = {}
        collection_key = tags.get("collection_key")
        if collection_key:
            row["collection_id"] = collection_map.get(collection_key)
        if row.get("collection_id") == "":
            row["collection_id"] = None
        row["duration_sec"] = _to_float(row.get("duration_sec"))
        row["rank"] = _to_int(row.get("rank"))
        row["tags"] = json.dumps(tags, ensure_ascii=False)
        normalized_sources.append(row)

    upsert_rows(supabase_url, supabase_key, "recording_sources", normalized_sources, "source_key")

    source_rows = fetch_mapping(supabase_url, supabase_key, "recording_sources", "id,source_key,raga")
    source_map = {r["source_key"]: r for r in source_rows}

    # Upload normalized sources + insert recording_assets
    if upload_mode in ("all", "sources"):
        recording_assets = []
        for manifest_path in SOURCES_ROOT.rglob("source_manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            raga = manifest.get("raga")
            if limit and raga not in limit:
                continue
            source_key = manifest.get("source_key")
            source_row = source_map.get(source_key)
            if not source_row:
                continue
            wav_path = PROJECT_ROOT / manifest["normalized_path"]
            remote_path = f"sources/{raga}/{source_key}/normalized.wav"
            uploaded = upload_file(
                supabase_url,
                supabase_key,
                bucket,
                wav_path,
                remote_path,
                max_mb=max_upload_mb,
            )
            if not uploaded:
                continue
            recording_assets.append({
                "source_id": source_row["id"],
                "storage_path_wav": remote_path,
                "duration_sec": manifest.get("duration_sec"),
                "sample_rate": manifest.get("sample_rate"),
                "channels": manifest.get("channels"),
                "checksum_sha256": manifest.get("checksum_sha256"),
                "raw_checksum_sha256": manifest.get("raw_checksum_sha256"),
                "raw_size_mb": manifest.get("raw_size_mb"),
                "wav_size_mb": manifest.get("wav_size_mb"),
                "ingest_warnings": manifest.get("ingest_warnings", []),
            })

        if recording_assets:
            endpoint = f"{supabase_url}/rest/v1/recording_assets"
            headers = {"Prefer": "return=minimal"}
            for batch in chunked(recording_assets, 200):
                status, body = _request_json("POST", endpoint, supabase_key, payload=batch, headers=headers)
                if status not in (200, 201, 204):
                    raise RuntimeError(f"Insert failed for recording_assets: {status} {body}")

    # Upload phrase assets + insert phrase_assets
    if upload_mode in ("all", "phrases"):
        phrase_rows = []
        for meta_path in PHRASES_ROOT.rglob("phrases_metadata.json"):
            library_dir = meta_path.parent.name
            raga = library_dir.replace("_gold", "").replace("_generated", "")
            if limit and raga not in limit:
                continue
            phrases = json.loads(meta_path.read_text())
            for p in phrases:
                source_key = p.get("source_key")
                if not source_key:
                    continue
                source_row = source_map.get(source_key)
                if not source_row:
                    continue
                file_name = p.get("file")
                if not file_name:
                    continue
                local_path = meta_path.parent / file_name
                remote_path = f"phrases/{library_dir}/{file_name}"
                uploaded = upload_file(
                    supabase_url,
                    supabase_key,
                    bucket,
                    local_path,
                    remote_path,
                    max_mb=max_upload_mb,
                )
                if not uploaded:
                    continue
                phrase_rows.append({
                    "source_id": source_row["id"],
                    "phrase_id": p.get("phrase_id"),
                    "storage_path": remote_path,
                    "duration_sec": p.get("duration"),
                    "notes_sequence": p.get("notes_sequence"),
                    "notes_detected": p.get("notes_detected"),
                    "starts_with": p.get("starts_with"),
                    "ends_with": p.get("ends_with"),
                    "energy_level": p.get("energy_level"),
                    "quality_score": p.get("quality_score"),
                    "authenticity_score": p.get("authenticity_score"),
                    "library_tier": p.get("library_tier", "standard"),
                    "source_type": p.get("source_type", "library"),
                    "metadata": p,
                })

        if phrase_rows:
            endpoint = f"{supabase_url}/rest/v1/phrase_assets"
            headers = {"Prefer": "return=minimal"}
            for batch in chunked(phrase_rows, 200):
                status, body = _request_json("POST", endpoint, supabase_key, payload=batch, headers=headers)
                if status not in (200, 201, 204):
                    raise RuntimeError(f"Insert failed for phrase_assets: {status} {body}")

    print("Supabase load complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
