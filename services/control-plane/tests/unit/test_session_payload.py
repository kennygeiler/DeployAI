"""Session record parsing (Story 2-4 code review)."""

from __future__ import annotations

import json
import uuid

import pytest

from control_plane.auth.session_service import InvalidRefreshError, _parse_session_blob


def test_parse_session_blob_ok() -> None:
    tid, uid, roles = str(uuid.uuid4()), str(uuid.uuid4()), ["platform_admin"]
    raw = json.dumps({"tenant_id": tid, "user_id": uid, "roles": roles})
    out_tid, out_uid, out_roles = _parse_session_blob(raw)
    assert str(out_tid) == tid
    assert str(out_uid) == uid
    assert out_roles == roles


def test_parse_session_blob_rejects_malformed_json() -> None:
    with pytest.raises(InvalidRefreshError, match="corrupt"):
        _parse_session_blob("not-json")


def test_parse_session_blob_rejects_dict_without_uuids() -> None:
    with pytest.raises(InvalidRefreshError, match="invalid session record fields"):
        _parse_session_blob(json.dumps({"tenant_id": "x", "user_id": "y"}))
