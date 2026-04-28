//! DeployAI edge-capture agent (FR13, NFR20).
//!
//! Story 1.3 establishes the module layout only. Capture, signing, kill-switch,
//! and updater implementations land in later Epic 6 / security stories.

mod audio_capture;
mod crypto;
mod device_identity;
mod kill_switch;
mod net;
mod signing;
mod transcript;
mod transcription;
mod updater;

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
            transcript::edge_agent_write_transcript_bundle,
            updater::edge_agent_sparkle_fetch_latest_item,
            updater::edge_agent_sparkle_verify_local_archive,
            kill_switch::edge_agent_kill_switch_status,
            kill_switch::edge_agent_refresh_kill_switch_from_control_plane,
            audio_capture::edge_agent_audio_capture_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
