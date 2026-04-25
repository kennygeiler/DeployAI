import { invoke } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";
import "./App.css";

const MIC_PROMPT_FLAG = "deployai.edgeAgent.micPrompted.v1";

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
  const [micStatus, setMicStatus] = useState(() =>
    import.meta.env.MODE === "test"
      ? "Microphone permission check skipped in tests."
      : "Checking first-launch permissions...",
  );
  const [keychainStatus, setKeychainStatus] = useState<string | null>(null);
  const [cpBase, setCpBase] = useState(
    import.meta.env.VITE_CONTROL_PLANE_URL?.trim() || "http://127.0.0.1:8000",
  );
  const [cpHealth, setCpHealth] = useState<string | null>(null);

  useEffect(() => {
    if (import.meta.env.MODE === "test") {
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
  }, []);

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
        Edge capture shell: first-launch mic check, keychain test, and control-plane reachability.
      </p>
      <section className="panel">
        <h2>Audio Permission (first launch)</h2>
        <p>{micStatus}</p>
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
