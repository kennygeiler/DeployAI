"use client";

import Link from "next/link";
import * as React from "react";

const UUID_RE = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const CITE_RE = new RegExp(`\\[(event|node):(${UUID_RE})\\]`, "g");

type Part =
  | { kind: "text"; text: string }
  | { kind: "cite"; type: "event" | "node"; id: string; raw: string };

function parseParts(content: string): Part[] {
  const parts: Part[] = [];
  let lastIndex = 0;
  for (const m of content.matchAll(CITE_RE)) {
    const start = m.index ?? 0;
    if (start > lastIndex) {
      parts.push({ kind: "text", text: content.slice(lastIndex, start) });
    }
    parts.push({
      kind: "cite",
      type: m[1] as "event" | "node",
      id: m[2]!,
      raw: m[0],
    });
    lastIndex = start + m[0].length;
  }
  if (lastIndex < content.length) {
    parts.push({ kind: "text", text: content.slice(lastIndex) });
  }
  return parts;
}

function citeHref(engagementId: string, type: "event" | "node", id: string): string {
  const eng = encodeURIComponent(engagementId);
  if (type === "event") {
    return `/engagements/${eng}/timeline?event=${encodeURIComponent(id)}`;
  }
  return `/engagements/${eng}?node=${encodeURIComponent(id)}`;
}

export type OracleMessageProps = {
  engagementId: string;
  role: "user" | "oracle";
  content: string;
  pending?: boolean;
};

/**
 * Single conversation turn. Oracle replies contain `[event:UUID]` or
 * `[node:UUID]` citation markers that this renderer converts into links
 * back to the ledger timeline / matrix-node detail surfaces.
 */
export function OracleMessage({ engagementId, role, content, pending }: OracleMessageProps) {
  const parts = React.useMemo(
    () => (role === "oracle" ? parseParts(content) : null),
    [role, content],
  );

  const isUser = role === "user";
  const labelId = React.useId();

  // Citation markers render as compact numbered source chips (Beautiful UI
  // component 03); the full `type:id` labels move to a sources row below.
  const cites = React.useMemo(
    () => (parts === null ? [] : parts.filter((p) => p.kind === "cite")),
    [parts],
  );
  const citeIndex = (raw: string): number => cites.findIndex((c) => c.raw === raw) + 1;

  return (
    <li
      className={isUser ? "flex justify-end" : "flex justify-start"}
      data-testid="oracle-message"
      data-role={role}
    >
      <div
        aria-labelledby={labelId}
        className={
          isUser
            ? "max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3 py-2 text-sm whitespace-pre-line text-primary-foreground"
            : "max-w-full text-sm leading-relaxed whitespace-pre-line text-ink"
        }
      >
        <span id={labelId} className="sr-only">
          {isUser ? "You said" : "Agent Kenny replied"}
        </span>
        {role === "user" || parts === null ? (
          <span>
            {content}
            {pending ? <span className="italic text-ink-500"> …</span> : null}
          </span>
        ) : (
          <>
            <span>
              {parts.map((p, i) =>
                p.kind === "text" ? (
                  <React.Fragment key={i}>{p.text}</React.Fragment>
                ) : (
                  <Link
                    key={i}
                    href={citeHref(engagementId, p.type, p.id)}
                    aria-label={`Source ${citeIndex(p.raw)}: ${p.type} ${p.id}`}
                    title={`${p.type}:${p.id}`}
                    className="mx-0.5 inline-flex h-4 min-w-4 translate-y-[-1px] items-center justify-center rounded-full bg-hover-2 px-1 align-middle font-mono text-[10px] leading-none font-semibold text-ink-600 no-underline shadow-hairline transition-colors hover:bg-accent-tint hover:text-accent-ink"
                    data-testid={`oracle-cite-${p.type}`}
                    data-cite-id={p.id}
                  >
                    {citeIndex(p.raw)}
                  </Link>
                ),
              )}
            </span>
            {cites.length > 0 ? (
              <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-600">
                <span className="font-medium text-ink">
                  {cites.length} source{cites.length === 1 ? "" : "s"}
                </span>
                {cites.map((c, i) => (
                  <span key={`${c.raw}-${i}`} className="font-mono">
                    {i + 1} · {c.type}:{c.id.slice(0, 8)}
                  </span>
                ))}
              </span>
            ) : null}
          </>
        )}
      </div>
    </li>
  );
}
