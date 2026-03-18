"""View page — displays a single visualization by ID or slug."""

import logging
import sys
import traceback
from datetime import datetime
from datetime import timezone

import panel as pn

from holoviz_mcp_app.display.database import Snippet
from holoviz_mcp_app.display.database import get_db
from holoviz_mcp_app.display.utils import execute_in_module
from holoviz_mcp_app.display.utils import extract_last_expression
from holoviz_mcp_app.display.utils import find_extensions

logger = logging.getLogger(__name__)


def create_view(snippet_id: str) -> pn.viewable.Viewable | None:
    """Create a view for a single visualization snippet."""
    db = get_db()
    snippet = db.get_snippet(snippet_id)

    session_extensions = list({"codeeditor"} | set(find_extensions(snippet.app) if snippet else []))
    pn.extension(*session_extensions)

    if not snippet:
        return pn.pane.Markdown(f"# Error\n\nSnippet {snippet_id} not found.")

    start_time = datetime.now(timezone.utc)
    try:
        result = _execute_code(snippet)
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        get_db().update_snippet(
            snippet_id,
            status="success",
            error_message="",
            execution_time=execution_time,
        )
        return result

    except Exception as e:
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

        get_db().update_snippet(
            snippet_id,
            status="error",
            error_message=error_msg,
            execution_time=execution_time,
        )

        snippet.status = "error"
        snippet.error_message = error_msg

    if snippet.status == "error":
        error_content = f"""
# Error: {snippet.name or snippet_id}

**Method:** {snippet.method}

## Error Message

```bash
{snippet.error_message}
```

## Code

```python
{snippet.app}
```
"""
        return pn.pane.Markdown(error_content, sizing_mode="stretch_width")

    return result


def _execute_code(snippet: Snippet) -> pn.viewable.Viewable | None:
    """Execute code and return Panel component."""
    module_name = f"bokeh_app_hvmcp_snippet_{snippet.id.replace('-', '_')}"
    preamble = "import panel as pn\n\npn.config.design = None\n\n"

    if snippet.method == "jupyter":
        app = preamble + snippet.app

        try:
            statements, last_expr = extract_last_expression(app)
        except ValueError as e:
            raise ValueError(f"Failed to parse code: {e}") from e

        namespace = execute_in_module(
            statements,
            module_name=module_name,
            cleanup=False,
        )

        try:
            if last_expr:
                result = eval(last_expr, namespace)  # noqa: S307
            else:
                result = None
        finally:
            sys.modules.pop(module_name, None)

        if result is not None:
            return pn.panel(result, sizing_mode="stretch_width")
        else:
            return pn.pane.Markdown("*Code executed successfully (no output to display)*")

    else:  # panel method
        app = preamble + snippet.app
        execute_in_module(
            app,
            module_name=module_name,
            cleanup=True,
        )

        servables = ".servable()" in snippet.app
        if not servables:
            pn.pane.Markdown("*Code executed (no servable objects found)*").servable()
    return None


def view_page():
    """Create the /view page."""
    snippet_id = ""
    slug = ""
    if hasattr(pn.state, "session_args"):
        snippet_id_bytes = pn.state.session_args.get("id", [b""])[0]
        snippet_id = snippet_id_bytes.decode("utf-8") if snippet_id_bytes else ""

        slug_bytes = pn.state.session_args.get("slug", [b""])[0]
        slug = slug_bytes.decode("utf-8") if slug_bytes else ""

    if snippet_id:
        return create_view(snippet_id)
    elif slug:
        db = get_db()
        snippet = db.get_snippet_by_slug(slug)
        if snippet:
            return create_view(snippet.id)
        else:
            return pn.pane.Markdown(f"# Error\n\nNo snippet found with slug '{slug}'.")
    else:
        return pn.pane.Markdown("# Error\n\nNo snippet ID or slug provided.")


if pn.state.served:
    pn.state.cache["views"] = pn.state.cache.get("views", {})
    view_page().servable()
