# Edge Agent Platform Assessment (Story 1.15)

Date: 2026-04-23  
Scope: Signed Hello-World spike on macOS, keychain round-trip, audio permission prompt, Sparkle feed stub.

## Summary

The spike proves that the Tauri shell can:

- request microphone access on first launch,
- perform a local keychain write/read/delete round-trip from Rust,
- produce a Sparkle-compatible appcast stub for signed updates,
- run a macOS CI workflow that builds the Tauri app and publishes artifacts.

## Findings

1. **Code signing/notarization is environment-dependent**  
   Full notarization requires Apple Developer credentials and keychain setup on CI.
   The workflow gates those steps behind secrets, while still producing build artifacts
   when secrets are absent.

2. **Tauri build output shape depends on bundle settings**  
   `bundle.active` must be enabled for packaging workflows to emit `.app/.dmg/.app.tar.gz`
   artifacts in predictable locations.

3. **Audio prompt behavior is WebView/runtime specific**  
   `getUserMedia` prompt behavior is reliable on macOS desktop with system prompts, but the
   exact UX differs by OS and prior consent state; explicit docs are required for support.

4. **Credential store integration is straightforward**  
   The `keyring` crate provided a simple way to validate local secret persistence without
   introducing additional unsafe platform bindings in this story.

## Risks / follow-ups for Epic 11

- Replace placeholder `appcast.xml` enclosure URL + signature with release automation.
- Promote signing/notarization from optional to required in CI once secrets are provisioned.
- Add explicit macOS entitlements/usage strings checks in CI.
- Add Windows code-signing parity + update feed validation for WinSparkle path.
- Add an end-to-end updater verification test (download + signature check + apply).
