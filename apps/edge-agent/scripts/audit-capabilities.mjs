#!/usr/bin/env node
/**
 * Story 11.1: fail CI on over-broad filesystem (or related) grants in Tauri capabilities.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_TAURI = path.resolve(__dirname, "../src-tauri");
const CAP_DIR = path.join(SRC_TAURI, "capabilities");
const CONF = path.join(SRC_TAURI, "tauri.conf.json");

const REQUIRED_CAPABILITIES = [
  "default",
  "fs:local-only",
  "dialog:file-select",
  "audio:capture",
  "keychain:read-write",
  "http:api-only",
];

/** Exact permission identifiers that must never appear (Story 11.1 AC). */
const FORBIDDEN_PERMISSIONS = new Set([
  "fs:all",
  "fs:default",
  "dialog:default",
  "shell:default",
  "opener:default",
]);

/** If any permission identifier matches, fail (catches *:all style fs grants). */
const FORBIDDEN_REGEXES = [/^(fs|dialog|shell|opener):.*:all$/];

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function capabilityIdsFromConf(entries) {
  return entries.map((e) => (typeof e === "string" ? e : e.identifier));
}

function collectPermissionIds(permissions) {
  const out = [];
  if (!Array.isArray(permissions)) return out;
  for (const p of permissions) {
    if (typeof p === "string") out.push(p);
    else if (p && typeof p === "object" && typeof p.identifier === "string") {
      out.push(p.identifier);
    }
  }
  return out;
}

function auditPermission(id, source) {
  if (FORBIDDEN_PERMISSIONS.has(id)) {
    console.error(`audit-capabilities: forbidden permission "${id}" in ${source}`);
    process.exit(1);
  }
  for (const re of FORBIDDEN_REGEXES) {
    if (re.test(id)) {
      console.error(
        `audit-capabilities: forbidden permission pattern ${re} matched "${id}" in ${source}`,
      );
      process.exit(1);
    }
  }
}

function main() {
  const conf = readJson(CONF);
  const entries = conf?.app?.security?.capabilities;
  if (!Array.isArray(entries)) {
    console.error("audit-capabilities: tauri.conf.json app.security.capabilities must be an array");
    process.exit(1);
  }

  const enabled = capabilityIdsFromConf(entries);
  for (const req of REQUIRED_CAPABILITIES) {
    if (!enabled.includes(req)) {
      console.error(`audit-capabilities: missing required capability "${req}" in tauri.conf.json`);
      process.exit(1);
    }
  }

  const files = fs.readdirSync(CAP_DIR).filter((f) => f.endsWith(".json"));
  const idToFile = new Map();
  for (const f of files) {
    const full = path.join(CAP_DIR, f);
    const cap = readJson(full);
    if (typeof cap.identifier !== "string") continue;
    idToFile.set(cap.identifier, f);
  }

  for (const id of enabled) {
    const file = idToFile.get(id);
    if (!file) {
      console.error(
        `audit-capabilities: enabled capability "${id}" has no capabilities/*.json file`,
      );
      process.exit(1);
    }
    const cap = readJson(path.join(CAP_DIR, file));
    const perms = collectPermissionIds(cap.permissions);
    const label = `${file} (${id})`;
    for (const pid of perms) {
      auditPermission(pid, label);
    }
  }

  console.log("audit-capabilities: OK (required capabilities present; no forbidden grants)");
}

main();
