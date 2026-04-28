//! DeployAI edge-capture agent (FR13, NFR20).
//!
//! Story 1.3 establishes the module layout only. Capture, signing, kill-switch,
//! and updater implementations land in later Epic 6 / security stories.

mod kill_switch;
mod net;
mod signing;
mod transcription;
mod updater;
mod crypto;
mod device_identity;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            crypto::keychain_roundtrip,
            net::control_plane_health,
            device_identity::edge_agent_signing_identity,
            device_identity::edge_agent_register_with_control_plane,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
