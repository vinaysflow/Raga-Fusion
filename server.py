#!/usr/bin/env python3
"""
server.py — FastAPI backend for the Raga-Fusion Music Generator.

Endpoints:
    POST /api/parse-prompt   — parse free-text into structured params
    POST /api/generate       — start async track generation
    GET  /api/status/{id}    — poll generation status
    GET  /api/tracks         — list all generated tracks
    GET  /api/tracks/{id}    — get track metadata
    GET  /api/tracks/{id}/audio — stream the WAV file
    GET  /api/styles         — available production styles
    GET  /api/ragas          — available ragas

Usage:
    python server.py                    # starts on :8000
    uvicorn server:app --reload         # dev mode with auto-reload
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from prompt_parser import parse_prompt
from recommender import Recommender
from supabase_client import log_ai_event, log_arrangement_plan, log_feedback

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
TELEMETRY_DIR = OUTPUT_DIR / "telemetry"
TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = PROJECT_ROOT / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
CREATOR_LIBS_DIR = PROJECT_ROOT / "data" / "phrases"
CREATOR_LIBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Raga-Fusion Music Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

# In-memory job tracker: track_id -> {"status", "error", "metadata"}
jobs: dict[str, dict] = {}
recommender: Recommender | None = None
telemetry_seen: set[str] = set()

TRACE_VERSION = "1.0.0"
RECOMMENDER_VERSION = "1.0.0"
VARIATION_ENGINE_VERSION = "1.0.0"
RULES_VERSION = "1.0.0"

RF_DIAGNOSTICS = os.environ.get("RF_DIAGNOSTICS", "1") == "1"
logger = logging.getLogger("raga-fusion")
logging.basicConfig(
    level=logging.DEBUG if RF_DIAGNOSTICS else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

STAGE_BUDGET_MS: dict[str, int] = {
    "generate_melody": 6_000,
    "assemble_track": 4_000,
    "add_production": 18_000,
    "interactive_total": 36_000,
}
CACHE_DIR = OUTPUT_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(*parts: str) -> str:
    """Deterministic cache key from component parts."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_get(namespace: str, key: str) -> Path | None:
    """Return cached directory path if it exists, else None."""
    cached = CACHE_DIR / namespace / key
    if cached.exists():
        return cached
    return None


def _cache_put(namespace: str, key: str, source_dir: Path) -> Path:
    """Copy source_dir into the cache under namespace/key."""
    dest = CACHE_DIR / namespace / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_dir, dest)
    return dest


