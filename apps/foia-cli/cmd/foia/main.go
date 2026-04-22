// Package main is the DeployAI FOIA verification CLI entry point (FR60, FR61, NFR29).
//
// Story 1.3 ships only the scaffold binary. Signature + chain-of-custody
// verification, envelope parsing, and export-bundle handling land in
// later Epic 1 stories (1.12+).
package main

import (
	"fmt"

	"github.com/kennygeiler/deployai/foia-cli/pkg/verify"
)

// Version is the CLI version; populated at build time via -ldflags, defaults to "0.0.0-scaffold".
var Version = "0.0.0-scaffold"

func main() {
	fmt.Printf("DeployAI FOIA CLI v%s\n", Version)
	fmt.Println(verify.Description())
}
