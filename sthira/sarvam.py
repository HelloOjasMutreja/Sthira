"""Sarvam AI client: speech to text (Saaras), text to speech (Bulbul), translation (Sarvam-Translate) and chat (Sarvam-105B).

Used for Sthira's voice talkback: you speak in your own language, Sthira understands and answers from your ledger,
and speaks the answer back. The API key is read from SARVAM_API_KEY and never logged or returned.
"""

from __future__ import annotations

import base64
import os
import re

import httpx

BASE = "https://api.sarvam.ai"
TTS_MODEL = "bulbul:v3"
STT_MODEL = "saaras:v3"
CHAT_MODEL = "sarvam-105b"
SPEAKER = "shubh"

# Languages Bulbul v3 can speak. Keys are BCP-47 codes, values the native name shown in the UI.
LANGS = {
    "en-IN": "English", "hi-IN": "हिन्दी", "kn-IN": "ಕನ್ನಡ", "ta-IN": "தமிழ்", "te-IN": "తెలుగు", "ml-IN": "മലയാളം",
    "mr-IN": "मराठी", "bn-IN": "বাংলা", "gu-IN": "ગુજરાતી", "pa-IN": "ਪੰਜਾਬੀ", "od-IN": "ଓଡ଼ିଆ",
}
ENGLISH_NAMES = {
    "en-IN": "English", "hi-IN": "Hindi", "kn-IN": "Kannada", "ta-IN": "Tamil", "te-IN": "Telugu", "ml-IN": "Malayalam",
    "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati", "pa-IN": "Punjabi", "od-IN": "Odia",
}


class SarvamError(RuntimeError):
    pass


def _key() -> str:
    return os.environ.get("SARVAM_API_KEY", "")


def enabled() -> bool:
    return bool(_key())


def _headers() -> dict:
    if not enabled():
        raise SarvamError("Voice is not configured (no SARVAM_API_KEY).")
    return {"api-subscription-key": _key()}


def _check(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise SarvamError(f"{what} failed ({r.status_code}): {str(msg)[:200]}")
    return r.json()


def normalize_lang(code: str | None, default: str = "en-IN") -> str:
    return code if code in LANGS else default


def stt(audio: bytes, filename: str = "speech.wav", mime: str = "audio/wav", mode: str = "transcribe") -> dict:
    """Returns {"transcript", "language_code"}. mode='translate' returns the English translation instead."""
    r = httpx.post(f"{BASE}/speech-to-text", headers=_headers(), data={"model": STT_MODEL, "mode": mode},
                   files={"file": (filename, audio, mime)}, timeout=60)
    d = _check(r, "Speech recognition")
    return {"transcript": (d.get("transcript") or "").strip(), "language_code": d.get("language_code") or ""}


def tts(text: str, lang: str = "en-IN") -> bytes:
    """Speak `text` in `lang`; returns WAV bytes. Long text is clipped to keep it quick and cheap."""
    text = re.sub(r"\s+", " ", text).strip()[:1200]
    if not text:
        raise SarvamError("Nothing to speak.")
    r = httpx.post(f"{BASE}/text-to-speech", headers={**_headers(), "Content-Type": "application/json"}, timeout=60,
                   json={"text": text, "target_language_code": normalize_lang(lang), "speaker": SPEAKER, "model": TTS_MODEL})
    d = _check(r, "Speech synthesis")
    audios = d.get("audios") or []
    if not audios:
        raise SarvamError("Speech synthesis returned no audio.")
    return base64.b64decode(audios[0])


def chat(messages: list[dict], max_tokens: int = 500) -> str:
    r = httpx.post(f"{BASE}/v1/chat/completions", headers={**_headers(), "Content-Type": "application/json"}, timeout=60,
                   json={"model": CHAT_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2})
    d = _check(r, "Sarvam chat")
    text = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def translate(text: str, target: str, source: str = "en-IN") -> str:
    """Translate with Sarvam's translation model. Returns the text unchanged when source and target match."""
    if not text.strip() or normalize_lang(target) == normalize_lang(source):
        return text
    r = httpx.post(f"{BASE}/translate", headers={**_headers(), "Content-Type": "application/json"}, timeout=60,
                   json={"input": text[:1800], "source_language_code": normalize_lang(source), "target_language_code": normalize_lang(target),
                         "model": "sarvam-translate:v1"})
    return (_check(r, "Translation").get("translated_text") or text).strip()
