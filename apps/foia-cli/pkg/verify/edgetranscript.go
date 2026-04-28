package verify

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/digitorus/timestamp"
)

// Edge bundle format (Story 11.3 / 12.1). See docs/foia/bundle-format.md.
const EdgeTranscriptFormat = "deployai.edge.transcript.v1"

// EdgeTranscriptFormatV2 adds consent attestation hash to the signed payload (Story 11.4+).
const EdgeTranscriptFormatV2 = "deployai.edge.transcript.v2"

// EdgeTranscriptManifest is manifest.json for an edge transcript bundle.
type EdgeTranscriptManifest struct {
	Format              string `json:"format"`
	DeviceID            string `json:"deviceId"`
	PublicKeyEd25519B64 string `json:"publicKeyEd25519B64"`
	MerkleRootHex       string `json:"merkleRootHex"`
	TranscriptSHA256Hex string `json:"transcriptSha256Hex"`
	SegmentsFile        string `json:"segmentsFile"`
	CreatedAtUnixMs     int64  `json:"createdAtUnixMs"`
	ConsentSHA256Hex    string `json:"consentSha256Hex,omitempty"`
	RFC3161             *struct {
		TsaURL         string `json:"tsaUrl"`
		TokenDerBase64 string `json:"tokenDerBase64"`
	} `json:"rfc3161,omitempty"`
}

// EdgeTranscriptSigningPayload matches the edge-agent Rust canonical payload (UTF-8, trailing newline on last line).
func EdgeTranscriptSigningPayload(deviceID string, merkleRoot32, transcriptSHA256_32 []byte) []byte {
	var b strings.Builder
	b.WriteString("DEPLOYAI_EDGE_TRANSCRIPT_V1\n")
	b.WriteString("device_id:")
	b.WriteString(deviceID)
	b.WriteByte('\n')
	b.WriteString("merkle_root:")
	b.WriteString(hex.EncodeToString(merkleRoot32))
	b.WriteByte('\n')
	b.WriteString("transcript_sha256:")
	b.WriteString(hex.EncodeToString(transcriptSHA256_32))
	b.WriteByte('\n')
	return []byte(b.String())
}

// EdgeTranscriptSigningPayloadV2 matches the edge-agent v2 payload.
func EdgeTranscriptSigningPayloadV2(deviceID string, merkleRoot32, transcriptSHA256_32, consentSHA256_32 []byte) []byte {
	var b strings.Builder
	b.WriteString("DEPLOYAI_EDGE_TRANSCRIPT_V2\n")
	b.WriteString("device_id:")
	b.WriteString(deviceID)
	b.WriteByte('\n')
	b.WriteString("merkle_root:")
	b.WriteString(hex.EncodeToString(merkleRoot32))
	b.WriteByte('\n')
	b.WriteString("transcript_sha256:")
	b.WriteString(hex.EncodeToString(transcriptSHA256_32))
	b.WriteByte('\n')
	b.WriteString("consent_sha256:")
	b.WriteString(hex.EncodeToString(consentSHA256_32))
	b.WriteByte('\n')
	return []byte(b.String())
}

// MerkleRootChain mirrors the edge-agent sequential chain (32 zero seed).
func MerkleRootChain(segments []string) [32]byte {
	var acc [32]byte
	for _, s := range segments {
		h := sha256.New()
		h.Write(acc[:])
		h.Write([]byte(s))
		copy(acc[:], h.Sum(nil))
	}
	return acc
}

