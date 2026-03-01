#!/usr/bin/env python3
"""
prompt_parser.py — Extract structured generation params from free-text prompts.

Usage (as module):
    from prompt_parser import parse_prompt
    params = parse_prompt("Romantic lofi for sunset meditation")
    # {"raga": "yaman", "genre": "lofi", "duration": 120, "source": "generated"}

Usage (CLI test):
    python prompt_parser.py "Romantic lofi for sunset meditation"
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

GENRE_KEYWORDS: dict[str, list[str]] = {
    "lofi": ["lofi", "lo-fi", "lo fi", "lofi hip hop"],
    "ambient": ["ambient", "meditative", "zen", "spacey", "drone", "ethereal", "atmospheric"],
    "calm": ["calm", "peaceful", "relaxed", "gentle", "soft", "soothing", "mellow"],
    "upbeat": ["upbeat", "energetic", "bright", "happy", "lively"],
    "chillhop": ["chillhop", "chill hop", "jazzy beats", "coffeehouse", "coffee shop"],
    "trap": ["trap", "808", "drill", "hard", "heavy", "bass drop"],
    "bass_house": ["bass house", "house", "club", "dance", "edm", "nucleya", "ritviz"],
    "psytrance": ["psytrance", "psy", "trance", "psychedelic", "festival", "rave"],
    "downtempo": ["downtempo", "trip hop", "triphop", "organic", "electronica", "chill out"],
    "jazz_fusion": ["jazz", "fusion", "modal", "bebop", "swing", "groovy", "funky"],
    "cinematic": ["cinematic", "film", "trailer", "epic", "orchestral", "score", "movie"],
    "reggae_dub": ["reggae", "dub", "riddim", "offbeat", "ska", "roots", "jamaican"],
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "meditative": ["meditative", "meditation", "zen", "tranquil", "contemplative"],
    "energetic": ["energetic", "upbeat", "driving", "dance", "club", "festival"],
    "dense": ["dense", "busy", "fast", "complex", "taan", "virtuosic"],
    "minimal": ["minimal", "sparse", "slow", "ambient", "drone"],
    "calm": ["calm", "peaceful", "relaxed", "soothing"],
    "intense": ["intense", "powerful", "forceful", "majestic"],
}

MOOD_TO_RAGA: dict[str, list[str]] = {
    "yaman": [
        "serene", "joyful", "bright", "uplifting", "dreamy",
        "nostalgic", "spiritual", "prayer", "yaman",
    ],
    "bhairavi": [
        "devotional", "compassionate", "melancholic", "tender", "bittersweet",
        "sad", "emotional", "bhajan", "morning prayer", "bhairavi",
    ],
    "bhairav": [
        "majestic", "serious", "awe", "solemn", "powerful", "intense",
        "fierce", "shiva", "dawn", "bhairav",
    ],
    "malkauns": [
        "deep", "introspective", "haunting", "profound", "dark",
        "mysterious", "supernatural", "focus", "concentration", "malkauns",
    ],
    "desh": [
        "romantic", "playful", "rain", "monsoon", "patriotic", "longing",
        "homecoming", "light", "cheerful", "nostalgia", "desh",
    ],
}

TIME_TO_RAGA: dict[str, list[str]] = {
    "yaman": ["evening", "sunset", "dusk", "twilight", "6pm", "7pm", "8pm"],
    "bhairavi": ["early morning", "sunrise", "dawn", "6am", "7am", "8am"],
    "bhairav": ["morning", "sunrise", "dawn", "daybreak", "6am", "7am", "8am"],
    "malkauns": ["midnight", "late night", "deep night", "12am", "1am", "2am", "3am"],
    "desh": ["night", "9pm", "10pm", "11pm", "rainy night", "monsoon night"],
}

DURATION_WORDS: dict[str, int] = {
    "short": 30,
    "brief": 30,
    "quick": 30,
    "medium": 60,
    "long": 120,
    "extended": 180,
    "full": 180,
}

DEFAULTS = {
    "raga": "yaman",
    "genre": "lofi",
    "duration": 120,
    "source": "generated",
}


def _load_available_styles() -> list[str]:
    try:
        with open(PROJECT_ROOT / "data" / "styles.json") as f:
            return list(json.load(f).keys())
    except Exception:
        return list(GENRE_KEYWORDS.keys())


def _load_available_ragas() -> list[str]:
    rules_dir = PROJECT_ROOT / "data" / "raga_rules"
    if rules_dir.exists():
        return [p.stem for p in rules_dir.glob("*.json")]
    return ["yaman"]


def parse_prompt(text: str, use_ai: bool = True) -> dict:
    """Parse a free-text prompt into structured generation parameters.

    When use_ai=True and OPENAI_API_KEY is set, uses GPT for richer understanding
    of complex prompts. Falls back to keyword matching if AI is unavailable.

    >>> parse_prompt("Romantic lofi for sunset meditation", use_ai=False)
    {'raga': 'yaman', 'genre': 'lofi', 'duration': 120, 'source': 'generated'}
    """
    if use_ai:
        try:
            from raga_ai import ai_parse_prompt
            ai_result = ai_parse_prompt(text)
            if ai_result is not None:
                result = dict(DEFAULTS)
                result["raga"] = ai_result.get("raga", DEFAULTS["raga"])
                result["genre"] = ai_result.get("genre", DEFAULTS["genre"])
                result["duration"] = ai_result.get("duration", DEFAULTS["duration"])
                result["intent_tags"] = ai_result.get("intent_tags", [])
                result["ai_parsed"] = True
                result["ai_confidence"] = ai_result.get("confidence", 0.5)
                result["ai_reasoning"] = ai_result.get("reasoning", "")
                return result
        except Exception:
            pass

    lower = text.lower().strip()
    result = dict(DEFAULTS)

    result["genre"] = _extract_genre(lower)
    result["raga"] = _extract_raga(lower)
    result["duration"] = _extract_duration(lower)
    result["intent_tags"] = _extract_intent_tags(lower)
    result["ai_parsed"] = False

    return result


def _extract_intent_tags(text: str) -> list[str]:
    tags: list[str] = []
    for tag, keywords in INTENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    return tags


def _extract_genre(text: str) -> str:
    available = _load_available_styles()
    scores: dict[str, int] = {}
    for genre, keywords in GENRE_KEYWORDS.items():
        if genre not in available:
            continue
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scores[genre] = hits
    if scores:
        return max(scores, key=lambda g: scores[g])
    return DEFAULTS["genre"]


def _extract_raga(text: str) -> str:
    available = _load_available_ragas()

    # Direct name match takes priority
    for raga in available:
        if raga in text:
            return raga

    # Score each raga by number of keyword matches (mood + time)
    scores: dict[str, int] = {}
    for raga, keywords in MOOD_TO_RAGA.items():
        if raga not in available:
            continue
        hits = sum(1 for kw in keywords if kw in text)
        scores[raga] = scores.get(raga, 0) + hits

    for raga, keywords in TIME_TO_RAGA.items():
        if raga not in available:
            continue
        hits = sum(1 for kw in keywords if kw in text)
        scores[raga] = scores.get(raga, 0) + hits

    if scores:
        best = max(scores, key=lambda r: scores[r])
        if scores[best] > 0:
            return best

    return DEFAULTS["raga"]


def _extract_duration(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:minute|min|m)\b", text)
    if m:
        return int(m.group(1)) * 60

    m = re.search(r"(\d+)\s*(?:second|sec|s)\b", text)
    if m:
        return max(10, int(m.group(1)))

    for word, dur in DURATION_WORDS.items():
        if word in text:
            return dur

    return DEFAULTS["duration"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python prompt_parser.py \"your prompt here\"")
        sys.exit(1)
    prompt = " ".join(sys.argv[1:])
    result = parse_prompt(prompt)
    print(f"  Prompt:   {prompt!r}")
    print(f"  Raga:     {result['raga']}")
    print(f"  Genre:    {result['genre']}")
    print(f"  Duration: {result['duration']}s")
    print(f"  Source:   {result['source']}")


if __name__ == "__main__":
    main()
