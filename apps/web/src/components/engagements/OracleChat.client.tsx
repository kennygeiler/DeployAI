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

/**
 * Right-side collapsible Mr. Oracle chat panel. Single-turn POST against
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
    try {
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
        // Roll back the optimistic user turn so the input can be edited + retried.
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        setInput(message);
        return;
      }
      if (!r.ok) {
        const desc = await readStrategistBffErrorDescription(r);
        toast.error("Mr. Oracle could not reply", { description: desc.slice(0, 240) });
        setTurns((prev) => prev.filter((t) => t.id !== optimisticId));
        setInput(message);
        return;
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
    } finally {
      setSending(false);
    }
  }, [conversationId, engagementId, input, sending]);

  const clear = React.useCallback(() => {
    setTurns([]);
    setConversationId(null);
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
        className="border-border bg-paper-50 text-ink-800 hover:bg-paper-100 fixed top-1/3 right-0 z-40 flex h-32 w-8 items-center justify-center rounded-l-md rounded-r-none border border-r-0 px-0 shadow-md"
      >
        <span
          className="text-ink-800 text-[11px] font-semibold tracking-wide"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          Mr. Oracle ›
        </span>
      </Button>
    );
  }

  return (
    <aside
      className="border-border bg-paper-50 fixed top-16 right-0 bottom-0 z-40 flex w-[400px] max-w-[95vw] flex-col border-l shadow-xl"
      data-testid="oracle-chat-panel"
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 id={PANEL_TITLE_ID} className="text-ink-900 text-sm font-semibold">
          Mr. Oracle
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
              Ask Mr. Oracle about this engagement. He grounds every answer in ledger events.
            </p>
          ) : (
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
          )}
        </div>
        <div className="border-border border-t px-3 py-2">
          <Textarea
            aria-label="Message Mr. Oracle"
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
