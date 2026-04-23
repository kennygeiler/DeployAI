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
      <p>Story 1.15 spike shell: first-launch mic prompt + keychain round-trip command.</p>
      <section className="panel">
        <h2>Audio Permission (first launch)</h2>
        <p>{micStatus}</p>
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
