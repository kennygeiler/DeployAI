"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  BuiltinNodeType,
  CustomNodeType,
  NodeTypesResponse,
} from "@/lib/internal/node-types-cp";

export function NodeTypesForm() {
  const [builtin, setBuiltin] = React.useState<BuiltinNodeType[]>([]);
  const [custom, setCustom] = React.useState<CustomNodeType[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  const [name, setName] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [color, setColor] = React.useState("#fde68a");
  const [description, setDescription] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await fetch("/api/bff/tenant/node-types", { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load node types (${r.status})`);
      return;
    }
    setErr(null);
    const body = (await r.json()) as NodeTypesResponse;
    setBuiltin(body.builtin);
    setCustom(body.custom);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load node types.");
        }
      }
      if (!cancelled) {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const onCreate = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCreating(true);
      try {
        const r = await fetch("/api/bff/tenant/node-types", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            label: label.trim(),
            color: color || null,
            description: description.trim() || null,
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not create node type", { description: text.slice(0, 240) });
          return;
        }
        setName("");
        setLabel("");
        setDescription("");
        await load();
        toast.success("Node type created");
      } finally {
        setCreating(false);
      }
    },
    [name, label, color, description, load],
  );

  const onDelete = React.useCallback(
    async (id: string, slug: string) => {
      const r = await fetch(`/api/bff/tenant/node-types/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (r.status === 409) {
        toast.error("Cannot delete node type", {
          description: `"${slug}" is in use by existing matrix nodes — delete or retype those first.`,
        });
        return;
      }
      if (!r.ok && r.status !== 204) {
        toast.error("Could not delete node type");
        return;
      }
      await load();
      toast.success("Node type deleted");
    },
    [load],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <section aria-labelledby="node-types-heading" className="max-w-3xl space-y-6">
      <div>
        <h2 id="node-types-heading" className="text-base font-semibold">
          Matrix node types
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Built-in types ship with DeployAI and cannot be edited. Add custom slugs to extend the map
          for your team — they appear in the graph, in matrix CRUD, and in the extraction
          agent&apos;s prompt.
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Built-in types</h3>
        <ul className="border-border divide-border divide-y rounded-md border text-sm">
          {builtin.map((b) => (
            <li key={b.name} className="flex items-center justify-between px-3 py-2">
              <div>
                <span className="font-medium">{b.label}</span>
                <span className="text-ink-600 ml-2 font-mono text-xs">{b.name}</span>
              </div>
              <span className="text-ink-600 text-xs">built-in</span>
            </li>
          ))}
        </ul>
      </div>

      <form onSubmit={onCreate} className="border-border space-y-4 rounded-md border p-4">
        <h3 className="text-sm font-semibold">Add custom type</h3>
        <div className="space-y-2">
          <Label htmlFor="nt-name">Slug</Label>
          <Input
            id="nt-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="patient_journey"
            autoComplete="off"
            required
          />
          <p className="text-ink-600 text-xs">
            Lowercase letters, digits, underscores. Must start with a letter. Immutable once
            created.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="nt-label">Label</Label>
          <Input
            id="nt-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Patient journey"
            autoComplete="off"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="nt-color">Color</Label>
          <input
            id="nt-color"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className="border-border h-9 w-16 cursor-pointer rounded border"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="nt-desc">Description (extraction-agent hint)</Label>
          <Input
            id="nt-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A patient's path through a clinical pathway."
            autoComplete="off"
          />
        </div>
        <Button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create node type"}
        </Button>
      </form>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Custom types</h3>
        {custom.length === 0 ? (
          <p className="text-ink-600 text-sm">No custom node types yet.</p>
        ) : (
          <ul className="space-y-2">
            {custom.map((c) => (
              <NodeTypeRow
                key={c.id}
                row={c}
                onDelete={() => onDelete(c.id, c.name)}
                onChanged={load}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function NodeTypeRow({
  row,
  onDelete,
  onChanged,
}: {
  row: CustomNodeType;
  onDelete: () => void | Promise<void>;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [label, setLabel] = React.useState(row.label);
  const [color, setColor] = React.useState(row.color ?? "#fde68a");
  const [description, setDescription] = React.useState(row.description ?? "");
  const [saving, setSaving] = React.useState(false);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const r = await fetch(`/api/bff/tenant/node-types/${encodeURIComponent(row.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: label.trim(),
          color: color || null,
          description: description.trim() || null,
        }),
      });
      if (!r.ok) {
        toast.error("Could not update node type");
        return;
      }
      setEditing(false);
      await onChanged();
      toast.success("Node type updated");
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="border-border rounded-md border p-3">
      {editing ? (
        <form onSubmit={onSave} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor={`nt-label-${row.id}`}>Label</Label>
            <Input
              id={`nt-label-${row.id}`}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`nt-color-${row.id}`}>Color</Label>
            <input
              id={`nt-color-${row.id}`}
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="border-border h-9 w-16 cursor-pointer rounded border"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`nt-desc-${row.id}`}>Description</Label>
            <Input
              id={`nt-desc-${row.id}`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(false);
                setLabel(row.label);
                setColor(row.color ?? "#fde68a");
                setDescription(row.description ?? "");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">
              {row.label}
              <span className="text-ink-600 ml-2 font-mono text-xs">{row.name}</span>
            </p>
            {row.color ? (
              <p className="text-ink-600 mt-1 flex items-center gap-2 text-xs">
                <span
                  className="border-border inline-block h-4 w-4 rounded border"
                  style={{ background: row.color }}
                />
                <span className="font-mono">{row.color}</span>
              </p>
            ) : null}
            {row.description ? (
              <p className="text-ink-600 mt-1 text-xs">{row.description}</p>
            ) : null}
          </div>
          <div className="flex flex-shrink-0 gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void onDelete()}>
              Delete
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
