"""joist/htmx — HTMX request detection and response utilities.

Provides helpers for the HTMX response pattern:

* :func:`is_hx_request` — detect HTMX requests
* :class:`HX` — namespace for response header builders
* :class:`RenderResult` — typed result of rendering a component
* :func:`render_page_or_fragment` — one path for both HTMX and direct
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from markupsafe import Markup

from joist.component import Component, Page, render_component

__all__ = [
    "is_hx_request",
    "HX",
    "RenderResult",
    "render_page_or_fragment",
    "hx_trigger",
    "hx_retarget",
    "hx_redirect",
    "hx_refresh",
    "hx_push_url",
    "hx_replace_url",
    "hx_reselect",
]


def is_hx_request(request: Any) -> bool:
    """Return ``True`` when *request* is an HTMX request.

    Accepts any object with a ``.headers`` mapping (FastAPI ``Request``,
    Starlette ``Request``, Django ``HttpRequest``, etc.).
    """
    return request.headers.get("HX-Request") == "true"


# ── HX-Response-* header builders ──────────────────────────────────────


class HX:
    """Namespace for HTMX response header builders.

    Each method returns a ``dict`` of response headers that can be
    unpacked into a ``Response`` constructor::

        from joist.htmx import HX

        response = HTMLResponse(content=html, **HX.trigger("toast", "Saved!"))
    """

    @staticmethod
    def trigger(
        name: str, value: Any = None, *, after: str | None = None
    ) -> dict[str, str]:
        """Return ``HX-Trigger`` headers.

        Args:
            name: Event name (e.g. ``"toast"``, ``"reload-table"``).
            value: Optional JSON-serialisable payload.
            after: ``"settle"`` or ``"swap"`` — use
                   ``HX-Trigger-After-Settle`` or
                   ``HX-Trigger-After-Swap`` instead of ``HX-Trigger``.

        Returns:
            ``{"HX-Trigger": '...'}`` (or ``-After-Settle`` /
            ``-After-Swap`` variant).

        A trigger without a payload is emitted as a plain string::

            HX.trigger("toast")                     # HX-Trigger: toast

        A trigger with a payload is serialised as a JSON object::

            HX.trigger("toast", {"msg": "Saved!"})   # HX-Trigger: {"toast": ...}
        """
        header = "HX-Trigger"
        if after == "settle":
            header = "HX-Trigger-After-Settle"
        elif after == "swap":
            header = "HX-Trigger-After-Swap"

        if value is not None:
            import json
            raw = json.dumps({name: value}, ensure_ascii=False)
        else:
            raw = name

        return {header: raw}

    @staticmethod
    def retarget(target: str) -> dict[str, str]:
        """Return ``HX-Retarget`` header to change the swap target.

        Example::

            return HTMLResponse(content=html, **HX.retarget("#toast-container"))
        """
        return {"HX-Retarget": target}

    @staticmethod
    def redirect(url: str) -> dict[str, str]:
        """Return ``HX-Redirect`` header for client-side redirect."""
        return {"HX-Redirect": url}

    @staticmethod
    def refresh() -> dict[str, str]:
        """Return ``HX-Refresh`` header to refresh the current page."""
        return {"HX-Refresh": "true"}

    @staticmethod
    def push_url(url: str) -> dict[str, str]:
        """Return ``HX-Push-Url`` header to push a new browser history entry."""
        return {"HX-Push-Url": url}

    @staticmethod
    def replace_url(url: str) -> dict[str, str]:
        """Return ``HX-Replace-Url`` header to replace the current URL."""
        return {"HX-Replace-Url": url}

    @staticmethod
    def reselect(css_selector: str) -> dict[str, str]:
        """Return ``HX-Reselect`` header to override the swap target selection."""
        return {"HX-Reselect": css_selector}


# Convenience aliases
hx_trigger = HX.trigger
hx_retarget = HX.retarget
hx_redirect = HX.redirect
hx_refresh = HX.refresh
hx_push_url = HX.push_url
hx_replace_url = HX.replace_url
hx_reselect = HX.reselect


# ── Render result ──────────────────────────────────────────────────────


@dataclass
class RenderResult:
    """Typed result of rendering a component as an HTMX fragment or
    full-page document.

    Returned by :func:`render_page_or_fragment`.  Framework integrations
    (e.g. FastAPI) consume this to produce a proper ``Response``.

    Attributes:
        content: The rendered HTML string.
        headers: Response headers (e.g. ``HX-Trigger``).
        is_fragment: ``True`` when the result is an HTMX fragment
                     (just the component), ``False`` when it is a
                     full ``Page`` document.
    """

    content: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    is_fragment: bool = False


# ── Render helpers ─────────────────────────────────────────────────────


def render_page_or_fragment(
    request: Any,
    page_title: str,
    content: Component,
    *,
    page_cls: type[Page] = Page,
    page_kwargs: dict[str, Any] | None = None,
    hx_trigger_headers: dict[str, str] | None = None,
) -> RenderResult:
    """Render a fragment for HTMX, or a full page for direct navigation.

    HTMX requests receive only the content component's HTML.
    Direct navigation receives a ``Page`` shell wrapping that content.

    Framework integrations (FastAPI, Starlette) consume the returned
    ``RenderResult`` to produce a proper ``Response``.  Bare users can
    use the ``.content`` and ``.headers`` attributes directly.

    Usage with FastAPI::

        @router.get("/users")
        async def users_page(request: Request):
            table = UserTable(users=await load_users())
            result = render_page_or_fragment(request, "Users", table)
            return HTMLResponse(
                content=result.content,
                headers=result.headers or None,
            )

    Args:
        request: Incoming request object (must have ``.headers``).
        page_title: Value for ``<title>``.
        content: The main content component.
        page_cls: Page shell class (default :class:`Page`).
        page_kwargs: Extra kwargs for the ``Page`` constructor.
        hx_trigger_headers: Additional HTMX trigger headers.

    Returns:
        A :class:`RenderResult` with ``.content``, ``.headers``,
        and ``.is_fragment``.
    """
    content_html = render_component(content)
    headers: dict[str, str] = {}
    if hx_trigger_headers:
        headers.update(hx_trigger_headers)

    if is_hx_request(request):
        return RenderResult(
            content=str(content_html),
            headers=headers,
            is_fragment=True,
        )

    kw = page_kwargs or {}
    page = page_cls(
        request=request,
        page_title=page_title,
        content=content_html,
        **kw,
    )
    return RenderResult(
        content=str(page.render_html()),
        headers=headers,
        is_fragment=False,
    )
