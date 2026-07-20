"""joist — Build HTML UI with Python dataclasses + Jinja2 templates.

joist gives you a single architectural primitive: Component = dataclass + template.
Everything else is a consequence of that choice.

You define components as dataclasses, build component trees with plain
functions (builders), and render them through Jinja2.  The framework stays
out of your way.

Core exports:

* :class:`Component` — base class for dataclass-driven UI components.
* :class:`Fragment` — lightweight variant for HTMX partials.
* :class:`Page` — full HTML document shell.
* :func:`setup` — configure the Jinja2 environment.
* :func:`get_env` — access the global Jinja2 environment.
* :func:`render_component` — render a component to ``Markup``.
* :func:`render_template` — render a template by name with only context.
"""

from joist.component import (
    Component,
    ComponentError,
    Fragment,
    Page,
    get_env,
    render_component,
    render_template,
    setup,
)

__all__ = [
    "Component",
    "ComponentError",
    "Fragment",
    "Page",
    "get_env",
    "render_component",
    "render_template",
    "setup",
]
