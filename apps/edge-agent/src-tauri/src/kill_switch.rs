//! Story 11.7 — control-plane kill switch: poll `by-device` and block transcript signing when revoked.

use std::sync::atomic::{AtomicBool, Ordering};

use serde::Deserialize;

use crate::device_identity::ensure_signing_identity;

static REVOKED: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Deserialize)]
struct ByDeviceResponse {
    revoked_at: Option<serde_json::Value>,
}

/// Whether the last successful refresh indicated this device is revoked on the control plane.
pub fn is_revoked() -> bool {
    REVOKED.load(Ordering::SeqCst)
}

#[cfg(test)]
pub fn test_set_revoked(v: bool) {
    REVOKED.store(v, Ordering::SeqCst);
}

#[tauri::command]
pub fn edge_agent_kill_switch_status() -> serde_json::Value {
    serde_json::json!({ "revoked": is_revoked() })
}

/// GET `/internal/v1/edge-agents/by-device` and set local revoked flag from `revoked_at`.
#[tauri::command]
pub async fn edge_agent_refresh_kill_switch_from_control_plane(
    app: tauri::AppHandle,
    base_url: String,
    tenant_id: String,
    internal_api_key: String,
) -> Result<serde_json::Value, String> {
    let ident = ensure_signing_identity(&app)?;
    let b = base_url.trim_end_matches('/').to_string();
    let url = format!("{b}/internal/v1/edge-agents/by-device");
    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .get(&url)
        .query(&[
            ("tenant_id", tenant_id.trim()),
            ("device_id", ident.device_id.trim()),
        ])
        .header(
            "X-DeployAI-Internal-Key",
            internal_api_key.trim().to_string(),
        )
        .send()
        .await
        .map_err(|e| format!("kill-switch poll: {e}"))?;
    let status = resp.status();
    let text = resp.text().await.map_err(|e| e.to_string())?;
    if status == reqwest::StatusCode::NOT_FOUND {
        REVOKED.store(false, Ordering::SeqCst);
        return Ok(serde_json::json!({
            "revoked": false,
            "httpStatus": status.as_u16(),
            "note": "edge agent not registered — treating as not revoked",
        }));
    }
    if !status.is_success() {
        return Err(format!("kill-switch poll failed {status}: {text}"));
    }
    let body: ByDeviceResponse =
        serde_json::from_str(&text).map_err(|e| format!("kill-switch json: {e}: {text}"))?;
    let revoked = body.revoked_at.is_some();
    REVOKED.store(revoked, Ordering::SeqCst);
    Ok(serde_json::json!({
        "revoked": revoked,
        "httpStatus": status.as_u16(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn revoked_flag_roundtrip() {
        test_set_revoked(true);
        assert!(is_revoked());
        test_set_revoked(false);
        assert!(!is_revoked());
    }
}
