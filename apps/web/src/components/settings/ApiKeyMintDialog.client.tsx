"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiKeyMintResponse } from "@/lib/internal/api-keys-cp";

export type EngagementOption = {
  id: string;
  name: string;
};

export type ApiKeyMintDialogProps = {
  open: boolean;
  engagements: EngagementOption[];
  onOpenChange: (open: boolean) => void;
  onMinted: (result: ApiKeyMintResponse) => void;
};

export function ApiKeyMintDialog({
  open,
  engagements,
  onOpenChange,
  onMinted,
}: ApiKeyMintDialogProps) {
  const [name, setName] = React.useState("");
  const [engagementId, setEngagementId] = React.useState<string>(engagements[0]?.id ?? "");
  const [submitting, setSubmitting] = React.useState(false);
  const [minted, setMinted] = React.useState<ApiKeyMintResponse | null>(null);
  const [copied, setCopied] = React.useState(false);

  const handleOpenChange = React.useCallback(
    (next: boolean) => {
      if (next) {
        setName("");
        setEngagementId(engagements[0]?.id ?? "");
        setMinted(null);
        setCopied(false);
      }
      onOpenChange(next);
    },
    [engagements, onOpenChange],
  );

  const onSubmit = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!name.trim() || !engagementId) return;
      setSubmitting(true);
      try {
        const r = await fetch("/api/bff/tenant/api-keys", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.trim(), engagement_id: engagementId }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not mint api key", { description: text.slice(0, 240) });
          return;
        }
        const body = (await r.json()) as ApiKeyMintResponse;
        setMinted(body);
        onMinted(body);
      } catch (err) {
        toast.error("Could not mint api key", {
          description: err instanceof Error ? err.message : "network error",
        });
      } finally {
        setSubmitting(false);
      }
    },
    [name, engagementId, onMinted],
  );

  const onCopy = React.useCallback(async () => {
    if (!minted) return;
    try {
      await navigator.clipboard.writeText(minted.raw_key);
      setCopied(true);
      toast.success("API key copied to clipboard");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }, [minted]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        {minted ? (
          <>
            <DialogHeader>
              <DialogTitle>API key minted</DialogTitle>
              <DialogDescription>
                Copy this key now. You will NOT be able to view it again — DeployAI only stores its
                hash.
              </DialogDescription>
            </DialogHeader>
            <div className="border-accent bg-accent/10 space-y-2 rounded-md border p-3">
              <code
                data-testid="raw-key-display"
                className="bg-bg-subtle block break-all rounded px-2 py-1 font-mono text-xs"
              >
                {minted.raw_key}
              </code>
              <Button type="button" size="sm" onClick={() => void onCopy()}>
                {copied ? "Copied" : "Copy to clipboard"}
              </Button>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Done</Button>
              </DialogClose>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Mint MCP api key</DialogTitle>
              <DialogDescription>
                Bind one bearer token to one engagement, read-only.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="api-key-name">Name</Label>
              <Input
                id="api-key-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Bob's Claude desktop"
                autoComplete="off"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-key-engagement">Engagement</Label>
              <select
                id="api-key-engagement"
                className="border-border bg-background ring-offset-background focus:ring-2 focus:ring-ring h-9 w-full rounded-md border px-3 text-sm"
                value={engagementId}
                onChange={(e) => setEngagementId(e.target.value)}
                required
              >
                {engagements.length === 0 ? (
                  <option value="" disabled>
                    No engagements available
                  </option>
                ) : (
                  engagements.map((eng) => (
                    <option key={eng.id} value={eng.id}>
                      {eng.name}
                    </option>
                  ))
                )}
              </select>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={submitting || !name.trim() || !engagementId}>
                {submitting ? "Minting…" : "Mint"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
