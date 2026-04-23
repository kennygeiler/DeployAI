import { zodToJsonSchema } from "zod-to-json-schema";
import {
  CITATION_ENVELOPE_SCHEMA_VERSION,
  CitationEnvelopeSchema,
} from "../../src/citation-envelope.js";

export function buildCitationEnvelopeJsonDocument(): Record<string, unknown> {
  const jsonSchema = zodToJsonSchema(CitationEnvelopeSchema, { target: "jsonSchema7" });
  return {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: `https://deployai.local/schema/citation-envelope/v${CITATION_ENVELOPE_SCHEMA_VERSION}.json`,
    title: "CitationEnvelope",
    description:
      "DeployAI mandatory citation envelope (Story 1.11). Zod in citation-envelope.ts is canonical.",
    ...(jsonSchema as Record<string, unknown>),
  };
}
