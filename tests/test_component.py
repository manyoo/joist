"""Tests for Component, Fragment, Page, and render helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from jinja2 import Environment
from markupsafe import Markup
import pytest

from joist import (
    Component,
    ComponentError,
    Fragment,
    Page,
    render_component,
    render_template,
    setup,
)
from joist.component import _resolve

from tests.conftest import DictLoader


# ── Test Doubles ───────────────────────────────────────────────────────


@dataclass(kw_only=True)
class Simple(Component):
    template_path: ClassVar = "simple.html"
    name: str = ""
    greeting: str = "Hello"


@dataclass(kw_only=True)
class WithChildren(Component):
    template_path: ClassVar = "with_children.html"
    title: str = ""
    child: Component | None = None
    items: list[Component] = field(default_factory=list)


@dataclass(kw_only=True)
class WithProps(Component):
    template_path: ClassVar = "with_props.html"
    raw_name: str = ""

    def get_props(self):
        return {"greeting": f"Hello, {self.raw_name}!"}


@dataclass(kw_only=True)
class WithExcluded(Component):
    """Has a field with exclude_if_none."""
    template_path: ClassVar = "simple.html"
    name: str = "default"
    optional: str | None = field(default=None, metadata={"exclude_if_none": True})


TEMPLATES = {
    "simple.html": "<div>{{ greeting }}, {{ name }}!</div>",
    "with_children.html": (
        "<article>"
        "<h1>{{ title }}</h1>"
        "<div class='child'>{{ child }}</div>"
        "<ul>{% for item in items %}<li>{{ item }}</li>{% endfor %}</ul>"
        "</article>"
    ),
    "with_props.html": "<p>{{ greeting }}</p>",
    "fragment_example.html": "<tr><td>{{ label }}</td><td>{{ value }}</td></tr>",
}


@pytest.fixture(autouse=True)
def _setup_env():
    """Set up a clean environment per test with known templates."""
    loader = DictLoader(TEMPLATES)
    env = Environment(loader=loader, autoescape=True)
    # Override the global env that Component._resolve_env() will use
    Simple._joist_env = env
    WithChildren._joist_env = env
    WithProps._joist_env = env
    WithExcluded._joist_env = env
    Fragment._joist_env = env
    Page._joist_env = Environment(loader=DictLoader({
        "joist/page.html": "<!DOCTYPE html><html><head><title>{{ page_title }}</title>{{ head_extras }}</head><body>{{ content }}</body></html>",
    }), autoescape=True)
    yield
    # Reset to force fresh resolution next time
    Simple._joist_env = None
    WithChildren._joist_env = None
    WithProps._joist_env = None
    WithExcluded._joist_env = None
    Fragment._joist_env = None
    Page._joist_env = None


# ── Component Tests ────────────────────────────────────────────────────


class TestComponent:
    def test_simple_render(self):
        c = Simple(name="World")
        html = c.render_html()
        assert str(html) == "<div>Hello, World!</div>"

    def test_render_via_str(self):
        c = Simple(name="测试")
        assert str(c) == "<div>Hello, 测试!</div>"

    def test_render_via_html_protocol(self):
        """__html__() should satisfy MarkupSafe protocol."""
        c = Simple(name="Alice")
        raw = c.__html__()
        assert raw == "<div>Hello, Alice!</div>"

    def test_get_props_shadows_field(self):
        c = WithProps(raw_name="Alice")
        html = c.render_html()
        assert "<p>Hello, Alice!</p>" in str(html)

    def test_no_template_path_raises(self):
        """Component subclasses without template_path should raise."""

        @dataclass(kw_only=True)
        class MissingPath(Component):
            pass

        MissingPath._joist_env = Simple._joist_env  # borrow env
        c = MissingPath()
        with pytest.raises(ComponentError, match="no template_path"):
            c.render_html()

    @pytest.mark.parametrize("name,expected", [
        ("World", "<div>Hello, World!</div>"),
        ("", "<div>Hello, !</div>"),
        ("<script>", "<div>Hello, &lt;script&gt;!</div>"),  # autoescape
    ])
    def test_autoescape(self, name, expected):
        c = Simple(name=name)
        assert str(c.render_html()) == expected

    def test_exclude_if_none(self):
        """Fields with exclude_if_none metadata should be omitted when None."""
        c = WithExcluded(name="test")
        ctx = c.props()
        assert "name" in ctx
        assert "optional" not in ctx

    def test_props_public_for_introspection(self):
        """props() should be a public method returning the context dict."""
        c = Simple(name="World")
        ctx = c.props()
        assert ctx["name"] == "World"
        assert ctx["greeting"] == "Hello"


class TestNestedComponents:
    def test_nested_component_auto_renders(self):
        inner = Simple(name="Inner")
        outer = WithChildren(
            title="Wrapper",
            child=inner,
        )
        html = str(outer.render_html())
        assert "Wrapper" in html
        assert "<div>Hello, Inner!</div>" in html

    def test_list_of_components(self):
        items = [
            Simple(name="A"),
            Simple(name="B"),
            Simple(name="C"),
        ]
        outer = WithChildren(
            title="List",
            items=items,
        )
        html = str(outer.render_html())
        assert "<li><div>Hello, A!</div></li>" in html
        assert "<li><div>Hello, B!</div></li>" in html
        assert "<li><div>Hello, C!</div></li>" in html

    def test_str_method(self):
        inner = Simple(name="Child")
        outer = WithChildren(title="Test", child=inner)
        assert "Hello, Child!" in str(outer)

    def test_markup_is_not_nested(self):
        """Markup objects should pass through unchanged."""
        result = _resolve(Markup("<b>safe</b>"))
        assert isinstance(result, Markup)
        assert result == Markup("<b>safe</b>")


class TestFragment:
    def test_fragment_inline(self):
        """Fragment supports inline subclass with proper annotations."""
        @dataclass(kw_only=True)
        class _Inline(Fragment):
            template_path: str = "fragment_example.html"
            label: str = ""
            value: str = ""

        _Inline._joist_env = Fragment._joist_env
        frag = _Inline(label="姓名", value="张三")
        html = str(frag.render_html())
        assert "<tr><td>姓名</td><td>张三</td></tr>" in html

    def test_fragment_subclass(self):
        @dataclass(kw_only=True)
        class Row(Fragment):
            template_path: str = "fragment_example.html"
            label: str = ""
            value: str = ""

        Row._joist_env = Fragment._joist_env
        row = Row(label="年龄", value="28")
        html = str(row.render_html())
        assert "<td>年龄</td>" in html
        assert "<td>28</td>" in html


class TestPage:
    def test_page_renders_full_document(self):
        page = Page(
            page_title="测试页面",
            content=Markup("<h1>Hello</h1>"),
        )
        html = str(page.render_html())
        assert "<!DOCTYPE html>" in html
        assert "<title>测试页面</title>" in html
        assert "<h1>Hello</h1>" in html
        assert "</html>" in html

    def test_page_with_head_extras(self):
        page = Page(
            page_title="Test",
            content=Markup("<p>Hi</p>"),
            head_extras=Markup('<link rel="stylesheet" href="app.css">'),
        )
        html = str(page.render_html())
        assert 'href="app.css"' in html

    def test_page_accepts_component_directly(self):
        """Page.content accepts a Component without explicit .render_html()."""
        inner = Simple(name="World")
        page = Page(page_title="Test", content=inner)
        html = str(page.render_html())
        assert "Hello, World!" in html
        assert "<!DOCTYPE html>" in html


class TestRenderHelpers:
    def test_render_component(self):
        c = Simple(name="Helper")
        result = render_component(c)
        assert isinstance(result, Markup)
        assert "<div>Hello, Helper!</div>" in str(result)

    def test_render_template(self):
        # Set up env with DictLoader for this test
        loader = DictLoader({"test.html": "<b>{{ value }}</b>"})
        env = Environment(loader=loader, autoescape=True)
        setup(environment=env)
        result = render_template("test.html", value="bold")
        assert str(result) == "<b>bold</b>"

    def test_has_any_default(self):
        c = Simple(name="X")
        assert c.has_any is True

    def test_has_any_override(self):
        @dataclass(kw_only=True)
        class Conditional(Component):
            template_path: ClassVar = "simple.html"
            items: list = field(default_factory=list)

            @property
            def has_any(self):
                return len(self.items) > 0

        Conditional._joist_env = Simple._joist_env
        empty = Conditional()
        assert empty.has_any is False
        full = Conditional(items=[1, 2])
        assert full.has_any is True
