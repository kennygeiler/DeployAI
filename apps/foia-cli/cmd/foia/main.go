// Package main is the DeployAI FOIA verification CLI entry point (FR60, FR61, NFR29).
package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"

	"github.com/kennygeiler/deployai/foia-cli/pkg/export"
	"github.com/kennygeiler/deployai/foia-cli/pkg/verify"
)

// Version is the CLI version; populated at build time via -ldflags, defaults to "0.0.0-scaffold".
var Version = "0.0.0-scaffold"

func usage() {
	fmt.Fprintf(os.Stderr, `DeployAI FOIA CLI v%s

Usage:
  foia verify [flags] <bundle-dir>
  foia export [flags]

Verify checks deployai.edge.transcript.v1/v2 bundles offline: Ed25519 detached signature,
Merkle chain, optional consent hash (v2), optional RFC3161 token, optional --edge-revocation (Story 11.7).

`, Version)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Printf("DeployAI FOIA CLI v%s\n", Version)
		fmt.Println(verify.Description())
		os.Exit(0)
	}

	switch os.Args[1] {
	case "verify":
		if err := runVerify(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "verify: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("verify: OK")
	case "export":
		if err := runExport(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "export: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("export: OK")
	case "-h", "--help", "help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func runVerify(args []string) error {
	fs := flag.NewFlagSet("verify", flag.ContinueOnError)
	pub := fs.String("public-key-b64", "", "Ed25519 public key (std base64); must match manifest if both set")
	skipTSA := fs.Bool("skip-tsa", false, "Skip RFC3161 checks even if token is present")
	edgeRev := fs.String("edge-revocation", "", "JSON sidecar: revocations[].deviceId + revokedAtUnixMs (Story 11.7)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	rest := fs.Args()
	if len(rest) != 1 {
		return fmt.Errorf("expected exactly one bundle directory argument")
	}
	return verify.VerifyEdgeTranscriptBundleDir(rest[0], *pub, *skipTSA, *edgeRev)
}

func runExport(args []string) error {
	fs := flag.NewFlagSet("export", flag.ContinueOnError)
	out := fs.String("out", "", "output directory (required)")
	acct := fs.String("account", "", "account identifier label (required)")
	from := fs.String("from", "0", "export window start (unix ms)")
	to := fs.String("to", "0", "export window end (unix ms)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return fmt.Errorf("unexpected arguments: %v", fs.Args())
	}
	if *out == "" || *acct == "" {
		return fmt.Errorf("--out and --account are required")
	}
	fromMs, err := strconv.ParseInt(*from, 10, 64)
	if err != nil {
		return fmt.Errorf("--from: %w", err)
	}
	toMs, err := strconv.ParseInt(*to, 10, 64)
	if err != nil {
		return fmt.Errorf("--to: %w", err)
	}
	return export.RunExport(*out, *acct, fromMs, toMs)
}
