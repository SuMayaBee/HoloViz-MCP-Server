"""Guided tools sub-server (namespace: viz).

High-level tools where the LLM provides structured config, not Python code.
Internally, these generate Panel/hvPlot code and pass it through the display server.
"""

import json

from fastmcp import Context
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig

mcp = FastMCP("Guided Viz Tools")

# Resource URIs match those defined on the main server
VIZ_RESOURCE_URI = "ui://holoviz-mcp-server/viz-v7"
STREAM_RESOURCE_URI = "ui://holoviz-mcp-server/stream"
DASHBOARD_RESOURCE_URI = "ui://holoviz-mcp-server/dashboard-v2"


@mcp.tool(name="create", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def viz_create(
    kind: str,
    data: dict[str, list],
    x: str,
    y: str,
    title: str = "Visualization",
    color: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Create an interactive visualization from structured config — no Python needed.

    Parameters
    ----------
    kind : str
        Chart type: bar, line, scatter, area, hist, box, violin, kde, step, heatmap, hexbin.
    data : dict[str, list]
        Data as {column_name: [values]}. All lists must be same length.
    x : str
        Column for x-axis.
    y : str
        Column for y-axis.
    title : str
        Chart title.
    color : str
        Optional column for color grouping.
    """
    from holoviz_mcp_server.codegen.codegen import generate_viz_code

    code = generate_viz_code(kind=kind, data=data, x=x, y=y, title=title, color=color)

    from holoviz_mcp_server.server.main import _viz_store
    from holoviz_mcp_server.server.main import show

    result = await show(
        code=code,
        name=title,
        description=f"{kind} chart of {y} vs {x}",
        method="jupyter",
        quick=True,
        ctx=ctx,
    )

    try:
        parsed = json.loads(result)
        viz_id = parsed.get("viz_id") or parsed.get("id")
        if viz_id:
            _viz_store[viz_id] = {
                "id": viz_id,
                "kind": kind,
                "title": title,
                "data": data,
                "x": x,
                "y": y,
                "color": color,
                "theme": "dark",
                "annotations": [],
                "target_id": "chart-container",
            }
    except Exception:  # noqa: S110
        pass

    return result


@mcp.tool(name="dashboard", app=AppConfig(resource_uri=DASHBOARD_RESOURCE_URI))
async def viz_dashboard(
    title: str,
    data: dict[str, list],
    x: str,
    y: str,
    chart_kind: str = "bar",
    color: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Create an interactive dashboard with chart, summary stats, data table, and live filter widgets.

    The dashboard renders INLINE in the chat as an MCP App.
    After calling this tool, always include the markdown link from the result's "message" field
    in your response so the user can open the Panel server in a browser.

    Parameters
    ----------
    title : str
        Dashboard title.
    data : dict[str, list]
        Data as {column_name: [values]}.
    x : str
        Column for x-axis.
    y : str
        Column for y-axis (must be numeric for stats).
    chart_kind : str
        Chart type: bar, line, scatter, area, histogram, etc.
    color : str
        Optional column for color grouping.
    """
    import uuid

    import pandas as pd

    from holoviz_mcp_server.chart_builders import build_bokeh_figure
    from holoviz_mcp_server.chart_builders import build_widget_config
    from holoviz_mcp_server.server.main import _viz_store

    try:
        df = pd.DataFrame(data)
        spec = build_bokeh_figure(chart_kind, df, x, y, title, color, target_id="chart")

        y_series = pd.to_numeric(df[y], errors="coerce").dropna()
        stats = {
            "count": int(y_series.count()),
            "mean": round(float(y_series.mean()), 2),
            "median": round(float(y_series.median()), 2),
            "min": round(float(y_series.min()), 2),
            "max": round(float(y_series.max()), 2),
            "std": round(float(y_series.std()), 2) if len(y_series) > 1 else 0.0,
            "sum": round(float(y_series.sum()), 2),
        }

        widget_config = build_widget_config(df)

        viz_id = str(uuid.uuid4())[:8]
        _viz_store[viz_id] = {
            "id": viz_id, "kind": chart_kind, "title": title,
            "data": data, "x": x, "y": y,
            "color": color, "theme": "dark", "annotations": [],
            "is_dashboard": True, "target_id": "chart",
        }

        # Also store in Panel server to get a proper view URL
        panel_url = ""
        try:
            from holoviz_mcp_server.codegen.codegen import generate_dashboard_code
            from holoviz_mcp_server.server.main import _client
            from holoviz_mcp_server.server.main import _externalize_url

            if _client and _client.is_healthy():
                code = generate_dashboard_code(title=title, data=data, x=x, y=y, chart_kind=chart_kind, color=color)
                resp = _client.create_snippet(code=code, name=title, description=f"Dashboard: {title}", method="panel")
                panel_url = _externalize_url(resp.get("url", ""))
        except Exception:  # noqa: S110
            pass

        max_table_rows = 200
        total_rows = len(df)
        open_link = f"[Open visualization]({panel_url})" if panel_url else "[Open visualization](http://localhost:5077)"
        result: dict = {
            "action": "dashboard",
            "id": viz_id,
            "title": title,
            "message": (
                f"Dashboard '{title}' is now rendering inline in the chat. "
                "It has an interactive chart, statistics, sortable data table, and filter widgets. "
                f"Always include this exact markdown link in your response: {open_link}"
            ),
            "figure": spec,
            "stats": stats,
            "table": {
                "columns": list(df.columns),
                "rows": df.head(max_table_rows).values.tolist(),
                "total": total_rows,
            },
            "widget_config": widget_config,
        }
        if total_rows > 10_000:
            result["sampled"] = True
            result["total_rows"] = total_rows
            result["shown_rows"] = 10_000
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(name="stream", app=AppConfig(resource_uri=STREAM_RESOURCE_URI))
async def viz_stream(
    title: str = "Live Stream",
    metric_name: str = "value",
    interval_ms: int = 1000,
    ctx: Context | None = None,
) -> str:
    """Create a live streaming visualization with periodic data updates.

    Parameters
    ----------
    title : str
        Stream title.
    metric_name : str
        Name of the metric being streamed.
    interval_ms : int
        Update interval in milliseconds.
    """
    from holoviz_mcp_server.codegen.codegen import generate_stream_code

    code = generate_stream_code(title=title, metric_name=metric_name, interval_ms=interval_ms)

    from holoviz_mcp_server.server.main import stream as stream_tool

    return await stream_tool(code=code, name=title, description=f"Live stream: {metric_name}", ctx=ctx)


@mcp.tool(name="multi", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def viz_multi(
    title: str,
    data: dict[str, list],
    charts: list[dict],
    ctx: Context | None = None,
) -> str:
    """Create a multi-chart view with linked selections.

    Parameters
    ----------
    title : str
        Dashboard title.
    data : dict[str, list]
        Shared data for all charts.
    charts : list[dict]
        List of chart configs: [{"kind": "bar", "x": "col1", "y": "col2", "title": "..."}].
    """
    from holoviz_mcp_server.codegen.codegen import generate_multi_chart_code

    code = generate_multi_chart_code(title=title, data=data, charts=charts)

    from holoviz_mcp_server.server.main import show

    return await show(code=code, name=title, description=f"Multi-chart: {title}", method="panel", quick=True, ctx=ctx)


@mcp.tool(name="annotate")
async def viz_annotate(
    viz_id: str,
    annotation_type: str,
    config: dict,
    ctx: Context | None = None,
) -> str:
    """Add an annotation to an existing visualization (hline, vline, text, band, arrow).

    Parameters
    ----------
    viz_id : str
        ID of the visualization to annotate.
    annotation_type : str
        One of: hline, vline, text, band, arrow.
    config : dict
        hline: {y_value, color?, dash?, label?}  vline: {x_value, color?, dash?}
        text: {x, y, text, color?, font_size?}   band: {lower, upper, color?, alpha?}
        arrow: {x_start, y_start, x_end, y_end, color?}
    """
    from holoviz_mcp_server.server.main import annotate_viz

    return await annotate_viz(viz_id=viz_id, annotation_type=annotation_type, config=config, ctx=ctx)


@mcp.tool(name="export")
async def viz_export(
    viz_id: str,
    format: str = "csv",
    ctx: Context | None = None,
) -> str:
    """Export visualization data as CSV or JSON.

    Parameters
    ----------
    viz_id : str
        ID of the visualization to export.
    format : str
        "csv" or "json".
    """
    from holoviz_mcp_server.server.main import export_data

    return await export_data(viz_id=viz_id, format=format, ctx=ctx)
