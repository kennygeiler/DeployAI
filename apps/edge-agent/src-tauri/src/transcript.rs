//! Story 11.3 — tamper-evident local transcript: SHA256 Merkle chain + Ed25519 detached signature + optional RFC3161.

use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use base64::Engine;
use ed25519_dalek::Signer;
use serde::Serialize;
use tauri::Manager;
use sha2::{Digest, Sha256};
use tsp_ltv::crypto::algorithm::DigestAlgorithm;
use tsp_ltv::tsp::TsaClient;

use crate::device_identity::{ensure_signing_identity, load_or_create_signing_key};

pub const FORMAT: &str = "deployai.edge.transcript.v1";
const PAYLOAD_LINE: &str = "DEPLOYAI_EDGE_TRANSCRIPT_V1";

/// Canonical JSON array of segment strings (compact, stable key order).
pub fn canonical_segments_json(segments: &[String]) -> Result<Vec<u8>, String> {
    serde_json::to_vec(segments).map_err(|e| e.to_string())
}

/// Sequential Merkle chain: acc := SHA256(acc || utf8(segment)), starting acc = 32 zero bytes.
pub fn merkle_root_chain(segments: &[String]) -> [u8; 32] {
    let mut acc = [0u8; 32];
    for s in segments {
        let mut h = Sha256::new();
        h.update(&acc);
        h.update(s.as_bytes());
        acc.copy_from_slice(&h.finalize());
    }
    acc
}

pub fn signing_payload(
    device_id: &str,
    merkle_root: &[u8; 32],
    transcript_sha256: &[u8; 32],
) -> Vec<u8> {
    let mut msg = String::new();
    msg.push_str(PAYLOAD_LINE);
    msg.push('\n');
    msg.push_str("device_id:");
    msg.push_str(device_id);
    msg.push('\n');
    msg.push_str("merkle_root:");
    msg.push_str(&hex::encode(merkle_root));
    msg.push('\n');
    msg.push_str("transcript_sha256:");
    msg.push_str(&hex::encode(transcript_sha256));
    msg.push('\n');
    msg.into_bytes()
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Rfc3161Meta {
    tsa_url: String,
    token_der_base64: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Manifest {
    format: String,
    device_id: String,
    public_key_ed25519_b64: String,
    merkle_root_hex: String,
    transcript_sha256_hex: String,
    created_at_unix_ms: i64,
    segments_file: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    rfc3161: Option<Rfc3161Meta>,
}

fn app_data_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_local_data_dir()
        .map_err(|e| format!("app_local_data_dir: {e}"))
}

async fn maybe_rfc3161(
    merkle_root: &[u8; 32],
    attach: bool,
) -> Result<Option<Rfc3161Meta>, String> {
    if !attach {
        return Ok(None);
    }
    let url = std::env::var("DEPLOYAI_EDGE_TSA_URL")
        .unwrap_or_else(|_| "https://freetsa.org/tsr".to_string());
    let http = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_secs(25))
        .build()
        .map_err(|e| e.to_string())?;
    let client = TsaClient::new(url.trim())
        .digest_algorithm(DigestAlgorithm::Sha256)
        .timeout(std::time::Duration::from_secs(25))
        .http_client(http);
    let token = client
        .timestamp(merkle_root.as_slice())
        .await
        .map_err(|e| format!("rfc3161 timestamp: {e}"))?;
    Ok(Some(Rfc3161Meta {
        tsa_url: url,
        token_der_base64: base64::engine::general_purpose::STANDARD.encode(token),
    }))
}

/// Writes `segments.json`, `transcript.sig` (base64 Ed25519), and `manifest.json` under `app_local_data/transcripts/<uuid>/`.
#[tauri::command]
pub async fn edge_agent_write_transcript_bundle(
    app: tauri::AppHandle,
    segments: Vec<String>,
    attach_rfc3161: bool,
) -> Result<serde_json::Value, String> {
    let ident = ensure_signing_identity(&app)?;
    let sk = load_or_create_signing_key()?;

    let segments_bytes = canonical_segments_json(&segments)?;
    let transcript_sha256: [u8; 32] = Sha256::digest(&segments_bytes).into();
    let merkle_root = merkle_root_chain(&segments);
    let payload = signing_payload(&ident.device_id, &merkle_root, &transcript_sha256);
    let sig = sk.sign(&payload);
    let sig_b64 = base64::engine::general_purpose::STANDARD.encode(sig.to_bytes());

    let rfc3161 = maybe_rfc3161(&merkle_root, attach_rfc3161).await?;

    let dir = app_data_dir(&app)?;
    let bundle = dir.join("transcripts").join(uuid::Uuid::new_v4().to_string());
    std::fs::create_dir_all(&bundle).map_err(|e| format!("create bundle dir: {e}"))?;

    std::fs::write(bundle.join("segments.json"), &segments_bytes)
        .map_err(|e| format!("write segments.json: {e}"))?;
    std::fs::write(bundle.join("transcript.sig"), sig_b64.trim())
        .map_err(|e| format!("write transcript.sig: {e}"))?;

    let created_at_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_millis() as i64;

    let manifest = Manifest {
        format: FORMAT.to_string(),
        device_id: ident.device_id.clone(),
        public_key_ed25519_b64: ident.public_key_ed25519_b64,
        merkle_root_hex: hex::encode(merkle_root),
        transcript_sha256_hex: hex::encode(transcript_sha256),
        created_at_unix_ms,
        segments_file: "segments.json".to_string(),
        rfc3161,
    };
    let mf = serde_json::to_string_pretty(&manifest).map_err(|e| e.to_string())?;
    std::fs::write(bundle.join("manifest.json"), mf)
        .map_err(|e| format!("write manifest.json: {e}"))?;

    serde_json::to_value(serde_json::json!({
        "bundleDir": bundle.to_string_lossy(),
    }))
    .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{SigningKey, Verifier};
    use rand::rngs::OsRng;

    #[test]
    fn merkle_chain_order_matters() {
        let a = merkle_root_chain(&["x".into(), "y".into()]);
        let b = merkle_root_chain(&["y".into(), "x".into()]);
        assert_ne!(a, b);
    }

    #[test]
    fn tamper_segment_invalidates_signature() {
        let sk = SigningKey::generate(&mut OsRng);
        let vk = sk.verifying_key();
        let segs = vec!["hello".into(), "world".into()];
        let sj = canonical_segments_json(&segs).unwrap();
        let tsh: [u8; 32] = Sha256::digest(&sj).into();
        let mr = merkle_root_chain(&segs);
        let payload = signing_payload("dev-device", &mr, &tsh);
        let sig = sk.sign(&payload);

        let mut bad = segs.clone();
        bad[0] = "hallo".into();
        let sj2 = canonical_segments_json(&bad).unwrap();
        let tsh2: [u8; 32] = Sha256::digest(&sj2).into();
        let mr2 = merkle_root_chain(&bad);
        assert_ne!(tsh, tsh2);
        let ok = vk.verify(&payload, &sig);
        assert!(ok.is_ok());
        let payload2 = signing_payload("dev-device", &mr2, &tsh2);
        assert!(vk.verify(&payload2, &sig).is_err());
    }
}
