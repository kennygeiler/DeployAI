"use client";

import * as React from "react";

import { OracleChat } from "@/components/engagements/OracleChat.client";
import { Button } from "@/components/ui/button";
import type { EngagementSummaryChange } from "@/lib/bff/summary-types";
import type { MatrixNode } from "@/lib/bff/matrix-types";
import { stripRedundantKindPrefix } from "@/lib/labels";
import {
  TOUR_CHAT_OPENED_EVENT,
  TOUR_CLOSE_CHAT_EVENT,
  TOUR_PREFILL_EVENT,
} from "@/lib/tour/steps";

/**
 * Wave 2.5 U4 — Kenny's front door on the Brief.
 *
 * A persistent ask-bar (sticky at the bottom of the Brief) with a free-text
 * input plus three suggested questions derived from engagement state.
 * Submitting opens the chat as a full-width overlay that mounts the existing
 * OracleChat surface and auto-sends the question. The old collapsed side
 * rail is gone.
 */

const FALLBACK_QUESTIONS = [
  "What changed on this deal in the last week?",
  "Who matters most on this deal right now?",
  "What did we promise, and when is it due?",
] as const;

export function deriveSuggestedQuestions({
  nodes,
  changes,
}: {
  nodes: MatrixNode[];
  changes: EngagementSummaryChange[];
}): string[] {
  const suggestions: string[] = [];

  const openRisk = nodes.find((n) => n.node_type === "risk" && n.status !== "closed");
  if (openRisk) {
    suggestions.push(`What's the latest on the risk "${openRisk.title}"?`);
  }

  const recentDecision = changes.find((c) => c.kind.includes("decision"));
  if (recentDecision) {
    const title = stripRedundantKindPrefix(recentDecision.title, recentDecision.kind);
    suggestions.push(`What led to "${title}"?`);
  } else {
    const decisionNode = nodes.find((n) => n.node_type === "decision");
    if (decisionNode) {
      suggestions.push(`What led to the decision "${decisionNode.title}"?`);
    }
  }

  for (const q of FALLBACK_QUESTIONS) {
    if (suggestions.length >= 3) break;
    suggestions.push(q);
  }
  return suggestions.slice(0, 3);
}

export function AskKennyBar({
  engagementId,
  nodes,
  changes,
}: {
  engagementId: string;
  nodes: MatrixNode[];
  changes: EngagementSummaryChange[];
}) {
  const [input, setInput] = React.useState("");
  const [overlay, setOverlay] = React.useState<{ question: string | null } | null>(null);

  const suggestions = React.useMemo(
    () => deriveSuggestedQuestions({ nodes, changes }),
    [nodes, changes],
  );

  const submit = React.useCallback(
    (question?: string) => {
      const q = (question ?? input).trim();
      setOverlay({ question: q.length > 0 ? q : null });
      if (!question) {
        setInput("");
      }
    },
    [input],
  );

  const close = React.useCallback(() => setOverlay(null), []);

  // K6 demo tour — the tour popover's "Use this question" button prefills
  // the bar (closing the chat overlay if it's covering it), and the tour
  // advances its "ask Kenny" step when the overlay opens.
  React.useEffect(() => {
    const onPrefill = (e: Event) => {
      const question = (e as CustomEvent<{ question?: unknown }>).detail?.question;
      if (typeof question === "string") {
        setInput(question);
        setOverlay(null);
      }
    };
    window.addEventListener(TOUR_PREFILL_EVENT, onPrefill);
    return () => window.removeEventListener(TOUR_PREFILL_EVENT, onPrefill);
  }, []);

  // demo-polish fix 3 — steps that spotlight Brief content (graph tab, the
  // slip act's capture/needs-you beats) declare `closeChat`; the tour
  // dispatches this event on their activation so a chat overlay left open
  // from an earlier ask beat never hides the target. No-op when closed.
  React.useEffect(() => {
    const onCloseChat = () => setOverlay(null);
    window.addEventListener(TOUR_CLOSE_CHAT_EVENT, onCloseChat);
    return () => window.removeEventListener(TOUR_CLOSE_CHAT_EVENT, onCloseChat);
  }, []);

  React.useEffect(() => {
    if (overlay) window.dispatchEvent(new CustomEvent(TOUR_CHAT_OPENED_EVENT));
  }, [overlay]);

  return (
    <>
      <div
        data-testid="ask-kenny-bar"
        data-tour="ask-kenny-bar"
        className="sticky bottom-0 z-30 -mx-1 space-y-2 border-t border-line bg-page/95 px-1 py-3 backdrop-blur"
      >
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <input
            aria-label="Ask Agent Kenny"
            placeholder="Ask Kenny about this deal…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="min-w-0 flex-1 rounded-card border border-transparent bg-field px-3 py-2 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          />
          <Button type="submit" size="sm" disabled={input.trim().length === 0}>
            Ask
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => submit("")}
            data-testid="ask-kenny-open-chat"
          >
            Chat
          </Button>
        </form>
        <ul className="flex flex-wrap gap-1.5" aria-label="Suggested questions">
          {suggestions.map((q) => (
            <li key={q}>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => submit(q)}
                data-testid="ask-kenny-suggestion"
                className="h-auto rounded-full bg-hover px-2.5 py-1 text-xs font-normal text-ink-600 shadow-hairline transition-colors hover:bg-hover-2 hover:text-ink"
              >
                {q}
              </Button>
            </li>
          ))}
        </ul>
      </div>

      {overlay ? (
        <div data-testid="ask-kenny-overlay">
          <Button
            type="button"
            variant="ghost"
            aria-label="Close chat"
            onClick={close}
            className="fixed inset-0 z-40 h-auto w-auto cursor-default rounded-none bg-black/30 hover:bg-black/30"
          />
          <OracleChat
            key={overlay.question ?? "chat"}
            engagementId={engagementId}
            variant="overlay"
            onClose={close}
            initialInput={overlay.question ?? ""}
            autoSend={overlay.question !== null}
          />
        </div>
      ) : null}
    </>
  );
}
