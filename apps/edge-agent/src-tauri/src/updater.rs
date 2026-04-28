//! Story 11.5 — Sparkle-compatible update feed: parse `appcast.xml`, verify `sparkle:edSignature` (Ed25519) over archive bytes.
//!
//! Sparkle's `sign_update` signs the **raw update archive** (dmg/zip/tar) with Ed25519. This module mirrors that check in Rust before any replace/relaunch logic runs (apply-update wiring is platform-specific and may use Sparkle.framework in a future native shell).

use base64::Engine;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::Serialize;

/// First `<item>` in the feed (Sparkle convention: newest release first).
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SparkleItemSummary {
    pub sparkle_version: Option<String>,
    pub short_version_string: Option<String>,
    pub enclosure_url: String,
    pub ed_signature_b64: String,
    pub length: u64,
}

fn find_first_complete_item(xml: &str) -> Option<&str> {
    let start = xml.find("<item")?;
    let open_end = xml[start..].find('>')? + start + 1;
    let close = xml[open_end..].find("</item>")? + open_end;
    Some(&xml[open_end..close])
}

fn sparkle_tag_text(item_xml: &str, tag: &str) -> Option<String> {
    let open = format!("<sparkle:{tag}>");
    let close = format!("</sparkle:{tag}>");
    let i = item_xml.find(&open)? + open.len();
    let end = item_xml[i..].find(&close)?;
    Some(item_xml[i..i + end].trim().to_string())
}

/// Pull `<sparkle:version>` / `<sparkle:shortVersionString>` from raw item XML.
fn parse_sparkle_version_fields(item_xml: &str) -> (Option<String>, Option<String>) {
    let ver = sparkle_tag_text(item_xml, "version");
    let short = sparkle_tag_text(item_xml, "shortVersionString");
    (ver, short)
}

fn attr_value(open_tag_slice: &str, attr: &str) -> Option<String> {
    let needle = format!("{attr}=\"");
    let i = open_tag_slice.find(&needle)? + needle.len();
    let end = open_tag_slice[i..].find('"')?;
    Some(open_tag_slice[i..i + end].to_string())
}

/// Parse the first `<enclosure .../>` in an item block (attributes may appear in any order).
fn parse_enclosure_in_item(item_xml: &str) -> Result<(String, String, u64), String> {
    let enc_rel = item_xml
        .find("<enclosure")
        .ok_or_else(|| "item missing <enclosure".to_string())?;
    let from_enc = &item_xml[enc_rel..];
    let tag_end = if let Some(i) = from_enc.find("/>") {
        i
    } else {
        from_enc
            .find('>')
            .ok_or_else(|| "malformed enclosure tag".to_string())?
    };
    let open = &from_enc[..tag_end];
    let url = attr_value(open, "url").ok_or_else(|| "enclosure missing url".to_string())?;
    let sig = attr_value(open, "sparkle:edSignature")
        .ok_or_else(|| "enclosure missing sparkle:edSignature".to_string())?;
    let len_s = attr_value(open, "length").ok_or_else(|| "enclosure missing length".to_string())?;
    let length: u64 = len_s
        .parse()
        .map_err(|_| "enclosure length must be integer".to_string())?;
    Ok((url, sig, length))
}

/// Parse the first channel item from a Sparkle appcast RSS document.
pub fn parse_sparkle_appcast_first_item(xml: &str) -> Result<SparkleItemSummary, String> {
    let item = find_first_complete_item(xml).ok_or_else(|| "appcast missing <item>".to_string())?;
    let (sparkle_version, short_version_string) = parse_sparkle_version_fields(item);
    let (enclosure_url, ed_signature_b64, length) = parse_enclosure_in_item(item)?;
    Ok(SparkleItemSummary {
        sparkle_version,
        short_version_string,
        enclosure_url,
        ed_signature_b64,
        length,
    })
}

