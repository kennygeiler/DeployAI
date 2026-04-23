"""Fuzz harnesses for DeployAI control-plane security invariants.

Currently ships only the cross-tenant isolation fuzzer (Story 1.10). Future
stories add fuzzers for the authorization boundary, citation-envelope schema,
and phase-retrieval matrix — all live here so they share the seed-driven
reporting harness.
"""

from control_plane.fuzz.report import FuzzReport, TableReport

__all__ = ["FuzzReport", "TableReport"]
