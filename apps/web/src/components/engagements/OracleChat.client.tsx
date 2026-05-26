"use client";

import * as React from "react";
import { toast } from "sonner";

import { OracleMessage } from "@/components/engagements/OracleMessage.client";
import { Button } from "@/components/ui/button";
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
        className="border-border bg-paper-200 text-ink-800 hover:bg-paper-300 fixed top-1/3 right-0 z-40 flex h-32 w-8 items-center justify-center rounded-l-md rounded-r-none border border-r-0 px-0 shadow-md"
      >
        <span
          className="text-ink-800 text-[11px] font-semibold tracking-wide"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          Agent Kenny ›
        </span>
      </Button>
    );
  }

  return (
    <aside
      className="border-border bg-paper-200 fixed top-16 right-0 bottom-0 z-40 flex w-[400px] max-w-[95vw] flex-col border-l shadow-xl"
      data-testid="oracle-chat-panel"
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 id={PANEL_TITLE_ID} className="text-ink-900 text-sm font-semibold">
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
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2" data-testid="oracle-chat-scroll">
          {err ? <p className="text-error-700 text-sm">{err}</p> : null}
          {loadingHistory && turns.length === 0 ? (
            <p className="text-ink-600 text-sm">Loading…</p>
          ) : turns.length === 0 ? (
            <p className="text-ink-600 text-sm">
              Ask Agent Kenny about this engagement. He grounds every answer in ledger events.
            </p>
          ) : (
            <>
              <ul className="space-y-2">
                {turns.map((t) => (
                  <OracleMessage
                    key={t.id}
                    engagementId={engagementId}
                    role={t.role}
                    content={t.content}
                  />
                ))}
              </ul>
              {streamingContent !== null ? (
                <div
                  aria-live="polite"
                  aria-atomic="false"
                  data-testid="oracle-chat-streaming"
                  className="mt-2"
                >
                  {reasoning.length > 0 ? (
                    <ul className="mb-1 flex flex-wrap gap-1" data-testid="oracle-chat-reasoning">
                      {reasoning.map((r, i) => (
                        <li
                          key={i}
                          className="bg-paper-300 text-ink-700 rounded px-2 py-0.5 text-[10px]"
                          data-testid={`oracle-chat-${r.kind}`}
                        >
                          {r.kind === "thinking"
                            ? `thinking: ${r.content.slice(0, 80)}`
                            : r.kind === "tool_call"
                              ? `tool: ${r.name}`
                              : `result: ${r.name} (${r.row_count}${r.truncated ? "+" : ""})`}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {citationBadges.length > 0 ? (
                    <ul className="mb-1 flex flex-wrap gap-1" data-testid="oracle-chat-citations">
                      {citationBadges.map((b, i) => (
                        <li
                          key={`${b.kind}-${b.id}-${i}`}
                          className={
                            b.outcome === "verified"
                              ? "bg-success-100 text-success-800 rounded px-1.5 py-0.5 text-[10px]"
                              : "bg-error-100 text-error-800 rounded px-1.5 py-0.5 text-[10px]"
                          }
                          data-testid={
                            b.outcome === "verified"
                              ? "oracle-citation-verified"
                              : "oracle-citation-unverified"
                          }
                        >
                          {b.kind}:{b.id.slice(0, 8)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {inlineNotes.length > 0 ? (
                    <ul className="mb-1 flex flex-col gap-1" data-testid="oracle-chat-inline-notes">
                      {inlineNotes.map((n, i) =>
                        n.kind === "cross_engagement_leak" ? (
                          <li
                            key={`leak-${i}`}
                            className="bg-error-100 text-error-800 rounded px-2 py-1 text-[11px]"
                            data-testid="oracle-cross-engagement-leak"
                          >
                            Cross-engagement leak blocked: {n.citationKind}:{n.id.slice(0, 8)}
                          </li>
                        ) : (
                          <li
                            key={`concern-${i}`}
                            className={
                              n.severity === "blocking"
                                ? "bg-error-100 text-error-800 rounded px-2 py-1 text-[11px]"
                                : n.severity === "warning"
                                  ? "bg-warning-100 text-warning-900 rounded px-2 py-1 text-[11px]"
                                  : "bg-paper-300 text-ink-700 rounded px-2 py-1 text-[11px]"
                            }
                            data-testid={`oracle-adversarial-concern-${n.severity}`}
                          >
                            Concern: {n.concern}
                          </li>
                        ),
                      )}
                    </ul>
                  ) : null}
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
        <div className="border-border border-t px-3 py-2">
          <Textarea
            aria-label="Message Agent Kenny"
            placeholder="Ask about risks, decisions, or recent activity…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            disabled={sending}
            className="min-h-[44px]"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <p className="text-ink-500 text-[11px]">
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
      </section>
    </aside>
  );
}