def _run_subprocess_timed(
    cmd: list[str],
    track_id: str,
    stage_name: str,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> dict:
    """Run a subprocess with wall-clock timing and optional captured output.

    When RF_DIAGNOSTICS is off, stdout/stderr are discarded to avoid pipe
    overhead; only exit code and elapsed time are collected.
    Timeout defaults to the stage budget (with 50% headroom) or 120s.
    """
    if timeout is None:
        budget = STAGE_BUDGET_MS.get(stage_name, 60_000)
        timeout = max(int(budget / 1000 * 1.5), 30)
    logger.info("[%s] Starting stage: %s (timeout=%ds)", track_id, stage_name, timeout)
    t0 = time.monotonic()
    try:
        if RF_DIAGNOSTICS:
            proc = subprocess.run(
                cmd, cwd=cwd or PROJECT_ROOT,
                capture_output=True, text=True, timeout=timeout,
            )
        else:
            proc = subprocess.run(
                cmd, cwd=cwd or PROJECT_ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        logger.error("[%s] Stage %s TIMED OUT after %dms", track_id, stage_name, elapsed_ms)
        return {
            "stage": stage_name,
            "elapsed_ms": elapsed_ms,
            "returncode": -1,
            "stdout_tail": "",
            "stderr_tail": f"TIMEOUT after {timeout}s",
            "timed_out": True,
        }
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    stdout_tail = (getattr(proc, "stdout", None) or "")[-2000:]
    stderr_tail = (proc.stderr or "")[-2000:]
    logger.info(
        "[%s] Stage %s completed in %dms (exit=%d)",
        track_id, stage_name, elapsed_ms, proc.returncode,
    )
    budget = STAGE_BUDGET_MS.get(stage_name)
    if budget and elapsed_ms > budget:
        logger.warning(
            "[%s] BUDGET EXCEEDED: %s took %dms (budget: %dms)",
            track_id, stage_name, elapsed_ms, budget,
        )
    if proc.returncode != 0:
        logger.warning("[%s] %s stderr: %s", track_id, stage_name, stderr_tail[-500:])
    return {
        "stage": stage_name,
        "elapsed_ms": elapsed_ms,
        "returncode": proc.returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "timed_out": False,
    }


def _get_recommender() -> Recommender:
    global recommender
    if recommender is None:
        recommender = Recommender()
    return recommender


# ── Request / Response models ────────────────────────────────────────

class PromptRequest(BaseModel):
    prompt: str

class GenerateRequest(BaseModel):
    raga: str = "yaman"
    genre: str = "lofi"
    duration: int = 120
    source: str = "generated"
    prompt: str = ""
    intent_tags: list[str] = []
    recommend: bool = False
    upload_id: str | None = None
    variation_profile: str | None = None


class RecommendRequest(BaseModel):
    raga: str = "yaman"
    genre: str = "lofi"
    duration: int = 120
    source: str | None = None
    intent_tags: list[str] = []


class TelemetryEvent(BaseModel):
    track_id: str
    session_id: str
    event_type: str
    timestamp: float | None = None
    payload: dict | None = None


# ── Helpers ──────────────────────────────────────────────────────────

def _load_styles() -> dict:
    try:
        with open(PROJECT_ROOT / "data" / "styles.json") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_ragas() -> list[dict]:
    rules_dir = PROJECT_ROOT / "data" / "raga_rules"
    ragas = []
    if rules_dir.exists():
        for p in sorted(rules_dir.glob("*.json")):
            try:
                with open(p) as f:
                    data = json.load(f)
                raga_info = data.get("raga", {})
                context = data.get("context", {})
                ragas.append({
                    "id": p.stem,
                    "name": raga_info.get("name", p.stem.capitalize()),
                    "thaat": raga_info.get("thaat", ""),
                    "mood": context.get("mood", []),
                    "time": context.get("time", {}).get("window", ""),
                    "description": raga_info.get("description", ""),
                })
            except Exception:
                ragas.append({"id": p.stem, "name": p.stem.capitalize()})
    return ragas


def _read_wav_duration(path: Path) -> float | None:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return round(info.duration, 2)
    except Exception:
        return None


def _artifact_paths(track_id: str) -> dict[str, Path]:
    return {
        "meta": OUTPUT_DIR / f"{track_id}.json",
        "wav": OUTPUT_DIR / f"{track_id}.wav",
        "plan": OUTPUT_DIR / f"{track_id}_plan.json",
        "trace": OUTPUT_DIR / f"{track_id}_trace.json",
        "quality": OUTPUT_DIR / f"{track_id}_quality.json",
        "timing": OUTPUT_DIR / f"{track_id}_timing.json",
    }


def _write_json(path: Path, payload: dict | list):
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _build_artifact_urls(track_id: str) -> dict[str, str]:
    return {
        "audio": f"/api/tracks/{track_id}/audio",
        "plan": f"/api/plan/{track_id}",
        "trace": f"/api/trace/{track_id}",
        "quality": f"/api/quality/{track_id}",
        "timing": f"/api/timing/{track_id}",
    }


def _telemetry_key(track_id: str, session_id: str, event_type: str, ts: float, bucket_seconds: int = 5) -> str:
    bucket = int(ts // bucket_seconds)
    return f"{track_id}:{session_id}:{event_type}:{bucket}"


def _run_pipeline(track_id: str, raga: str, genre: str, duration: int,
                  source: str, prompt: str, intent_tags: list[str], recommend: bool,
                  variation_profile: str | None):
    """Run the generation pipeline (blocking). Called from thread pool."""
    pipeline_t0 = time.monotonic()
    artifacts = _artifact_paths(track_id)
    wav_path = artifacts["wav"]
    meta_path = artifacts["meta"]
    timing_path = OUTPUT_DIR / f"{track_id}_timing.json"
    plan_path = None

    timing: dict = {
        "track_id": track_id,
        "raga": raga,
        "genre": genre,
        "requested_duration": duration,
        "source": source,
        "recommend": recommend,
        "diagnostics_enabled": RF_DIAGNOSTICS,
        "started_at": datetime.now().isoformat(),
        "stages": [],
    }

    trace = {
        "trace_version": TRACE_VERSION,
        "created_at": datetime.now().isoformat(),
        "track_id": track_id,
        "request": {
            "raga": raga,
            "genre": genre,
            "duration": duration,
            "source": source,
            "prompt": prompt,
            "intent_tags": intent_tags,
            "recommend": recommend,
            "variation_profile": variation_profile,
        },
        "versions": {
            "recommender_version": RECOMMENDER_VERSION,
            "variation_engine_version": VARIATION_ENGINE_VERSION,
            "rules_version": RULES_VERSION,
        },
        "resolved": {},
        "artifacts": {},
        "stages": [],
    }

    def _save_timing():
        timing["total_ms"] = round((time.monotonic() - pipeline_t0) * 1000)
        timing["finished_at"] = datetime.now().isoformat()
        _write_json(timing_path, timing)

    try:
        # ── Stage: generate_melody (with cache) ───────────────────────
        gen_lib = PROJECT_ROOT / "data" / "phrases" / f"{raga}_generated"
        melody_cache_key = _cache_key(raga, "generated", "20", RULES_VERSION)

        if source == "generated":
            cached_lib = _cache_get("melody", melody_cache_key)
            if cached_lib is not None:
                if gen_lib.exists():
                    shutil.rmtree(gen_lib)
                shutil.copytree(cached_lib, gen_lib)
                logger.info("[%s] generate_melody CACHE HIT (%s)", track_id, melody_cache_key)
                timing["stages"].append({"stage": "generate_melody", "elapsed_ms": 0, "returncode": 0, "timed_out": False, "cache": True})
                trace["stages"].append({"name": "generate_melody", "status": "cached", "elapsed_ms": 0})
            else:
                melody_args = [
                    sys.executable,
                    str(PROJECT_ROOT / "generate_melody.py"),
                    "--rules", str(PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"),
                    "--output", str(gen_lib),
                    "--count", "20",
                ]
                result = _run_subprocess_timed(melody_args, track_id, "generate_melody")
                timing["stages"].append(result)
                if result["returncode"] != 0:
                    jobs[track_id]["status"] = "error"
                    jobs[track_id]["error"] = result["stderr_tail"] or "Melody generation failed"
                    _save_timing()
                    return
                trace["stages"].append({"name": "generate_melody", "status": "ok", "elapsed_ms": result["elapsed_ms"]})
                if gen_lib.exists():
                    _cache_put("melody", melody_cache_key, gen_lib)

        # ── Resolve library path ──────────────────────────────────────
        real_lib = PROJECT_ROOT / "data" / "phrases" / raga
        if source == "generated":
            lib_path = gen_lib
        elif real_lib.exists() and (real_lib / "phrases_metadata.json").exists():
            lib_path = real_lib
        else:
            lib_path = gen_lib

        actual_source = "library" if lib_path == real_lib else "generated"
        trace["resolved"] = {"library_path": str(lib_path), "actual_source": actual_source}
        timing["resolved_source"] = actual_source
        timing["resolved_library"] = str(lib_path)

        # ── Optional: apply variation profile to library ───────────────
        if variation_profile:
            try:
                from variation_engine import create_variation_library, PRESET_FALLBACK
                variation_root = OUTPUT_DIR / ".variation"
                variation_root.mkdir(parents=True, exist_ok=True)
                profile = variation_profile
                last_error = None
                while profile:
                    try:
                        var_dir = variation_root / f"{track_id}_{profile}"
                        create_variation_library(
                            source_dir=lib_path,
                            output_dir=var_dir,
                            variation_type="tempo",
                            amount=0.2,
                            preset=profile,
                        )
                        lib_path = var_dir
                        actual_source = "variation"
                        trace["resolved"]["variation_profile"] = profile
                        timing["variation_profile"] = profile
                        break
                    except Exception as err:
                        last_error = err
                        profile = PRESET_FALLBACK.get(profile)
                if profile is None and last_error:
                    logger.warning("[%s] variation_profile failed; using base library: %s", track_id, last_error)
            except Exception as err:
                logger.warning("[%s] variation_profile setup failed; using base library: %s", track_id, err)

        # Refresh resolved paths after optional variation
        trace["resolved"]["library_path"] = str(lib_path)
        trace["resolved"]["actual_source"] = actual_source
        timing["resolved_source"] = actual_source
        timing["resolved_library"] = str(lib_path)

        # ── Stage: recommend_arrangement (with cache) ─────────────────
        duration_bucket = str((duration // 15) * 15)
        plan_cache_key = _cache_key(raga, genre, duration_bucket, actual_source, str(recommend), ",".join(sorted(intent_tags or [])), RECOMMENDER_VERSION)

        if recommend:
            plan_cache_path = CACHE_DIR / "plans" / f"{plan_cache_key}.json"
            if plan_cache_path.exists():
                with open(plan_cache_path) as f:
                    plan = json.load(f)
                logger.info("[%s] recommend_arrangement CACHE HIT (%s)", track_id, plan_cache_key)
                timing["stages"].append({"stage": "recommend_arrangement", "elapsed_ms": 0, "returncode": 0, "timed_out": False, "cache": True})
                trace["stages"].append({"name": "recommend_arrangement", "status": "cached", "elapsed_ms": 0})
            else:
                t0 = time.monotonic()
                rec = _get_recommender()
                plan = rec.recommend_arrangement(
                    raga=raga,
                    style=genre,
                    duration=duration,
                    source=actual_source,
                    intent_tags=intent_tags or [],
                )
                rec_ms = round((time.monotonic() - t0) * 1000)
                logger.info("[%s] recommend_arrangement completed in %dms", track_id, rec_ms)
                timing["stages"].append({"stage": "recommend_arrangement", "elapsed_ms": rec_ms, "returncode": 0, "timed_out": False})
                trace["stages"].append({
                    "name": "recommend_arrangement",
                    "status": "ok",
                    "elapsed_ms": rec_ms,
                    "summary": {
                        "total_phrases": plan.get("total_phrases", 0),
                        "avg_authenticity": plan.get("avg_authenticity", 0.0),
                        "avg_recommendation_score": plan.get("avg_recommendation_score", 0.0),
                        "constraint_passes": plan.get("constraints", {}).get("passes", False),
                    },
                })
                plan_cache_path.parent.mkdir(parents=True, exist_ok=True)
                _write_json(plan_cache_path, plan)

            plan_path = artifacts["plan"]
            _write_json(plan_path, plan)
            trace["artifacts"]["plan"] = str(plan_path.name)
            try:
                log_arrangement_plan(track_id, plan, actual_source, intent_tags or [])
            except Exception as err:
                logger.warning("[%s] Supabase plan log failed: %s", track_id, err)

        # ── Stage: assemble_track ─────────────────────────────────────
        temp_assembled = OUTPUT_DIR / f".tmp_{track_id}.wav"
        assemble_cmd = [
            sys.executable, str(PROJECT_ROOT / "assemble_track.py"),
            "--library", str(lib_path),
            "--duration", str(duration),
            "--output", str(temp_assembled),
        ]
        if plan_path is not None:
            assemble_cmd.extend(["--plan", str(plan_path)])

        result = _run_subprocess_timed(assemble_cmd, track_id, "assemble_track")
        timing["stages"].append(result)
        if result["returncode"] != 0:
            jobs[track_id]["status"] = "error"
            jobs[track_id]["error"] = result["stderr_tail"] or "Assembly failed"
            _save_timing()
            return
        trace["stages"].append({"name": "assemble_track", "status": "ok", "elapsed_ms": result["elapsed_ms"]})

        # ── Stage: add_production ─────────────────────────────────────
        result = _run_subprocess_timed(
            [
                sys.executable, str(PROJECT_ROOT / "add_production.py"),
                str(temp_assembled),
                "--style", genre,
                "--rules", str(PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"),
                "--output", str(wav_path),
            ],
            track_id, "add_production",
        )
        timing["stages"].append(result)
        if temp_assembled.exists():
            temp_assembled.unlink()

        if result["returncode"] != 0:
            jobs[track_id]["status"] = "error"
            jobs[track_id]["error"] = result["stderr_tail"] or "Production failed"
            _save_timing()
            return
        trace["stages"].append({"name": "add_production", "status": "ok", "elapsed_ms": result["elapsed_ms"]})

        # ── Stage: quality_metrics (async — fire and forget) ─────────
        quality_payload = None
        def _run_quality_async(tid: str, wav: Path, raga_name: str, arts: dict):
            """Run quality evaluation in background; write results when done."""
            try:
                from quality_metrics import evaluate_track
                rules_file = PROJECT_ROOT / "data" / "raga_rules" / f"{raga_name}.json"
                payload = evaluate_track(str(wav), str(rules_file))
                _write_json(arts["quality"], payload)
                meta_path_q = arts["meta"]
                if meta_path_q.exists():
                    with open(meta_path_q) as f:
                        meta = json.load(f)
                    meta["quality_score"] = payload.get("overall_score")
                    meta["commercial_ready"] = payload.get("commercial_ready")
                    meta["quality_status"] = "complete"
                    _write_json(meta_path_q, meta)
                logger.info("[%s] quality_metrics completed asynchronously", tid)
            except Exception as qe:
                logger.warning("[%s] quality_metrics async failed: %s", tid, qe)

        executor.submit(_run_quality_async, track_id, wav_path, raga, artifacts)
        trace["stages"].append({"name": "quality_metrics", "status": "async", "elapsed_ms": 0})

        # ── Write metadata ────────────────────────────────────────────
        actual_duration = _read_wav_duration(wav_path) or duration
        display_name = f"{raga}_{genre}_{datetime.now().year}_{track_id[:8]}"

        metadata = {
            "track_id": track_id,
            "filename": f"{track_id}.wav",
            "display_name": display_name,
            "raga": raga,
            "genre": genre,
            "duration": actual_duration,
            "requested_duration": duration,
            "source": source,
            "variation_profile": variation_profile,
            "prompt": prompt,
            "intent_tags": intent_tags,
            "recommend": recommend,
            "versions": trace["versions"],
            "artifact_urls": _build_artifact_urls(track_id),
            "quality_status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        _write_json(meta_path, metadata)

        trace["artifacts"]["metadata"] = meta_path.name
        trace["artifacts"]["audio"] = wav_path.name
        _write_json(artifacts["trace"], trace)

        _save_timing()
        interactive_budget = STAGE_BUDGET_MS["interactive_total"]
        if timing["total_ms"] > interactive_budget:
            logger.warning(
                "[%s] INTERACTIVE BUDGET EXCEEDED: total %dms (budget: %dms)",
                track_id, timing["total_ms"], interactive_budget,
            )
        logger.info("[%s] Pipeline complete. Total: %dms", track_id, timing["total_ms"])

        jobs[track_id]["status"] = "complete"
        jobs[track_id]["metadata"] = metadata

    except Exception as e:
        jobs[track_id]["status"] = "error"
        jobs[track_id]["error"] = str(e)
        _save_timing()
        logger.error("[%s] Pipeline FAILED: %s", track_id, e)


# ── Endpoints ────────────────────────────────────────────────────────

@app.post("/api/parse-prompt")
def api_parse_prompt(req: PromptRequest):
    return parse_prompt(req.prompt)


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    track_id = uuid.uuid4().hex[:12]
    jobs[track_id] = {"status": "processing", "error": None, "metadata": None}

    raga = req.raga
    intent_tags = list(req.intent_tags)
    recommend = req.recommend

    if req.upload_id:
        upload_files = list(UPLOADS_DIR.glob(f"{req.upload_id}.*"))
        if upload_files:
            try:
                from audio_analyzer import analyze_upload
                analysis = analyze_upload(str(upload_files[0]))
                best = analysis.get("raga", {}).get("best_match")
                if best:
                    raga = best.lower()
                derived_tags = analysis.get("intent_tags", [])
                intent_tags = list(set(intent_tags + derived_tags))
                recommend = True
            except Exception:
                pass

    executor.submit(
        _run_pipeline,
        track_id, raga, req.genre, req.duration, req.source, req.prompt,
        intent_tags, recommend, req.variation_profile,
    )

    return {"track_id": track_id, "status": "processing"}


@app.get("/api/status/{track_id}")
def api_status(track_id: str):
    if track_id in jobs:
        job = jobs[track_id]
        resp = {"track_id": track_id, "status": job["status"]}
        if job["status"] == "error":
            resp["error"] = job["error"]
        if job["status"] == "complete" and job["metadata"]:
            resp["metadata"] = job["metadata"]
        return resp

    meta_path = OUTPUT_DIR / f"{track_id}.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return {"track_id": track_id, "status": "complete", "metadata": json.load(f)}

    raise HTTPException(404, "Track not found")


@app.get("/api/tracks")
def api_tracks():
    tracks = []
    for meta_path in sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if any(suffix in meta_path.stem for suffix in ("_plan", "_trace", "_quality", "_timing")):
            continue
        try:
            with open(meta_path) as f:
                data = json.load(f)
            if "track_id" not in data:
                continue
            data.setdefault("artifact_urls", _build_artifact_urls(data["track_id"]))
            tracks.append(data)
        except Exception:
            continue
    return tracks


@app.get("/api/tracks/{track_id}")
def api_track(track_id: str):
    meta_path = OUTPUT_DIR / f"{track_id}.json"
    if not meta_path.exists():
        raise HTTPException(404, "Track not found")
    with open(meta_path) as f:
        data = json.load(f)
    data.setdefault("artifact_urls", _build_artifact_urls(track_id))
    return data


@app.get("/api/tracks/{track_id}/audio")
def api_track_audio(track_id: str):
    wav_path = OUTPUT_DIR / f"{track_id}.wav"
    if not wav_path.exists():
        raise HTTPException(404, "Audio file not found")
    return FileResponse(
        str(wav_path),
        media_type="audio/wav",
        filename=f"{track_id}.wav",
    )


@app.get("/api/styles")
def api_styles():
    return _load_styles()


@app.get("/api/ragas")
def api_ragas():
    return _load_ragas()


@app.post("/api/telemetry/event")
def api_telemetry_event(event: TelemetryEvent):
    ts = event.timestamp or time.time()
    key = _telemetry_key(event.track_id, event.session_id, event.event_type, ts)
    if key in telemetry_seen:
        return {"status": "duplicate"}
    telemetry_seen.add(key)
    if len(telemetry_seen) > 10000:
        telemetry_seen.clear()

    payload = {
        "track_id": event.track_id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "timestamp": ts,
        "received_at": time.time(),
        "payload": event.payload or {},
    }

    out_path = TELEMETRY_DIR / f"{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
    with open(out_path, "a") as f:
        f.write(json.dumps(payload) + "\n")

    return {"status": "ok"}


@app.post("/api/recommend/phrases")
def api_recommend_phrases(req: RecommendRequest):
    rec = _get_recommender()
    phrases = rec.recommend_phrases(
        raga=req.raga,
        style=req.genre,
        duration=req.duration,
        source=req.source,
        intent_tags=req.intent_tags,
    )
    return {
        "raga": req.raga,
        "genre": req.genre,
        "duration": req.duration,
        "total_phrases": len(phrases),
        "phrases": phrases,
    }


@app.post("/api/recommend/arrangement")
def api_recommend_arrangement(req: RecommendRequest):
    rec = _get_recommender()
    plan = rec.recommend_arrangement(
        raga=req.raga,
        style=req.genre,
        duration=req.duration,
        source=req.source,
        intent_tags=req.intent_tags,
    )
    try:
        log_arrangement_plan(None, plan, req.source, req.intent_tags)
    except Exception:
        pass
    return plan


# ── Upload & Analysis ─────────────────────────────────────────────────

@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...)):
    """Analyze an uploaded audio file: detect raga, tonal center, density, intent."""
    ext = Path(file.filename or "upload.wav").suffix.lower()
    if ext not in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
        raise HTTPException(400, f"Unsupported format: {ext}")

    upload_id = uuid.uuid4().hex[:12]
    upload_path = UPLOADS_DIR / f"{upload_id}{ext}"

    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        from audio_analyzer import analyze_upload
        result = analyze_upload(str(upload_path))
        result["upload_id"] = upload_id
        result["upload_path"] = str(upload_path)

        try:
            from raga_ai import ai_narrate_analysis
            narration = ai_narrate_analysis(result)
            if narration:
                result["ai_narration"] = narration
        except Exception:
            pass

        return result
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")


@app.get("/api/plan/{track_id}")
def api_plan(track_id: str):
    """Return the recommendation plan (with explanations) for a track."""
    plan_path = OUTPUT_DIR / f"{track_id}_plan.json"
    if not plan_path.exists():
        raise HTTPException(404, "Plan not found for this track")
    with open(plan_path) as f:
        return json.load(f)


@app.get("/api/trace/{track_id}")
def api_trace(track_id: str):
    """Return generation trace artifact for a track."""
    trace_path = OUTPUT_DIR / f"{track_id}_trace.json"
    if not trace_path.exists():
        raise HTTPException(404, "Trace not found for this track")
    with open(trace_path) as f:
        return json.load(f)


@app.get("/api/timing/{track_id}")
def api_timing(track_id: str):
    """Return per-stage timing report for a track generation."""
    timing_path = OUTPUT_DIR / f"{track_id}_timing.json"
    if not timing_path.exists():
        raise HTTPException(404, "Timing report not found for this track")
    with open(timing_path) as f:
        return json.load(f)


@app.get("/api/quality/{track_id}")
def api_quality(track_id: str):
    """Return cached quality report when available, else compute on demand."""
    quality_path = OUTPUT_DIR / f"{track_id}_quality.json"
    if quality_path.exists():
        with open(quality_path) as f:
            return json.load(f)
    return api_evaluate(track_id)


# ── AI Intelligence ────────────────────────────────────────────────────

@app.get("/api/ai/status")
def api_ai_status():
    """Check whether OpenAI intelligence layer is available."""
    try:
        from raga_ai import is_ai_available
        return {"available": is_ai_available()}
    except Exception:
        return {"available": False}


class AIParseRequest(BaseModel):
    prompt: str


@app.post("/api/ai/parse-prompt")
def api_ai_parse_prompt(req: AIParseRequest):
    """Parse a prompt using OpenAI for richer understanding."""
    t0 = time.monotonic()
    try:
        from raga_ai import ai_parse_prompt, is_ai_available
        if not is_ai_available():
            fallback = parse_prompt(req.prompt)
            try:
                log_ai_event(
                    event_type="parse_prompt",
                    prompt=req.prompt,
                    input_payload={"prompt": req.prompt},
                    output_payload={"fallback": fallback},
                    model=None,
                    latency_ms=round((time.monotonic() - t0) * 1000),
                )
            except Exception:
                pass
            return {"error": "OPENAI_API_KEY not configured", "fallback": fallback}
        result = ai_parse_prompt(req.prompt)
        if result is None:
            fallback = parse_prompt(req.prompt)
            try:
                log_ai_event(
                    event_type="parse_prompt",
                    prompt=req.prompt,
                    input_payload={"prompt": req.prompt},
                    output_payload={"fallback": fallback},
                    model=None,
                    latency_ms=round((time.monotonic() - t0) * 1000),
                )
            except Exception:
                pass
            return {"error": "AI parsing failed", "fallback": fallback}
        try:
            log_ai_event(
                event_type="parse_prompt",
                prompt=req.prompt,
                input_payload={"prompt": req.prompt},
                output_payload=result,
                model="gpt-4o-mini" if result.get("ai_parsed") else None,
                latency_ms=round((time.monotonic() - t0) * 1000),
            )
        except Exception:
            pass
        return result
    except Exception as e:
        return {"error": str(e), "fallback": parse_prompt(req.prompt)}


class AIExplainRequest(BaseModel):
    raga: str = "yaman"
    style: str = "lofi"
    duration: int = 60


@app.post("/api/ai/explain")
def api_ai_explain(req: AIExplainRequest):
    """Generate an AI explanation for a raga+style arrangement."""
    t0 = time.monotonic()
    rec = _get_recommender()
    plan = rec.recommend_arrangement(
        raga=req.raga, style=req.style, duration=req.duration,
    )
    try:
        log_ai_event(
            event_type="explain_plan",
            prompt=None,
            input_payload={"raga": req.raga, "style": req.style, "duration": req.duration},
            output_payload={"ai_explanation": plan.get("ai_explanation")},
            model="gpt-4o-mini" if plan.get("ai_explanation") else None,
            latency_ms=round((time.monotonic() - t0) * 1000),
        )
    except Exception:
        pass
    return {
        "plan_summary": {
            "raga": plan.get("raga"),
            "style": plan.get("style"),
            "total_phrases": plan.get("total_phrases"),
            "avg_authenticity": plan.get("avg_authenticity"),
            "constraints": plan.get("constraints"),
        },
        "explanations": plan.get("explanations", []),
        "ai_explanation": plan.get("ai_explanation"),
    }


class AISuggestRequest(BaseModel):
    raga: str = "yaman"
    style: str = "lofi"


@app.post("/api/ai/suggest-variations")
def api_ai_suggest_variations(req: AISuggestRequest):
    """Get AI-suggested creative variations for a raga+style."""
    t0 = time.monotonic()
    try:
        from raga_ai import ai_suggest_variations, is_ai_available
        if not is_ai_available():
            try:
                log_ai_event(
                    event_type="suggest_variations",
                    prompt=None,
                    input_payload={"raga": req.raga, "style": req.style},
                    output_payload={"variations": []},
                    model=None,
                    latency_ms=round((time.monotonic() - t0) * 1000),
                )
            except Exception:
                pass
            return {"error": "OPENAI_API_KEY not configured", "variations": []}
        variations = ai_suggest_variations(req.raga, req.style)
        try:
            log_ai_event(
                event_type="suggest_variations",
                prompt=None,
                input_payload={"raga": req.raga, "style": req.style},
                output_payload={"variations": variations or []},
                model="gpt-4o-mini" if variations else None,
                latency_ms=round((time.monotonic() - t0) * 1000),
            )
        except Exception:
            pass
        return {"raga": req.raga, "style": req.style, "variations": variations or []}
    except Exception as e:
        return {"error": str(e), "variations": []}


class FeedbackRequest(BaseModel):
    plan_id: str | None = None
    track_id: str | None = None
    rating: int | None = None
    feedback: str = ""
    tags: list[str] = []
    metadata: dict = {}


@app.post("/api/feedback")
def api_feedback(req: FeedbackRequest):
    """Persist user feedback on a plan or generated track."""
    try:
        log_feedback(
            plan_id=req.plan_id,
            track_id=req.track_id,
            rating=req.rating,
            feedback=req.feedback,
            tags=req.tags,
            metadata=req.metadata,
        )
    except Exception as e:
        return {"status": "error", "error": str(e)}
    return {"status": "ok"}


# ── Creator Upload ────────────────────────────────────────────────────

@app.post("/api/creator/upload")
async def api_creator_upload(
    file: UploadFile = File(...),
    raga: str = "auto",
    creator_name: str = "anonymous",
    count: int = 20,
):
    """Upload a recording, extract phrases, and build a creator-specific library."""
    ext = Path(file.filename or "upload.wav").suffix.lower()
    if ext not in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
        raise HTTPException(400, f"Unsupported format: {ext}")

    upload_id = uuid.uuid4().hex[:12]
    upload_path = UPLOADS_DIR / f"{upload_id}{ext}"
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    job_id = f"creator_{upload_id}"
    jobs[job_id] = {"status": "processing", "error": None, "metadata": None}

    executor.submit(
        _run_creator_pipeline, job_id, upload_id, str(upload_path),
        raga, creator_name, count
    )

    return {"job_id": job_id, "upload_id": upload_id, "status": "processing"}


@app.get("/api/creator/status/{job_id}")
def api_creator_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Creator job not found")
    job = jobs[job_id]
    resp = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "error":
        resp["error"] = job["error"]
    if job["status"] == "complete" and job["metadata"]:
        resp["metadata"] = job["metadata"]
    return resp


def _run_creator_pipeline(job_id: str, upload_id: str, upload_path: str,
                          raga: str, creator_name: str, count: int):
    """Run phrase extraction on a creator upload (blocking, thread pool)."""
    try:
        if raga == "auto":
            from audio_analyzer import analyze_upload
            analysis = analyze_upload(upload_path, max_analysis_seconds=60)
            detected_raga = analysis.get("raga", {}).get("best_match", "yaman")
            raga = detected_raga.lower() if isinstance(detected_raga, str) else "yaman"

        lib_name = f"{raga}_{creator_name}_{upload_id}"
        lib_dir = CREATOR_LIBS_DIR / lib_name

        proc = subprocess.run(
            [
                sys.executable, str(PROJECT_ROOT / "extract_phrases.py"),
                upload_path,
                "--count", str(count),
                "--output", str(lib_dir),
                "--min-dur", "1.0",
                "--max-dur", "8.0",
            ],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = proc.stderr or proc.stdout or "Phrase extraction failed"
            return

        from phrase_indexer import build_index
        build_index(force=True)

        meta_path = lib_dir / "phrases_metadata.json"
        phrase_count = 0
        if meta_path.exists():
            with open(meta_path) as f:
                phrase_count = len(json.load(f))

        metadata = {
            "job_id": job_id,
            "upload_id": upload_id,
            "raga": raga,
            "creator": creator_name,
            "library_name": lib_name,
            "library_dir": str(lib_dir),
            "phrase_count": phrase_count,
            "created_at": datetime.now().isoformat(),
        }
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["metadata"] = metadata

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


# ── Variation Engine ──────────────────────────────────────────────────

@app.get("/api/evaluate/{track_id}")
def api_evaluate(track_id: str):
    """Evaluate quality metrics (polish + authenticity) for a generated track."""
    wav_path = OUTPUT_DIR / f"{track_id}.wav"
    if not wav_path.exists():
        raise HTTPException(404, "Audio file not found")

    meta_path = OUTPUT_DIR / f"{track_id}.json"
    raga = "yaman"
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                raga = json.load(f).get("raga", "yaman")
        except Exception:
            pass

    rules_path = PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"
    rp = str(rules_path) if rules_path.exists() else None

    try:
        from quality_metrics import evaluate_track
        return evaluate_track(str(wav_path), rp)
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {e}")


class VariationRequest(BaseModel):
    raga: str = "yaman"
    source_library: str | None = None
    style: str = "lofi"
    duration: int = 60
    preset: str | None = None
    variation_type: str = "tempo"
    variation_amount: float = 0.2
    intent_tags: list[str] = []


@app.post("/api/variation/generate")
def api_variation_generate(req: VariationRequest):
    """Generate a variation from an existing phrase library."""
    track_id = uuid.uuid4().hex[:12]
    jobs[track_id] = {"status": "processing", "error": None, "metadata": None}

    executor.submit(
        _run_variation_pipeline, track_id, req.raga, req.source_library,
        req.style, req.duration, req.preset, req.variation_type, req.variation_amount,
        req.intent_tags,
    )

    return {"track_id": track_id, "status": "processing"}


def _run_variation_pipeline(track_id: str, raga: str, source_library: str | None,
                            style: str, duration: int, preset: str | None,
                            variation_type: str, variation_amount: float,
                            intent_tags: list[str]):
    """Generate a variation track (blocking, thread pool)."""
    try:
        from variation_engine import create_variation_library, PRESET_FALLBACK, resolve_variation_ops

        if source_library:
            src_lib = PROJECT_ROOT / "data" / "phrases" / source_library
        else:
            src_lib = PROJECT_ROOT / "data" / "phrases" / raga

        if not (src_lib / "phrases_metadata.json").exists():
            src_lib = PROJECT_ROOT / "data" / "phrases" / f"{raga}_generated"

        attempts: list[str | None] = []
        if preset:
            attempts.append(preset)
            fallback = PRESET_FALLBACK.get(preset)
            if fallback:
                attempts.append(fallback)
        else:
            attempts.append(None)

        wav_path = OUTPUT_DIR / f"{track_id}.wav"
        plan_path = OUTPUT_DIR / f"{track_id}_plan.json"
        applied_preset = preset or "custom"
        fallback_used = False
        quality_payload = None

        for attempt_idx, attempt_preset in enumerate(attempts):
            var_lib = OUTPUT_DIR / f".var_{track_id}_{attempt_idx}"
            create_variation_library(
                source_dir=src_lib,
                output_dir=var_lib,
                variation_type=variation_type,
                amount=variation_amount,
                preset=attempt_preset,
            )

            rec = _get_recommender()
            plan = rec.recommend_arrangement(
                raga=raga, style=style, duration=duration,
                source=None, intent_tags=intent_tags,
            )
            with open(plan_path, "w") as f:
                json.dump(plan, f, indent=2)

            temp_assembled = OUTPUT_DIR / f".tmp_{track_id}.wav"
            proc = subprocess.run(
                [
                    sys.executable, str(PROJECT_ROOT / "assemble_track.py"),
                    "--library", str(var_lib),
                    "--duration", str(duration),
                    "--output", str(temp_assembled),
                ],
                cwd=PROJECT_ROOT, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                jobs[track_id]["status"] = "error"
                jobs[track_id]["error"] = proc.stderr or "Assembly failed"
                return

            proc = subprocess.run(
                [
                    sys.executable, str(PROJECT_ROOT / "add_production.py"),
                    str(temp_assembled),
                    "--style", style,
                    "--rules", str(PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"),
                    "--output", str(wav_path),
                ],
                cwd=PROJECT_ROOT, capture_output=True, text=True,
            )
            if temp_assembled.exists():
                temp_assembled.unlink()

            if proc.returncode != 0:
                jobs[track_id]["status"] = "error"
                jobs[track_id]["error"] = proc.stderr or "Production failed"
                return

            try:
                from quality_metrics import evaluate_track
                quality_payload = evaluate_track(
                    str(wav_path),
                    str(PROJECT_ROOT / "data" / "raga_rules" / f"{raga}.json"),
                )
                quality_path = OUTPUT_DIR / f"{track_id}_quality.json"
                with open(quality_path, "w") as f:
                    json.dump(quality_payload, f, indent=2)
            except Exception:
                quality_payload = None

            if var_lib.exists():
                shutil.rmtree(var_lib, ignore_errors=True)

            applied_preset = attempt_preset or "custom"
            fallback_used = attempt_preset != preset and preset is not None

            if quality_payload and quality_payload.get("commercial_ready"):
                break

        actual_duration = _read_wav_duration(wav_path) or duration
        preset_for_ops = None if applied_preset == "custom" else applied_preset
        _, ops = resolve_variation_ops(variation_type, variation_amount, preset_for_ops)
        metadata = {
            "track_id": track_id,
            "filename": f"{track_id}.wav",
            "display_name": f"{raga}_{style}_var_{track_id[:8]}",
            "raga": raga,
            "genre": style,
            "duration": actual_duration,
            "variation_preset_requested": preset,
            "variation_preset_applied": applied_preset,
            "variation_fallback_used": fallback_used,
            "variation_type": variation_type,
            "variation_amount": variation_amount,
            "variation_ops": [{"type": t, "amount": a} for t, a in ops],
            "source_library": str(src_lib.name),
            "versions": {
                "recommender_version": RECOMMENDER_VERSION,
                "variation_engine_version": VARIATION_ENGINE_VERSION,
                "rules_version": RULES_VERSION,
            },
            "artifact_urls": _build_artifact_urls(track_id),
            "created_at": datetime.now().isoformat(),
        }
        if quality_payload:
            metadata["quality_score"] = quality_payload.get("overall_score")
            metadata["commercial_ready"] = quality_payload.get("commercial_ready")
        meta_path = OUTPUT_DIR / f"{track_id}.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        jobs[track_id]["status"] = "complete"
        jobs[track_id]["metadata"] = metadata

    except Exception as e:
        jobs[track_id]["status"] = "error"
        jobs[track_id]["error"] = str(e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
