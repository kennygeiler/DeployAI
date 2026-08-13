"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

type IntakeAddressView = {
  local_part: string;
  email: string | null;
  created_at: string;
  can_regenerate: boolean;
};

function isIntakeAddress(v: unknown): v is IntakeAddressView {
  return (
    typeof v === "object" &&
    v !== null &&
    typeof (v as { local_part?: unknown }).local_part === "string" &&
    typeof (v as { can_regenerate?: unknown }).can_regenerate === "boolean"
  );
}

/**
 * Wave 5 IN2 — the "Or CC the deal address" block on the Capture tab.
 *
 * Shows the engagement's inbound-email intake address in a copyable
 * monospace pill. Regenerate (revokes the old address) renders only when
 * the BFF says the actor may (`can_regenerate` — customer_admin /
 * platform_admin) and asks for confirmation, since mail to the old address
 * silently drops afterwards. When the address can't be loaded (older CP,
 * misconfigured env) the block renders nothing — the paste flow above is
 * the primary path and must not inherit an error banner from this extra.
 */
export function IntakeAddressBlock({ engagementId }: { engagementId: string }) {
  const [address, setAddress] = React.useState<IntakeAddressView | null>(null);
  const [regenerating, setRegenerating] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/intake-address`,
        );
        if (!r.ok) {
          return;
        }
        const body: unknown = await r.json();
        if (!cancelled && isIntakeAddress(body)) {
          setAddress(body);
        }
      } catch {
        // Silent: see docstring — this block is an optional extra.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId]);

  if (!address) {
    return null;
  }
  const display = address.email ?? address.local_part;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(display);
      toast.success("Deal address copied");
    } catch {
      toast.error("Could not copy — select the address text instead");
    }
  };

  const regenerate = async () => {
    if (
      !window.confirm(
        "Regenerate the deal address? Email sent to the current address will stop landing here.",
      )
    ) {
      return;
    }
    setRegenerating(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/intake-address/regenerate`,
        { method: "POST", headers: { "content-type": "application/json" }, body: "{}" },
      );
      if (!r.ok) {
        toast.error("Could not regenerate the deal address");
        return;
      }
      const body: unknown = await r.json();
      if (isIntakeAddress(body)) {
        setAddress(body);
        toast.success("Deal address regenerated", {
          description: "The old address is revoked — update anyone who had it.",
        });
      }
    } catch {
      toast.error("Could not regenerate the deal address");
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div
      className="rounded-card bg-surface flex flex-wrap items-center gap-2 p-3 shadow-card"
      data-testid="intake-address-block"
    >
      <span className="text-ink-600 text-xs font-medium">Or CC the deal address</span>
      <code className="rounded-control bg-field max-w-full overflow-x-auto px-2 py-1 font-mono text-xs whitespace-nowrap shadow-inset-field">
        {display}
      </code>
      <Button type="button" size="sm" variant="outline" onClick={() => void copy()}>
        Copy
      </Button>
      {address.can_regenerate ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={regenerating}
          onClick={() => void regenerate()}
        >
          Regenerate
        </Button>
      ) : null}
      <p className="text-ink-600 basis-full text-xs">
        CC or forward deal email here — it lands in this engagement for review.
      </p>
    </div>
  );
}
