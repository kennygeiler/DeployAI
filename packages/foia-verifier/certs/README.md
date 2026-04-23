# Public trust material (Placeholders, Story 1-13)

For production (Epic 12 Go CLI) this directory would ship:

- The FreeTSA TSA / CA public certificates in PEM form for **offline** TSR chain verification
- (Optional) AWS TSA public materials when a secondary chain is used

V1 `verifyTsrStub` only checks the in-repo stub prefix used by `deployai-tsa` tests. Full ASN.1 + CMS verification lands with the `apps/foia-cli` hardening work.
