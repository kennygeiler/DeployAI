"""Concrete Anthropic Messages API provider (Epic 5, Story 5.1)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx

from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, UsageCallback, httpx_post_with_retries, pseudo_embed, record_usage

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 120.0,
        tenant_id: str = "system",
        agent_name: str = "agent",
        on_usage: UsageCallback | None = None,
    ) -> None:
        self._key = (api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        self._model = (model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()
        self._timeout = timeout_s
        self._tenant_id = tenant_id
        self._agent_name = agent_name
        self._on_usage = on_usage
        self.id = "anthropic"

    def _headers(self) -> dict[str, str]:
        if not self._key:
            msg = "ANTHROPIC_API_KEY is not set"
            raise OSError(msg)
        return {
            "x-api-key": self._key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _to_anthropic_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            if role not in ("user", "assistant"):
                continue
            out.append({"role": role, "content": m.get("content", "")})
        if not out:
            out = [{"role": "user", "content": ""}]
        return out

    def _emit_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        record_usage(
            self._on_usage,
            {
                "provider": "anthropic",
                "model": self._model,
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
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        system = "\n\n".join(system_parts) if system_parts else None
        user_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_output_tokens or 1024,
            "messages": self._to_anthropic_messages(user_msgs if user_msgs else messages),
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature

        with httpx.Client(timeout=self._timeout) as client:
            r = httpx_post_with_retries(client, ANTHROPIC_URL, headers=self._headers(), json=body)
        if r.status_code >= 400:
            msg = f"Anthropic error {r.status_code}: {r.text[:500]}"
            raise OSError(msg)
        data = r.json()
        self._emit_usage(data.get("usage") if isinstance(data, dict) else None)
        blocks = data.get("content") if isinstance(data, dict) else None
        if not isinstance(blocks, list):
            msg = f"Bad Anthropic response: {data!r}"
            raise OSError(msg)
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                return str(b.get("text", ""))
        msg = f"No text in Anthropic response: {data!r}"
        raise OSError(msg)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        system = "\n\n".join(system_parts) if system_parts else None
        user_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_output_tokens or 1024,
            "stream": True,
            "messages": self._to_anthropic_messages(user_msgs if user_msgs else messages),
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature
        async for chunk in self._iter_sse(body):
            yield chunk

    async def _iter_sse(self, body: dict[str, Any]) -> AsyncGenerator[str]:
        import httpx as hx

        async with hx.AsyncClient(timeout=self._timeout) as aclient:
            async with aclient.stream("POST", ANTHROPIC_URL, headers=self._headers(), json=body) as resp:
                if resp.status_code >= 400:
                    err_body = await resp.aread()
                    msg = f"Anthropic error {resp.status_code}: {err_body[:500]!r}"
                    raise OSError(msg)
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip() or not line.startswith(b"data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == b"[DONE]":
                            break
                        try:
                            ev = json.loads(payload.decode("utf-8", errors="replace"))
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(ev, dict):
                            continue
                        t = ev.get("type")
                        if t == "message_delta" and isinstance(ev.get("usage"), dict):
                            self._emit_usage(ev["usage"])
                        if t == "content_block_delta" and isinstance(ev.get("delta"), dict):
                            d = ev["delta"]
                            if d.get("type") == "text_delta" and "text" in d:
                                yield str(d["text"])

    def embed(self, text: str) -> list[float]:
        """Pseudo-embed, or OpenAI if ``OPENAI_API_KEY`` is set (optional hybrid)."""
        if os.environ.get("OPENAI_API_KEY", "").strip():
            from llm_provider_py.openai import OpenAIProvider

            oa = OpenAIProvider(
                api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                tenant_id=self._tenant_id,
            )
            return oa.embed(text)
        return pseudo_embed(text, dim=256)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}
