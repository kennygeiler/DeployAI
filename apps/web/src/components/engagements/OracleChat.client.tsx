"use client";

import * as React from "react";
import { toast } from "sonner";

import { CheckIcon, TriangleAlertIcon } from "lucide-react";

import { OracleMessage } from "@/components/engagements/OracleMessage.client";
import { Button } from "@/components/ui/button";
import { PixelLoader, ShimmerLines } from "@/components/ui/shimmer";
import { Textarea } from "@/components/ui/textarea";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

type Turn = {
  id: string;
  role: "user" | "oracle";
  content: string;
  created_at: string;
};

type HistoryResponse = {
  conversation_id: string | null;
  turns: Turn[];
};

type ChatResponse = {
  turn_id: string;
  conversation_id: string;
  content: string;
  tokens_used: number;
};

const PANEL_TITLE_ID = "oracle-chat-title";
const ORACLE_ROLE = "oracle" as const;

function isV2Enabled(): boolean {
  const raw = (process.env.NEXT_PUBLIC_AGENT_KENNY_V2_ENABLED ?? "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
}

type V2Reasoning =
  | { kind: "thinking"; content: string }
  | { kind: "tool_call"; name: string }
  | { kind: "tool_result"; name: string; row_count: number; truncated: boolean; error?: string };

type V2CitationBadge = {
  kind: string;
  id: string;
  outcome: "verified" | "unverified" | "external" | "cross_engagement_leak" | "not_found";
};

type V2InlineNote =
  | { kind: "cross_engagement_leak"; citationKind: string; id: string }
  | { kind: "adversarial_concern"; concern: string; severity: "info" | "warning" | "blocking" };

/**
 * Right-side collapsible Agent Kenny chat panel. Single-turn POST against
 * the BFF (G1.a CP route returns JSON; SSE upgrade is a follow-up). Loads
 * conversation history on first open + after each send.
 */
export function OracleChat({ engagementId }: { engagementId: string }) {
  const [open, setOpen] = React.useState(false);
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [input, setInput] = React.useState("");
  const [loadingHistory, setLoadingHistory] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [streamingContent, setStreamingContent] = React.useState<string | null>(null);
  const [reasoning, setReasoning] = React.useState<V2Reasoning[]>([]);
  const [citationBadges, setCitationBadges] = React.useState<V2CitationBadge[]>([]);
  const [inlineNotes, setInlineNotes] = React.useState<V2InlineNote[]>([]);
  const [err, setErr] = React.useState<string | null>(null);
  const loadedRef = React.useRef(false);
  // Presentational only — powers the "Thought for Ns" trace header
  // (Beautiful UI component 02). No effect on transport or fallback logic.
  const [traceOpen, setTraceOpen] = React.useState(false);
  const [thoughtSeconds, setThoughtSeconds] = React.useState<number | null>(null);
  const thinkStartRef = React.useRef<number | null>(null);

  const loadHistory = React.useCallback(async () => {
    setLoadingHistory(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/oracle/history`,
        { cache: "no-store" },
      );
      if (!r.ok) {
        setErr(await readStrategistBffErrorDescription(r));
        return;
      }
      setErr(null);
      const body = (await r.json()) as HistoryResponse;
      setTurns(Array.isArray(body.turns) ? body.turns : []);
      setConversationId(body.conversation_id ?? null);
    } finally {
      setLoadingHistory(false);
    }
  }, [engagementId]);

  React.useEffect(() => {
    if (!open || loadedRef.current) return;
    loadedRef.current = true;
    void (async () => {
      try {
        await loadHistory();
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not load conversation.");
      }
    })();
  }, [open, loadHistory]);

  const sendJsonFallback = React.useCallback(
    async (message: string, optimisticId: string): Promise<boolean> => {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/oracle/chat`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ conversation_id: conversationId, message }),
        },
      );
      if (r.status === 429) {
        const j = (await r.json().catch(() => ({}))) as { userMessage?: string };
        toast.error(
          j.userMessage && typeof j.userMessage === "string" && j.userMessage.trim()
            ? j.userMessage
            : "Daily LLM budget reached. Try again tomorrow.",
        );
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        setInput(message);
        return false;
      }
      if (!r.ok) {
        const desc = await readStrategistBffErrorDescription(r);
        toast.error("Agent Kenny could not reply", { description: desc.slice(0, 240) });
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        setInput(message);
        return false;
      }
      const body = (await r.json()) as ChatResponse;
      setConversationId(body.conversation_id);
      setTurns((prev) =>
        prev
          .filter((t) => t.id !== optimisticId)
          .concat([
            {
              id: `user-${body.turn_id}`,
              role: "user",
              content: message,
              created_at: new Date().toISOString(),
            },
            {
              id: body.turn_id,
              role: "oracle",
              content: body.content,
              created_at: new Date().toISOString(),
            },
          ]),
      );
      setErr(null);
      return true;
    },
    [conversationId, engagementId],
  );

  const consumeStream = React.useCallback(
    async (
      r: Response,
      message: string,
      optimisticId: string,
    ): Promise<{
      ok: boolean;
      turn?: { turn_id: string; conversation_id: string };
      acc?: string;
    }> => {
      if (!r.body) return { ok: false };
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";
      let done: { turn_id: string; conversation_id: string } | null = null;
      let streamError: string | null = null;
      for (;;) {
        const { value, done: rdrDone } = await reader.read();
        if (value) buffer += decoder.decode(value, { stream: true });
        let split = buffer.indexOf("\n\n");
        while (split !== -1) {
          const block = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          let eventName = "";
          let dataText = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event: ")) {
              eventName = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              dataText = line.slice(6).trim();
            }
          }
          if (!dataText) {
            split = buffer.indexOf("\n\n");
            continue;
          }
          try {
            const frame = JSON.parse(dataText) as Record<string, unknown>;
            if (eventName) {
              // v2 typed frames.
              if (eventName === "delta" && typeof frame.content === "string") {
                acc += frame.content;
                setStreamingContent(acc);
              } else if (eventName === "thinking" && typeof frame.content === "string") {
                setReasoning((prev) => [
                  ...prev,
                  { kind: "thinking", content: frame.content as string },
                ]);
              } else if (eventName === "tool_call" && typeof frame.name === "string") {
                setReasoning((prev) => [
                  ...prev,
                  { kind: "tool_call", name: frame.name as string },
                ]);
              } else if (eventName === "tool_result" && typeof frame.name === "string") {
                setReasoning((prev) => [
                  ...prev,
                  {
                    kind: "tool_result",
                    name: frame.name as string,
                    row_count: Number(frame.row_count ?? 0),
                    truncated: Boolean(frame.truncated),
                    error: typeof frame.error === "string" ? frame.error : undefined,
                  },
                ]);
              } else if (eventName === "citation_verified" && typeof frame.id === "string") {
                setCitationBadges((prev) => [
                  ...prev,
                  { kind: String(frame.kind ?? ""), id: frame.id as string, outcome: "verified" },
                ]);
              } else if (eventName === "citation_unverified" && typeof frame.id === "string") {
                const outcome = (
                  typeof frame.outcome === "string" ? frame.outcome : "unverified"
                ) as "unverified" | "external" | "cross_engagement_leak" | "not_found";
                setCitationBadges((prev) => [
                  ...prev,
                  { kind: String(frame.kind ?? ""), id: frame.id as string, outcome },
                ]);
              } else if (eventName === "cross_engagement_leak" && typeof frame.id === "string") {
                setCitationBadges((prev) => [
                  ...prev,
                  {
                    kind: String(frame.kind ?? ""),
                    id: frame.id as string,
                    outcome: "cross_engagement_leak",
                  },
                ]);
                setInlineNotes((prev) => [
                  ...prev,
                  {
                    kind: "cross_engagement_leak",
                    citationKind: String(frame.kind ?? ""),
                    id: frame.id as string,
                  },
                ]);
              } else if (
                eventName === "adversarial_concern" &&
                typeof frame.concern_text === "string"
              ) {
                const sev = (
                  frame.severity === "blocking" || frame.severity === "warning"
                    ? frame.severity
                    : "info"
                ) as "info" | "warning" | "blocking";
                setInlineNotes((prev) => [
                  ...prev,
                  {
                    kind: "adversarial_concern",
                    concern: frame.concern_text as string,
                    severity: sev,
                  },
                ]);
              } else if (eventName === "done") {
                if (typeof frame.final_text === "string" && frame.final_text) {
                  acc = frame.final_text;
                }
                if (
                  typeof frame.turn_id === "string" &&
                  typeof frame.conversation_id === "string"
                ) {
                  done = { turn_id: frame.turn_id, conversation_id: frame.conversation_id };
                }
              } else if (eventName === "error" && typeof frame.error === "string") {
                streamError = frame.error;
              }
            } else {
              // v1 unkeyed frames: { delta, done } or { done: true, turn_id, ... }
              const f = frame as
                | { delta?: string; done?: false }
                | { done: true; turn_id?: string; conversation_id?: string; error?: string };
              if (
                "done" in f &&
                f.done === false &&
                typeof (f as { delta?: string }).delta === "string"
              ) {
                acc += (f as { delta: string }).delta;
                setStreamingContent(acc);
              } else if ("error" in f && typeof f.error === "string") {
                streamError = f.error;
              } else if ("turn_id" in f && f.turn_id && f.conversation_id) {
                done = { turn_id: f.turn_id, conversation_id: f.conversation_id };
              }
            }
          } catch {
            // ignore malformed frame
          }
          split = buffer.indexOf("\n\n");
        }
        if (rdrDone) break;
      }

      if (streamError || !done) {
        setStreamingContent(null);
        await sendJsonFallback(message, optimisticId);
        return { ok: false };
      }
      return { ok: true, turn: done, acc };
    },
    [sendJsonFallback],
  );

  const send = React.useCallback(async () => {
    const message = input.trim();
    if (!message || sending) return;
    setSending(true);
    setReasoning([]);
    setCitationBadges([]);
    setInlineNotes([]);
    thinkStartRef.current = Date.now();
    setThoughtSeconds(null);
    setTraceOpen(true);
    const optimisticId = `pending-${Date.now()}`;
    setTurns((prev) => [
      ...prev,
      { id: optimisticId, role: "user", content: message, created_at: new Date().toISOString() },
    ]);
    setInput("");
    setStreamingContent("");
    let streamOk = false;
    try {
      let r: Response | null = null;
      if (isV2Enabled()) {
        const v2r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/oracle/chat/stream-v2`,
          {
            method: "POST",
            headers: { "content-type": "application/json", accept: "text/event-stream" },
            body: JSON.stringify({ conversation_id: conversationId, message }),
          },
        );
        if (v2r.status === 404) {
          // CP feature flag is off — fall through to v1 stream.
          r = null;
        } else {
          r = v2r;
        }
      }
      if (r === null) {
        r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/oracle/chat/stream`,
          {
            method: "POST",
            headers: { "content-type": "application/json", accept: "text/event-stream" },
            body: JSON.stringify({ conversation_id: conversationId, message }),
          },
        );
      }
      if (r.status === 429) {
        const j = (await r.json().catch(() => ({}))) as { userMessage?: string };
        toast.error(
          j.userMessage && typeof j.userMessage === "string" && j.userMessage.trim()
            ? j.userMessage
            : "Daily LLM budget reached. Try again tomorrow.",
        );
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        setInput(message);
        setStreamingContent(null);
        return;
      }
      if (!r.ok || !r.body) {
        // Stream path unavailable — fall back to the JSON sibling route.
        setStreamingContent(null);
        await sendJsonFallback(message, optimisticId);
        return;
      }

      const consumed = await consumeStream(r, message, optimisticId);
      if (!consumed.ok || !consumed.turn) {
        return;
      }

      const done = consumed.turn;
      const acc = consumed.acc ?? "";
      setConversationId(done.conversation_id);
      setTurns((prev) =>
        prev
          .filter((t) => t.id !== optimisticId)
          .concat([
            {
              id: `user-${done.turn_id}`,
              role: "user",
              content: message,
              created_at: new Date().toISOString(),
            },
            {
              id: done.turn_id,
              role: "oracle",
              content: acc,
              created_at: new Date().toISOString(),
            },
          ]),
      );
      setStreamingContent(null);
      setErr(null);
      streamOk = true;
    } catch {
      // Network error on the stream path — fall back to JSON so the panel
      // still works even if SSE is unavailable.
      setStreamingContent(null);
      if (!streamOk) {
        try {
          await sendJsonFallback(message, optimisticId);
        } catch {
          setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
          setInput(message);
          toast.error("Agent Kenny could not reply");
        }
      }
    } finally {
      setSending(false);
      setTraceOpen(false);
      if (thinkStartRef.current !== null) {
        setThoughtSeconds(Math.max(1, Math.round((Date.now() - thinkStartRef.current) / 1000)));
        thinkStartRef.current = null;
      }
    }
  }, [conversationId, consumeStream, engagementId, input, sending, sendJsonFallback]);

  const clear = React.useCallback(() => {
    setTurns([]);
    setConversationId(null);
    setStreamingContent(null);
    setReasoning([]);
    setCitationBadges([]);
    setInlineNotes([]);
    setErr(null);
    setThoughtSeconds(null);
    setTraceOpen(false);
    loadedRef.current = false;
  }, []);

  const onKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void send();
      }
    },
    [send],
  );

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-expanded={false}
        aria-controls="oracle-chat-body"
        onClick={() => setOpen(true)}
        data-testid="oracle-chat-rail-toggle"
        className="fixed top-1/3 right-0 z-40 flex h-32 w-8 items-center justify-center rounded-l-md rounded-r-none bg-surface px-0 text-ink shadow-raised hover:bg-hover"
      >
        <span
          className="text-[11px] font-semibold tracking-wide text-ink"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          Agent Kenny ›
        </span>
      </Button>
    );
  }

  return (
    <aside
      className="fixed top-16 right-0 bottom-0 z-40 flex w-[400px] max-w-[95vw] flex-col border-l border-line bg-page shadow-overlay"
      data-testid="oracle-chat-panel"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line bg-surface px-3 py-2">
        <h2 id={PANEL_TITLE_ID} className="text-sm font-semibold text-ink">
          Agent Kenny
        </h2>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={clear}
            disabled={sending || turns.length === 0}
          >
            Clear
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 px-2 text-xs"
            aria-expanded={true}
            aria-controls="oracle-chat-body"
            onClick={() => setOpen(false)}
          >
            Hide
          </Button>
        </div>
      </header>

      <section
        id="oracle-chat-body"
        aria-labelledby={PANEL_TITLE_ID}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3" data-testid="oracle-chat-scroll">
          {err ? <p className="text-sm text-red-ink">{err}</p> : null}
          {loadingHistory && turns.length === 0 ? (
            <div className="space-y-3">
              <PixelLoader label="Loading conversation" showElapsed={false} />
              <ShimmerLines lines={3} />
            </div>
          ) : turns.length === 0 ? (
            <p className="text-sm text-ink-600">
              Ask Agent Kenny about this engagement. He grounds every answer in ledger events.
            </p>
          ) : (
            <>
              <ul className="space-y-3">
                {turns.map((t) => (
                  <OracleMessage
                    key={t.id}
                    engagementId={engagementId}
                    role={t.role}
                    content={t.content}
                  />
                ))}
              </ul>

              {/* Thinking trace — Beautiful UI component 02. Persists after
                  the stream completes as a collapsed "Thought for Ns" row. */}
              {reasoning.length > 0 ? (
                <details
                  open={traceOpen}
                  onToggle={(e) => setTraceOpen(e.currentTarget.open)}
                  className="mt-3 rounded-card bg-surface shadow-hairline"
                  data-testid="oracle-chat-reasoning"
                >
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-ink-600 select-none [&::-webkit-details-marker]:hidden">
                    {sending ? (
                      <PixelLoader label="Thinking" showElapsed={false} className="text-xs" />
                    ) : (
                      <span>
                        Thought for {thoughtSeconds ?? 1}s · {reasoning.length} step
                        {reasoning.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </summary>
                  <div className="border-t border-line px-3 py-2">
                    <ul className="space-y-1.5">
                      {reasoning
                        .filter((r) => r.kind === "thinking")
                        .map((r, i) => (
                          <li
                            key={`think-${i}`}
                            className="text-xs leading-relaxed text-ink-600"
                            data-testid="oracle-chat-thinking"
                          >
                            {r.kind === "thinking" ? r.content : null}
                          </li>
                        ))}
                    </ul>
                    {/* Tool chips — Beautiful UI component 05: compact
                        expandable chips with status ticks. */}
                    {reasoning.some((r) => r.kind !== "thinking") ? (
                      <ul className="mt-2 flex flex-wrap gap-1.5">
                        {reasoning.map((r, i) =>
                          r.kind === "tool_call" ? (
                            <li key={`tool-${i}`} data-testid="oracle-chat-tool_call">
                              <span className="inline-flex items-center gap-1.5 rounded-full bg-hover px-2 py-0.5 font-mono text-[10px] text-ink-600 shadow-hairline">
                                <span
                                  aria-hidden="true"
                                  className="size-1.5 animate-pulse rounded-full bg-accent"
                                />
                                {r.name}
                              </span>
                            </li>
                          ) : r.kind === "tool_result" ? (
                            <li key={`result-${i}`} data-testid="oracle-chat-tool_result">
                              <details className="inline-block">
                                <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full bg-hover px-2 py-0.5 font-mono text-[10px] text-ink-600 shadow-hairline select-none [&::-webkit-details-marker]:hidden">
                                  {r.error ? (
                                    <TriangleAlertIcon
                                      aria-hidden="true"
                                      className="size-3 text-orange-ink"
                                    />
                                  ) : (
                                    <CheckIcon
                                      aria-hidden="true"
                                      className="size-3 text-green-ink"
                                    />
                                  )}
                                  {r.name}
                                  <span className="text-ink-3">
                                    {r.row_count}
                                    {r.truncated ? "+" : ""}
                                  </span>
                                </summary>
                                <p className="mt-1 rounded-md bg-inset px-2 py-1 text-[10px] text-ink-600 shadow-hairline">
                                  {r.error
                                    ? `Error: ${r.error}`
                                    : `${r.row_count} row${r.row_count === 1 ? "" : "s"}${
                                        r.truncated ? " (truncated)" : ""
                                      }`}
                                </p>
                              </details>
                            </li>
                          ) : null,
                        )}
                      </ul>
                    ) : null}
                  </div>
                </details>
              ) : null}

              {/* Citation verification chips — inline sources row. */}
              {citationBadges.length > 0 ? (
                <ul className="mt-2 flex flex-wrap gap-1.5" data-testid="oracle-chat-citations">
                  {citationBadges.map((b, i) => (
                    <li
                      key={`${b.kind}-${b.id}-${i}`}
                      className={
                        b.outcome === "verified"
                          ? "inline-flex items-center gap-1 rounded-full bg-green-tint px-2 py-0.5 font-mono text-[10px] text-green-ink shadow-hairline"
                          : "inline-flex items-center gap-1 rounded-full bg-red-tint px-2 py-0.5 font-mono text-[10px] text-red-ink shadow-hairline"
                      }
                      data-testid={
                        b.outcome === "verified"
                          ? "oracle-citation-verified"
                          : "oracle-citation-unverified"
                      }
                    >
                      {b.outcome === "verified" ? (
                        <CheckIcon aria-hidden="true" className="size-3" />
                      ) : (
                        <TriangleAlertIcon aria-hidden="true" className="size-3" />
                      )}
                      {b.kind}:{b.id.slice(0, 8)}
                    </li>
                  ))}
                </ul>
              ) : null}

              {inlineNotes.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1.5" data-testid="oracle-chat-inline-notes">
                  {inlineNotes.map((n, i) =>
                    n.kind === "cross_engagement_leak" ? (
                      <li
                        key={`leak-${i}`}
                        className="rounded-md bg-red-tint px-2.5 py-1.5 text-[11px] text-red-ink shadow-hairline"
                        data-testid="oracle-cross-engagement-leak"
                      >
                        Cross-engagement leak blocked: {n.citationKind}:{n.id.slice(0, 8)}
                      </li>
                    ) : (
                      <li
                        key={`concern-${i}`}
                        className={
                          n.severity === "blocking"
                            ? "rounded-md bg-red-tint px-2.5 py-1.5 text-[11px] text-red-ink shadow-hairline"
                            : n.severity === "warning"
                              ? "rounded-md bg-orange-tint px-2.5 py-1.5 text-[11px] text-orange-ink shadow-hairline"
                              : "rounded-md bg-hover px-2.5 py-1.5 text-[11px] text-ink-600 shadow-hairline"
                        }
                        data-testid={`oracle-adversarial-concern-${n.severity}`}
                      >
                        Concern: {n.concern}
                      </li>
                    ),
                  )}
                </ul>
              ) : null}

              {streamingContent !== null ? (
                <div
                  aria-live="polite"
                  aria-atomic="false"
                  data-testid="oracle-chat-streaming"
                  className="mt-3"
                >
                  <ul>
                    <OracleMessage
                      engagementId={engagementId}
                      role={ORACLE_ROLE}
                      content={streamingContent || "…"}
                    />
                  </ul>
                </div>
              ) : null}
            </>
          )}
        </div>

        {/* Prompt bar — Beautiful UI component 08 (visual only: same
            submit / keyboard / aria behavior as before). */}
        <div className="border-t border-line bg-surface px-3 py-3">
          <div className="rounded-card bg-field shadow-inset-field transition-shadow focus-within:ring-2 focus-within:ring-ring/40">
            <Textarea
              aria-label="Message Agent Kenny"
              placeholder="Ask about risks, decisions, or recent activity…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              disabled={sending}
              className="min-h-[44px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
            />
            <div className="flex items-center justify-between gap-2 px-3 pb-2">
              <p className="text-[11px] text-ink-500">
                AI-generated. Verify before acting on any reply.
              </p>
              <Button
                type="button"
                size="sm"
                onClick={() => void send()}
                disabled={sending || input.trim().length === 0}
              >
                {sending ? "Asking…" : "Send"}
              </Button>
            </div>
          </div>
        </div>
      </section>
    </aside>
  );
}