/// Verify Sparkle `edSignature` (standard Base64, 64-byte Ed25519) over the full archive bytes.
pub fn verify_sparkle_archive_ed25519(
    archive_bytes: &[u8],
    ed_signature_b64: &str,
    public_key_ed25519_b64: &str,
    expected_length: u64,
) -> Result<(), String> {
    if archive_bytes.len() as u64 != expected_length {
        return Err(format!(
            "archive size {} does not match appcast length {}",
            archive_bytes.len(),
            expected_length
        ));
    }
    let sig_bytes = base64::engine::general_purpose::STANDARD
        .decode(ed_signature_b64.trim())
        .map_err(|e| format!("edSignature base64: {e}"))?;
    if sig_bytes.len() != 64 {
        return Err("edSignature must decode to 64 bytes".into());
    }
    let sig_arr: [u8; 64] = sig_bytes
        .as_slice()
        .try_into()
        .map_err(|_| "invalid Ed25519 signature length".to_string())?;
    let sig = Signature::from_bytes(&sig_arr);
    let pk_bytes = base64::engine::general_purpose::STANDARD
        .decode(public_key_ed25519_b64.trim())
        .map_err(|e| format!("public key base64: {e}"))?;
    if pk_bytes.len() != 32 {
        return Err("Ed25519 public key must be 32 bytes (std base64)".into());
    }
    let pk_arr: [u8; 32] = pk_bytes
        .as_slice()
        .try_into()
        .map_err(|_| "bad public key length".to_string())?;
    let vk = VerifyingKey::from_bytes(&pk_arr).map_err(|e| e.to_string())?;
    vk.verify(archive_bytes, &sig).map_err(|_| {
        "Ed25519 verify failed (archive does not match sparkle:edSignature / wrong key)".to_string()
    })
}

#[tauri::command]
pub async fn edge_agent_sparkle_fetch_latest_item(
    appcast_url: String,
) -> Result<serde_json::Value, String> {
    let url = appcast_url.trim().to_string();
    if url.is_empty() {
        return Err("appcast_url required".into());
    }
    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("appcast fetch: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("appcast HTTP {}", resp.status()));
    }
    let xml = resp.text().await.map_err(|e| e.to_string())?;
    let item = parse_sparkle_appcast_first_item(&xml)?;
    serde_json::to_value(&item).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn edge_agent_sparkle_verify_local_archive(
    archive_path: String,
    ed_signature_b64: String,
    public_key_ed25519_b64: String,
    expected_length: u64,
) -> Result<serde_json::Value, String> {
    let bytes = std::fs::read(archive_path.trim()).map_err(|e| format!("read archive: {e}"))?;
    verify_sparkle_archive_ed25519(
        &bytes,
        &ed_signature_b64,
        &public_key_ed25519_b64,
        expected_length,
    )?;
    Ok(serde_json::json!({ "ok": true }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::Signer;
    use rand::rngs::OsRng;

    #[test]
    fn ed25519_sign_verify_matches_sparkle_tool_convention() {
        let sk = ed25519_dalek::SigningKey::generate(&mut OsRng);
        let vk = sk.verifying_key();
        let archive = b"fake-dmg-bytes-for-test";
        let sig = sk.sign(archive);
        let sig_b64 = base64::engine::general_purpose::STANDARD.encode(sig.to_bytes());
        let pk_b64 = base64::engine::general_purpose::STANDARD.encode(vk.to_bytes());
        verify_sparkle_archive_ed25519(archive, &sig_b64, &pk_b64, archive.len() as u64).unwrap();
        let mut bad = archive.to_vec();
        bad[0] ^= 0xff;
        assert!(verify_sparkle_archive_ed25519(&bad, &sig_b64, &pk_b64, bad.len() as u64).is_err());
    }

    #[test]
    fn parse_minimal_appcast_item() {
        let xml = r#"<?xml version="1.0"?><rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" version="2.0"><channel><item>
<sparkle:version>1</sparkle:version>
<sparkle:shortVersionString>0.1.0</sparkle:shortVersionString>
<enclosure url="https://x.test/a.dmg" sparkle:edSignature="abc=" length="9" type="application/octet-stream"/>
</item></channel></rss>"#;
        let item = parse_sparkle_appcast_first_item(xml).unwrap();
        assert_eq!(item.enclosure_url, "https://x.test/a.dmg");
        assert_eq!(item.ed_signature_b64, "abc=");
        assert_eq!(item.length, 9);
        assert_eq!(item.sparkle_version.as_deref(), Some("1"));
    }
}
