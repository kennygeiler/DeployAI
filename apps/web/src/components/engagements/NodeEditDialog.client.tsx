"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { MatrixNode } from "@/lib/bff/matrix-types";

export type NodeEditDialogProps = {
  engagementId: string;
  node: Pick<MatrixNode, "id" | "title" | "node_type" | "attributes"> | null;
  open: boolean;
  onClose: () => void;
  onSaved: (next: MatrixNode) => void;
};

function safeStringifyAttrs(attrs: Record<string, unknown>): string {
  try {
    return JSON.stringify(attrs, null, 2);
  } catch {
    return "{}";
  }
}

export function NodeEditDialog({
  engagementId,
  node,
  open,
  onClose,
  onSaved,
}: NodeEditDialogProps): React.ReactElement {
  const [title, setTitle] = React.useState(node?.title ?? "");
  const [nodeType, setNodeType] = React.useState(node?.node_type ?? "");
  const [attrsText, setAttrsText] = React.useState(() =>
    safeStringifyAttrs(node?.attributes ?? {}),
  );
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  // Reset edit-state when the dialog opens with a different node — derived
  // from props via the standard "key" pattern so React doesn't flag a
  // setState-in-effect anti-pattern.
  const sessionKey = open && node ? node.id : null;
  const [lastSessionKey, setLastSessionKey] = React.useState<string | null>(null);
  if (sessionKey !== lastSessionKey) {
    setLastSessionKey(sessionKey);
    if (sessionKey !== null && node) {
      setTitle(node.title);
      setNodeType(node.node_type);
      setAttrsText(safeStringifyAttrs(node.attributes ?? {}));
      setErr(null);
    }
  }

  const handleSave = async () => {
    if (!node) return;
    setErr(null);
    let parsedAttrs: Record<string, unknown> = {};
    try {
      const raw: unknown = JSON.parse(attrsText || "{}");
      if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
        throw new Error("attributes must be a JSON object");
      }
      parsedAttrs = raw as Record<string, unknown>;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "invalid JSON in attributes");
      return;
    }
    const trimmedTitle = title.trim();
    const trimmedType = nodeType.trim();
    if (!trimmedTitle || !trimmedType) {
      setErr("title and node_type are required");
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}` +
          `/matrix/nodes/${encodeURIComponent(node.id)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: trimmedTitle,
            node_type: trimmedType,
            attributes: parsedAttrs,
          }),
          cache: "no-store",
        },
      );
      if (!r.ok) {
        setErr(await readStrategistBffErrorDescription(r));
        return;
      }
      const body = (await r.json()) as { node?: MatrixNode };
      if (body.node) {
        onSaved(body.node);
        onClose();
      } else {
        setErr("server returned no node");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent
        className="sm:max-w-lg"
        aria-label="Edit matrix node"
        data-testid="node-edit-dialog"
      >
        <DialogHeader>
          <DialogTitle>Edit node</DialogTitle>
          <DialogDescription>
            Save emits a `matrix_node_updated` event on the engagement timeline.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="node-edit-title">Title</Label>
            <Input
              id="node-edit-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="node-edit-type">Node type</Label>
            <Input
              id="node-edit-type"
              value={nodeType}
              onChange={(e) => setNodeType(e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="node-edit-attrs">Attributes (JSON)</Label>
            <Textarea
              id="node-edit-attrs"
              value={attrsText}
              onChange={(e) => setAttrsText(e.target.value)}
              disabled={busy}
              rows={8}
              className="font-mono text-xs"
              spellCheck={false}
            />
          </div>
          {err ? (
            <p role="alert" className="text-error-700 text-sm">
              {err}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={busy || !node}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
