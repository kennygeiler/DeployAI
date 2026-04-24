"""System tenant for OIDC logins that are not yet bound to a customer tenant (Story 2-2)."""

from __future__ import annotations

import uuid

# Kept in lockstep with migration 20260429_0007 (uuid5 namespace URL in migration comment).
SSO_PENDING_TENANT_ID: uuid.UUID = uuid.UUID("aa67db01-9627-57b8-86dc-8f01ab387fbf")
