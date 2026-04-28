//! CI/release helper: sign an update archive the same way Sparkle's `sign_update` does (Ed25519 over raw file bytes).
//! Usage: `SPARKLE_PRIVATE_KEY_SEED_B64=<std-b64-32-bytes> sign-sparkle-archive /path/to/file.dmg`
//! Or: `sign-sparkle-archive --print-public-key` with the same env var to emit SUPublicEDKey (std base64).

use base64::Engine;
use ed25519_dalek::{Signer, SigningKey};
use std::io::Write;

fn usage() -> ! {
    eprintln!(
        "Usage:\n  SPARKLE_PRIVATE_KEY_SEED_B64=... sign-sparkle-archive <archive-path>\n  SPARKLE_PRIVATE_KEY_SEED_B64=... sign-sparkle-archive --print-public-key"
    );
    std::process::exit(2);
}

fn load_signing_key() -> SigningKey {
    let seed_b64 = std::env::var("SPARKLE_PRIVATE_KEY_SEED_B64").unwrap_or_default();
    let raw = base64::engine::general_purpose::STANDARD
        .decode(seed_b64.trim())
        .expect("SPARKLE_PRIVATE_KEY_SEED_B64 must be standard base64 of 32-byte seed");
    if raw.len() != 32 {
        eprintln!("seed must decode to exactly 32 bytes");
        std::process::exit(1);
    }
    let arr: [u8; 32] = raw.try_into().expect("length");
    SigningKey::from_bytes(&arr)
}

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        usage();
    }
    if args[0] == "--print-public-key" {
        let sk = load_signing_key();
        let pk = sk.verifying_key();
        let b64 = base64::engine::general_purpose::STANDARD.encode(pk.to_bytes());
        println!("{b64}");
        return;
    }
    let path = std::mem::take(&mut args[0]);
    let sk = load_signing_key();
    let bytes = std::fs::read(&path).unwrap_or_else(|e| {
        eprintln!("read {path}: {e}");
        std::process::exit(1);
    });
    let sig = sk.sign(&bytes);
    let enc = base64::engine::general_purpose::STANDARD.encode(sig.to_bytes());
    let mut out = std::io::stdout();
    write!(
        &mut out,
        "sparkle:edSignature=\"{}\" length=\"{}\"",
        enc,
        bytes.len()
    )
    .expect("write");
    writeln!(&mut out).expect("write");
}
