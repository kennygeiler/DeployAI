#!/usr/bin/env node
/**
 * Recursively ingest TypeScript/Python sources into `codebase_embeddings` (pgvector).
 *
 * Env:
 *   GOOGLE_API_KEY or GEMINI_API_KEY — Google AI API key for text-embedding-004
 *   DATABASE_URL — Postgres connection (default: postgresql://n8n:n8n@127.0.0.1:5432/n8n)
 *
 * Run from repo root: node scripts/ingest-codebase.js
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const process = require("node:process");
const pg = require("pg");

const REPO_ROOT = path.resolve(__dirname, "..");

const SOURCE_ROOTS = [
  path.join(REPO_ROOT, "apps/web/src"),
  path.join(REPO_ROOT, "services/control-plane/src"),
];

const ALLOW_EXT = new Set([".ts", ".tsx", ".py"]);
const SKIP_DIR_NAMES = new Set([
  "node_modules",
  ".next",
  "dist",
  "build",
  ".turbo",
  "coverage",
  "__pycache__",
  ".git",
]);

/** ~1000 tokens heuristic: ~4 chars/token for code-like text */
const TARGET_CHUNK_CHARS = 4000;

function getApiKey() {
  return (process.env.GOOGLE_API_KEY ?? process.env.GEMINI_API_KEY ?? "").trim();
}

function getDatabaseUrl() {
  return (
    process.env.DATABASE_URL?.trim() ||
    "postgresql://n8n:n8n@127.0.0.1:5432/n8n"
  );
}

async function collectFiles(dir, out = []) {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (SKIP_DIR_NAMES.has(ent.name)) continue;
      await collectFiles(full, out);
    } else if (ent.isFile()) {
      const ext = path.extname(ent.name);
      if (ALLOW_EXT.has(ext)) {
        out.push(full);
      }
    }
  }
  return out;
}

function chunkText(text) {
  const chunks = [];
  let i = 0;
  while (i < text.length) {
    const end = Math.min(text.length, i + TARGET_CHUNK_CHARS);
    let slice = text.slice(i, end);
    if (end < text.length) {
      const lastNl = slice.lastIndexOf("\n");
      if (lastNl > TARGET_CHUNK_CHARS * 0.5) {
        slice = slice.slice(0, lastNl + 1);
      }
    }
    const t = slice.trim();
    if (t.length > 0) {
      chunks.push(t);
    }
    i += slice.length || 1;
  }
  return chunks;
}

async function embedChunk(apiKey, text) {
  const u = `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=${encodeURIComponent(apiKey)}`;
  const r = await fetch(u, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: { parts: [{ text }] },
    }),
  });
  if (!r.ok) {
    const errText = await r.text();
    throw new Error(`embed HTTP ${r.status}: ${errText.slice(0, 500)}`);
  }
  const data = await r.json();
  const values = data?.embedding?.values;
  if (!Array.isArray(values) || values.length !== 768) {
    throw new Error("unexpected embedding shape from Gemini");
  }
  return values;
}

async function main() {
  const apiKey = getApiKey();
  if (!apiKey) {
    console.error("Set GOOGLE_API_KEY or GEMINI_API_KEY");
    process.exit(1);
  }

  const files = [];
  for (const root of SOURCE_ROOTS) {
    await collectFiles(root, files);
  }
  files.sort();
  console.error(`Found ${files.length} source files under apps/web/src and services/control-plane/src`);

  const pool = new pg.Pool({ connectionString: getDatabaseUrl() });
  const client = await pool.connect();
  try {
    for (const filePath of files) {
      const rel = path.relative(REPO_ROOT, filePath);
      const raw = await fs.readFile(filePath, "utf8");
      const parts = chunkText(raw);
      let partIdx = 0;
      for (const chunk of parts) {
        partIdx += 1;
        const vec = await embedChunk(apiKey, chunk);
        const vecLiteral = `[${vec.join(",")}]`;
        await client.query(
          `INSERT INTO codebase_embeddings (file_path, chunk_content, embedding)
           VALUES ($1, $2, $3::vector)`,
          [rel + `#${partIdx}`, chunk, vecLiteral],
        );
        console.error(`embedded ${rel} chunk ${partIdx}/${parts.length}`);
      }
    }
  } finally {
    client.release();
    await pool.end();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
