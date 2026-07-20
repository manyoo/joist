"""joist FastAPI integration.

Provides :func:`setup_fastapi` to attach joist's rendering to a
FastAPI application.

Usage::

    from fastapi import FastAPI, Request
    from joist.integrators import setup_fastapi
    from joist import Fragment

    app = FastAPI()
    joist = setup_fastapi(app, template_dirs=["templates"])

    @app.get("/hello")
    async def hello(request: Request):
        frag = Fragment(template_path="hello.html", name="World")
        return joist.response(frag)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from starlette.responses import HTMLResponse as StarletteHTMLResponse

from joist import Component, Page, get_env, setup
from joist.htmx import is_hx_request, render_page_or_fragment

__all__ = [
    "setup_fastapi",
    "Joist",
    "html",
    "page",
    "fragment_or_page",
]


# ── Response builders (framework-agnostic) ─────────────────────────────


def html(content: str, **headers: str) -> HTMLResponse:
    """Return a bare ``HTMLResponse`` with optional extra headers."""
    return StarletteHTMLResponse(
        content=content,
        headers=headers or None,
    )


def page(
    page_title: str,
    content_component: Component,
    *,
    page_cls: type[Page] = Page,
    **page_kwargs: Any,
) -> HTMLResponse:
    """Render a full page inside a ``Page`` shell."""
    content_html = content_component.render_html()
    p = page_cls(page_title=page_title, content=content_html, **page_kwargs)
    return StarletteHTMLResponse(content=str(p.render_html()))


def fragment_or_page(
    request: Request,
    page_title: str,
    content_component: Component,
    *,
    page_cls: type[Page] = Page,
    page_kwargs: dict[str, Any] | None = None,
    hx_trigger_headers: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render a fragment for HTMX or a full page for direct navigation.

    This is the primary rendering function for routes that serve both
    HTMX partials and full-page loads::

        @router.get("/items")
        async def list_items(request: Request):
            table = ItemTable(items=await load_items())
            return fragment_or_page(request, "Items", table)

    Delegates to :func:`joist.htmx.render_page_or_fragment` and wraps
    the result in a proper ``HTMLResponse``.

    HTMX requests return only the content component's HTML.
    Direct navigation returns a ``Page`` shell wrapping the content.
    """
    result = render_page_or_fragment(
        request,
        page_title,
        content_component,
        page_cls=page_cls,
        page_kwargs=page_kwargs,
        hx_trigger_headers=hx_trigger_headers,
    )
    return StarletteHTMLResponse(
        content=result.content,
        headers=result.headers or None,
    )


# ── Convenience wrapper ────────────────────────────────────────────────


class Joist:
    """Convenience wrapper bundling the most common render helpers.

    Returned by :func:`setup_fastapi` so you can call::

        joist = setup_fastapi(app)

        # Render a component directly (bare HTML)
        return joist.response(my_component)

        # Render a full page with shell
        return joist.page_response(request, "Title", my_component)

        # HTMX-aware: fragment or full page
        return joist.fragment_or_page(request, "Title", my_component)
    """

    def __init__(self, app: FastAPI, template_dirs: list[str | Path] | None = None):
        self.app = app
        setup(template_dirs=template_dirs)

    def response(
        self,
        component: Component,
        *,
        hx_trigger_headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        """Render a component to a standalone HTML response."""
        headers: dict[str, str] = {}
        if hx_trigger_headers:
            headers.update(hx_trigger_headers)
        html_content = component.render_html()
        return StarletteHTMLResponse(content=str(html_content), headers=headers or None)

    def page_response(
        self,
        request: Request,
        page_title: str,
        content_component: Component,
        *,
        page_cls: type[Page] = Page,
        **page_kwargs: Any,
    ) -> HTMLResponse:
        """Render a full page with the ``Page`` shell."""
        return page(page_title, content_component, page_cls=page_cls, **page_kwargs)

    def fragment_or_page(
        self,
        request: Request,
        page_title: str,
        content_component: Component,
        *,
        page_cls: type[Page] = Page,
        page_kwargs: dict[str, Any] | None = None,
        hx_trigger_headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        """Render a fragment for HTMX or a full page for direct nav."""
        return fragment_or_page(
            request,
            page_title,
            content_component,
            page_cls=page_cls,
            page_kwargs=page_kwargs,
            hx_trigger_headers=hx_trigger_headers,
        )


def setup_fastapi(
    app: FastAPI,
    *,
    template_dirs: list[str | Path] | None = None,
) -> Joist:
    """Configure joist for a FastAPI application.

    Sets up the global Jinja2 environment (including built-in templates)
    and returns a :class:`Joist` helper with common render methods.

    Args:
        app: The FastAPI application instance.
        template_dirs: Additional template directories (your app's
                       templates).  Built-in joist templates are
                       included automatically.

    Returns:
        A :class:`Joist` instance bound to the app.
    """
    return Joist(app, template_dirs=template_dirs)
