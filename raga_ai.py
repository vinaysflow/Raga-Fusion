#!/usr/bin/env python3
"""
raga_ai.py — OpenAI-powered intelligence layer for the Raga-Fusion platform.

Provides three AI capabilities:
1. Smart prompt parsing (complex/ambiguous natural language -> structured params)
2. Arrangement plan explanation (educational, music-theory-rich narratives)
3. Upload analysis narration (song analysis -> consumer-friendly description)

The module gracefully degrades: if OPENAI_API_KEY is not set or a call fails,
every function returns a sensible fallback so the rest of the system works.

Setup:
    export OPENAI_API_KEY="sk-..."

Usage:
    from raga_ai import ai_parse_prompt, ai_explain_plan, ai_narrate_analysis
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

_client = None


def _get_client():
    """Lazy-init the OpenAI client. Returns None if key not set."""
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set — AI features disabled, using fallbacks")
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
        return _client
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}")
        return None


def _load_available_ragas() -> list[str]:
    rules_dir = PROJECT_ROOT / "data" / "raga_rules"
    if rules_dir.exists():
        return [p.stem for p in rules_dir.glob("*.json")]
    return ["yaman"]


def _load_raga_summary(raga_name: str) -> str:
    """Load a short summary of a raga from its rules file."""
    path = PROJECT_ROOT / "data" / "raga_rules" / f"{raga_name}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            rules = json.load(f)
        r = rules.get("raga", {})
        ctx = rules.get("context", {})
        return (
            f"{r.get('name', raga_name)}: thaat={r.get('thaat', '?')}, "
            f"mood={ctx.get('mood', '?')}, time={ctx.get('time', {}).get('window', '?')}"
        )
    except Exception:
        return raga_name


# ═══════════════════════════════════════════════════════════════════════
#  1. Smart Prompt Parsing
# ═══════════════════════════════════════════════════════════════════════

PROMPT_SYSTEM = """You are a Hindustani classical music expert who helps users create raga fusion music.

Given a user's free-text prompt, extract structured parameters for music generation.

Available ragas: {ragas}
Available styles: lofi, ambient, calm, upbeat, chillhop, trap, bass_house, psytrance, downtempo, jazz_fusion, cinematic, reggae_dub

Raga context:
{raga_context}

Return ONLY valid JSON with these fields:
- "raga": one of the available ragas (pick best match based on mood, time of day, or explicit mention)
- "genre": one of the available styles
- "duration": integer seconds (default 120)
- "intent_tags": array of strings from [meditative, energetic, dense, minimal, calm, intense]
- "confidence": float 0-1 how confident you are in the raga selection
- "reasoning": one sentence explaining your raga choice"""


def ai_parse_prompt(text: str) -> dict | None:
    """Use OpenAI to parse a complex prompt into structured generation params.

    Returns a dict with raga, genre, duration, intent_tags, confidence, reasoning.
    Returns None if AI is unavailable (caller should fall back to keyword parser).
    """
    client = _get_client()
    if client is None:
        return None

    ragas = _load_available_ragas()
    raga_context = "\n".join(f"- {_load_raga_summary(r)}" for r in ragas)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": PROMPT_SYSTEM.format(ragas=", ".join(ragas), raga_context=raga_context),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        parsed = json.loads(content)

        result = {
            "raga": parsed.get("raga", "yaman"),
            "genre": parsed.get("genre", "lofi"),
            "duration": int(parsed.get("duration", 120)),
            "intent_tags": parsed.get("intent_tags", []),
            "confidence": float(parsed.get("confidence", 0.5)),
            "reasoning": parsed.get("reasoning", ""),
            "ai_parsed": True,
        }

        if result["raga"] not in ragas:
            result["raga"] = "yaman"

        return result

    except Exception as e:
        logger.warning(f"AI prompt parsing failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  2. Plan Explanation
# ═══════════════════════════════════════════════════════════════════════

EXPLAIN_SYSTEM = """You are a Hindustani classical music educator explaining a raga fusion arrangement.

Given an arrangement plan (JSON), write a concise, educational explanation covering:
1. Why this raga was chosen and its musical character
2. How the phrase arrangement preserves raga identity (pakad, vadi emphasis)
3. How the style/genre fusion complements the raga's mood
4. The musical arc (opening -> development -> resolution)

Keep it under 200 words. Be specific about music theory (mention svaras, thaats, time of day).
Write for someone who is curious about Indian classical music but may not be an expert."""


def ai_explain_plan(plan: dict) -> str | None:
    """Generate an educational explanation of an arrangement plan.

    Returns a string explanation, or None if AI is unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    raga = plan.get("raga", "yaman")
    raga_summary = _load_raga_summary(raga)

    plan_summary = {
        "raga": raga,
        "raga_info": raga_summary,
        "style": plan.get("style", "lofi"),
        "duration": plan.get("duration", 120),
        "total_phrases": plan.get("total_phrases", 0),
        "avg_authenticity": plan.get("avg_authenticity", 0),
        "constraints": plan.get("constraints", {}),
        "phases": {
            phase: len(phrases)
            for phase, phrases in plan.get("phases", {}).items()
        },
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXPLAIN_SYSTEM},
                {"role": "user", "content": json.dumps(plan_summary, indent=2)},
            ],
            temperature=0.5,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"AI plan explanation failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  3. Upload Analysis Narration
