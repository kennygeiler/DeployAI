"""Unit tests for OIDC PKCE + authorize URL (Story 2-2, no network)."""

from __future__ import annotations

from control_plane.auth.oidc_flow import build_authorization_url, pkce_pair


def test_pkce_generates_s256() -> None:
    v, c = pkce_pair()
    assert len(v) >= 43
    assert c and c != v


def test_build_authorization_url_includes_params() -> None:
    md: dict = {
        "authorization_endpoint": "https://idp.example.com/oauth2/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "issuer": "https://idp.example.com",
        "jwks_uri": "https://idp.example.com/jwks",
    }
    u = build_authorization_url(
        metadata=md,
        client_id="c1",
        redirect_uri="https://app/cb",
        state="s1",
        code_challenge="ch",
        nonce="n1",
    )
    assert u.startswith("https://idp.example.com/oauth2/authorize?")
    assert "code_challenge=ch" in u
    assert "code_challenge_method=S256" in u
    assert "state=s1" in u
    assert "nonce=n1" in u
    assert "openid" in u
