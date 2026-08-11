"use client";

/**
 * Bootstrap access-token form. Until a real OIDC issuer is registered, hosted
 * deployments authenticate with short-lived CP-minted session JWTs
 * (scripts/cloud-token.sh). This form sets the cookie the middleware already
 * verifies — replacing the paste-in-devtools instruction, nothing more. It
 * renders only when NEXT_PUBLIC_BOOTSTRAP_TOKEN_LOGIN=1.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";

const COOKIE_NAME = "deployai_access_token";

export function TokenForm({ next }: { next: string }) {
  const [token, setToken] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = token.trim();
    if (!value) {
      setErr("Paste the access token from scripts/cloud-token.sh.");
      return;
    }
    const secure = window.location.protocol === "https:" ? "; secure" : "";
    document.cookie = `${COOKIE_NAME}=${value}; path=/; samesite=lax${secure}`;
    window.location.assign(next.startsWith("/") ? next : "/engagements");
  };

  return (
    <form onSubmit={submit} style={{ marginTop: "1.5rem", textAlign: "left" }}>
      <label htmlFor="bootstrap-token" style={{ display: "block", fontWeight: 500 }}>
        Access token
      </label>
      <p style={{ margin: "0.25rem 0 0.5rem", fontSize: "0.85rem", opacity: 0.75 }}>
        Operator bootstrap: mint one with <code>scripts/cloud-token.sh</code> (expires in 15
        minutes).
      </p>
      <textarea
        id="bootstrap-token"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        rows={3}
        style={{
          width: "100%",
          borderRadius: "0.5rem",
          border: "1px solid currentColor",
          padding: "0.5rem",
          fontFamily: "monospace",
          fontSize: "0.8rem",
        }}
      />
      {err ? (
        <p role="alert" style={{ color: "#dc2626", fontSize: "0.85rem" }}>
          {err}
        </p>
      ) : null}
      <Button type="submit" variant="outline" className="mt-3">
        Continue with token
      </Button>
    </form>
  );
}
