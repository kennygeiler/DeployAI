from __future__ import annotations

import httpx

# FreeTSA time-stamp protocol endpoint (public internet — CI uses stub via dependency injection).
_FREETSA = "https://freetsa.org/tsr"

async def try_freetsa(digest: bytes) -> bytes | None:
    """Request an RFC 3161 TSR. Returns None on any failure (caller implements AWS / stub fallback)."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(_FREETSA, content=digest, headers={"Content-Type": "application/timestamp-query"})
    except (httpx.HTTPError, OSError):
        return None
    if r.status_code >= 400:
        return None
    return r.content


def request_tsr_stub(digest: bytes) -> bytes:
    """Offline stub TSR bytes for tests + air-gapped environments."""
    return b"DEPLOYAI-TSA-STUB\x00" + digest
