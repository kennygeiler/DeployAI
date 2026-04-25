"""OpenAI chat + embeddings provider (Epic 5, Story 5.2)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx

from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, UsageCallback, httpx_post_with_retries, record_usage

CHAT_URL = "https://api.openai.com/v1/chat/completions"
EMBED_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_CHAT_MODEL = "gpt-4o"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        timeout_s: float = 120.0,
        tenant_id: str = "system",
        agent_name: str = "agent",
        on_usage: UsageCallback | None = None,
    ) -> None:
        self._key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self._chat_model = (chat_model or os.environ.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL).strip()
        self._embed_model = (embed_model or os.environ.get("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBED_MODEL).strip()
        self._timeout = timeout_s
        self._tenant_id = tenant_id
        self._agent_name = agent_name
        self._on_usage = on_usage
        self.id = "openai"

    def _headers(self) -> dict[str, str]:
        if not self._key:
            msg = "OPENAI_API_KEY is not set"
            raise OSError(msg)
        return {"authorization": f"Bearer {self._key}", "content-type": "application/json"}

    def _to_openai_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for m in messages:
            role = m.get("role", "user")
            if role not in ("system", "user", "assistant"):
                role = "user"
            out.append({"role": role, "content": m.get("content", "")})
        if not out:
            out = [{"role": "user", "content": ""}]
        return out

    def _emit_usage_tokens(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        record_usage(
            self._on_usage,
            {
                "provider": "openai",
                "model": self._chat_model,
                "tenant_id": self._tenant_id,
                "agent_name": self._agent_name,
                "usage": usage,
            },
        )

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": self._chat_model,
            "messages": self._to_openai_messages(messages),
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_output_tokens is not None:
            body["max_tokens"] = max_output_tokens

        with httpx.Client(timeout=self._timeout) as client:
            r = httpx_post_with_retries(client, CHAT_URL, headers=self._headers(), json=body)
        if r.status_code >= 400:
            msg = f"OpenAI error {r.status_code}: {r.text[:500]}"
            raise OSError(msg)
        data = r.json()
        self._emit_usage_tokens(data.get("usage") if isinstance(data, dict) else None)
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            msg = f"Bad OpenAI response: {data!r}"
            raise OSError(msg) from e

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": self._chat_model,
            "messages": self._to_openai_messages(messages),
            "stream": True,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_output_tokens is not None:
            body["max_tokens"] = max_output_tokens

        async for chunk in self._openai_sse(body):
            yield chunk

    async def _openai_sse(self, body: dict[str, Any]) -> AsyncGenerator[str]:
        import httpx as hx

        headers = {**self._headers(), "accept": "text/event-stream"}
        async with hx.AsyncClient(timeout=self._timeout) as aclient:
            async with aclient.stream("POST", CHAT_URL, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    t = await resp.aread()
                    msg = f"OpenAI error {resp.status_code}: {t[:500]!r}"
                    raise OSError(msg)
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        ls = line.strip()
                        if not ls or ls.startswith(b":"):
                            continue
                        if ls.startswith(b"data: "):
                            pay = ls[6:]
                            if pay == b"[DONE]":
                                return
                            try:
                                ev = json.loads(pay)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(ev, dict):
                                continue
                            ch = ev.get("choices")
                            if isinstance(ch, list) and ch:
                                delta = ch[0].get("delta") if isinstance(ch[0], dict) else None
                                if isinstance(delta, dict) and "content" in delta:
                                    c = delta["content"]
                                    if c:
                                        yield str(c)

    def embed(self, text: str) -> list[float]:
        body = {"model": self._embed_model, "input": text}
        with httpx.Client(timeout=self._timeout) as client:
            r = httpx_post_with_retries(client, EMBED_URL, headers=self._headers(), json=body)
        if r.status_code >= 400:
            msg = f"OpenAI embed error {r.status_code}: {r.text[:500]}"
            raise OSError(msg)
        data = r.json()
        try:
            vec = data["data"][0]["embedding"]
            return [float(x) for x in vec]
        except (KeyError, IndexError, TypeError) as e:
            msg = f"Bad OpenAI embed: {data!r}"
            raise OSError(msg) from e

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}
