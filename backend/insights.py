"""Turns raw detection events into natural-language text via an
OpenAI-compatible chat endpoint. Swap providers with the LLM_PROVIDER env var
(ollama | groq | kompact) -- nothing else in this file changes. See config.py.
"""
import time
from collections import Counter

from openai import OpenAI

import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        p = config.LLM_PROVIDERS[config.LLM_PROVIDER]
        _client = OpenAI(base_url=p["base_url"], api_key=p["api_key"] or "unset")
    return _client


def _chat(system: str, user: str, max_tokens: int = 150) -> str:
    p = config.LLM_PROVIDERS[config.LLM_PROVIDER]
    if not p["base_url"]:
        raise RuntimeError(f"LLM_PROVIDER={config.LLM_PROVIDER!r} has no base_url configured")
    resp = _get_client().chat.completions.create(
        model=p["model"],
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.4,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        # Reasoning models (e.g. gpt-oss) can spend the whole token budget on
        # hidden reasoning and leave nothing for the visible answer -- treat
        # that the same as a failed call so the template fallback kicks in.
        raise RuntimeError(f"empty completion from {p['model']!r} (finish_reason={resp.choices[0].finish_reason})")
    return text


def generate_hazard_alert(label: str, confidence: float, source: str) -> str:
    system = (
        "You write one-sentence safety alerts from a hazard detection event. "
        "Be direct and actionable. No preamble, no markdown."
    )
    user = f"Hazard detected: {label} (confidence {confidence:.2f}) on camera '{source}'. Write the alert."
    try:
        return _chat(system, user, max_tokens=200)
    except Exception as e:
        print(f"[insights] hazard alert LLM call failed, using template fallback: {e}")
        return f"Possible {label} detected on '{source}' (confidence {confidence:.0%}). Please check immediately."


def generate_mood_summary(events: list[dict], window_label: str) -> str | None:
    if not events:
        return None
    lines = [
        f"{time.strftime('%H:%M', time.localtime(e['ts']))} - {e['label']} ({e['confidence']:.2f})"
        for e in events
    ]
    system = (
        "You summarize a short log of detected facial expressions into one natural, "
        "grounded insight for the person being monitored. Warm, concise, 2-3 sentences. "
        "Do not moralize or give medical advice."
    )
    user = f"Emotion readings from the last {window_label}:\n" + "\n".join(lines)
    try:
        return _chat(system, user, max_tokens=300)
    except Exception as e:
        print(f"[insights] mood summary LLM call failed, using template fallback: {e}")
        counts = Counter(e["label"] for e in events)
        top_label, top_n = counts.most_common(1)[0]
        return f"Over the last {window_label}, the most common expression was '{top_label}' ({top_n} of {len(events)} readings)."
