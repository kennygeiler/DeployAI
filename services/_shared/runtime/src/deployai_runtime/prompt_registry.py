"""Versioned Jinja2 prompt resolution (Epic 5, Story 5.3)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import jinja2

_PKG = "deployai_runtime"
_TEMPLATES_ROOT = "prompts_data"


class PromptRegistry:
    """Resolves ``prompt_name`` + ``version`` to a rendered string."""

    def __init__(self, root: Path | None = None) -> None:
        if root is not None:
            self._fs_root = root
            self._use_package = False
        else:
            self._use_package = True
            self._fs_root = Path()

    def _load_raw(self, version: str, name: str) -> str:
        if self._use_package:
            try:
                base = resources.files(_PKG) / _TEMPLATES_ROOT / version
                f = base / f"{name}.md.j2"
                return f.read_text(encoding="utf-8")
            except (OSError, TypeError) as e:
                msg = f"prompt not found: {version}/{name}"
                raise FileNotFoundError(msg) from e
        p = self._fs_root / version / f"{name}.md.j2"
        if not p.is_file():
            msg = f"prompt not found: {p}"
            raise FileNotFoundError(msg)
        return p.read_text(encoding="utf-8")

    def render(
        self,
        *,
        version: str,
        name: str,
        variables: dict[str, Any] | None = None,
    ) -> str:
        raw = self._load_raw(version, name)
        env = jinja2.Environment(autoescape=False)
        t = env.from_string(raw)
        return t.render(**(variables or {}))
