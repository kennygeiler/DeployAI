//! DeployAI edge-capture agent (FR13, NFR20).
//!
//! Story 1.3 establishes the module layout only. Capture, signing, kill-switch,
//! and updater implementations land in later Epic 6 / security stories.

mod kill_switch;
mod signing;
mod transcription;
mod updater;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
