package main

import "testing"

func TestVersionDefault(t *testing.T) {
	if Version == "" {
		t.Fatalf("Version should not be empty")
	}
}
