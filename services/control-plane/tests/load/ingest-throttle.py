#!/usr/bin/env python3
"""Story 3-7: smoke load for Graph 429 handling + token bucket (dev; not full 2500/hour)."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from control_plane.integrations.graph_client import GraphTokenBucket


async def _main() -> None:
    n = int(os.environ.get("INGEST_LOAD_REQUESTS", "200"))
    rps = float(os.environ.get("GRAPH_RPS", "1000"))
    b = GraphTokenBucket(rate_per_sec=rps)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    for _ in range(n):
        await b.acquire()
    dt = loop.time() - t0
    print(f"ingest-throttle: {n} token acquisitions at cap {rps}/s in {dt:.2f}s (ok)")


if __name__ == "__main__":
    asyncio.run(_main())
