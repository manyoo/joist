# joist

**A server-side component architecture for Jinja2 + HTMX applications.**

joist introduces a component layer between your routes and your templates.
Components are typed dataclasses that map to Jinja2 templates. Builder
functions assemble them into trees. Routes just load data and render.

```
Routes (load data)
    ↓
Builders (assemble component trees)    ── joist lives here
    ↓
Templates (render markup)
```

joist ships as a single architectural primitive — **Component = dataclass + template** — plus HTMX utilities and optional FastAPI integration. There is no framework, no lifecycle, and no state management. Render and forget.

---

## Why this exists

Jinja works well for server-rendered pages, and HTMX works well for
incremental HTML updates. But once an application mixes full-page
rendering, partial swaps, modal content, and out-of-band updates,
the template layer becomes hard to manage.

Common problems:

- **Unstructured context dictionaries.** Route handlers assemble large,
  untyped dicts of template variables. Required fields are implicit,
  relationships are hard to see, and refactoring is risky.
- **Full-page and partial rendering drift apart.** The same UI element
  may be rendered by two different templates — one for the initial page
  load, another for an HTMX swap. Markup diverges over time.
- **Reusable fragments are awkward.** Avatars, badges, cards, and modals
  must be duplicated across templates or assembled with Jinja macros
  that mix logic with markup.
- **Route handlers become view assemblers.** Instead of focusing on
  HTTP and data loading, routes shape nested context structures,
  duplicate view logic, and decide between fragment vs. page rendering.

joist solves these problems with a lightweight component layer:

- Each UI fragment becomes a **typed Python object** with an explicit
  data contract.
- Builders (plain functions) **assemble components into trees**.
- The same component and template serve both **full-page and partial
  rendering** through the same code path.
- Templates stay thin — they render their own markup and place children,
  nothing more.

---

## Quick start

```bash
pip install joist
# with FastAPI integration:
pip install "joist[fastapi]"
```

### 1. Define a component

Components are `@dataclass` subclasses of `Component`. Fields become
template variables automatically.

```python
# components.py
from dataclasses import dataclass
from typing import ClassVar
from joist import Component


@dataclass(kw_only=True)
class UserCard(Component):
    template_path: ClassVar = "user_card.html"
    name: str = ""
    email: str = ""
    role: str = ""

    def get_props(self):
        return {"initial": self.name[0] if self.name else "?"}
```

### 2. Write its template

```html
<!-- templates/user_card.html -->
<div class="card">
  <div class="avatar">{{ initial }}</div>
  <h3>{{ name }}</h3>
  <p class="email">{{ email }}</p>
  <span class="badge">{{ role }}</span>
</div>
```

### 3. Build a component tree with a builder function

Builders are ordinary Python functions. They receive domain data and
return component instances. This is where UI composition happens.

```python
# builders.py
from joist import Page
from components import UserCard


def build_profile_page(user: dict, stats: dict) -> Page:
    profile = UserCard(
        name=user["name"],
        email=user["email"],
        role=user["role"],
    )
    # Page.content accepts a Component directly (auto-rendered).
    # Equivalent to: Page(page_title=..., content=profile.render_html())
    return Page(
        page_title=f"Profile — {user['name']}",
        content=profile,
    )
```

### 4. Wire up the route

Routes load data, call a builder, and return the result. They do not
assemble context dicts or choose between fragment/page rendering — that
is handled by the framework integration.

```python
# app.py
from fastapi import FastAPI, Request
from joist.integrators.fastapi import setup_fastapi

app = FastAPI()
joist = setup_fastapi(app, template_dirs=["templates"])


@app.get("/users/{uid}")
async def user_profile(request: Request, uid: str):
    user = load_user(uid)          # data loading
    stats = load_user_stats(uid)   # data loading
    page = build_profile_page(user, stats)  # builder — pure composition
    return joist.fragment_or_page(request, "Profile", page)
```

---

## Architecture

joist divides UI construction into three distinct layers:

### Routes

Routes handle HTTP concerns: request parsing, authentication,
authorization, and data loading. They call builders and return the
result. Routes do not construct template context dicts or decide
between fragment and page rendering.

```python
@router.get("/items")
async def list_items(request: Request):
    items = await load_items()
    return joist.fragment_or_page(
        request,
        "Items",
        build_item_table(items),
    )
```

### Builders

Builders are the composition layer. They take domain data and produce
component instances. Builders can be tested independently, reused
across different routes, and composed with each other.

```python
def build_item_table(items: list[Item]) -> Table:
    """Builder — assembles a table from domain data."""
    rows = [build_item_row(item) for item in items]
    return Table(
        title=f"{len(items)} items",
        rows=rows,
    )


def build_item_row(item: Item) -> Row:
    """Builder — assembles a single row."""
    return Row(
        name=item.name,
        status="active" if item.is_active else "archived",
        price=f"${item.price:.2f}",
    )
```

### Templates

Templates render their own markup and place children. They receive
typed data from component fields. They do not fetch data, compute
values, or make rendering decisions.

```html
<!-- table.html -->
<section>
  <h2>{{ title }}</h2>
  <div class="table-wrap">
    {% for row in rows %}
    {{ row }}  {# pre-rendered Markup — no |safe needed #}
    {% endfor %}
  </div>
</section>
```

---

## Core API

### `Component` — base class

