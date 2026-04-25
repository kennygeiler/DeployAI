from __future__ import annotations

import httpx

from llm_provider_py.util import httpx_post_with_retries


def test_retries_on_429_then_ok() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, text="rate")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        r = httpx_post_with_retries(client, "https://example.com/x", headers={}, json={})
    assert r.status_code == 200
    assert calls["n"] == 2
