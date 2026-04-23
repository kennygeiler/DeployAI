"""Expand-contract migration guardrail (NFR74).

Per the architecture doc and Story 1.8 AC11: canonical-memory migrations
must follow the expand-contract pattern. A migration that modifies a
canonical-memory column in place (``ALTER COLUMN`` / ``op.alter_column``)
is forbidden unless its ``upgrade()`` body explicitly opts in with a
literal marker comment on one of these forms:

- ``# expand-contract: expand``
- ``# expand-contract: contract``

The initial ``20260422_0001`` migration contains only additive operations
(``CREATE TABLE`` / ``CREATE INDEX`` / ``CREATE FUNCTION``) and is
therefore naturally exempt. The guardrail still scans it; it stays quiet
because there is no ``ALTER COLUMN`` to flag.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

CANONICAL_MEMORY_TABLES: frozenset[str] = frozenset(
    {
        "canonical_memory_events",
        "identity_nodes",
        "identity_attribute_history",
        "identity_supersessions",
        "solidified_learnings",
        "learning_lifecycle_states",
        "tombstones",
        "schema_proposals",
    }
)

_ALTER_COLUMN_RE = re.compile(
    r"(?:op\.alter_column\s*\(|\bALTER\s+COLUMN\b)",
    re.IGNORECASE,
)
_MARKER_RE = re.compile(
    r"#\s*expand-contract:\s*(expand|contract)\b",
    re.IGNORECASE,
)


def _migration_files() -> list[Path]:
    if not VERSIONS_DIR.is_dir():
        return []
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if not p.name.startswith("_"))


def _upgrade_body(source: str, path: Path) -> str:
    """Return the textual body of ``upgrade()`` within *source*.

    Falls back to the full file text when ``upgrade()`` cannot be
    located — better to over-flag than silently miss a violation.
    """

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return source

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return ast.get_source_segment(source, node) or source
    return source


def _references_canonical_memory_table(text: str) -> bool:
    for table in CANONICAL_MEMORY_TABLES:
        if re.search(rf"\b{re.escape(table)}\b", text):
            return True
    return False


def test_migration_versions_directory_exists() -> None:
    assert VERSIONS_DIR.is_dir(), f"expected alembic versions dir at {VERSIONS_DIR}"


def test_every_canonical_memory_alter_column_is_expand_or_contract_tagged() -> None:
    """Fail the build when a canonical-memory ALTER COLUMN skips the marker."""

    violations: list[str] = []
    for path in _migration_files():
        source = path.read_text(encoding="utf-8")
        if not _references_canonical_memory_table(source):
            continue

        body = _upgrade_body(source, path)
        if not _ALTER_COLUMN_RE.search(body):
            continue
        if _MARKER_RE.search(body):
            continue

        violations.append(
            f"{path.name}: ALTER COLUMN targets a canonical-memory table without "
            "an `# expand-contract: expand|contract` marker on the upgrade() "
            "function body. See docs/canonical-memory.md for the convention."
        )

    assert not violations, "Expand-contract guardrail violation(s):\n  - " + "\n  - ".join(violations)


def test_initial_canonical_memory_migration_is_present() -> None:
    """Sanity check: the schema-authoring migration from Story 1.8 is present."""

    files = {p.name for p in _migration_files()}
    assert any(name.startswith("20260422_0001_") and name.endswith("canonical_memory_schema.py") for name in files), (
        f"expected 20260422_0001_canonical_memory_schema.py in {VERSIONS_DIR}"
    )
