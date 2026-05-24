"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  BuiltinMemberRole,
  CustomMemberRole,
  MemberRolesResponse,
} from "@/lib/internal/member-roles-cp";

export function MemberRolesForm() {
  const [builtin, setBuiltin] = React.useState<BuiltinMemberRole[]>([]);
  const [custom, setCustom] = React.useState<CustomMemberRole[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  const [name, setName] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await fetch("/api/bff/tenant/member-roles", { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load member roles (${r.status})`);
      return;
    }
    setErr(null);
    const body = (await r.json()) as MemberRolesResponse;
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
          setErr(e instanceof Error ? e.message : "Could not load member roles.");
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
        const r = await fetch("/api/bff/tenant/member-roles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            label: label.trim(),
            description: description.trim() || null,
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not create member role", { description: text.slice(0, 240) });
          return;
        }
        setName("");
        setLabel("");
        setDescription("");
        await load();
        toast.success("Member role created");
      } finally {
        setCreating(false);
      }
    },
    [name, label, description, load],
  );

  const onDelete = React.useCallback(
    async (id: string, slug: string) => {
      const r = await fetch(`/api/bff/tenant/member-roles/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (r.status === 409) {
        toast.error("Cannot delete member role", {
          description: `"${slug}" is in use by existing engagement members — reassign those first.`,
        });
        return;
      }
      if (!r.ok) {
        toast.error("Could not delete member role");
        return;
      }
      await load();
      toast.success("Member role deleted");
    },
    [load],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <section aria-labelledby="member-roles-heading" className="max-w-3xl space-y-6">
      <div>
        <h2 id="member-roles-heading" className="text-base font-semibold">
          Engagement-member roles
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Built-in roles ship with DeployAI and cannot be edited. Add custom slugs to extend the
          team model — they appear in the member-add picker and the matrix role lens.
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Built-in roles</h3>
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
        <h3 className="text-sm font-semibold">Add custom role</h3>
        <div className="space-y-2">
          <Label htmlFor="mr-name">Slug</Label>
          <Input
            id="mr-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="clinical_lead"
            autoComplete="off"
            required
          />
          <p className="text-ink-600 text-xs">
            Lowercase letters, digits, underscores. Must start with a letter. Immutable once
            created.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="mr-label">Label</Label>
          <Input
            id="mr-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Clinical lead"
            autoComplete="off"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="mr-desc">Description</Label>
          <Input
            id="mr-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Owns clinical safety sign-off for healthcare deployments."
            autoComplete="off"
          />
        </div>
        <Button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create member role"}
        </Button>
      </form>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Custom roles</h3>
        {custom.length === 0 ? (
          <p className="text-ink-600 text-sm">No custom member roles yet.</p>
        ) : (
          <ul className="space-y-2">
            {custom.map((c) => (
              <MemberRoleRow
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

function MemberRoleRow({
  row,
  onDelete,
  onChanged,
}: {
  row: CustomMemberRole;
  onDelete: () => void | Promise<void>;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [label, setLabel] = React.useState(row.label);
  const [description, setDescription] = React.useState(row.description ?? "");
  const [saving, setSaving] = React.useState(false);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const r = await fetch(`/api/bff/tenant/member-roles/${encodeURIComponent(row.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: label.trim(),
          description: description.trim() || null,
        }),
      });
      if (!r.ok) {
        toast.error("Could not update member role");
        return;
      }
      setEditing(false);
      await onChanged();
      toast.success("Member role updated");
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="border-border rounded-md border p-3">
      {editing ? (
        <form onSubmit={onSave} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor={`mr-label-${row.id}`}>Label</Label>
            <Input
              id={`mr-label-${row.id}`}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`mr-desc-${row.id}`}>Description</Label>
            <Input
              id={`mr-desc-${row.id}`}
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
