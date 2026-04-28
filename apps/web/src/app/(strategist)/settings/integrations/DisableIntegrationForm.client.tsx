"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

type Props = { integrationId: string; provider: string };

export function DisableIntegrationForm({ integrationId, provider }: Props) {
  const [busy, setBusy] = React.useState(false);

  const onDisconnect = async () => {
    if (!window.confirm(`Disconnect ${provider}? Ingestion for this connector will stop.`)) {
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`/api/bff/integrations/${integrationId}/disable`, { method: "POST" });
      if (r.ok) {
        window.location.reload();
        return;
      }
      window.alert(`Could not disconnect (${r.status}).`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onDisconnect}>
      {busy ? "Disconnecting…" : "Disconnect"}
    </Button>
  );
}
