# Edge Agent Permissions (Story 1.15 spike)

This spike intentionally keeps permissions minimal while proving the first-launch
audio prompt path.

## What the app requests now

- **Microphone**: requested from the React shell on first launch using
  `navigator.mediaDevices.getUserMedia({ audio: true })`.
- **Credential store**: a local keychain write/read/delete round-trip via the
  Rust command `keychain_roundtrip` in `src-tauri/src/crypto.rs`.

## Why microphone appears

The first-launch prompt demonstrates the capture consent flow expected for Epic 6.
This spike stores a local flag (`deployai.edgeAgent.micPrompted.v1`) so the prompt
is shown once per machine profile by default.

## macOS notes

- The app bundle must include macOS usage descriptions before production release
  (`NSMicrophoneUsageDescription`).
- Notarization and hardened runtime settings are validated by CI when signing
  secrets are available.

## Security constraints

- No filesystem broad-write capability was added.
- No shell execution capability was added.
- The keychain round-trip deletes the stored test credential after verification.
