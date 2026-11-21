"""Optional: Gemini with Google Search grounding, for claims the free data
sources can't settle (company facts, tech figures, recent events).
Turned on by setting GEMINI_API_KEY (free key from aistudio.google.com)."""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPT = """You are a strict fact-checker. Today's date is {today}.
Check this claim against current, reliable web sources.

Claim: "{raw}"
Sentence it comes from: "{sentence}"

Reply with only a JSON object, no other text:
{{"status": "Verified" or "Inaccurate" or "False", "correct_fact": "the real, current fact in one short sentence", "year": the year of the correct figure or null, "explanation": "one short sentence"}}

Verified: matches the latest reliable figure.
Inaccurate: was true at some point but is outdated, or is close but wrong.
False: contradicted by sources, or no evidence it was ever true.
Always state the correct current fact."""


def key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def available() -> bool:
    return bool(key())


def verify_claim(sentence: str, raw: str, timeout: int = 25):
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(
            today=datetime.date.today().isoformat(), raw=raw, sentence=sentence)}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0},
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % MODEL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    cand = d["candidates"][0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    m = re.search(r"\{.*\}", text, re.S)
    obj = json.loads(m.group(0))
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    web = (chunks[0].get("web") or {}) if chunks else {}
    return obj, web.get("uri", ""), web.get("title", "")
