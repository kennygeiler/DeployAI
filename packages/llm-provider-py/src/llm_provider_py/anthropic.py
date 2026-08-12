"""Concrete Anthropic Messages API provider (Epic 5, Story 5.1)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx

from llm_provider_py.secrets import resolve_anthropic_api_key, resolve_openai_api_key
from llm_provider_py.types import (
    CapabilityMatrix,
    ChatMessage,
    StopReason,
    StreamChunk,
    TextDelta,
    ThinkingDelta,
    ThinkingSignature,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseInputDelta,
    ToolUseStart,
)
from llm_provider_py.util import (
    DEFAULT_CAPS,
    UsageCallback,
    httpx_post_with_retries,
    httpx_post_with_retries_async,
    httpx_stream_open_with_retries,
    pseudo_embed,
    record_usage,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"

# Extended-thinking token budget for tool-use streaming. Unset / 0 /
# non-numeric → thinking disabled (the pre-existing behaviour).
THINKING_BUDGET_ENV = "DEPLOYAI_ANTHROPIC_THINKING_BUDGET"

# Claude 5-family models reject the `temperature` parameter
# (invalid_request_error: "`temperature` is deprecated for this model").
_NO_TEMPERATURE_PREFIXES = ("claude-sonnet-5", "claude-opus-5", "claude-fable-5")


def _model_supports_temperature(model: str) -> bool:
    return not model.startswith(_NO_TEMPERATURE_PREFIXES)


# Claude Sonnet 5 / Opus 5 run ADAPTIVE THINKING when the `thinking` param is
# omitted — a silent default change from the 4.x family, where omission meant
# no thinking. `max_tokens` caps thinking + response text together, so a
# request sized for its answer alone (e.g. the Cartographer extractor's 2000)
# can burn the whole allowance on thinking and return zero text with
# stop_reason=max_tokens. This provider's documented contract is
# thinking-off unless a budget is configured; send an explicit
# {"type": "disabled"} on models that think by default and accept it.
# (claude-fable-5 / claude-mythos-5 think always-on and REJECT "disabled" —
# they must not be listed here; callers wanting those models get adaptive.)
_THINKING_DEFAULT_ON_PREFIXES = ("claude-sonnet-5", "claude-opus-5")


def _model_thinks_by_default(model: str) -> bool:
    return model.startswith(_THINKING_DEFAULT_ON_PREFIXES)


def _thinking_budget_from_env() -> int:
    raw = os.environ.get(THINKING_BUDGET_ENV, "").strip()
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


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
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        thinking_budget_tokens: int | None = None,
    ) -> None:
        self._key = (api_key or resolve_anthropic_api_key()).strip()
        self._model = (model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()
        # Extended-thinking budget: explicit constructor value wins, else the
        # DEPLOYAI_ANTHROPIC_THINKING_BUDGET env var; <= 0 disables thinking.
        self._thinking_budget = (
            max(thinking_budget_tokens, 0) if thinking_budget_tokens is not None else _thinking_budget_from_env()
        )
        self._timeout = timeout_s
        self._tenant_id = tenant_id
        self._agent_name = agent_name
        self._on_usage = on_usage
        # Test seam: httpx.MockTransport implements both the sync and async
        # transport interfaces, so one argument covers both client kinds.
        self._transport = transport
        self._async_client: httpx.AsyncClient | None = None
        self.id = "anthropic"

    def _get_async_client(self) -> httpx.AsyncClient:
        """One shared AsyncClient per provider instance (lazy init).

        Sharing keeps the connection pool warm across calls; httpx clients
        are safe for concurrent use. Closed via :meth:`aclose`.
        """
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport if isinstance(self._transport, httpx.AsyncBaseTransport) else None,
            )
        return self._async_client

    async def aclose(self) -> None:
        """Close the shared AsyncClient. Safe to call multiple times."""
        if self._async_client is not None and not self._async_client.is_closed:
            await self._async_client.aclose()

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
            content = m.get("content", "")
            # Pass through native content-block lists (tool_use / tool_result) unchanged.
            out.append({"role": role, "content": content})
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

    def _build_complete_body(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> dict[str, Any]:
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
        if temperature is not None and _model_supports_temperature(self._model):
            body["temperature"] = temperature
        if _model_thinks_by_default(self._model):
            # chat_complete has no thinking support — pin the contract.
            body["thinking"] = {"type": "disabled"}
        return body

    def _parse_complete_response(self, r: httpx.Response) -> str:
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

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        body = self._build_complete_body(messages, temperature=temperature, max_output_tokens=max_output_tokens)
        sync_transport = self._transport if isinstance(self._transport, httpx.BaseTransport) else None
        with httpx.Client(timeout=self._timeout, transport=sync_transport) as client:
            r = httpx_post_with_retries(client, ANTHROPIC_URL, headers=self._headers(), json=body)
        return self._parse_complete_response(r)

    async def chat_complete_async(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Async twin of :meth:`chat_complete` — use inside async code.

        The sync method blocks the event loop for the full HTTP round trip
        (up to the provider timeout); this one awaits on the shared
        AsyncClient instead.
        """
        body = self._build_complete_body(messages, temperature=temperature, max_output_tokens=max_output_tokens)
        r = await httpx_post_with_retries_async(
            self._get_async_client(),
            ANTHROPIC_URL,
            headers=self._headers(),
            json=body,
        )
        return self._parse_complete_response(r)

    def _build_stream_body(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> dict[str, Any]:
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
        if temperature is not None and _model_supports_temperature(self._model):
            body["temperature"] = temperature
        if _model_thinks_by_default(self._model):
            # chat_complete_stream_with_tools overwrites this key when a
            # thinking budget is enabled; every other stream path keeps the
            # provider contract of thinking-off unless explicitly enabled.
            body["thinking"] = {"type": "disabled"}
        return body

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        body = self._build_stream_body(messages, temperature=temperature, max_output_tokens=max_output_tokens)
        async for chunk in self._iter_sse(body):
            yield chunk

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        body = self._build_stream_body(messages, temperature=temperature, max_output_tokens=max_output_tokens)
        tokens_used = 0
        async for ev in self._iter_sse_events(body):
            t = ev.get("type")
            if t == "content_block_delta" and isinstance(ev.get("delta"), dict):
                d = ev["delta"]
                if d.get("type") == "text_delta" and "text" in d:
                    yield StreamChunk(delta=str(d["text"]), done=False, tokens_used=0)
            elif t == "message_delta" and isinstance(ev.get("usage"), dict):
                u = ev["usage"]
                inp = int(u.get("input_tokens", 0) or 0)
                out = int(u.get("output_tokens", 0) or 0)
                tokens_used = inp + out
            elif t == "message_start" and isinstance(ev.get("message"), dict):
                u = ev["message"].get("usage")
                if isinstance(u, dict):
                    inp = int(u.get("input_tokens", 0) or 0)
                    out = int(u.get("output_tokens", 0) or 0)
                    tokens_used = max(tokens_used, inp + out)
        # Final chunk: tokens_used reflects what Anthropic actually reported via
        # message_delta.usage / message_start.usage. May be 0 if neither event
        # arrived (e.g. truncated stream); caller treats 0 as "unknown" and
        # falls back to its pre-call estimate for budget accounting.
        yield StreamChunk(delta="", done=True, tokens_used=tokens_used)

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
        tool_choice: dict[str, Any] | None = None,
        thinking_budget_tokens: int | None = None,
    ) -> AsyncIterator[ToolStreamChunk]:
        body = self._build_stream_body(messages, temperature=temperature, max_output_tokens=max_output_tokens)
        if tools:
            body["tools"] = tools
        if tool_choice is not None:
            # e.g. {"type": "none"} — tools stay declared (the API requires
            # them when history carries tool_use/tool_result blocks) but the
            # model is barred from requesting more calls.
            body["tool_choice"] = tool_choice
        budget = self._thinking_budget if thinking_budget_tokens is None else max(thinking_budget_tokens, 0)
        if budget > 0:
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            # API constraint: `max_tokens` must exceed `budget_tokens` —
            # thinking spends from the same output allowance, so grow the cap
            # to keep the caller's visible-output room intact.
            if int(body["max_tokens"]) <= budget:
                body["max_tokens"] = budget + (max_output_tokens or 1024)
            # API constraint: thinking is incompatible with a pinned
            # temperature (only the default is accepted). Claude 5 models
            # already omit it; drop it for older models too when thinking on.
            body.pop("temperature", None)
        # block index → (id, name, partial-json buffer)
        active: dict[int, dict[str, Any]] = {}
        # block index → accumulated signature for open thinking blocks. The
        # signature arrives via one or more `signature_delta` events and is
        # surfaced as a ThinkingSignature chunk when the block closes, so
        # callers can replay the thinking block on follow-up requests.
        thinking_sigs: dict[int, str] = {}
        stop_reason: str | None = None
        usage_input = 0
        usage_output = 0
        async for ev in self._iter_sse_events(body):
            t = ev.get("type")
            if t == "content_block_start":
                idx = ev.get("index")
                block = ev.get("content_block") or {}
                if isinstance(idx, int) and isinstance(block, dict) and block.get("type") == "tool_use":
                    active[idx] = {
                        "id": str(block.get("id", "")),
                        "name": str(block.get("name", "")),
                        "buf": "",
                    }
                    yield ToolUseStart(id=str(block.get("id", "")), name=str(block.get("name", "")))
                elif isinstance(idx, int) and isinstance(block, dict) and block.get("type") == "thinking":
                    thinking_sigs[idx] = ""
            elif t == "content_block_delta" and isinstance(ev.get("delta"), dict):
                d = ev["delta"]
                idx = ev.get("index")
                if d.get("type") == "text_delta" and "text" in d:
                    yield TextDelta(content=str(d["text"]))
                elif d.get("type") == "thinking_delta" and "thinking" in d:
                    if isinstance(idx, int):
                        # Register the block even without a content_block_start
                        # so its signature + stop are still tracked.
                        thinking_sigs.setdefault(idx, "")
                    yield ThinkingDelta(content=str(d["thinking"]))
                elif d.get("type") == "signature_delta" and isinstance(idx, int):
                    thinking_sigs[idx] = thinking_sigs.get(idx, "") + str(d.get("signature", ""))
                elif d.get("type") == "input_json_delta" and isinstance(idx, int) and idx in active:
                    partial = str(d.get("partial_json", ""))
                    active[idx]["buf"] += partial
                    yield ToolUseInputDelta(id=str(active[idx]["id"]), partial_json=partial)
            elif t == "content_block_stop":
                idx = ev.get("index")
                if isinstance(idx, int) and idx in thinking_sigs:
                    yield ThinkingSignature(signature=thinking_sigs.pop(idx))
                elif isinstance(idx, int) and idx in active:
                    entry = active.pop(idx)
                    try:
                        parsed = json.loads(entry["buf"]) if entry["buf"] else {}
                    except json.JSONDecodeError:
                        parsed = {}
                    if not isinstance(parsed, dict):
                        parsed = {}
                    yield ToolUseEnd(id=str(entry["id"]), name=str(entry["name"]), input=parsed)
            elif t == "message_delta":
                d = ev.get("delta")
                if isinstance(d, dict) and isinstance(d.get("stop_reason"), str):
                    stop_reason = str(d["stop_reason"])
                u = ev.get("usage")
                if isinstance(u, dict):
                    usage_output = int(u.get("output_tokens", usage_output) or usage_output)
                    usage_input = int(u.get("input_tokens", usage_input) or usage_input)
            elif t == "message_start" and isinstance(ev.get("message"), dict):
                u = ev["message"].get("usage")
                if isinstance(u, dict):
                    usage_input = max(usage_input, int(u.get("input_tokens", 0) or 0))
                    usage_output = max(usage_output, int(u.get("output_tokens", 0) or 0))
        yield StopReason(
            reason=stop_reason or "end_turn",
            usage={"input_tokens": usage_input, "output_tokens": usage_output},
        )

    async def _iter_sse_events(self, body: dict[str, Any]) -> AsyncGenerator[dict[str, Any]]:
        # Retries cover the initial connection only. Once events start
        # flowing they are yielded to the caller (and may trigger side
        # effects there), so a mid-stream failure surfaces as an error —
        # see httpx_stream_open_with_retries for the full rationale.
        resp = await httpx_stream_open_with_retries(
            self._get_async_client(),
            ANTHROPIC_URL,
            headers=self._headers(),
            json=body,
        )
        try:
            if resp.status_code >= 400:
                err_body = await resp.aread()
                msg = f"Anthropic error {resp.status_code}: {err_body[:500]!r}"
                raise OSError(msg)
            buf = b""

            def _parse_line(line: bytes) -> dict[str, Any] | None | str:
                if not line.strip() or not line.startswith(b"data: "):
                    return None
                payload = line[6:].strip()
                if payload == b"[DONE]":
                    return "DONE"
                try:
                    parsed = json.loads(payload.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None

            async for chunk in resp.aiter_bytes():
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    ev = _parse_line(line)
                    if ev is None:
                        continue
                    if ev == "DONE":
                        return
                    assert isinstance(ev, dict)
                    yield ev
                    # Emit usage telemetry only AFTER caller consumed the event
                    # so an early break doesn't inflate counters with an event
                    # the caller never saw.
                    if ev.get("type") == "message_delta" and isinstance(ev.get("usage"), dict):
                        self._emit_usage(ev["usage"])
            # Flush any final line that arrived without a trailing newline
            # before the stream closed.
            if buf.strip():
                ev = _parse_line(buf)
                if ev not in (None, "DONE"):
                    assert isinstance(ev, dict)
                    yield ev
                    if ev.get("type") == "message_delta" and isinstance(ev.get("usage"), dict):
                        self._emit_usage(ev["usage"])
        finally:
            await resp.aclose()

    async def _iter_sse(self, body: dict[str, Any]) -> AsyncGenerator[str]:
        # Same transport rules as _iter_sse_events: retry the initial
        # connection only, never after bytes were yielded downstream.
        resp = await httpx_stream_open_with_retries(
            self._get_async_client(),
            ANTHROPIC_URL,
            headers=self._headers(),
            json=body,
        )
        try:
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
        finally:
            await resp.aclose()

    def embed(self, text: str) -> list[float]:
        """Pseudo-embed, or OpenAI if ``OPENAI_API_KEY`` is set (optional hybrid)."""
        oa_key = resolve_openai_api_key()
        if oa_key:
            from llm_provider_py.openai import OpenAIProvider

            oa = OpenAIProvider(api_key=oa_key, tenant_id=self._tenant_id)
            return oa.embed(text)
        return pseudo_embed(text, dim=256)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}
