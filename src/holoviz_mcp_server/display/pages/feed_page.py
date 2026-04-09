"""Feed page showing a live list of recent visualizations."""

import panel as pn

from holoviz_mcp_server.display.database import get_db


def _get_view_url(snippet_id: str) -> str:
    port = 5077
    try:
        from holoviz_mcp_server.config import get_config
        port = get_config().port
    except Exception:
        pass
    return f"http://localhost:{port}/view?id={snippet_id}"


def feed_page():
    """Create the /feed page."""
    limit = pn.widgets.IntSlider(name="Max visualizations", value=5, start=1, end=50, sizing_mode="stretch_width")
    feed = pn.Column(sizing_mode="stretch_both", scroll=True)

    def make_card(snippet):
        url = _get_view_url(snippet.id)
        created = snippet.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        title_md = f"### {snippet.name or snippet.id}  \n*{created}*"
        if snippet.description:
            title_md += f"  \n{snippet.description}"

        iframe_html = f"""
        <div style="resize:vertical;overflow:hidden;height:400px;min-height:200px;width:100%;border:1px solid #555;border-radius:4px;">
            <iframe src="{url}" style="width:100%;height:100%;border:none;" frameborder="0" allow="fullscreen"></iframe>
        </div>
        """

        code_editor = pn.widgets.CodeEditor(
            value=snippet.app,
            language="python",
            theme="monokai",
            sizing_mode="stretch_width",
            min_height=200,
            readonly=True,
        )

        delete_btn = pn.widgets.Button(name="Delete", button_type="danger", width=80)

        def on_delete(event, sid=snippet.id):
            get_db().delete_snippet(sid)
            if sid in pn.state.cache.get("views", {}):
                del pn.state.cache["views"][sid]
            update_feed()

        delete_btn.on_click(on_delete)

        open_btn = pn.widgets.Button(name="Open", button_type="light", width=80)
        open_btn.js_on_click(args={"url": url}, code="window.open(url, '_blank')")

        return pn.Card(
            pn.pane.Markdown(title_md),
            pn.Tabs(
                (
                    "View",
                    pn.pane.HTML(iframe_html, sizing_mode="stretch_width"),
                ),
                ("Code", code_editor),
            ),
            pn.Row(pn.Spacer(), open_btn, delete_btn),
            sizing_mode="stretch_width",
            collapsible=False,
            margin=(0, 0, 12, 0),
        )

    def update_feed(*_):
        snippets = get_db().list_snippets(limit=limit.value)
        if not snippets:
            feed.objects = [pn.pane.Markdown("*No visualizations yet. Ask the AI to show something.*")]
            return

        new_ids = [s.id for s in snippets]
        current_ids = [getattr(obj, "_snippet_id", None) for obj in feed.objects]
        if new_ids == current_ids:
            return

        cards = []
        for snippet in snippets:
            card = make_card(snippet)
            card._snippet_id = snippet.id  # type: ignore[attr-defined]
            cards.append(card)
        feed.objects = cards

    limit.param.watch(update_feed, "value")
    update_feed()
    pn.state.add_periodic_callback(update_feed, 3000)

    return pn.template.FastListTemplate(
        title="HoloViz MCP — Visualization Feed",
        sidebar=[
            pn.pane.Markdown("### Settings"),
            limit,
        ],
        main=[feed],
        theme="dark",
        sidebar_width=220,
    )


if pn.state.served:
    pn.state.cache.setdefault("views", {})
    feed_page().servable()
