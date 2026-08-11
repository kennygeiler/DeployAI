"""Provider-side OAuth token revocation for the integration kill switch.

Called by :mod:`control_plane.services.integration_kill_switch` when an
integration is disabled. Each helper returns a :class:`RevocationResult`
rather than raising, so the kill switch can keep going (delete stored
tokens, purge queues, disable the row) even when a provider call fails —
a dead provider must never block the kill switch.

Provider notes
--------------
Google
    ``POST https://oauth2.googleapis.com/revoke`` with the refresh token.
    Revoking the refresh token also invalidates access tokens minted from
    it. A 400 ``invalid_token`` response means the token was already
    revoked or expired — treated as success-with-note.

Microsoft (Entra ID / identity platform)
    There is **no** token-revocation endpoint for refresh tokens issued
    to confidential clients. The correct kill-switch action is to delete
    our stored tokens (the secrets-deletion phase does this) so we can
    never use them again. Full provider-side invalidation is an operator
    action: with admin consent, ``POST /users/{id}/invalidateAllRefreshTokens``
    (or ``revokeSignInSessions``) on Microsoft Graph. The helper records
    that posture instead of pretending to revoke.

Slack
    ``POST https://slack.com/api/auth.revoke`` with the stored bot token
    as a Bearer credential. Slack answers HTTP 200 with ``{"ok": false,
    "error": ...}`` on failure; ``invalid_auth`` / ``token_revoked`` /
    ``account_inactive`` mean the token is already dead — treated as
    success-with-note.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SLACK_REVOKE_URL = "https://slack.com/api/auth.revoke"

MICROSOFT_NO_REVOCATION_NOTE = (
    "Microsoft identity platform has no revocation endpoint for confidential-client "
    "refresh tokens; stored tokens deleted locally. Operator action for full "
    "invalidation: Graph invalidateAllRefreshTokens (requires admin consent)."
)

# Slack error codes that mean the token is already unusable — revoking an
# already-dead token is the outcome the kill switch wanted anyway.
_SLACK_ALREADY_DEAD_ERRORS: frozenset[str] = frozenset(
    {"invalid_auth", "token_revoked", "account_inactive", "token_expired", "not_authed"}
)

RevocationOutcome = Literal["revoked", "already_revoked", "unsupported", "skipped", "failed"]

#: Outcomes the kill switch counts as "the token is no longer a live threat".
SUCCESS_OUTCOMES: frozenset[str] = frozenset({"revoked", "already_revoked", "unsupported", "skipped"})


@dataclass(frozen=True)
class RevocationResult:
    """Outcome of one provider revocation attempt.

    ``outcome`` semantics:
      - ``revoked``: provider confirmed the revocation.
      - ``already_revoked``: provider reports the token was already invalid.
      - ``unsupported``: provider offers no revocation endpoint (Microsoft);
        local token deletion is the effective action.
      - ``skipped``: nothing stored to revoke.
      - ``failed``: provider errored; stored tokens must still be deleted.
    """

    outcome: RevocationOutcome
    note: str
    http_status: int | None = None

    @property
    def ok(self) -> bool:
        return self.outcome in SUCCESS_OUTCOMES


async def revoke_google_token(client: httpx.AsyncClient, *, token: str) -> RevocationResult:
    """Revoke a Google OAuth token (refresh preferred; access works too)."""
    if not token:
        return RevocationResult(outcome="skipped", note="no stored Google token to revoke")
    try:
        r = await client.post(
            GOOGLE_REVOKE_URL,
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return RevocationResult(outcome="failed", note=f"Google revoke transport error: {exc!r}")
    if r.status_code == 200:
        return RevocationResult(outcome="revoked", note="Google confirmed revocation", http_status=200)
    if 400 <= r.status_code < 500:
        # Google answers 400 invalid_token for already-revoked / expired
        # tokens. Any 4xx means the credential is not usable as presented;
        # the token cannot be a live threat, so count it as done-with-note.
        return RevocationResult(
            outcome="already_revoked",
            note=f"Google returned {r.status_code} (token already invalid or expired)",
            http_status=r.status_code,
        )
    return RevocationResult(
        outcome="failed",
        note=f"Google revoke failed: HTTP {r.status_code}",
        http_status=r.status_code,
    )


async def revoke_slack_token(client: httpx.AsyncClient, *, token: str) -> RevocationResult:
    """Revoke a Slack bot token via ``auth.revoke``."""
    if not token:
        return RevocationResult(outcome="skipped", note="no stored Slack token to revoke")
    try:
        r = await client.post(
            SLACK_REVOKE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return RevocationResult(outcome="failed", note=f"Slack revoke transport error: {exc!r}")
    if 400 <= r.status_code < 500:
        return RevocationResult(
            outcome="already_revoked",
            note=f"Slack returned {r.status_code} (token already invalid)",
            http_status=r.status_code,
        )
    if r.status_code != 200:
        return RevocationResult(
            outcome="failed",
            note=f"Slack revoke failed: HTTP {r.status_code}",
            http_status=r.status_code,
        )
    try:
        body = r.json()
    except ValueError:
        return RevocationResult(outcome="failed", note="Slack revoke returned non-JSON body", http_status=200)
    if body.get("ok") is True:
        return RevocationResult(outcome="revoked", note="Slack confirmed revocation", http_status=200)
    err = str(body.get("error") or "unknown_error")
    if err in _SLACK_ALREADY_DEAD_ERRORS:
        return RevocationResult(
            outcome="already_revoked",
            note=f"Slack reports token already unusable ({err})",
            http_status=200,
        )
    return RevocationResult(outcome="failed", note=f"Slack revoke failed: {err}", http_status=200)


def microsoft_revocation_posture(*, has_tokens: bool) -> RevocationResult:
    """Record the Microsoft no-endpoint posture (no network call possible)."""
    if not has_tokens:
        return RevocationResult(outcome="skipped", note="no stored Microsoft tokens")
    return RevocationResult(outcome="unsupported", note=MICROSOFT_NO_REVOCATION_NOTE)


async def revoke_provider_tokens(
    client: httpx.AsyncClient,
    *,
    provider: str,
    oauth_config: dict[str, object],
) -> RevocationResult:
    """Dispatch to the right provider revocation for one integration row.

    ``oauth_config`` is the ``integrations.config["oauth"]`` dict (may be
    empty). Unknown providers are ``skipped`` — there is nothing stored
    that this codebase knows how to revoke.
    """

    def _str(key: str) -> str:
        v = oauth_config.get(key)
        return v if isinstance(v, str) else ""

    if provider == "google_gmail":
        # Prefer the refresh token: revoking it kills the whole grant.
        token = _str("refresh_token") or _str("access_token")
        return await revoke_google_token(client, token=token)
    if provider == "slack":
        return await revoke_slack_token(client, token=_str("access_token"))
    if provider.startswith("m365_"):
        has = bool(_str("refresh_token") or _str("access_token"))
        return microsoft_revocation_posture(has_tokens=has)
    return RevocationResult(outcome="skipped", note=f"provider {provider!r} stores no revocable OAuth tokens")


__all__ = [
    "GOOGLE_REVOKE_URL",
    "MICROSOFT_NO_REVOCATION_NOTE",
    "SLACK_REVOKE_URL",
    "SUCCESS_OUTCOMES",
    "RevocationOutcome",
    "RevocationResult",
    "microsoft_revocation_posture",
    "revoke_google_token",
    "revoke_provider_tokens",
    "revoke_slack_token",
]
