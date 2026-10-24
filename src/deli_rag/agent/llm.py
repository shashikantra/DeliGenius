from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from openai import OpenAI
from deli_rag.config.settings import get_env, get_config

log = logging.getLogger(__name__)


@dataclass
class LLMReply:
    content: str
    model_used: str
    fallback_used: bool
    tokens_in: int
    tokens_out: int
    latency_ms: float


class GroqClient:
    """Wrapper over OpenAI-compatible SDKs (Groq and Ollama)."""

    def __init__(self) -> None:
        cfg = get_config().llm
        self.groq_primary = cfg.primary.id
        self.groq_fallbacks = [e.id for e in (cfg.fallback_1, cfg.fallback_2) if e.verified]

        # Ollama config
        ollama_cfg = getattr(cfg, "ollama", None)
        self.ollama_model = ollama_cfg.id if ollama_cfg else "llama3"
        self.ollama_url = ollama_cfg.base_url if ollama_cfg else "http://localhost:11434/v1"

        self.retry_backoffs = list(cfg.retry_backoff_s)

        # Groq Client
        self.groq_client = OpenAI(
            api_key=get_env().groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=60.0,
            max_retries=1
        )

        # Ollama Client
        self.ollama_client = OpenAI(
            api_key="ollama",
            base_url=self.ollama_url,
            timeout=120.0,  # Ollama can be slow on CPU
            max_retries=1
        )

    def complete_json(
            self,
            *,
            system: str,
            user: str,
            max_tokens: int = 2048,
            temperature: float = 0.0,
            prefer_local: bool = False,
    ) -> LLMReply:

        print(f"🔵 [LLM] complete_json called with prefer_local={prefer_local}")  # <--- ADD
        # Build the list of models to try based on preference
        if prefer_local:
            models_to_try = [("ollama", self.ollama_model)] + [("groq", m) for m in
                                                               [self.groq_primary, *self.groq_fallbacks]]
        else:
            models_to_try = [("groq", m) for m in [self.groq_primary, *self.groq_fallbacks]] + [
                ("ollama", self.ollama_model)]

        tried: list[str] = []
        print(f"🔵 [LLM] Models to try: {models_to_try}")  # <--- ADD

        for provider, model in models_to_try:
            print(f"🔵 [LLM] Trying {provider}:{model}")  # <--- ADD
            tried.append(f"{provider}:{model}")
            for attempt, backoff in enumerate([0, *self.retry_backoffs]):
                if backoff:
                    time.sleep(backoff)
                t0 = time.perf_counter()
                try:
                    client = self.groq_client if provider == "groq" else self.ollama_client

                    kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if provider == "groq":
                        kwargs["response_format"] = {"type": "json_object"}

                    resp = client.chat.completions.create(**kwargs)
                    dt_ms = (time.perf_counter() - t0) * 1000
                    content = (resp.choices[0].message.content or "").strip()
                    print(f"🟢 [LLM] Success with {provider}:{model}")  # <--- ADD
                    return LLMReply(
                        content=content,
                        model_used=f"{provider}:{model}",
                        fallback_used=(attempt > 0 or provider == "ollama"),
                        tokens_in=getattr(resp.usage, "prompt_tokens", 0) or 0,
                        tokens_out=getattr(resp.usage, "completion_tokens", 0) or 0,
                        latency_ms=dt_ms,
                    )
                except Exception as e:
                    msg = str(e)
                    log.warning(f"LLM Error {provider}:{model} attempt={attempt} err={msg[:120]}")
                    print(f"🔴 [LLM] Failed {provider}:{model} - {e}")  # <--- ADD
                    if "429" in msg or "rate limit" in msg.lower():
                        log.warning("Rate limit hit. Waiting 15s...")
                        time.sleep(15)

                    retryable = ("429" in msg or "500" in msg or "502" in msg
                                 or "503" in msg or "504" in msg or "timeout" in msg.lower())
                    if not retryable:
                        break

        raise RuntimeError(
            f"All LLM models failed. Tried: {tried}. "
            "Check your Groq API key and ensure Ollama is running."
        )


def parse_json_object(raw: str) -> dict:
    """Parse a JSON object from the LLM reply. Tolerant of code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        raise ValueError(f"No JSON object in reply: {raw[:120]!r}")
    return json.loads(s[i:j + 1])