// VerifyEdgeTranscriptBundleDir checks Ed25519 signature, segment hash, and Merkle chain. Optional RFC3161 when present.
// If edgeRevocationPath is non-empty, loads a sidecar JSON listing device revocations and fails when createdAtUnixMs
// is at or after revokedAtUnixMs for the manifest deviceId (Story 11.7).
func VerifyEdgeTranscriptBundleDir(bundleDir string, publicKeyB64 string, skipTSA bool, edgeRevocationPath string) error {
	manifestPath := filepath.Join(bundleDir, "manifest.json")
	manifestBytes, err := os.ReadFile(manifestPath)
	if err != nil {
		return fmt.Errorf("read manifest: %w", err)
	}
	var mf EdgeTranscriptManifest
	if err := json.Unmarshal(manifestBytes, &mf); err != nil {
		return fmt.Errorf("manifest json: %w", err)
	}
	if mf.Format != EdgeTranscriptFormat && mf.Format != EdgeTranscriptFormatV2 {
		return fmt.Errorf("unsupported format %q (want %s or %s)", mf.Format, EdgeTranscriptFormat, EdgeTranscriptFormatV2)
	}
	segName := mf.SegmentsFile
	if segName == "" {
		segName = "segments.json"
	}
	segmentsPath := filepath.Join(bundleDir, segName)
	segmentsBytes, err := os.ReadFile(segmentsPath)
	if err != nil {
		return fmt.Errorf("read segments: %w", err)
	}
	var segs []string
	if err := json.Unmarshal(segmentsBytes, &segs); err != nil {
		return fmt.Errorf("segments json: %w", err)
	}

	transcriptSHA256 := sha256.Sum256(segmentsBytes)
	merkle := MerkleRootChain(segs)

	mrh, err := hex.DecodeString(mf.MerkleRootHex)
	if err != nil || len(mrh) != 32 {
		return errors.New("manifest merkleRootHex must be 64 hex chars (32 bytes)")
	}
	tsh, err := hex.DecodeString(mf.TranscriptSHA256Hex)
	if err != nil || len(tsh) != 32 {
		return errors.New("manifest transcriptSha256Hex must be 64 hex chars")
	}
	if !bytesEq(merkle[:], mrh) {
		return errors.New("merkle root does not match segments (chain tampered or wrong segments.json)")
	}
	if !bytesEq(transcriptSHA256[:], tsh) {
		return errors.New("transcript sha256 does not match segments.json bytes (tampered)")
	}

	pubB64 := strings.TrimSpace(mf.PublicKeyEd25519B64)
	if publicKeyB64 != "" {
		if strings.TrimSpace(publicKeyB64) != pubB64 {
			return errors.New("--public-key-b64 does not match manifest publicKeyEd25519B64")
		}
	}
	if pubB64 == "" {
		return errors.New("manifest missing publicKeyEd25519B64 and no --public-key-b64 provided")
	}
	pkb, err := base64.StdEncoding.DecodeString(pubB64)
	if err != nil || len(pkb) != ed25519.PublicKeySize {
		return errors.New("invalid Ed25519 public key (expect std base64, 32 bytes decoded)")
	}

	sigB64, err := os.ReadFile(filepath.Join(bundleDir, "transcript.sig"))
	if err != nil {
		return fmt.Errorf("read transcript.sig: %w", err)
	}
	sig, err := base64.StdEncoding.DecodeString(strings.TrimSpace(string(sigB64)))
	if err != nil || len(sig) != ed25519.SignatureSize {
		return errors.New("transcript.sig must be base64-encoded 64-byte Ed25519 signature")
	}

	var payload []byte
	switch mf.Format {
	case EdgeTranscriptFormat:
		payload = EdgeTranscriptSigningPayload(mf.DeviceID, mrh, tsh)
	case EdgeTranscriptFormatV2:
		ch, err := decodeConsentSHA256Hex(mf.ConsentSHA256Hex)
		if err != nil {
			return err
		}
		payload = EdgeTranscriptSigningPayloadV2(mf.DeviceID, mrh, tsh, ch)
	default:
		return fmt.Errorf("unsupported format %q", mf.Format)
	}
	if !ed25519.Verify(pkb, payload, sig) {
		return errors.New("Ed25519 signature verification failed (payload or key does not match bundle)")
	}

	if edgeRevocationPath != "" {
		rev, err := loadEdgeRevocationFile(edgeRevocationPath)
		if err != nil {
			return fmt.Errorf("edge revocation list: %w", err)
		}
		if err := checkEdgeRevocation(mf.DeviceID, mf.CreatedAtUnixMs, rev); err != nil {
			return err
		}
	}

	if mf.RFC3161 != nil && mf.RFC3161.TokenDerBase64 != "" && !skipTSA {
		raw, err := base64.StdEncoding.DecodeString(mf.RFC3161.TokenDerBase64)
		if err != nil {
			return fmt.Errorf("rfc3161 tokenDerBase64: %w", err)
		}
		ts, err := timestamp.Parse(raw)
		if err != nil {
			return fmt.Errorf("rfc3161 parse/verify: %w", err)
		}
		if !bytesEq(ts.HashedMessage, mrh) {
			return errors.New("RFC3161 message imprint does not match merkle root")
		}
	}

	return nil
}

func decodeConsentSHA256Hex(s string) ([]byte, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return make([]byte, 32), nil
	}
	b, err := hex.DecodeString(s)
	if err != nil || len(b) != 32 {
		return nil, errors.New("consentSha256Hex must be 64 hex chars (32 bytes) or omitted for all-zero")
	}
	return b, nil
}

func bytesEq(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	var v byte
	for i := range a {
		v |= a[i] ^ b[i]
	}
	return v == 0
}
