from __future__ import annotations

import pytest

from deployai_tsa.batcher import TsaBatcher, hash_payload
from deployai_tsa.client import request_tsr_stub


@pytest.mark.asyncio
async def test_batcher_signs_at_least_100_digests() -> None:
    signed: list[bytes] = []

    async def sign_batch(digests: list[bytes]) -> None:
        for d in digests:
            signed.append(request_tsr_stub(d))

    b = TsaBatcher(sign_digests=sign_batch, interval_sec=0.01)
    for i in range(100):
        await b.submit(hash_payload(f"evt:{i}".encode()))
    await b.flush_now()
    b.stop()
    assert len(signed) >= 100
    assert all(x.startswith(b"DEPLOYAI-TSA-STUB\x00") for x in signed)
