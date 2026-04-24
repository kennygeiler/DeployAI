
import httpx
import pytest

from control_plane.integrations.graph_client import GraphTokenBucket, graph_request


@pytest.mark.asyncio
async def test_graph_request_retries_429_before_success() -> None:
    n = {"c": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["c"] += 1
        if n["c"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://g.test") as c:
        r = await graph_request(
            c,
            "GET",
            "/m",
            bucket=GraphTokenBucket(rate_per_sec=1_000_000.0),
            reauthorize=None,
        )
    assert r.status_code == 200
    assert n["c"] == 3
