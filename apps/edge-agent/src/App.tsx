import { invoke } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import "./App.css";
import { TwoPartyConsentDialog } from "./TwoPartyConsentDialog";

const MIC_PROMPT_FLAG = "deployai.edgeAgent.micPrompted.v1";
const CONSENT_KEY = "deployai.edgeAgent.twoPartyConsent.v1";

type ConsentRecord = {
  version: 1;
  jurisdiction: string;
  acceptedAt: string;
};

function readConsent(): ConsentRecord | null {
  try {
    const raw = localStorage.getItem(CONSENT_KEY);
    if (!raw) {
      return null;
    }
    const v = JSON.parse(raw) as ConsentRecord;
    if (
      v?.version !== 1 ||
      typeof v.jurisdiction !== "string" ||
      typeof v.acceptedAt !== "string"
    ) {
      return null;
    }
    return v;
  } catch {
    return null;
  }
}

function writeConsent(jurisdiction: string): ConsentRecord {
  const rec: ConsentRecord = {
    version: 1,
    jurisdiction,
    acceptedAt: new Date().toISOString(),
  };
  localStorage.setItem(CONSENT_KEY, JSON.stringify(rec));
  return rec;
}

function initialMicMessage(isTest: boolean): string {
  if (isTest) {
    return "Microphone permission check skipped in tests.";
  }
  if (!readConsent()) {
    return "Waiting for recording consent…";
  }
  if (localStorage.getItem(MIC_PROMPT_FLAG)) {
    return "Microphone permission prompt already shown on this machine.";
  }
  return "Requesting microphone access…";
}

async function promptMicAccess(): Promise<string> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return "Microphone permission API unavailable in this environment.";
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return "Microphone access granted.";
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return `Microphone access denied or unavailable: ${msg}`;
  }
}

