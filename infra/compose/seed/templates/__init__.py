"""Vertical-specific seed bundles for the `make init` `--template` flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Template:
    name: str
    default_engagement_name: str
    default_customer_account: str
    default_phase: str
    starter_nodes: list[dict[str, Any]] = field(default_factory=list)
    agent_prompts: dict[str, str] = field(default_factory=dict)


# Imported after Template is defined so the submodules can `from . import Template`.
from . import gov, healthcare, saas, sales

TEMPLATES: dict[str, Template] = {
    gov.TEMPLATE.name: gov.TEMPLATE,
    healthcare.TEMPLATE.name: healthcare.TEMPLATE,
    saas.TEMPLATE.name: saas.TEMPLATE,
    sales.TEMPLATE.name: sales.TEMPLATE,
}

__all__ = ["TEMPLATES", "Template"]
