"""LLM access: Gemini (primary) -> Groq (fallback), structured JSON only.

Providers take (prompt, json_schema) and return a parsed dict. `LLMClient.generate_json`
tries providers in order; if all fail it raises LLMUnavailable so callers can degrade
to retrieval-only results.
"""
import json
import logging
import time
from typing import Protocol

import requests

from app import config

log = logging.getLogger("specsure.llm")


class LLMUnavailable(Exception):
    pass


class Provider(Protocol):
    name: str

    def generate_json(self, prompt: str, schema: dict) -> dict: ...


def _post_with_backoff(url: str, headers: dict, body: dict, tries: int = 3) -> dict:
    delay = 2.0
    for attempt in range(tries):
        r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code in (429, 500, 502, 503) and attempt < tries - 1:
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


class GeminiProvider:
    name = "gemini"

    def __init__(self, key: str | None = None, model: str | None = None) -> None:
        self.key = key or config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL

    def generate_json(self, prompt: str, schema: dict) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = _post_with_backoff(
            url, {"x-goog-api-key": self.key},
            {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"responseMimeType": "application/json",
                                  "responseSchema": schema, "temperature": 0.1}})
        return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])


class GroqProvider:
    name = "groq"

    def __init__(self, key: str | None = None, model: str | None = None) -> None:
        self.key = key or config.GROQ_API_KEY
        self.model = model or config.GROQ_MODEL

    def generate_json(self, prompt: str, schema: dict) -> dict:
        # json_object mode + schema in the prompt; the validator enforces the enum afterwards.
        full = f"{prompt}\n\nReturn ONLY JSON matching this JSON schema:\n{json.dumps(schema)}"
        data = _post_with_backoff(
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {self.key}"},
            {"model": self.model, "temperature": 0.1,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": full}]})
        return json.loads(data["choices"][0]["message"]["content"])


class StubProvider:
    """Deterministic provider for tests / offline demos. `responder(prompt, schema)` -> dict."""
    name = "stub"

    def __init__(self, responder) -> None:
        self.responder = responder

    def generate_json(self, prompt: str, schema: dict) -> dict:
        return self.responder(prompt, schema)


class LLMClient:
    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers

    @classmethod
    def from_env(cls) -> "LLMClient":
        providers: list[Provider] = []
        if config.GEMINI_API_KEY:
            providers.append(GeminiProvider())
        if config.GROQ_API_KEY:
            providers.append(GroqProvider())
        return cls(providers)

    def generate_json(self, prompt: str, schema: dict) -> dict:
        for p in self.providers:
            try:
                return p.generate_json(prompt, schema)
            except Exception as e:  # noqa: BLE001 - any provider failure -> try next
                log.warning("LLM provider %s failed: %s", p.name, type(e).__name__)
        raise LLMUnavailable("no LLM provider succeeded")
