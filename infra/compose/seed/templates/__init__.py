"""Industry templates for `make init`.

Each template seeds a vertical-specific bundle into a freshly-created tenant:
default engagement name + customer account + phase, a small starter set of
matrix nodes typical of the vertical, and prompt overrides that nudge the
agents (Cartographer / Oracle / Master Strategist) toward vertical-aware
extraction and synthesis.

Templates are pure data — no DB / HTTP work happens here. `init.py` is the
caller that translates the dataclass into POST/PUT calls against the existing
internal CP API.
"""

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
