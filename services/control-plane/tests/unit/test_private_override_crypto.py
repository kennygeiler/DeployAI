"""Epic 10.5 — private annotation sealing round-trip."""

from __future__ import annotations

import uuid

from control_plane.services.private_override_crypto import (
    foia_private_scope_disclosure_tag,
    open_private_annotation_ciphertext,
    seal_private_annotation_plaintext,
)


def test_seal_and_open_round_trip() -> None:
    tid = uuid.uuid4()
    nonce, ct, wrapped = seal_private_annotation_plaintext(tenant_id=tid, plaintext="Successor must not read this.")
    out = open_private_annotation_ciphertext(tenant_id=tid, nonce=nonce, ciphertext=ct, wrapped_dek=wrapped)
    assert out == "Successor must not read this."


def test_foia_tag_shape() -> None:
    aid = uuid.uuid4()
    tag = foia_private_scope_disclosure_tag(annotation_id=aid)
    assert tag["scope"] == "private_override_annotation"
    assert tag["annotation_id"] == str(aid)
