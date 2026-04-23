import type { CapabilityMatrix, ChatMessage, LLMCallOptions, LLMProvider } from "./provider.js";

const stubCaps: CapabilityMatrix = {
  extraction: true,
  retrieval: true,
  arbitration: true,
  embeddings: true,
  tool_use: true,
};

/**
 * Deterministic provider for tests and local harnesses.
 */
export function createStubLlmProvider(prefix = "stub-out"): LLMProvider {
  return {
    id: "stub",
    async chatComplete(messages: readonly ChatMessage[], _options: LLMCallOptions | undefined) {
      const last = messages.filter((m) => m.role !== "system").at(-1)?.content ?? "";
      return `${prefix}:${last.length}`;
    },
    async embed(text: string) {
      // Deterministic fake embedding: length + simple hash
      return [text.length, text ? text.charCodeAt(0) & 0xff : 0, 0.25, 0.5];
    },
    capabilities: () => ({ ...stubCaps }),
  };
}

export { stubCaps };
