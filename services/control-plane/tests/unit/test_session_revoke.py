from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from control_plane.auth.session_revoke import revoke_sessions_for_user


@pytest.mark.asyncio
async def test_revoke_sessions_for_user_awaits_redis() -> None:
    with patch("control_plane.auth.session_revoke.revoke_all_for_user", new=AsyncMock(return_value=0)) as m:
        tid, uid = uuid.uuid4(), uuid.uuid4()
        await revoke_sessions_for_user(tid, uid)
    m.assert_awaited_once_with(tid, uid)
