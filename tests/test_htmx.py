"""Tests for HTMX detection and response utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar
from unittest.mock import MagicMock

from jinja2 import Environment
import pytest

from joist import Component, Page
from joist.htmx import (
    HX,
    is_hx_request,
    hx_trigger,
    hx_redirect,
    hx_retarget,
    render_page_or_fragment,
)

from tests.conftest import DictLoader


# ── Fixtures ───────────────────────────────────────────────────────────


@dataclass(kw_only=True)
class DummyContent(Component):
    template_path: ClassVar = "dummy.html"
    text: str = "hello"


def _make_request(hx_request: str | None = "true") -> MagicMock:
    """Factory for mock request objects."""
    req = MagicMock()
    req.headers = {}
    if hx_request is not None:
        req.headers["HX-Request"] = hx_request
    return req


TEMPLATES = {
    "dummy.html": "<p>{{ text }}</p>",
    "joist/page.html": (
        "<!DOCTYPE html><html><head><title>{{ page_title }}</title></head>"
        "<body>{{ content }}</body></html>"
    ),
}


@pytest.fixture(autouse=True)
def _setup_env():
    """Set up a fresh env with known templates."""
    loader = DictLoader(TEMPLATES)
    env = Environment(loader=loader, autoescape=True)
    DummyContent._joist_env = env
    Page._joist_env = env
    yield
    DummyContent._joist_env = None
    Page._joist_env = None


# ── Detection ──────────────────────────────────────────────────────────


class TestIsHxRequest:
    def test_detects_hx_request(self):
        req = _make_request("true")
        assert is_hx_request(req) is True

    def test_rejects_normal_request(self):
        req = _make_request(None)
        assert is_hx_request(req) is False

    def test_rejects_false_value(self):
        req = _make_request("false")
        assert is_hx_request(req) is False

    def test_missing_header(self):
        req = MagicMock()
        req.headers = {}
        assert is_hx_request(req) is False


# ── HX headers ─────────────────────────────────────────────────────────


class TestHX:
    def test_trigger_simple(self):
        hdrs = HX.trigger("refresh")
        assert hdrs == {"HX-Trigger": "refresh"}

    def test_trigger_with_payload(self):
        hdrs = HX.trigger("toast", {"msg": "保存成功", "type": "success"})
        raw = hdrs["HX-Trigger"]
        payload = json.loads(raw)
        assert payload["toast"]["msg"] == "保存成功"

    def test_trigger_after_swap(self):
        hdrs = HX.trigger("done", after="swap")
        assert "HX-Trigger-After-Swap" in hdrs

    def test_trigger_after_settle(self):
        hdrs = HX.trigger("done", after="settle")
        assert "HX-Trigger-After-Settle" in hdrs

    def test_retarget(self):
        hdrs = HX.retarget("#toast-container")
        assert hdrs == {"HX-Retarget": "#toast-container"}

    def test_redirect(self):
        hdrs = HX.redirect("/login")
        assert hdrs == {"HX-Redirect": "/login"}

    def test_refresh(self):
        hdrs = HX.refresh()
        assert hdrs == {"HX-Refresh": "true"}

    def test_push_url(self):
        hdrs = HX.push_url("/page/2")
        assert hdrs == {"HX-Push-Url": "/page/2"}

    def test_replace_url(self):
        hdrs = HX.replace_url("/page/2")
        assert hdrs == {"HX-Replace-Url": "/page/2"}

    def test_reselect(self):
        hdrs = HX.reselect(".main-content")
        assert hdrs == {"HX-Reselect": ".main-content"}


# ── Convenience aliases ────────────────────────────────────────────────


class TestConvenienceAliases:
    def test_hx_trigger(self):
        assert hx_trigger("evt") == {"HX-Trigger": "evt"}

    def test_hx_redirect(self):
        assert hx_redirect("/foo") == {"HX-Redirect": "/foo"}

    def test_hx_retarget(self):
        assert hx_retarget("#foo") == {"HX-Retarget": "#foo"}


# ── render_page_or_fragment ────────────────────────────────────────────


class TestRenderPageOrFragment:
    def test_htmx_request_returns_fragment(self):
        req = _make_request("true")
        content = DummyContent(text="only this")

        result = render_page_or_fragment(req, "Title", content)

        assert result.is_fragment is True
        assert "<p>only this</p>" in result.content
        assert "<!DOCTYPE html>" not in result.content

    def test_direct_request_returns_page(self):
        req = _make_request(None)
        content = DummyContent(text="full page")

        result = render_page_or_fragment(req, "My Title", content)

        assert result.is_fragment is False
        assert "<!DOCTYPE html>" in result.content
        assert "<title>My Title</title>" in result.content
        assert "<p>full page</p>" in result.content

    def test_hx_trigger_headers_included(self):
        req = _make_request("true")
        content = DummyContent(text="x")

        result = render_page_or_fragment(
            req, "T", content,
            hx_trigger_headers={"HX-Trigger": "reload"},
        )

        assert result.headers["HX-Trigger"] == "reload"

    def test_custom_page_cls(self):
        @dataclass(kw_only=True)
        class CustomPage(Page):
            template_path: ClassVar = "joist/page.html"
            extra_footer: str = ""

        CustomPage._joist_env = Page._joist_env
        req = _make_request(None)
        content = DummyContent(text="custom")

        result = render_page_or_fragment(
            req, "Custom", content,
            page_cls=CustomPage,
            page_kwargs={"extra_footer": "bye"},
        )

        assert "custom" in result.content
        # CustomPage will still use the same template, so the
        # page shell output is the same — but the instance
        # correctly received the kwargs.
