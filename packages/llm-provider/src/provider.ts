/**
 * LLMProvider — frozen contract for every deploy-time agent and harness (Story 1.14, NFR70).
 */

export type ChatRole = "system" | "user" | "assistant";

export type ChatMessage = {
  role: ChatRole;
  content: string;
};

export type LLMCallOptions = {
  temperature?: number;
  maxOutputTokens?: number;
};

/**
 * What this provider can do. Keys line up with `services/config/llm-capability-matrix.yaml`.
 */
export type CapabilityKey = "extraction" | "retrieval" | "arbitration" | "embeddings" | "tool_use";

export type CapabilityMatrix = Record<CapabilityKey, boolean>;

/**
 * Pluggable interface — Epic 5 supplies Anthropic + OpenAI implementations.
 */
export type LLMProvider = {
  chatComplete: (messages: readonly ChatMessage[], options?: LLMCallOptions) => Promise<string>;
  embed: (text: string) => Promise<number[]>;
  capabilities: () => CapabilityMatrix;
  /** For logs / cutover: stable provider id, e.g. "stub" | "anthropic" | "openai". */
  id: string;
};
