"""Minimal LLM client for the sales brain.

No SDK — a thin httpx call to an OpenAI-compatible chat endpoint
(OpenRouter by default). httpx is already a project dependency; this
mirrors how elevenlabs_agent.py talks to ElevenLabs via raw requests
(no new dependency). The sales brain treats the LLM as advisory and
degrades safely if this raises, so callers can let exceptions surface.
"""

import os
from typing import Callable

import httpx


def complete(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 500,
    timeout: float = 12.0,
) -> str:
    """One chat completion. Returns the assistant message content."""
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY (or OPENAI_API_KEY) not set — sales brain LLM unavailable"
        )
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = model or os.getenv("SALES_BRAIN_MODEL", "openai/gpt-4o-mini")

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def make_llm() -> Callable[[str, str], str]:
    """Return a (system, user) -> str callable for SalesBrain(llm=...)."""
    return lambda system, user: complete(system, user)
