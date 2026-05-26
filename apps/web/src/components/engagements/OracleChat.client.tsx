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

  const send = React.useCallback(async () => {
    const message = input.trim();
    if (!message || sending) return;
    setSending(true);
    const optimisticId = `pending-${Date.now()}`;
    setTurns((prev) => [
      ...prev,
      { id: optimisticId, role: "user", content: message, created_at: new Date().toISOString() },
    ]);
    setInput("");
    setStreamingContent("");
    let streamOk = false;
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/oracle/chat/stream`,
        {
          method: "POST",
          headers: { "content-type": "application/json", accept: "text/event-stream" },
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
        setStreamingContent(null);
        return;
      }
      if (!r.ok || !r.body) {
        // Stream path unavailable — fall back to the JSON sibling route.
        setStreamingContent(null);
        await sendJsonFallback(message, optimisticId);
        return;
      }

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
          const raw = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          const line = raw.trim();
          if (line.startsWith("data: ")) {
            try {
              const frame = JSON.parse(line.slice(6)) as
                | { delta: string; done: false }
                | { done: true; turn_id?: string; conversation_id?: string; error?: string };
              if (frame.done === false) {
                acc += frame.delta;
                setStreamingContent(acc);
              } else if (frame.error) {
                streamError = frame.error;
              } else if (frame.turn_id && frame.conversation_id) {
                done = { turn_id: frame.turn_id, conversation_id: frame.conversation_id };
              }
            } catch {
              // Malformed frame — ignore; the terminal done frame is what matters.
            }
          }
          split = buffer.indexOf("\n\n");
        }
        if (rdrDone) break;
      }

      if (streamError || !done) {
        // No terminal done frame (or upstream error mid-stream) — fall back.
        setStreamingContent(null);
        await sendJsonFallback(message, optimisticId);
        return;
      }

      setConversationId(done.conversation_id);
      setTurns((prev) =>
        prev
          .filter((t) => t.id !== optimisticId)
          .concat([
            {
              id: `user-${done!.turn_id}`,
              role: "user",
              content: message,
              created_at: new Date().toISOString(),
            },
            {
              id: done!.turn_id,
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
  }, [conversationId, engagementId, input, sending, sendJsonFallback]);

  const clear = React.useCallback(() => {
    setTurns([]);
    setConversationId(null);
    setStreamingContent(null);
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
