package export

import (
	"errors"
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

func TestRunExport_rejectsInvertedWindowWhenBothBounded(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if err := RunExport(dir, "a", 900, 100); err == nil {
		t.Fatal("expected error when both bounds non-zero and from > to")
	} else if !errors.Is(err, ErrExportWindow) {
		t.Fatalf("expected ErrExportWindow, got %v", err)
	}
}

func TestRunExport_allowsOpenEndedBounds(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	if err := RunExport(dir, "a", 100, 0); err != nil {
		t.Fatal(err)
	}
	if err := RunExport(dir, "b", 0, 200); err != nil {
		t.Fatal(err)
	}
}
