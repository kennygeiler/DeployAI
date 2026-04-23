//! Keychain round-trip helper for Story 1.15 spike.
//!
//! Uses the system credential store via `keyring` (macOS Keychain, Windows
//! Credential Manager, Linux Secret Service/KWallet backend depending on host).

use keyring::Entry;

const SERVICE: &str = "app.deployai.edge-agent.spike";
const ACCOUNT: &str = "story-1-15-roundtrip";

#[tauri::command]
pub fn keychain_roundtrip(value: String) -> Result<String, String> {
    let entry = Entry::new(SERVICE, ACCOUNT).map_err(|e| format!("entry: {e}"))?;
    // Best-effort cleanup in case a prior run left state.
    let _ = entry.delete_credential();
    entry
        .set_password(&value)
        .map_err(|e| format!("set_password: {e}"))?;
    let read = entry
        .get_password()
        .map_err(|e| format!("get_password: {e}"))?;
    // Keep host keychain clean after the spike check.
    let _ = entry.delete_credential();
    Ok(read)
}
