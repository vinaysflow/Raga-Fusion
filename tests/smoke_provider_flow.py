#!/usr/bin/env python3
"""
Smoke test: Provider portal end-to-end flow.

Usage:
  python tests/smoke_provider_flow.py --file /path/to/audio.wav
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib import request


def request_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    data = None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=hdrs)
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def encode_multipart(fields: dict, file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----RagaBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for key, value in fields.items():
        lines.extend([
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{key}"'.encode(),
            b"",
            str(value).encode(),
        ])
    mime, _ = mimetypes.guess_type(str(file_path))
    mime = mime or "application/octet-stream"
    lines.extend([
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"'.encode(),
        f"Content-Type: {mime}".encode(),
        b"",
        file_path.read_bytes(),
    ])
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    body = b"\r\n".join(lines)
    return body, boundary


def post_multipart(url: str, fields: dict, file_field: str, file_path: Path) -> dict:
    body, boundary = encode_multipart(fields, file_field, file_path)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = request.Request(url, data=body, method="POST", headers=headers)
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Provider portal smoke test.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--file", required=True, help="Audio file to upload")
    parser.add_argument("--raga", default="bageshree")
    parser.add_argument("--declared-sa", default="A#3")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")

    provider = request_json(
        "POST",
        f"{args.base_url}/api/provider/register",
        {
            "name": "Smoke Provider",
            "email": f"smoke_{uuid.uuid4().hex[:6]}@example.com",
            "gharana": "Demo",
            "instruments": ["Sitar"],
            "training_lineage": "Smoke",
            "bio": "Automated smoke test",
        },
    )
    provider_id = provider["id"]

    upload = post_multipart(
        f"{args.base_url}/api/provider/upload",
        {
            "provider_id": provider_id,
            "raga": args.raga,
            "declared_sa": args.declared_sa,
            "count": 6,
        },
        "file",
        file_path,
    )
    upload_id = upload["upload_id"]

    for _ in range(40):
        status = request_json("GET", f"{args.base_url}/api/provider/upload/{upload_id}/status")
        if status.get("status") in {"complete", "review_ready"}:
            break
        if status.get("status") == "error":
            raise SystemExit("Upload processing failed")
        time.sleep(2)

    review = request_json("GET", f"{args.base_url}/api/provider/upload/{upload_id}/review")
    phrase_ids = [p["phrase_id"] for p in review.get("phrases", [])[:1]]
    if not phrase_ids:
        raise SystemExit("No phrases available for approval")

    request_json(
        "POST",
        f"{args.base_url}/api/provider/upload/{upload_id}/approve",
        {"approved_phrase_ids": phrase_ids, "reviewer_notes": "Smoke approval"},
    )

    request_json(
        "POST",
        f"{args.base_url}/api/provider/upload/{upload_id}/recalibrate",
    )

    print("Smoke test complete:", upload_id)


if __name__ == "__main__":
    main()
