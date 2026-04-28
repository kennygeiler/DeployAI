package verify

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestVerifyEdgeTranscriptBundleDir_roundTrip(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	segs := []string{"alpha", "beta"}
	segBytes, err := json.Marshal(segs)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "segments.json"), segBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	th := sha256.Sum256(segBytes)
	mr := MerkleRootChain(segs)
	payload := EdgeTranscriptSigningPayload("device-1", mr[:], th[:])
	sig := ed25519.Sign(priv, payload)
	sigB64 := base64.StdEncoding.EncodeToString(sig)
	if err := os.WriteFile(filepath.Join(dir, "transcript.sig"), []byte(sigB64), 0o600); err != nil {
		t.Fatal(err)
	}
	mf := map[string]any{
		"format":              EdgeTranscriptFormat,
		"deviceId":            "device-1",
		"publicKeyEd25519B64": base64.StdEncoding.EncodeToString(pub),
		"merkleRootHex":       hex.EncodeToString(mr[:]),
		"transcriptSha256Hex": hex.EncodeToString(th[:]),
		"segmentsFile":        "segments.json",
		"createdAtUnixMs":     int64(0),
	}
	mb, err := json.MarshalIndent(mf, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), mb, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, ""); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "segments.json"), []byte(`["alpha","gamma"]`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, ""); err == nil {
		t.Fatal("expected error after tamper")
	}
}

func testdataDir(t *testing.T, name string) string {
	t.Helper()
	dir, err := filepath.Abs(filepath.Join("..", "..", "testdata", name))
	if err != nil {
		t.Fatal(err)
	}
	return dir
}

func TestVerifyGoldenCommittedBundle_valid(t *testing.T) {
	t.Parallel()
	dir := testdataDir(t, "edge-transcript-v1-valid")
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, ""); err != nil {
		t.Fatal(err)
	}
}

func TestVerifyGoldenCommittedBundle_tampered(t *testing.T) {
	t.Parallel()
	dir := testdataDir(t, "edge-transcript-v1-tampered")
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, ""); err == nil {
		t.Fatal("expected verify failure for tampered segments with original signature")
	}
}

func TestVerifyEdgeTranscriptBundleDir_v2RoundTrip(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	segs := []string{"v2-a", "v2-b"}
	segBytes, err := json.Marshal(segs)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "segments.json"), segBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	th := sha256.Sum256(segBytes)
	mr := MerkleRootChain(segs)
	consent := sha256.Sum256([]byte(`{"version":1}`))
	payload := EdgeTranscriptSigningPayloadV2("dev-v2", mr[:], th[:], consent[:])
	sig := ed25519.Sign(priv, payload)
	sigB64 := base64.StdEncoding.EncodeToString(sig)
	if err := os.WriteFile(filepath.Join(dir, "transcript.sig"), []byte(sigB64), 0o600); err != nil {
		t.Fatal(err)
	}
	mf := map[string]any{
		"format":              EdgeTranscriptFormatV2,
		"deviceId":            "dev-v2",
		"publicKeyEd25519B64": base64.StdEncoding.EncodeToString(pub),
		"merkleRootHex":       hex.EncodeToString(mr[:]),
		"transcriptSha256Hex": hex.EncodeToString(th[:]),
		"segmentsFile":        "segments.json",
		"createdAtUnixMs":     int64(42),
		"consentSha256Hex":    hex.EncodeToString(consent[:]),
	}
	mb, err := json.MarshalIndent(mf, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), mb, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, ""); err != nil {
		t.Fatal(err)
	}
	revPath := filepath.Join(dir, "revoke.json")
	rev := map[string]any{
		"revocations": []map[string]any{
			{"deviceId": "dev-v2", "revokedAtUnixMs": 100},
		},
	}
	rb, _ := json.Marshal(rev)
	if err := os.WriteFile(revPath, rb, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, revPath); err != nil {
		t.Fatal(err)
	}
	mfLate := map[string]any{
		"format":              EdgeTranscriptFormatV2,
		"deviceId":            "dev-v2",
		"publicKeyEd25519B64": base64.StdEncoding.EncodeToString(pub),
		"merkleRootHex":       hex.EncodeToString(mr[:]),
		"transcriptSha256Hex": hex.EncodeToString(th[:]),
		"segmentsFile":        "segments.json",
		"createdAtUnixMs":     int64(200),
		"consentSha256Hex":    hex.EncodeToString(consent[:]),
	}
	mb2, _ := json.MarshalIndent(mfLate, "", "  ")
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), mb2, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyEdgeTranscriptBundleDir(dir, "", false, revPath); err == nil {
		t.Fatal("expected revocation failure when createdAtUnixMs is after revokedAtUnixMs")
	}
}
