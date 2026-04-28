// Package export implements Story 12.2 skeleton layout for canonical-memory FOIA bundles.
package export

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// RunExport writes a minimal directory layout: manifest.json + placeholder events.jsonl.
func RunExport(outDir, account string, fromMs, toMs int64) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	now := time.Now().UnixMilli()
	mf := map[string]any{
		"format":           "deployai.foia.export.v0",
		"accountId":        account,
		"createdAtUnixMs":  now,
		"exportFromUnixMs": fromMs,
		"exportToUnixMs":   toMs,
		"eventsFile":       "events.jsonl",
		"schemaNote":       "Story 12.2 skeleton — replace with canonical-memory export",
	}
	b, err := json.MarshalIndent(mf, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(outDir, "manifest.json"), b, 0o644); err != nil {
		return err
	}
	evPath := filepath.Join(outDir, "events.jsonl")
	f, err := os.OpenFile(evPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.WriteString("# placeholder events.jsonl (Story 12.2 skeleton)\n")
	return err
}
