"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  BuiltinMemberRole,
  CustomMemberRole,
  MemberRolesRead,
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
    const body = (await r.json()) as MemberRolesRead;
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
            ...(description.trim() ? { description: description.trim() } : {}),
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not create role", { description: text.slice(0, 240) });
          return;
        }
        setName("");
        setLabel("");
        setDescription("");
        await load();
        toast.success("Role created");
      } finally {
        setCreating(false);
      }
    },
    [name, label, description, load],
  );

  const onDelete = React.useCallback(
    async (id: string) => {
      const r = await fetch(`/api/bff/tenant/member-roles/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!r.ok && r.status !== 204) {
        const text = await r.text();
        toast.error("Could not delete role", { description: text.slice(0, 240) });
        return;
      }
      await load();
      toast.success("Role deleted");
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
          Engagement member roles
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Built-in roles always work. Add custom roles your team uses (<code>clinical_lead</code>,{" "}
          <code>sales_engineer</code>); they become assignable when adding members to an engagement.
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Built-in</h3>
        <ul className="border-border divide-border divide-y rounded-md border text-sm">
          {builtin.map((b) => (
            <li key={b.name} className="flex items-center justify-between px-3 py-2">
              <span>
                <span className="font-medium">{b.label}</span>{" "}
                <code className="text-ink-600 text-xs">{b.name}</code>
              </span>
              <span className="text-ink-600 text-xs">Read-only</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Custom</h3>
        {custom.length === 0 ? (
          <p className="text-ink-600 text-sm">No custom roles yet.</p>
        ) : (
          <ul className="space-y-2">
            {custom.map((c) => (
              <CustomRoleRow key={c.id} role={c} onDelete={() => onDelete(c.id)} onChanged={load} />
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={onCreate} className="border-border space-y-3 rounded-md border p-4">
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
            Lowercase letters, digits, underscores. Must start with a letter. Immutable once set.
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
          <Label htmlFor="mr-description">Description</Label>
          <Input
            id="mr-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
            autoComplete="off"
          />
        </div>
        <Button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create role"}
        </Button>
      </form>
    </section>
  );
}

function CustomRoleRow({
  role,
  onDelete,
  onChanged,
}: {
  role: CustomMemberRole;
  onDelete: () => void | Promise<void>;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [label, setLabel] = React.useState(role.label);
  const [description, setDescription] = React.useState(role.description ?? "");
  const [saving, setSaving] = React.useState(false);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const r = await fetch(`/api/bff/tenant/member-roles/${encodeURIComponent(role.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: label.trim(),
          description: description.trim() ? description.trim() : null,
        }),
      });
      if (!r.ok) {
        toast.error("Could not update role");
        return;
      }
      setEditing(false);
      await onChanged();
      toast.success("Role updated");
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="border-border rounded-md border p-3 text-sm">
      {editing ? (
        <form onSubmit={onSave} className="space-y-2">
          <div className="space-y-1">
            <Label htmlFor={`role-label-${role.id}`}>Label</Label>
            <Input
              id={`role-label-${role.id}`}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`role-desc-${role.id}`}>Description</Label>
            <Input
              id={`role-desc-${role.id}`}
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
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setLabel(role.label);
                setDescription(role.description ?? "");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-medium">
              {role.label} <code className="text-ink-600 text-xs">{role.name}</code>
            </p>
            {role.description ? <p className="text-ink-600 text-xs">{role.description}</p> : null}
          </div>
          <div className="flex gap-2">
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
