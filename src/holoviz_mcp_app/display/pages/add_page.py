"""Add page — web form for creating visualizations."""

import panel as pn

from holoviz_mcp_app.display.database import get_db


def add_page():
    """Create the /add page with a code submission form."""
    pn.extension("codeeditor")

    name_input = pn.widgets.TextInput(name="Name", placeholder="My visualization")
    description_input = pn.widgets.TextInput(name="Description", placeholder="What this shows...")
    method_select = pn.widgets.Select(name="Method", options=["jupyter", "panel"], value="jupyter")

    code_editor = pn.widgets.CodeEditor(
        value='import hvplot.pandas\nimport pandas as pd\n\ndf = pd.DataFrame({"x": [1,2,3,4,5], "y": [2,4,1,5,3]})\ndf.hvplot.line(x="x", y="y", title="Sample Plot")',
        language="python",
        theme="monokai",
        height=300,
        sizing_mode="stretch_width",
    )

    status = pn.pane.Alert("Ready to create visualization.", alert_type="info")
    view_link = pn.pane.HTML("", sizing_mode="stretch_width")

    def submit(event):
        code = code_editor.value
        if not code.strip():
            status.param.update(object="Please enter some code.", alert_type="warning")
            return

        try:
            db = get_db()
            snippet = db.create_visualization(
                app=code,
                name=name_input.value,
                description=description_input.value,
                method=method_select.value,
            )

            if snippet.status == "error":
                status.param.update(
                    object=f"Created with errors: {snippet.error_message}", alert_type="warning"
                )
            else:
                status.param.update(object="Visualization created successfully!", alert_type="success")

            view_link.object = (
                f'<a href="/view?id={snippet.id}" target="_blank" '
                f'style="color:#818cf8;font-size:14px;">View Visualization</a>'
            )
        except Exception as e:
            status.param.update(object=f"Error: {e}", alert_type="danger")

    submit_btn = pn.widgets.Button(name="Create Visualization", button_type="primary")
    submit_btn.on_click(submit)

    return pn.Column(
        pn.pane.HTML('<h1 style="color:#e0e0e0;">Create Visualization</h1>'),
        name_input,
        description_input,
        method_select,
        code_editor,
        submit_btn,
        status,
        view_link,
        sizing_mode="stretch_width",
        styles={"max-width": "900px", "margin": "0 auto", "padding": "20px"},
    )


if pn.state.served:
    add_page().servable()
