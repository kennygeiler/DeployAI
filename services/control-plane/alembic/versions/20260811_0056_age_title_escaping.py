"""Re-apply the AGE node-mirror trigger with correct Cypher title escaping.

The previous trigger body escaped single quotes in ``matrix_nodes.title`` with
a doubled backslash sequence, so any title containing an apostrophe (e.g.
"Sean O'Connor") produced ``O\\'`` inside the generated Cypher string — the
backslash pair reads as a literal backslash and the quote terminates the
string early, failing the INSERT with a Postgres syntax error. Titles
containing ``$$`` could also break out of the outer dollar-quoting.

The trigger function source lives in
``control_plane.domain.canonical_memory.age_sync`` (same import 0042 uses);
this revision simply re-runs CREATE OR REPLACE with the fixed body:
Cypher-style escaping (``\\`` then ``\\'``), a unique ``$age_sync$`` outer
dollar tag, and stripping of that tag from titles.

expand-contract: pure function replacement, no schema change, safe both ways.
"""

from __future__ import annotations

from alembic import op
from control_plane.domain.canonical_memory.age_sync import (
    EDGE_TRIGGER_ATTACH,
    EDGE_TRIGGER_FN,
    NODE_TRIGGER_ATTACH,
    NODE_TRIGGER_FN,
)

revision = "20260811_0056"
down_revision = "20260811_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0042 ran its CREATE FUNCTION under AGE's search_path
    # (ag_catalog first), so on databases migrated by it the live trigger
    # functions landed in ag_catalog — an unqualified CREATE OR REPLACE here
    # would create a *second* copy in public and leave the buggy bound one
    # untouched. The DDL is now schema-qualified (public.*): install the
    # fixed functions, re-attach both triggers to them, then drop any stray
    # ag_catalog copies.
    op.execute(NODE_TRIGGER_FN)
    op.execute(EDGE_TRIGGER_FN)
    op.execute(NODE_TRIGGER_ATTACH)
    op.execute(EDGE_TRIGGER_ATTACH)
    op.execute("DROP FUNCTION IF EXISTS ag_catalog.matrix_nodes_age_sync_trigger();")
    op.execute("DROP FUNCTION IF EXISTS ag_catalog.matrix_edges_age_sync_trigger();")


def downgrade() -> None:
    # The old body was defective (apostrophes broke inserts); downgrading the
    # schema should not resurrect it. Keep the fixed function.
    pass
