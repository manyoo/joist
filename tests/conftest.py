"""Test fixtures for joist."""

from __future__ import annotations

from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound
from markupsafe import Markup
import pytest


class DictLoader(BaseLoader):
    """Jinja2 loader that serves templates from a dict.

    Simpler than jinja2.DictLoader because it wraps values in
    ``Markup`` to match the real loader behaviour we test against.
    """

    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def get_source(self, environment: Environment, template: str) -> tuple[str, str | None, callable | None]:
        if template in self.mapping:
            source = self.mapping[template]
            return source, None, lambda: True
        raise TemplateNotFound(template)


@pytest.fixture
def env():
    """Create a fresh Jinja2 environment for each test."""
    loader = DictLoader({})
    return Environment(loader=loader, autoescape=True)
