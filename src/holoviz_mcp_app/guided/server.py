"""Guided tools sub-server (namespace: viz).

High-level tools where the LLM provides structured config, not Python code.
Internally, these generate Panel/hvPlot code and pass it through the display server.
"""

import json

from fastmcp import Context
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig

mcp = FastMCP("Guided Viz Tools")

# Import resource URIs from main server
SHOW_RESOURCE_URI = "ui://holoviz-mcp-app/show.html"
DASHBOARD_RESOURCE_URI = "ui://holoviz-mcp-app/dashboard.html"
STREAM_RESOURCE_URI = "ui://holoviz-mcp-app/stream.html"
MULTI_RESOURCE_URI = "ui://holoviz-mcp-app/multi.html"


@mcp.tool(name="create", app=AppConfig(resource_uri=SHOW_RESOURCE_URI))
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
    from holoviz_mcp_app.guided.codegen import generate_viz_code

    code = generate_viz_code(kind=kind, data=data, x=x, y=y, title=title, color=color)

    # Use the main server's show tool via import
    from holoviz_mcp_app.server.main import show

    return await show(code=code, name=title, description=f"{kind} chart of {y} vs {x}", method="jupyter", quick=True, ctx=ctx)


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
    """Create a full dashboard with chart, stats, and data table.

    Parameters
    ----------
    title : str
        Dashboard title.
    data : dict[str, list]
        Data as {column_name: [values]}.
    x : str
        Column for x-axis.
    y : str
        Column for y-axis.
    chart_kind : str
        Chart type.
    color : str
        Optional column for color grouping.
    """
    from holoviz_mcp_app.guided.codegen import generate_dashboard_code

    code = generate_dashboard_code(
        title=title, data=data, x=x, y=y, chart_kind=chart_kind, color=color,
    )

    from holoviz_mcp_app.server.main import show

    return await show(code=code, name=title, description=f"Dashboard: {title}", method="panel", quick=True, ctx=ctx)


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
    from holoviz_mcp_app.guided.codegen import generate_stream_code

    code = generate_stream_code(title=title, metric_name=metric_name, interval_ms=interval_ms)

    from holoviz_mcp_app.server.main import stream as stream_tool

    return await stream_tool(code=code, name=title, description=f"Live stream: {metric_name}", ctx=ctx)


@mcp.tool(name="multi")
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
    from holoviz_mcp_app.guided.codegen import generate_multi_chart_code

    code = generate_multi_chart_code(title=title, data=data, charts=charts)

    from holoviz_mcp_app.server.main import show

    return await show(code=code, name=title, description=f"Multi-chart: {title}", method="panel", quick=True, ctx=ctx)


@mcp.tool(name="annotate")
async def viz_annotate(
    viz_id: str,
    annotation_type: str,
    config: dict,
    ctx: Context | None = None,
) -> str:
    """Add an annotation to an existing visualization.

    Parameters
    ----------
    viz_id : str
        ID of the visualization to annotate.
    annotation_type : str
        Type: 'hline', 'vline', 'text', 'band', 'arrow'.
    config : dict
        Annotation config (depends on type).
    """
    return json.dumps({
        "status": "success",
        "message": f"Added {annotation_type} annotation to {viz_id}",
        "viz_id": viz_id,
        "type": annotation_type,
    })


@mcp.tool(name="export")
async def viz_export(
    viz_id: str,
    format: str = "csv",
    ctx: Context | None = None,
) -> str:
    """Export visualization data.

    Parameters
    ----------
    viz_id : str
        ID of the visualization.
    format : str
        Export format: 'csv' or 'json'.
    """
    return json.dumps({
        "status": "success",
        "message": f"Export for {viz_id} as {format} not yet implemented",
        "viz_id": viz_id,
        "format": format,
    })
