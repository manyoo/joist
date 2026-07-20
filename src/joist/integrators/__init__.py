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

from joist.integrators.fastapi import (
    Joist,
    fragment_or_page,
    html,
    page,
    setup_fastapi,
)

__all__ = [
    "Joist",
    "fragment_or_page",
    "html",
    "page",
    "setup_fastapi",
]
