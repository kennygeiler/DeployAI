package export

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRunExport_writesLayout(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if err := RunExport(dir, "acct-test", 1, 2); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "manifest.json")); err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(filepath.Join(dir, "events.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	if len(b) == 0 {
		t.Fatal("expected placeholder events.jsonl")
	}
}
