//! Optional connectivity check to the DeployAI control plane (local or hosted).

use serde::Serialize;

#[derive(Serialize)]
pub struct ControlPlaneHealth {
    /// HTTP status in 200–299
    pub ok: bool,
    /// Response body, truncated
    pub body: String,
    /// The URL that was requested
    pub url: String,
}

/// GET `{base}/health` (or `/health` if the base already endswith /health) with an 8s timeout.
#[tauri::command]
pub async fn control_plane_health(base_url: String) -> Result<ControlPlaneHealth, String> {
    let b = base_url.trim().to_string();
    if b.is_empty() {
        return Err("base_url is empty".to_string());
    }
    let url = if b.ends_with("/health") {
        b
    } else {
        format!("{}/health", b.trim_end_matches('/'))
    };
    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_secs(8))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client.get(&url).send().await.map_err(|e| e.to_string())?;
    let ok = resp.status().is_success();
    let text = resp.text().await.map_err(|e| e.to_string())?;
    let body: String = text.chars().take(4_000).collect();
    Ok(ControlPlaneHealth { ok, body, url })
}
