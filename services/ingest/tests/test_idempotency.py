"""Story 3-6: idempotency key helper (FR18)."""

from __future__ import annotations

import pytest

from ingest.idempotency import canonical_ingestion_dedup_key


def test_dedup_key_format() -> None:
    k = canonical_ingestion_dedup_key(provider="m365", source_id="thread:abc", version="1")
    assert k == "m365:thread:abc:1"


def test_dedup_key_requires_ids() -> None:
    with pytest.raises(ValueError, match="required"):
        canonical_ingestion_dedup_key(provider="", source_id="x", version="1")
    with pytest.raises(ValueError, match="required"):
        canonical_ingestion_dedup_key(provider="g", source_id="", version="1")
