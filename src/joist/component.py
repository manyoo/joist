"""joist — Build HTML UI with Python dataclasses + Jinja2 templates.

Architecture
------------

joist implements a server-side component layer on top of Jinja2, designed
for HTMX-heavy applications where the same UI fragment can be rendered
as a full page, a partial swap, or an out-of-band update.

The pattern follows three layers:

    Routes (load data)
        ↓
    Builders (assemble component trees)    ← joist lives here
        ↓
    Templates (render markup)

- **Routes** handle HTTP, authentication, and data loading. They call
  builders and return the rendered result.
- **Builders** are plain functions that create and compose Component
  instances.  Builders are the primary way to assemble UI from data.
- **Templates** render markup and place child components.  They receive
  typed context from the Component's dataclass fields.

Component = ``@dataclass(kw_only=True)`` + Jinja2 template.

This module provides the primitive: :class:`Component`, :class:`Fragment`
for HTMX partials, :class:`Page` for the document shell, and helpers
for template environment setup.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

__all__ = [
    "Component",
    "Fragment",
    "Page",
    "setup",
    "get_env",
    "render_component",
    "render_template",
]


# ── Global Jinja2 environment ──────────────────────────────────────────

_env: Environment | None = None


def setup(
    *,
    template_dirs: list[str | Path] | None = None,
    extensions: list[str] | None = None,
    environment: Environment | None = None,
    autoescape: bool = True,
    **env_kwargs: Any,
) -> Environment:
    """Configure the global Jinja2 environment.

    Args:
        template_dirs: Additional directories to search for templates
                       (built-in templates are included automatically).
        extensions: Jinja2 extensions to load.
        environment: An existing Environment to use instead of creating one.
        autoescape: Enable autoescaping (default True). Ignored when
                    ``environment`` is provided.
        **env_kwargs: Additional kwargs passed to ``Environment``.
                      Ignored when ``environment`` is provided.

    The built-in templates directory is automatically prepended to the
    loader chain so joist's own templates (e.g. ``Page``) are always
    resolvable regardless of your project's template directories.
    """
    global _env
    if environment is not None:
        _env = environment
        return _env

    builtin_dir = str(Path(__file__).parent / "templates")
    all_dirs = [builtin_dir]
    if template_dirs:
        all_dirs.extend(str(d) for d in template_dirs)

    _env = Environment(
        loader=FileSystemLoader(all_dirs),
        autoescape=autoescape,
        extensions=extensions or [],
        **env_kwargs,
    )
    return _env


def get_env() -> Environment:
    """Return the global Jinja2 environment, creating a default if needed.

    The first call without an explicit ``setup()`` will create a default
    environment pointing only at joist's built-in templates.  Call
    ``setup()`` first if you need to add custom template directories.
    """
    if _env is None:
        return setup()
    return _env


# ── Component base class ───────────────────────────────────────────────


@dataclass(kw_only=True)
class Component:
    """Base class for UI components.

    A component is a typed data contract that maps to a Jinja2 template.
    Dataclass fields become template context automatically.  Override
    :meth:`get_props` to add computed properties.  Methods named
    ``get_*()`` are callable from templates.

    This is the core primitive of the three-layer architecture:

    *Routes* load data and pass it to builders.
    *Builders* create and compose Component instances into a tree.
    *Templates* render their own markup and place children.

    Nested ``Component`` instances are automatically pre-rendered to
    ``Markup`` before reaching the template — you never need ``|safe``
    or manual ``render()`` calls for children.

    Usage::

        @dataclass(kw_only=True)
        class Greeting(Component):
            template_path: ClassVar = "greeting.html"
            name: str = ""
            items: list = field(default_factory=list)

            def get_props(self):
                return {"count": len(self.items)}

    The template at ``greeting.html`` receives ``{{ name }}``,
    ``{{ items }}``, and ``{{ count }}``.
    """

    template_path: ClassVar[str] = ""
    _joist_env: ClassVar[Environment | None] = None

    #: Reserved — excluded from template context.  Pass a request-like
    #: object when you need URL generation or other request data in
    #: ``get_props()``.
    request: Any | None = field(default=None, repr=False)

    # ── introspection ────────────────────────────────────────────────

    @property
    def has_any(self) -> bool:
        """Whether the component yields visible content.

        Override to ``False`` when the component should be invisible
        (e.g. empty list, missing data).  Parent components can check
        this to decide whether to render a wrapper.
        """
        return True

    # ── rendering ───────────────────────────────────────────────────

    def get_props(self) -> dict[str, Any]:
        """Override to inject computed properties into the template context.

        The returned dict is merged *on top of* the dataclass fields so
        it can shadow raw field values with formatted versions.
        """
        return {}

    def props(self) -> dict[str, Any]:
        """Return the full template context dict (public, for introspection).

        Order of precedence (later wins):
          1. Dataclass fields (excluding ``request``, private fields).
          2. ``get_props()`` computed values.
          3. ``get_*`` methods (callable from templates, but do not
             override fields or props).

        You can inspect this dict for debugging or testing without
        rendering the template.
        """
        ctx: dict[str, Any] = {}

        for f in fields(self):
            if f.name == "request" or f.name.startswith("_"):
                continue
            value = getattr(self, f.name)
            if value is None and f.metadata.get("exclude_if_none") is True:
                continue
            ctx[f.name] = _resolve(value)

        ctx.update(self.get_props())

        for method_name, method in inspect.getmembers(
            self, predicate=inspect.ismethod
        ):
            if method_name.startswith("get_") and not method_name.startswith(
                "_get_"
            ):
                if method_name not in ctx:
                    ctx[method_name] = method

        return ctx

    def render_html(self) -> Markup:
        """Render the component to safe HTML markup.

        Returns a ``Markup`` object that Jinja2 and other template
        engines treat as safe — no ``|safe`` filter needed when
        embedding in parent templates.
        """
        if not self.template_path:
            raise ComponentError(
                f"{type(self).__name__} has no template_path set"
            )
        env = self._resolve_env()
        template = env.get_template(self.template_path)
        return Markup(template.render(self.props()))

    def render(self) -> str:
        """Render to a plain HTML string (same as ``str(component)``)."""
        return str(self.render_html())

    def __str__(self) -> str:
        return self.render()

    def __html__(self) -> str:
        """Jinja2 / MarkupSafe protocol — same as ``render_html()``.

        This allows ``Markup(component)`` and direct embedding in
        parent templates via the ``|safe`` protocol.
        """
        return str(self.render_html())

    # ── utilities ───────────────────────────────────────────────────

    @classmethod
    def _resolve_env(cls) -> Environment:
        if cls._joist_env is None:
            cls._joist_env = get_env()
        return cls._joist_env


# ── Fragment (inline HTMX partial) ─────────────────────────────────────


@dataclass(kw_only=True)
class Fragment(Component):
    """Lightweight component for HTMX partials.

    Unlike :class:`Component`, ``template_path`` is an *instance* field,
    which lets you create fragments inline for HTMX partial routes::

        @router.get("/users/{uid}/card")
        async def user_card(request: Request, uid: str):
            user = await load_user(uid)
            return Fragment(
                template_path="users/_card.html",
                name=user.name,
                role=user.role,
            ).render_html()

    For reusable HTMX partials, subclass with typed fields::

        @dataclass(kw_only=True)
        class UserRow(Fragment):
            template_path: str = "users/_row.html"
            user_id: str = ""
            name: str = ""
            role: str = ""
    """

    template_path: str = ""


# ── Page shell ─────────────────────────────────────────────────────────


@dataclass(kw_only=True)
class Page(Component):
    """Full HTML document shell.

    Wraps content in a ``<!DOCTYPE html>`` document with ``<head>``
    and ``<body>``.  The default template is minimal — override or
    subclass for your own layout.

    Designed for the :func:`~joist.htmx.render_page_or_fragment`
    pattern: direct navigation returns a ``Page``, HTMX requests
    return just the content component.

    The ``content`` field accepts either pre-rendered ``Markup``
    (from ``component.render_html()``) or a ``Component`` instance
    directly.  When a ``Component`` is passed, it is automatically
    rendered before reaching the template.

    Usage::

        # Explicit (builder pattern — recommended):
        Page(page_title="Hi", content=card.render_html())

        # Implicit (convenient — works with AI agents):
        Page(page_title="Hi", content=card)

    The default template produces::

        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>{{ page_title }}</title>
          {{ head_extras }}
        </head>
        <body>
          {{ content }}
        </body>
        </html>
    """

    template_path: ClassVar[str] = "joist/page.html"

    page_title: str = ""
    content: Component | Markup | str = Markup("")
    head_extras: Markup = Markup("")
    body_attrs: dict[str, str] = field(default_factory=dict)
    lang: str = "zh-CN"

    def get_props(self) -> dict[str, Any]:
        """Ensure content is pre-rendered if a Component was passed.

        This makes ``Page(content=my_component)`` work without an
        explicit ``.render_html()`` call — convenient when an AI
        agent or a new user is assembling the page.
        """
        if isinstance(self.content, Component):
            return {"content": self.content.render_html()}
        return {}


# ── Pure helpers ───────────────────────────────────────────────────────


def render_component(component: Component) -> Markup:
    """Render a component to ``Markup``.

    Convenience alias for ``component.render_html()``.
    """
    return component.render_html()


def render_template(template_name: str, **context: Any) -> Markup:
    """Render a template directly without a component class.

    Useful for one-off snippets or when migrating existing code.

    Example::

        html = render_template("emails/welcome.html", name="Alice")
    """
    env = get_env()
    return Markup(env.get_template(template_name).render(context))


# ── Internals ──────────────────────────────────────────────────────────


class ComponentError(Exception):
    """Raised for component system errors."""


def _resolve(value: Any) -> Any:
    """Recursively render nested ``Component`` instances to ``Markup``.

    This is what makes the component tree work:
      - A ``Component`` child becomes pre-rendered ``Markup``.
      - Lists and dicts are traversed recursively.
      - Everything else passes through unchanged.

    Templates can therefore use ``{{ child }}`` directly instead of
    ``{{ child.render_html() }}``.
    """
    if isinstance(value, Component):
        return value.render_html()
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_resolve(v) for v in value]
    return value
