"""Feed page — live-updating visualization list."""

import logging

import panel as pn

from holoviz_mcp_app.display.database import get_db

logger = logging.getLogger(__name__)


def _get_snippets(limit: int = 20):
    """Get recent snippets from the database."""
    db = get_db()
    return db.list_snippets(limit=limit)


def _build_snippet_card(snippet) -> pn.Column:
    """Build a card for a single snippet."""
    status_color = {"success": "#4ade80", "error": "#f87171", "pending": "#fbbf24"}.get(
        snippet.status, "#94a3b8"
    )

    header = pn.pane.HTML(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;
             border-bottom:1px solid #334155;">
            <div>
                <strong style="color:#e0e0e0;">{snippet.name or 'Unnamed'}</strong>
                <span style="color:#64748b;font-size:12px;margin-left:8px;">
                    {snippet.method} | {snippet.created_at.strftime('%Y-%m-%d %H:%M')}
                </span>
            </div>
            <span style="color:{status_color};font-size:12px;font-weight:bold;">
                {snippet.status.upper()}
            </span>
        </div>
        """,
        sizing_mode="stretch_width",
    )

    view_link = pn.pane.HTML(
        f'<a href="/view?id={snippet.id}" target="_blank" '
        f'style="color:#818cf8;font-size:13px;padding:4px 12px;">View</a>',
        sizing_mode="stretch_width",
    )

    code_pane = pn.pane.Markdown(
        f"```python\n{snippet.app[:500]}{'...' if len(snippet.app) > 500 else ''}\n```",
        sizing_mode="stretch_width",
    )

    return pn.Column(
        header,
        code_pane,
        view_link,
        sizing_mode="stretch_width",
        css_classes=["card"],
        styles={
            "background": "#1e293b",
            "border": "1px solid #334155",
            "border-radius": "8px",
            "margin-bottom": "12px",
        },
    )


def feed_page():
    """Create the /feed page with live-updating visualization list."""
    pn.extension()

    snippets = _get_snippets()
    cards = [_build_snippet_card(s) for s in snippets]

    title = pn.pane.HTML(
        '<h1 style="color:#e0e0e0;margin:0;">HoloViz MCP App — Feed</h1>',
        sizing_mode="stretch_width",
    )

    feed_column = pn.Column(
        *cards,
        sizing_mode="stretch_width",
    )

    if not cards:
        feed_column.append(
            pn.pane.HTML(
                '<div style="text-align:center;color:#64748b;padding:40px;">'
                "No visualizations yet. Use the MCP tools to create one!</div>",
                sizing_mode="stretch_width",
            )
        )

    layout = pn.Column(
        title,
        pn.layout.Divider(),
        feed_column,
        sizing_mode="stretch_width",
        styles={"max-width": "900px", "margin": "0 auto", "padding": "20px"},
    )

    def _refresh():
        snippets = _get_snippets()
        feed_column.clear()
        for s in snippets:
            feed_column.append(_build_snippet_card(s))

    pn.state.add_periodic_callback(_refresh, period=3000)

    return layout


if pn.state.served:
    pn.state.cache["views"] = pn.state.cache.get("views", {})
    feed_page().servable()
