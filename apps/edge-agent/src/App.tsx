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
  const [tenantId, setTenantId] = useState("");
  const [internalKey, setInternalKey] = useState("");
  const [killStatus, setKillStatus] = useState<string | null>(null);
  const [transcriptStatus, setTranscriptStatus] = useState<string | null>(null);
  const [segmentLines, setSegmentLines] = useState("demo-line-1\ndemo-line-2");
  const [audioCaptureStatus, setAudioCaptureStatus] = useState<string | null>(null);

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

  async function runRefreshKillSwitch() {
    const t = tenantId.trim();
    const k = internalKey.trim();
    const u = cpBase.trim();
    if (!t || !k || !u) {
      setKillStatus("Set control plane URL, tenant id, and internal API key first.");
      return;
    }
    try {
      const j = await invoke<{ revoked: boolean; httpStatus?: number; note?: string }>(
        "edge_agent_refresh_kill_switch_from_control_plane",
        { baseUrl: u, tenantId: t, internalApiKey: k },
      );
      setKillStatus(
        j.revoked
          ? "Device is revoked on the control plane — transcript signing will be blocked."
          : `Not revoked (HTTP ${j.httpStatus ?? "?"})${j.note ? ` — ${j.note}` : ""}`,
      );
    } catch (error) {
      setKillStatus(`Kill-switch refresh failed: ${String(error)}`);
    }
  }

  async function runWriteTranscriptBundle() {
    if (isTest) {
      setTranscriptStatus("Skipped in test mode.");
      return;
    }
    const lines = segmentLines
      .split("\n")
      .map((s) => s.trimEnd())
      .filter((s) => s.length > 0);
    if (lines.length === 0) {
      setTranscriptStatus("Add at least one non-empty segment line.");
      return;
    }
    const consentJson = consentRecord ? JSON.stringify(consentRecord) : null;
    try {
      const out = await invoke<{ bundleDir?: string }>("edge_agent_write_transcript_bundle", {
        segments: lines,
        attachRfc3161: false,
        consentJson,
        transcriptFormat: "v2",
      });
      setTranscriptStatus(`Wrote transcript v2 bundle: ${out.bundleDir ?? "(path unknown)"}`);
    } catch (error) {
      setTranscriptStatus(`Write bundle failed: ${String(error)}`);
    }
  }

  async function runAudioCaptureStatus() {
    try {
      const s = await invoke<string>("edge_agent_audio_capture_status");
      setAudioCaptureStatus(s);
    } catch (error) {
      setAudioCaptureStatus(`Status failed: ${String(error)}`);
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
        <label>
          Tenant id (UUID)
          <input
            className="cp-input"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            spellCheck={false}
          />
        </label>
        <label>
          Internal API key
          <input
            className="cp-input"
            value={internalKey}
            onChange={(e) => setInternalKey(e.target.value)}
            placeholder="X-DeployAI-Internal-Key value"
            spellCheck={false}
            type="password"
            autoComplete="off"
          />
        </label>
        <button type="button" onClick={() => void runRefreshKillSwitch()}>
          Refresh kill-switch (by-device)
        </button>
        {killStatus ? <p className="cp-out">{killStatus}</p> : null}
      </section>
      {!isTest ? (
        <section className="panel">
          <h2>Transcript bundle (Story 11.4 / 11.7)</h2>
          <p>
            Writes <code>deployai.edge.transcript.v2</code> under app data. Consent JSON from
            localStorage is hashed into the signed manifest when present.
          </p>
          <label>
            Segment lines (one string per line)
            <textarea
              className="cp-input"
              value={segmentLines}
              onChange={(e) => setSegmentLines(e.target.value)}
              rows={4}
              spellCheck={false}
            />
          </label>
          <button type="button" onClick={() => void runWriteTranscriptBundle()}>
            Write signed transcript bundle (v2)
          </button>
          {transcriptStatus ? <p className="cp-out">{transcriptStatus}</p> : null}
        </section>
      ) : null}
      <section className="panel">
        <h2>Local audio capture (spike)</h2>
        <button type="button" onClick={() => void runAudioCaptureStatus()}>
          CoreAudio / local capture status
        </button>
        {audioCaptureStatus ? <p>{audioCaptureStatus}</p> : null}
      </section>
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
