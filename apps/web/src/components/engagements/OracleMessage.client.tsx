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
            ? "bg-primary text-primary-foreground max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-line"
            : "bg-ink-100 text-ink-900 max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-line"
        }
      >
        <span id={labelId} className="sr-only">
          {isUser ? "You said" : "Agent Kenny replied"}
        </span>
        {role === "user" || parts === null ? (
          <span>
            {content}
            {pending ? <span className="text-ink-500 italic"> …</span> : null}
          </span>
        ) : (
          <span>
            {parts.map((p, i) =>
              p.kind === "text" ? (
                <React.Fragment key={i}>{p.text}</React.Fragment>
              ) : (
                <Link
                  key={i}
                  href={citeHref(engagementId, p.type, p.id)}
                  className="text-evidence-800 underline underline-offset-2 hover:no-underline"
                  data-testid={`oracle-cite-${p.type}`}
                  data-cite-id={p.id}
                >
                  {p.type}:{p.id.slice(0, 8)}
                </Link>
              ),
            )}
          </span>
        )}
      </div>
    </li>
  );
}
