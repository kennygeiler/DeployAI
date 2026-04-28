// Command gen-golden-edge-bundle writes committed FOIA verifier fixtures (Story 11.6).
// Run from apps/foia-cli: go run ./hack/gen-golden-edge-bundle
package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
)

func merkle(segs []string) [32]byte {
	var acc [32]byte
	for _, s := range segs {
		h := sha256.New()
		h.Write(acc[:])
		h.Write([]byte(s))
		copy(acc[:], h.Sum(nil))
	}
	return acc
}

func payload(device string, mr, th [32]byte) []byte {
	s := "DEPLOYAI_EDGE_TRANSCRIPT_V1\ndevice_id:" + device +
		"\nmerkle_root:" + hex.EncodeToString(mr[:]) +
		"\ntranscript_sha256:" + hex.EncodeToString(th[:]) + "\n"
	return []byte(s)
}

func main() {
	root := filepath.Join("testdata", "edge-transcript-v1-valid")
	troot := filepath.Join("testdata", "edge-transcript-v1-tampered")
	_ = os.MkdirAll(root, 0o755)
	_ = os.MkdirAll(troot, 0o755)

	seed := sha256.Sum256([]byte("deployai-golden-edge-transcript-v1"))
	priv := ed25519.NewKeyFromSeed(seed[:32])
	pub := priv.Public().(ed25519.PublicKey)
	segs := []string{"fixture-a", "fixture-b"}
	segBytes, _ := json.Marshal(segs)
	th := sha256.Sum256(segBytes)
	mr := merkle(segs)
	sig := ed25519.Sign(priv, payload("golden-device", mr, th))

	_ = os.WriteFile(filepath.Join(root, "segments.json"), segBytes, 0o644)
	_ = os.WriteFile(filepath.Join(root, "transcript.sig"), []byte(base64.StdEncoding.EncodeToString(sig)), 0o644)
	mf := map[string]any{
		"format":              "deployai.edge.transcript.v1",
		"deviceId":            "golden-device",
		"publicKeyEd25519B64": base64.StdEncoding.EncodeToString(pub),
		"merkleRootHex":       hex.EncodeToString(mr[:]),
		"transcriptSha256Hex": hex.EncodeToString(th[:]),
		"segmentsFile":        "segments.json",
		"createdAtUnixMs":     0,
	}
	mb, _ := json.MarshalIndent(mf, "", "  ")
	_ = os.WriteFile(filepath.Join(root, "manifest.json"), mb, 0o644)

	tamper := []string{"fixture-a", "fixture-X"}
	tb, _ := json.Marshal(tamper)
	_ = os.WriteFile(filepath.Join(troot, "segments.json"), tb, 0o644)
	_ = os.WriteFile(filepath.Join(troot, "manifest.json"), mb, 0o644)
	_ = os.WriteFile(filepath.Join(troot, "transcript.sig"), []byte(base64.StdEncoding.EncodeToString(sig)), 0o644)
	println("wrote", root, "and", troot)
}
