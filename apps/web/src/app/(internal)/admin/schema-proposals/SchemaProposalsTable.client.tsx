"use client";

import { useCallback, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import type { V1Role } from "@deployai/authz";

export type ProposalRow = {
  id: string;
  status: string;
  proposed_ddl: string;
  proposer_agent: string | null;
  proposed_field_path: string | null;
  proposed_type: string | null;
  created_at: string;
};

type Forward = { role: V1Role; tenantId: string } | null;

type Props = {
  forwardActor: Forward;
  initialRows: ProposalRow[];
};

function forwardHeaders(a: Forward): Record<string, string> {
  if (!a) {
    return {};
  }
  return { "x-deployai-role": a.role, "x-deployai-tenant": a.tenantId };
}

export function SchemaProposalsTable({ forwardActor, initialRows }: Props) {
  const [rows, setRows] = useState<ProposalRow[]>(initialRows);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<ProposalRow | null>(null);
  const [open, setOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const tenant = forwardActor?.tenantId;

  const load = useCallback(async () => {
    if (!tenant) {
      setError("Set header x-deployai-tenant to a tenant UUID to load proposals.");
      return;
    }
    setLoading(true);
    setError(null);
    const h = forwardHeaders(forwardActor);
    const r = await fetch(
      `/api/internal/schema-proposals?tenant=${encodeURIComponent(tenant)}&status=pending`,
      { headers: { ...h }, cache: "no-store" },
    );
    if (!r.ok) {
      setError((await r.text()) || r.statusText);
      setRows([]);
    } else {
      setRows((await r.json()) as ProposalRow[]);
    }
    setLoading(false);
  }, [tenant, forwardActor]);

  async function promote(id: string) {
    if (!tenant) {
      return;
    }
    const rev = globalThis.crypto.randomUUID();
    const h = forwardHeaders(forwardActor);
    const r = await fetch(
      `/api/internal/schema-proposals/${id}/promote?tenant=${encodeURIComponent(tenant)}`,
      {
        method: "POST",
        headers: { ...h, "x-deployai-reviewer-actor-id": rev },
        cache: "no-store",
      },
    );
    if (!r.ok) {
      setError(await r.text());
      return;
    }
    await load();
  }

  async function reject(id: string) {
    if (!tenant) {
      return;
    }
    const rev = globalThis.crypto.randomUUID();
    const h = forwardHeaders(forwardActor);
    const r = await fetch(
      `/api/internal/schema-proposals/${id}/reject?tenant=${encodeURIComponent(tenant)}`,
      {
        method: "POST",
        headers: { ...h, "x-deployai-reviewer-actor-id": rev, "content-type": "application/json" },
        body: JSON.stringify({ rejection_reason: rejectReason }),
        cache: "no-store",
      },
    );
    if (!r.ok) {
      setError(await r.text());
      return;
    }
    setRejectReason("");
    await load();
  }

  if (loading) {
    return <p className="text-body text-ink-600">Loading…</p>;
  }
  if (error) {
    return <p className="text-body text-rose-800">{error}</p>;
  }

  return (
    <>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="text-body border-ink-200 bg-white text-ink-950"
            onClick={() => void load()}
          >
            Refresh
          </Button>
          <p className="text-body text-ink-600">Pending proposals — tenant: {tenant ?? "—"}</p>
        </div>
        <div className="flex max-w-md flex-col gap-1">
          <label className="text-body text-ink-800" htmlFor="reject-reason">
            Rejection reason (optional, next Reject click)
          </label>
          <input
            id="reject-reason"
            className="text-body rounded-md border border-ink-200 bg-white px-2 py-1 text-ink-950"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
          />
        </div>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Field / agent</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.id} className="align-top">
              <TableCell>
                <div className="text-body text-ink-950">
                  {p.proposed_field_path ?? "—"}{" "}
                  <span className="text-ink-500">({p.proposer_agent ?? "?"})</span>
                </div>
                <Button
                  type="button"
                  variant="link"
                  className="text-body mt-1 h-auto min-h-0 p-0 text-left text-ink-700"
                  onClick={() => {
                    setDetail(p);
                    setOpen(true);
                  }}
                >
                  view DDL
                </Button>
              </TableCell>
              <TableCell>{p.status}</TableCell>
              <TableCell className="text-body whitespace-nowrap">{p.created_at}</TableCell>
              <TableCell className="text-right">
                <div className="flex flex-col items-end gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="text-body border-ink-200 bg-white"
                    onClick={() => void promote(p.id)}
                  >
                    Promote
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="text-body border-ink-200 bg-white"
                    onClick={() => void reject(p.id)}
                  >
                    Reject
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Proposal {detail?.id}</SheetTitle>
            <SheetDescription>Raw proposed DDL and metadata (Story 1-17).</SheetDescription>
          </SheetHeader>
          {detail ? (
            <pre className="mt-4 overflow-x-auto text-xs break-words whitespace-pre-wrap">
              {detail.proposed_ddl}
            </pre>
          ) : null}
        </SheetContent>
      </Sheet>
    </>
  );
}
