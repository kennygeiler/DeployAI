//! Story 11.4 — local audio capture (CoreAudio) is not wired yet; status command for integration tests and UX.

#[tauri::command]
pub fn edge_agent_audio_capture_status() -> Result<String, String> {
    Ok(
        "coreaudio/local-capture: stub (Story 11.4 spike — use WebView getUserMedia for mic gate)"
            .to_string(),
    )
}
