// Package verify implements FR61/NFR29 signature + chain-of-custody verification.
//
// Empty in Story 1.3; real implementation lands in Epic 1 Story 1.12+.
package verify

// Description returns a human-readable banner for the CLI.
func Description() string {
	return "subcommands: verify <bundle-dir> (edge transcript v1/v2, optional --edge-revocation), export --out --account (Story 12.2 skeleton)"
}
