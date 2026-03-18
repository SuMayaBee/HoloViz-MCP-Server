"""Admin page — management table for all snippets."""

import panel as pn

from holoviz_mcp_app.display.database import get_db


def admin_page():
    """Create the /admin page with snippet management."""
    pn.extension("tabulator")

    db = get_db()
    snippets = db.list_snippets(limit=1000)

    if not snippets:
        return pn.Column(
            pn.pane.HTML('<h1 style="color:#e0e0e0;">Admin — Snippets</h1>'),
            pn.pane.HTML(
                '<div style="text-align:center;color:#64748b;padding:40px;">No snippets found.</div>'
            ),
            sizing_mode="stretch_width",
            styles={"max-width": "1200px", "margin": "0 auto", "padding": "20px"},
        )

    import pandas as pd

    data = []
    for s in snippets:
        data.append(
            {
                "ID": s.id[:8],
                "Name": s.name or "Unnamed",
                "Method": s.method,
                "Status": s.status,
                "Created": s.created_at.strftime("%Y-%m-%d %H:%M"),
                "Full ID": s.id,
            }
        )

    df = pd.DataFrame(data)

    table = pn.widgets.Tabulator(
        df,
        sizing_mode="stretch_width",
        height=600,
        show_index=False,
        selectable="checkbox",
        hidden_columns=["Full ID"],
    )

    status = pn.pane.Alert("", alert_type="info", visible=False)

    def delete_selected(event):
        selection = table.selection
        if not selection:
            status.param.update(object="No rows selected.", alert_type="warning", visible=True)
            return

        deleted = 0
        for idx in selection:
            full_id = df.iloc[idx]["Full ID"]
            if db.delete_snippet(full_id):
                deleted += 1

        status.param.update(
            object=f"Deleted {deleted} snippet(s).", alert_type="success", visible=True
        )

    delete_btn = pn.widgets.Button(name="Delete Selected", button_type="danger")
    delete_btn.on_click(delete_selected)

    return pn.Column(
        pn.pane.HTML('<h1 style="color:#e0e0e0;">Admin — Snippets</h1>'),
        pn.Row(delete_btn),
        status,
        table,
        sizing_mode="stretch_width",
        styles={"max-width": "1200px", "margin": "0 auto", "padding": "20px"},
    )


if pn.state.served:
    admin_page().servable()
