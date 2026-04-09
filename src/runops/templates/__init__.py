"""Template loading utilities for runops."""

from __future__ import annotations

from pathlib import Path

import jinja2

_TEMPLATES_DIR = Path(__file__).resolve().parent


def get_jinja_env() -> jinja2.Environment:
    """Return a Jinja2 environment that loads from runops/templates/."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )


def load_static(relative_path: str) -> str:
    """Load a static (non-Jinja2) template file as text."""
    return (_TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


def render(template_path: str, **kwargs: object) -> str:
    """Render a Jinja2 template with the given variables."""
    env = get_jinja_env()
    return env.get_template(template_path).render(**kwargs)
