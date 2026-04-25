"use client";

import * as React from "react";
import { CitationChip, EvidencePanel } from "@deployai/shared-ui";
import { toast } from "sonner";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  parseAdjudicationCitation,
  type ParsedAdjudicationCitation,
} from "./parseAdjudicationCitation";

export type AdjudicationRow = {
  id: string;
  tenant: string;
  queryId: string;
  status: string;
  createdAt: string;
  /** Rule/judge flags and notes */
  raw: Record<string, unknown>;
};

function CitationBlock({ rowId, data }: { rowId: string; data: ParsedAdjudicationCitation }) {
  const [expanded, setExpanded] = React.useState(false);
  const onToggle = React.useCallback(() => {
    setExpanded((v) => !v);
  }, []);
  const {
    preview,
    bodyText,
    evidenceSpan,
    state,
    retrievalPhase,
    panelMetadata,
    visualState,
    chipLabel,
  } = data;
  const rootId = `citation-${rowId}`;

  const onCopyLink = React.useCallback(() => {
    const url = `${window.location.origin}${window.location.pathname}#${rootId}`;
    void navigator.clipboard.writeText(url).then(
      () => {
        toast("Link copied", { description: "Adjudication row anchor with citation" });
      },
      () => {
        toast.error("Could not copy link");
      },
    );
  }, [rootId]);

  return (
    <div id={rootId} className="flex min-w-0 flex-col gap-3 py-1">
      <div className="min-w-0">
        <CitationChip
          id={`${rootId}-chip`}
          label={chipLabel}
          expanded={expanded}
          onToggleExpand={onToggle}
          visualState={visualState}
          variant="inline"
          preview={preview}
          onViewEvidence={onToggle}
          onOverride={() => toast("Override flow is not wired in this build")}
          onCopyLink={onCopyLink}
          onCiteInOverride={() => toast("Cite in override is not wired in this build")}
        />
      </div>
      {expanded ? (
        <EvidencePanel
          id={`${rootId}-panel`}
          variant="compact"
          retrievalPhase={retrievalPhase}
          metadata={panelMetadata}
          state={state}
          bodyText={bodyText}
          evidenceSpan={evidenceSpan}
          visible
          degradedHint={data.degradedHint}
          tombstoneMessage={data.tombstoneMessage}
        />
      ) : null}
    </div>
  );
}

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
            <TableHead>Memory</TableHead>
            <TableHead>Tenant</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const parsed = parseAdjudicationCitation(row.raw);
            return (
              <React.Fragment key={row.id}>
                <TableRow>
                  <TableCell className="font-mono text-sm max-w-[14rem] break-all align-top">
                    {row.queryId}
                  </TableCell>
                  <TableCell className="align-top min-w-0 max-w-sm">
                    {parsed ? <CitationBlock rowId={row.id} data={parsed} /> : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-sm align-top">{row.tenant}</TableCell>
                  <TableCell className="align-top">{row.status}</TableCell>
                  <TableCell className="text-ink-600 align-top">{row.createdAt}</TableCell>
                </TableRow>
              </React.Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
