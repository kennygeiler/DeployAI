"""Render an engagement packet dict to Markdown and PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_markdown(data: dict[str, Any]) -> str:
    template = _env().get_template("engagement_packet.md.j2")
    return template.render(**data)


def render_pdf(markdown_text: str) -> bytes:
    # Lazy import: weasyprint pulls in cairo/pango/gdk-pixbuf via cffi,
    # which is brittle on macOS dev machines. Importing inside the function
    # lets the rest of the module load (and tests for render_markdown run)
    # even when those system libs are missing.
    from weasyprint import HTML

    html_body = md.markdown(markdown_text, extensions=["tables"])
    result = HTML(string=html_body).write_pdf()
    if result is None:
        raise RuntimeError("weasyprint returned no PDF bytes")
    return bytes(result)