Subclass with `@dataclass(kw_only=True)`. Dataclass fields become
template context. Override `get_props()` for computed properties.

```python
@dataclass(kw_only=True)
class MyComponent(Component):
    template_path: ClassVar = "my_template.html"
    count: int = 0

    def get_props(self):
        return {"label": f"Count: {self.count}"}
```

| Method | Returns | Purpose |
|--------|---------|---------|
| `render_html()` | `Markup` | Safe HTML markup for embedding |
| `render()` | `str` | Plain HTML string |
| `props()` | `dict` | Full template context (for testing/debugging) |
| `has_any` | `bool` | Whether component has content (override to skip empty states) |

Nested `Component` instances are automatically pre-rendered to `Markup`.
Templates use `{{ child }}` directly.

### `Fragment` — HTMX partials

`Fragment` is identical to `Component` except `template_path` is an
instance field. This makes it convenient for inline use in HTMX
partial routes.

```python
from joist import Fragment

# Inline — no subclass needed
frag = Fragment(
    template_path="users/_row.html",
    name=user.name,
    role=user.role,
)
```

Or subclass for reuse:

```python
@dataclass(kw_only=True)
class UserRow(Fragment):
    template_path: str = "users/_row.html"
    user_id: str = ""
    name: str = ""
    role: str = ""
```

### `Page` — document shell

`Page` wraps content in a `<!DOCTYPE html>` document. Ships with a
minimal built-in template that you can override or replace by
subclassing.

```python
from joist import Page

page = Page(
    page_title="Users",
    content=table.render_html(),
    head_extras=Markup('<link rel="stylesheet" href="app.css">'),
)
```

---

## HTMX

```python
from joist.htmx import (
    is_hx_request,           # bool: is this an HTMX request?
    HX,                      # response header builders
    render_page_or_fragment, # one route for both HTMX and direct
)
```

| `HX.*` call | Header produced |
|---|---|
| `HX.trigger("evt")` | `HX-Trigger: evt` |
| `HX.trigger("evt", {...})` | `HX-Trigger: {"evt": {...}}` |
| `HX.trigger("evt", after="swap")` | `HX-Trigger-After-Swap` |
| `HX.retarget("#el")` | `HX-Retarget: #el` |
| `HX.redirect("/url")` | `HX-Redirect: /url` |
| `HX.refresh()` | `HX-Refresh: true` |
| `HX.push_url("/url")` | `HX-Push-Url: /url` |
| `HX.replace_url("/url")` | `HX-Replace-Url: /url` |
| `HX.reselect(".sel")` | `HX-Reselect: .sel` |

`render_page_or_fragment(request, page_title, content)` returns a dict
that your framework integration uses to produce the right kind of
response — fragment for HTMX, full page for direct navigation.

---

## Framework integration

### FastAPI

```python
from joist.integrators.fastapi import setup_fastapi

app = FastAPI()
joist = setup_fastapi(app, template_dirs=["templates"])

# Methods on the joist helper:
joist.response(component)                          # bare HTML
joist.page_response(request, "Title", component)    # full page shell
joist.fragment_or_page(request, "Title", component) # HTMX-aware
```

### Any framework

The core has no framework dependency. Use `render()` to get an HTML
string and return it however your framework expects:

```python
from joist import Component

html = MyComponent(name="test").render()

# Works with Django, Flask, aiohttp, etc.:
return HttpResponse(html)
```

---

## Example: three layers in practice

```python
# ── 1. Components (data contracts) ─────────────────────────────────
@dataclass(kw_only=True)
class ArticleCard(Component):
    template_path: ClassVar = "article_card.html"
    title: str = ""
    summary: str = ""
    author: str = ""
    tags: list = field(default_factory=list)


@dataclass(kw_only=True)
class ArticleList(Component):
    template_path: ClassVar = "article_list.html"
    section_title: str = ""
    articles: list = field(default_factory=list)


# ── 2. Builder (composition) ────────────────────────────────────────
def build_article_page(articles: list[dict]) -> Page:
    cards = [ArticleCard(**a) for a in articles]
    listing = ArticleList(section_title="Latest", articles=cards)
    return Page(
        page_title="Articles",
        content=listing,  # Component auto-rendered — no .render_html() needed
    )


# ── 3. Routes (HTTP + data) ──────────────────────────────────────────
@router.get("/articles")
async def articles_page(request: Request):
    articles = await fetch_articles()               # data
    page = build_article_page(articles)             # build
    return joist.fragment_or_page(request, "Articles", page)  # render
```

---

## Design notes

**No component state or lifecycle.** Components are render-and-forget.
They receive data, produce HTML, and are done. There is no mounting,
updating, or unmounting. This keeps the mental model simple and avoids
an entire class of bugs.

**Builder functions are the right place for composition.** Putting
composition in the route handler embeds presentation logic in HTTP code.
Putting it in the component couples the component to specific children.
Builders — plain functions that receive data and return components —
are the natural middle ground.

**Templates are pure markup.** Conditionals, formatting, and data
transformation happen in Python (`get_props()`, builder functions).
Templates only interpolate values and iterate over lists.

**The same component renders the same HTML everywhere.** Whether it is
the initial page load, an HTMX partial swap, or an out-of-band update,
the rendering path is identical. This eliminates markup drift.

---

## Requirements

- Python 3.13+
- Jinja2 3.1+

Optional: FastAPI 0.115+, Starlette 0.40+

---

## License

MIT
