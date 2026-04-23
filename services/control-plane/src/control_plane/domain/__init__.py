"""Domain layer for the DeployAI Control Plane.

Story 1.8 adds the canonical memory schema under
``control_plane.domain.canonical_memory``. Repositories and services are
deliberately absent at this story — models are import-only so that
Story 1.9's tenant-scoped session can wrap them without a rewrite.
"""