function App() {
  const isTest = import.meta.env.MODE === "test";
  const [consentRecord, setConsentRecord] = useState<ConsentRecord | null>(() =>
    isTest ? null : readConsent(),
  );
  const [consentOpen, setConsentOpen] = useState(() => (isTest ? false : !readConsent()));
  const [consentDeclined, setConsentDeclined] = useState(false);
  const [micStatus, setMicStatus] = useState(() => initialMicMessage(isTest));
  const [keychainStatus, setKeychainStatus] = useState<string | null>(null);
  const [cpBase, setCpBase] = useState(
    import.meta.env.VITE_CONTROL_PLANE_URL?.trim() || "http://127.0.0.1:8000",
  );
  const [cpHealth, setCpHealth] = useState<string | null>(null);
  const [appcastUrl, setAppcastUrl] = useState(
    import.meta.env.VITE_APPCAST_URL?.trim() || "",
  );
  const [sparkleFetchOut, setSparkleFetchOut] = useState<string | null>(null);
  const [verifyPath, setVerifyPath] = useState("");
  const [verifySig, setVerifySig] = useState("");
  const [verifyLen, setVerifyLen] = useState("");
  const [verifyPk, setVerifyPk] = useState("");
  const [sparkleVerifyOut, setSparkleVerifyOut] = useState<string | null>(null);

  const micGateOpen = !isTest && !consentOpen && !consentDeclined && !!consentRecord;

  useEffect(() => {
    if (isTest || !micGateOpen) {
      return;
    }
    const prompted = localStorage.getItem(MIC_PROMPT_FLAG);
    if (prompted) {
      setMicStatus("Microphone permission prompt already shown on this machine.");
      return;
    }
    void promptMicAccess().then((msg) => {
      setMicStatus(msg);
      localStorage.setItem(MIC_PROMPT_FLAG, "1");
    });
  }, [isTest, micGateOpen]);

  async function runControlPlaneHealth() {
    const u = cpBase.trim();
    if (!u) {
      setCpHealth("Set a control plane base URL.");
      return;
    }
    try {
      const h = await invoke<{ ok: boolean; body: string; url: string }>("control_plane_health", {
        baseUrl: u,
      });
      setCpHealth(
        h.ok
          ? `OK ${h.url} — ${h.body.slice(0, 240)}`
          : `Non-success from ${h.url} — ${h.body.slice(0, 240)}`,
      );
    } catch (error) {
      setCpHealth(`Request failed: ${String(error)}`);
    }
  }

  async function runSparkleFetchLatest() {
    const u = appcastUrl.trim();
    if (!u) {
      setSparkleFetchOut("Set appcast HTTPS URL (or VITE_APPCAST_URL).");
      return;
    }
    try {
      const j = await invoke<Record<string, unknown>>("edge_agent_sparkle_fetch_latest_item", {
        appcastUrl: u,
      });
      setSparkleFetchOut(JSON.stringify(j, null, 2));
    } catch (error) {
      setSparkleFetchOut(`Fetch/parse failed: ${String(error)}`);
    }
  }

  async function runSparkleVerifyLocal() {
    const path = verifyPath.trim();
    const sig = verifySig.trim();
    const pk = verifyPk.trim();
    const len = verifyLen.trim();
    if (!path || !sig || !pk || !len) {
      setSparkleVerifyOut("Path, edSignature, public key (std base64), and length are required.");
      return;
    }
    const expectedLength = Number(len);
    if (!Number.isFinite(expectedLength) || expectedLength < 0) {
      setSparkleVerifyOut("Length must be a non-negative number (appcast enclosure).");
      return;
    }
    try {
      await invoke("edge_agent_sparkle_verify_local_archive", {
        archivePath: path,
        edSignatureB64: sig,
        publicKeyEd25519B64: pk,
        expectedLength,
      });
      setSparkleVerifyOut("Verify OK — archive matches signature and length.");
    } catch (error) {
      setSparkleVerifyOut(`Verify failed: ${String(error)}`);
    }
  }

  async function runKeychainRoundtrip() {
    const sample = `deployai-spike-${Date.now()}`;
    try {
      const readBack = await invoke<string>("keychain_roundtrip", { value: sample });
      setKeychainStatus(
        readBack === sample ? "Keychain round-trip passed." : "Keychain value mismatch.",
      );
    } catch (error) {
      setKeychainStatus(`Keychain round-trip failed: ${String(error)}`);
    }
  }

  return (
    <main className="container">
      <h1>DeployAI Edge Agent</h1>
      <p>
        Edge capture shell: two-party consent gate, first-launch mic check, keychain test, and
        control-plane reachability.
      </p>
      {!isTest ? (
        <TwoPartyConsentDialog
          open={consentOpen}
          onDecline={() => {
            setConsentOpen(false);
            setConsentDeclined(true);
            setMicStatus("Recording disabled — consent was declined. Clear site data to reset.");
          }}
          onAccept={(jurisdiction) => {
            const rec = writeConsent(jurisdiction);
            setConsentRecord(rec);
            setConsentOpen(false);
            setMicStatus("Consent recorded. Requesting microphone access…");
          }}
        />
      ) : null}
      <section className="panel">
        <h2>Recording consent (Story 11.4)</h2>
        {isTest ? (
          <p>Consent dialog skipped in test mode.</p>
        ) : consentDeclined ? (
          <p>{micStatus}</p>
        ) : consentRecord ? (
          <p>
            On-device attestation stored (jurisdiction:{" "}
            <strong>{consentRecord.jurisdiction}</strong>, accepted {consentRecord.acceptedAt}).
          </p>
        ) : consentOpen ? (
          <p>Complete the dialog above to enable capture.</p>
        ) : (
          <p>Waiting for consent…</p>
        )}
      </section>
      <section className="panel">
        <h2>Audio permission (after consent)</h2>
        {isTest || consentDeclined ? <p>{micStatus}</p> : null}
        {!isTest && !consentDeclined && micGateOpen ? <p>{micStatus}</p> : null}
        {!isTest && !consentDeclined && consentOpen ? (
          <p>Microphone prompt runs after you accept.</p>
        ) : null}
      </section>
      <section className="panel">
        <h2>Control plane</h2>
        <label>
          Base URL
          <input
            className="cp-input"
            value={cpBase}
            onChange={(e) => setCpBase(e.target.value)}
            type="url"
            placeholder="http://127.0.0.1:8000"
            spellCheck={false}
          />
        </label>
        <button type="button" onClick={() => void runControlPlaneHealth()}>
          Check /health
        </button>
        {cpHealth ? <p className="cp-out">{cpHealth}</p> : null}
      </section>
      {!isTest ? (
        <section className="panel">
          <h2>Updates — Sparkle appcast (Story 11.5)</h2>
          <p>
            Fetch parses the first <code>&lt;item&gt;</code>. Verify checks a downloaded DMG/ZIP against{" "}
            <code>sparkle:edSignature</code> (Ed25519 over raw bytes).
          </p>
          <label>
            Appcast URL (HTTPS)
            <input
              className="cp-input"
              value={appcastUrl}
              onChange={(e) => setAppcastUrl(e.target.value)}
              type="url"
              placeholder="https://…/appcast.xml"
              spellCheck={false}
            />
          </label>
          <button type="button" onClick={() => void runSparkleFetchLatest()}>
            Fetch latest enclosure
          </button>
          {sparkleFetchOut ? <pre className="cp-out">{sparkleFetchOut}</pre> : null}
          <hr />
          <label>
            Local archive path
            <input
              className="cp-input"
              value={verifyPath}
              onChange={(e) => setVerifyPath(e.target.value)}
              spellCheck={false}
            />
          </label>
          <label>
            sparkle:edSignature (std base64)
            <input
              className="cp-input"
              value={verifySig}
              onChange={(e) => setVerifySig(e.target.value)}
              spellCheck={false}
            />
          </label>
          <label>
            Public key (std base64, 32-byte Ed25519)
            <input
              className="cp-input"
              value={verifyPk}
              onChange={(e) => setVerifyPk(e.target.value)}
              spellCheck={false}
            />
          </label>
          <label>
            Length (bytes, from appcast)
            <input
              className="cp-input"
              value={verifyLen}
              onChange={(e) => setVerifyLen(e.target.value)}
              inputMode="numeric"
            />
          </label>
          <button type="button" onClick={() => void runSparkleVerifyLocal()}>
            Verify local archive
          </button>
          {sparkleVerifyOut ? <p className="cp-out">{sparkleVerifyOut}</p> : null}
        </section>
      ) : null}
      <section className="panel">
        <h2>Keychain Round-trip</h2>
        <button type="button" onClick={() => void runKeychainRoundtrip()}>
          Run keychain write/read check
        </button>
        {keychainStatus ? <p>{keychainStatus}</p> : null}
      </section>
    </main>
  );
}

export default App;