# ═══════════════════════════════════════════════════════════════════════

NARRATE_SYSTEM = """You are a Hindustani classical music expert analyzing a recording.

Given the analysis results (JSON) from our audio analyzer, write a consumer-friendly narration:
1. What raga was detected and how confident the system is
2. Key musical characteristics found (tonal center, energy, density)
3. What fusion styles would complement this recording
4. Suggestions for the user (e.g. "Try pairing with lofi for a meditative evening vibe")

Keep it under 150 words. Be warm and educational, not overly technical."""


def ai_narrate_analysis(analysis: dict) -> str | None:
    """Generate a natural language narration of an audio analysis.

    Returns a string narration, or None if AI is unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    safe_analysis = {
        "raga": analysis.get("raga", {}),
        "tonal_center": analysis.get("tonal_center", {}),
        "density": analysis.get("density", {}),
        "energy_profile": {
            "avg_energy": analysis.get("energy_profile", {}).get("avg_energy", 0),
            "dynamic_range_db": analysis.get("energy_profile", {}).get("dynamic_range_db", 0),
        },
        "tempo": analysis.get("tempo", {}),
        "intent_tags": analysis.get("intent_tags", []),
        "thaat": analysis.get("thaat", {}),
    }

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": NARRATE_SYSTEM},
                {"role": "user", "content": json.dumps(safe_analysis, indent=2)},
            ],
            temperature=0.6,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"AI analysis narration failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  4. Creative Variation Suggestions
# ═══════════════════════════════════════════════════════════════════════

VARIATION_SYSTEM = """You are a music producer who specializes in Indian classical fusion.

Given a raga and style, suggest 3 creative variations that would sound interesting.
Each variation should specify:
- variation_type: one of [tempo, pitch, density, motif, harmonic]
- amount: float between 0.1 and 0.5
- description: one sentence explaining the musical effect

Return ONLY valid JSON: {"variations": [...]}"""


def ai_suggest_variations(raga: str, style: str) -> list[dict] | None:
    """Suggest creative variations for a raga+style combination.

    Returns a list of variation dicts, or None if AI is unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    raga_summary = _load_raga_summary(raga)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VARIATION_SYSTEM},
                {
                    "role": "user",
                    "content": f"Raga: {raga} ({raga_summary})\nStyle: {style}",
                },
            ],
            temperature=0.7,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        parsed = json.loads(content)
        return parsed.get("variations", [])
    except Exception as e:
        logger.warning(f"AI variation suggestion failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  Utility: check if AI is available
# ═══════════════════════════════════════════════════════════════════════

def is_ai_available() -> bool:
    """Check whether OpenAI API key is configured."""
    return bool(os.environ.get("OPENAI_API_KEY"))


# ═══════════════════════════════════════════════════════════════════════
#  CLI test
# ═══════════════════════════════════════════════════════════════════════

def main():
    import sys

    if not is_ai_available():
        print("\n  OPENAI_API_KEY not set.")
        print("  Run: export OPENAI_API_KEY='sk-...'")
        print("  Then try again.\n")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python raga_ai.py \"your prompt here\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    print(f"\n  Prompt: {prompt!r}\n")

    print("  [1] AI Prompt Parsing...")
    result = ai_parse_prompt(prompt)
    if result:
        print(f"      Raga: {result['raga']} (confidence: {result['confidence']:.0%})")
        print(f"      Genre: {result['genre']}")
        print(f"      Duration: {result['duration']}s")
        print(f"      Intent: {', '.join(result['intent_tags'])}")
        print(f"      Reasoning: {result['reasoning']}")
    else:
        print("      (AI unavailable)")

    print("\n  [2] AI Plan Explanation...")
    dummy_plan = {
        "raga": result["raga"] if result else "yaman",
        "style": result["genre"] if result else "lofi",
        "duration": 60,
        "total_phrases": 10,
        "avg_authenticity": 0.54,
        "constraints": {"passes": True, "violations": []},
        "phases": {
            "opening": [{}] * 2,
            "ascending": [{}] * 2,
            "development": [{}] * 3,
            "peak": [{}] * 2,
            "resolution": [{}] * 1,
        },
    }
    explanation = ai_explain_plan(dummy_plan)
    if explanation:
        for line in explanation.split("\n"):
            print(f"      {line}")
    else:
        print("      (AI unavailable)")

    print("\n  [3] AI Variation Suggestions...")
    variations = ai_suggest_variations(
        result["raga"] if result else "yaman",
        result["genre"] if result else "lofi",
    )
    if variations:
        for v in variations:
            print(f"      - {v.get('variation_type', '?')} ({v.get('amount', 0):.1f}): "
                  f"{v.get('description', '')}")
    else:
        print("      (AI unavailable)")

    print()


if __name__ == "__main__":
    main()
