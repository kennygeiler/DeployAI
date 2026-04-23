-- Story 1.7 — required Postgres extensions for DeployAI local dev stack.
-- Runs once on first container init (data volume empty). Safe to run on
-- already-initialized volumes because of IF NOT EXISTS.
--
-- pgvector:  HNSW + flat vector similarity (secondary retrieval path).
-- pgcrypto:  pgp_sym_encrypt/decrypt used by Story 1.9 envelope encryption.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
