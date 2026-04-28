//! Story 11.2 — stable device id + Ed25519 signing key in the OS credential store.

use std::path::PathBuf;

use base64::Engine;
use ed25519_dalek::SigningKey;
use rand::rngs::OsRng;
use serde::Serialize;
use tauri::Manager;

const KEYRING_SERVICE: &str = "app.deployai.edge-agent";
const KEYRING_ACCOUNT: &str = "ed25519-signing-key-v1";
const DEVICE_FILE: &str = "device_id_v1.txt";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SigningIdentityPublic {
    pub device_id: String,
    pub public_key_ed25519_b64: String,
}

fn app_data_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_local_data_dir()
        .map_err(|e| format!("app_local_data_dir: {e}"))
}

fn read_or_create_device_id(app: &tauri::AppHandle) -> Result<String, String> {
    let dir = app_data_dir(app)?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("create_dir_all: {e}"))?;
    let path = dir.join(DEVICE_FILE);
    if path.exists() {
        let s = std::fs::read_to_string(&path).map_err(|e| format!("read device_id: {e}"))?;
        let t = s.trim();
        if t.is_empty() {
            return Err("device_id file empty".into());
        }
        return Ok(t.to_string());
    }
    let id = uuid::Uuid::new_v4().to_string();
    std::fs::write(&path, &id).map_err(|e| format!("write device_id: {e}"))?;
    Ok(id)
}

fn keyring_entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT).map_err(|e| format!("keyring entry: {e}"))
}

pub(crate) fn load_or_create_signing_key() -> Result<SigningKey, String> {
    let entry = keyring_entry()?;
    if let Ok(s) = entry.get_password() {
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(s.trim())
            .map_err(|e| format!("decode stored key: {e}"))?;
        if bytes.len() != 32 {
            return Err("stored signing key has wrong length".into());
        }
        let arr: [u8; 32] = bytes
            .try_into()
            .map_err(|_| "stored signing key: bad length".to_string())?;
        return Ok(SigningKey::from_bytes(&arr));
    }
    let sk = SigningKey::generate(&mut OsRng);
    let enc = base64::engine::general_purpose::STANDARD.encode(sk.to_bytes());
    entry
        .set_password(&enc)
        .map_err(|e| format!("store signing key: {e}"))?;
    Ok(sk)
}

/// Ensure a stable device UUID (on disk under app local data) and Ed25519 keypair (in keychain).
pub fn ensure_signing_identity(app: &tauri::AppHandle) -> Result<SigningIdentityPublic, String> {
    let device_id = read_or_create_device_id(app)?;
    let sk = load_or_create_signing_key()?;
    let vk = sk.verifying_key();
    let public_key_ed25519_b64 = base64::engine::general_purpose::STANDARD.encode(vk.to_bytes());
    Ok(SigningIdentityPublic {
        device_id,
        public_key_ed25519_b64,
    })
}

#[tauri::command]
pub fn edge_agent_signing_identity(app: tauri::AppHandle) -> Result<SigningIdentityPublic, String> {
    ensure_signing_identity(&app)
}

#[tauri::command]
pub async fn edge_agent_register_with_control_plane(
    app: tauri::AppHandle,
    base_url: String,
    tenant_id: String,
    internal_api_key: String,
) -> Result<serde_json::Value, String> {
    let ident = ensure_signing_identity(&app)?;
    let b = base_url.trim_end_matches('/').to_string();
    let url = format!("{b}/internal/v1/edge-agents/register");
    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let body = serde_json::json!({
        "tenant_id": tenant_id.trim(),
        "device_id": ident.device_id,
        "public_key_ed25519_b64": ident.public_key_ed25519_b64,
    });
    let resp = client
        .post(&url)
        .header(
            "X-DeployAI-Internal-Key",
            internal_api_key.trim().to_string(),
        )
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("register request: {e}"))?;
    let status = resp.status();
    let text = resp.text().await.map_err(|e| e.to_string())?;
    if !status.is_success() {
        return Err(format!("register failed {status}: {text}"));
    }
    serde_json::from_str(&text).map_err(|e| format!("register json: {e}: {text}"))
}
