"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type AdjudicationRow = {
  id: string;
  tenant: string;
  queryId: string;
  status: string;
  createdAt: string;
  /** Rule/judge flags and notes */
  raw: Record<string, unknown>;
};

export function AdjudicationTable({ rows }: { rows: AdjudicationRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="border border-dashed border-ink-200 rounded-lg p-6 text-body text-ink-500">
        No items in the adjudication queue.
      </div>
    );
  }
  return (
    <div className="border border-ink-200 rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Query</TableHead>
            <TableHead>Tenant</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="font-mono text-sm">{row.queryId}</TableCell>
              <TableCell className="font-mono text-sm">{row.tenant}</TableCell>
              <TableCell>{row.status}</TableCell>
              <TableCell className="text-ink-600">{row.createdAt}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
