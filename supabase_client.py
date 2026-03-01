#!/usr/bin/env python3
"""
supabase_client.py — Minimal Supabase REST helper for logging.

Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. Disabled unless
SUPABASE_LOGGING=1 is set.
"""

import json
import os
from datetime import datetime
from urllib import request, error, parse


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
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, body


def _get_env() -> tuple[str | None, str | None, bool]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    enabled = os.getenv("SUPABASE_LOGGING", "0") == "1"
    return url, key, enabled


def insert_rows(table: str, rows: list[dict]) -> None:
    if not rows:
        return
    url, key, enabled = _get_env()
    if not url or not key or not enabled:
        return
    endpoint = f"{url}/rest/v1/{table}"
    status, body = _request_json(
        "POST",
        endpoint,
        key,
        payload=rows,
        headers={"Prefer": "return=minimal"},
    )
    if status not in (200, 201, 204):
        raise RuntimeError(f"Supabase insert failed for {table}: {status} {body}")


def log_ai_event(event_type: str, prompt: str | None = None,
                 input_payload: dict | None = None,
                 output_payload: dict | None = None,
                 model: str | None = None,
                 latency_ms: int | None = None) -> None:
    row = {
        "event_type": event_type,
        "prompt": prompt,
        "input": input_payload or {},
        "output": output_payload or {},
        "model": model,
        "latency_ms": latency_ms,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    insert_rows("ai_events", [row])


def log_arrangement_plan(track_id: str | None, plan: dict, source: str | None,
                         intent_tags: list[str] | None) -> None:
    row = {
        "track_id": track_id,
        "raga": plan.get("raga"),
        "style": plan.get("style"),
        "duration_sec": plan.get("duration"),
        "source": source,
        "intent_tags": intent_tags or [],
        "constraints": plan.get("constraints", {}),
        "metrics": {
            "avg_authenticity": plan.get("avg_authenticity"),
            "avg_recommendation_score": plan.get("avg_recommendation_score"),
            "total_phrases": plan.get("total_phrases"),
        },
        "plan": plan,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    insert_rows("arrangement_plans", [row])


def log_feedback(plan_id: str | None, track_id: str | None, rating: int | None,
                 feedback: str | None, tags: list[str] | None,
                 metadata: dict | None) -> None:
    row = {
        "plan_id": plan_id,
        "track_id": track_id,
        "rating": rating,
        "feedback": feedback,
        "tags": tags or [],
        "metadata": metadata or {},
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    insert_rows("user_feedback", [row])
