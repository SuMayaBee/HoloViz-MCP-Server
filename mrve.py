"""
MRVE — Minimum Reproducible Viable Example
HoloViz MCP Server: Inline interactive charts with bidirectional communication.

Run:  fastmcp run mrve.py

Core concept:
  1. LLM calls create_viz → hvPlot builds chart → Bokeh json_item() → BokehJS renders inline in MCP App
  2. User clicks chart  → iframe calls handle_click (app-only tool) → server computes insight → UI shows it
  3. User calls update_viz / set_theme → chart re-renders with new data or colours
"""

import json
import uuid

import bokeh
import holoviews as hv
import hvplot.pandas  # noqa: F401
import pandas as pd
from bokeh.embed import json_item
from bokeh.models import CustomJS, NumeralTickFormatter, TapTool
from fastmcp import FastMCP
from fastmcp.server.apps import AppConfig, ResourceCSP

hv.extension("bokeh")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="holoviz-mrve",
    instructions=(
        "Create interactive charts with create_viz. "
        "Charts render inline in the conversation. "
        "After creating a chart you can update it with update_viz or switch themes with set_theme."
    ),
)

_viz_store: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BOKEH_VERSION = bokeh.__version__
BOKEH_CDN = "https://cdn.bokeh.org/bokeh/release"
MCP_SDK = "https://unpkg.com/@modelcontextprotocol/ext-apps@1.3.1/dist/src/app-with-deps"
VIEW_URI = "ui://holoviz-mrve/viz.html"

PALETTE = ["#818cf8", "#4ade80", "#f59e0b", "#f87171", "#38bdf8", "#c084fc"]

THEME_COLORS = {
    "dark": {
        "bg": "#0f172a", "label": "#94a3b8", "tick": "#475569",
        "grid": "#334155", "grid_alpha": 0.5, "title": "#e0e0e0",
        "legend_text": "#94a3b8",
    },
    "light": {
        "bg": "#ffffff", "label": "#6b7280", "tick": "#d1d5db",
        "grid": "#e5e7eb", "grid_alpha": 0.8, "title": "#1f2937",
        "legend_text": "#6b7280",
    },
}

CHART_TYPES = {"bar", "line", "scatter", "area", "step", "histogram", "kde", "box"}


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------
def _build_chart(kind: str, df: pd.DataFrame, x: str, y: str, title: str,
                 color: str | None = None, theme: str = "dark") -> dict:
    """Build a Bokeh figure via hvPlot and serialize to Bokeh json_item dict."""
    opts: dict = {"title": title, "height": 350, "responsive": True}

    if kind == "histogram":
        opts["y"] = y
        if color and color in df.columns:
            opts["by"] = color
        else:
            opts["color"] = PALETTE[0]
        plot = df.hvplot.hist(**opts)
    elif kind in ("box", "violin"):
        opts["y"] = y
        opts["color"] = PALETTE[0]
        if x and x in df.columns:
            opts["by"] = x
        method = df.hvplot.box if kind == "box" else df.hvplot.violin
        plot = method(**opts)
    else:
        opts["x"] = x
        opts["y"] = y
        if color and color in df.columns:
            opts["by"] = color
        else:
            opts["color"] = PALETTE[0]
            opts["hover_cols"] = "all"
        method = getattr(df.hvplot, kind, df.hvplot.bar)
        plot = method(**opts)

    fig = hv.render(plot, backend="bokeh")

    # Apply theme
    t = THEME_COLORS.get(theme, THEME_COLORS["dark"])
    fig.background_fill_alpha = 0
    fig.border_fill_alpha = 0
    fig.outline_line_alpha = 0
    for axis in fig.axis:
        axis.axis_label_text_color = t["label"]
        axis.major_label_text_color = t["label"]
        axis.major_tick_line_color = t["tick"]
        axis.minor_tick_line_color = None
        axis.axis_line_color = t["tick"]
    for grid in fig.grid:
        grid.grid_line_color = t["grid"]
        grid.grid_line_alpha = t["grid_alpha"]
    if fig.title:
        fig.title.text_color = t["title"]
        fig.title.text_font_size = "14px"
    if fig.legend:
        fig.legend.label_text_color = t["legend_text"]
        fig.legend.background_fill_alpha = 0
        fig.legend.border_line_alpha = 0

    fig.sizing_mode = "stretch_width"
    for axis in fig.yaxis:
        try:
            axis.formatter = NumeralTickFormatter(format="0,0.[00]")
        except Exception:  # noqa: S110
            pass

    # Wire TapTool → postMessage("bokeh-tap") for bidirectional click handling
    fig.add_tools(TapTool())
    for renderer in fig.renderers:
        if hasattr(renderer, "data_source"):
            source = renderer.data_source
            cols = list(source.data.keys())
            x_key = x if x in source.data else (cols[0] if cols else "x")
            y_key = y if y in source.data else (cols[1] if len(cols) > 1 else "y")
            source.selected.js_on_change(
                "indices",
                CustomJS(
                    args=dict(source=source),
                    code=(
                        "try {"
                        "const idx = source.selected.indices;"
                        "if (!idx.length) return;"
                        "const i = idx[0];"
                        f"const xd = source.data['{x_key}'];"
                        f"const yd = source.data['{y_key}'];"
                        "if (!xd || !yd) return;"
                        "window.dispatchEvent(new CustomEvent('bokeh-tap', {"
                        "  detail: { index: i, xValue: String(xd[i]), yValue: Number(yd[i]) }"
                        "}));"
                        "} catch(e) { console.warn('Click callback:', e); }"
                    ),
                ),
            )
            break

    return json_item(fig, "chart-container")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def create_viz(
    kind: str,
    title: str,
    data: dict[str, list],
    x: str,
    y: str,
    color: str | None = None,
) -> str:
    """Create an interactive chart rendered inline in the conversation.

    Parameters
    ----------
    kind : str
        Chart type — bar, line, scatter, area, step, histogram, kde, box.
    title : str
        Chart title displayed above the chart.
    data : dict[str, list]
        Dataset as {column_name: [values]}.
    x : str
        Column for the x-axis.
    y : str
        Column for the y-axis (should be numeric).
    color : str
        Optional column for color / grouping.
    """
    try:
        df = pd.DataFrame(data)
        spec = _build_chart(kind, df, x, y, title, color)
        viz_id = str(uuid.uuid4())[:8]
        _viz_store[viz_id] = {
            "id": viz_id, "kind": kind, "title": title,
            "data": data, "x": x, "y": y, "color": color,
            "theme": "dark",
        }
        return json.dumps({"action": "create", "id": viz_id, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def update_viz(
    viz_id: str,
    kind: str | None = None,
    title: str | None = None,
    x: str | None = None,
    y: str | None = None,
    color: str | None = None,
) -> str:
    """Update an existing chart — change chart type, axes, or title without re-creating it.

    Parameters
    ----------
    viz_id : str
        ID returned by create_viz.
    kind : str
        New chart type, or omit to keep the existing one.
    title : str
        New title, or omit to keep the existing one.
    x : str
        New x-axis column, or omit to keep.
    y : str
        New y-axis column, or omit to keep.
    color : str
        New grouping column, or omit to keep.
    """
    if viz_id not in _viz_store:
        return json.dumps({"action": "error", "message": f"Visualization '{viz_id}' not found."})
    viz = _viz_store[viz_id]
    if kind:
        viz["kind"] = kind
    if title:
        viz["title"] = title
    if x:
        viz["x"] = x
    if y:
        viz["y"] = y
    if color is not None:
        viz["color"] = color or None

    try:
        df = pd.DataFrame(viz["data"])
        spec = _build_chart(viz["kind"], df, viz["x"], viz["y"], viz["title"], viz.get("color"), viz.get("theme", "dark"))
        return json.dumps({"action": "update", "id": viz_id, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(app=AppConfig(resource_uri=VIEW_URI))
def set_theme(viz_id: str, theme: str = "dark") -> str:
    """Switch a chart between dark and light theme.

    Parameters
    ----------
    viz_id : str
        ID returned by create_viz.
    theme : str
        "dark" or "light".
    """
    if theme not in ("dark", "light"):
        return json.dumps({"action": "error", "message": "theme must be 'dark' or 'light'"})
    if viz_id not in _viz_store:
        return json.dumps({"action": "error", "message": f"Visualization '{viz_id}' not found."})
    viz = _viz_store[viz_id]
    viz["theme"] = theme
    try:
        df = pd.DataFrame(viz["data"])
        spec = _build_chart(viz["kind"], df, viz["x"], viz["y"], viz["title"], viz.get("color"), theme)
        return json.dumps({"action": "theme_change", "id": viz_id, "theme": theme, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(app=AppConfig(resource_uri=VIEW_URI, visibility=["app"]))
def handle_click(viz_id: str, point_index: int, x_value: str, y_value: float) -> str:
    """Handle a chart click event. Called by the MCP App, not the LLM.

    Parameters
    ----------
    viz_id : str
        ID of the clicked visualization.
    point_index : int
        Index of the clicked data point.
    x_value : str
        X-axis value at the clicked point.
    y_value : float
        Y-axis value at the clicked point.
    """
    if viz_id not in _viz_store:
        return json.dumps({"action": "insight", "message": "Visualization not found."})
    viz = _viz_store[viz_id]
    df = pd.DataFrame(viz["data"])
    y_col = viz["y"]
    if y_col in df.columns:
        series = pd.to_numeric(df[y_col], errors="coerce").dropna()
        mean_val = float(series.mean())
        max_val = float(series.max())
        comparison = "above" if y_value > mean_val else "below"
        pct = round((y_value / max_val) * 100, 1) if max_val else 0
        message = (
            f"{x_value}: {y_value:,.2f}\n"
            f"This is {comparison} the mean ({mean_val:,.2f}).\n"
            f"Represents {pct}% of the maximum ({max_val:,.2f})."
        )
    else:
        message = f"Clicked: {x_value} = {y_value}"
    return json.dumps({"action": "insight", "message": message})


# ---------------------------------------------------------------------------
# HTML Resource (MCP App template)
# ---------------------------------------------------------------------------
_BOKEH_SCRIPTS = "\n".join(
    f'  <script src="{BOKEH_CDN}/bokeh{ext}{BOKEH_VERSION}.min.js" crossorigin="anonymous"></script>'
    for ext in ["-", "-gl-", "-widgets-", "-tables-"]
)


@mcp.resource(
    VIEW_URI,
    app=AppConfig(
        csp=ResourceCSP(resource_domains=["https://cdn.bokeh.org", "https://unpkg.com"]),
    ),
)
def viz_view() -> str:
    """Interactive chart viewer rendered inline inside the AI chat UI."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>HoloViz MRVE</title>
{_BOKEH_SCRIPTS}
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0f172a; color: #e0e0e0; padding: 8px; }}
    .toolbar {{
      display: flex; align-items: center; gap: 6px; padding: 6px 0 8px 0;
      border-bottom: 1px solid #334155; margin-bottom: 8px;
    }}
    .btn {{
      padding: 3px 10px; border-radius: 4px; border: 1px solid #334155;
      background: #1e293b; color: #94a3b8; cursor: pointer; font-size: 11px;
    }}
    .btn:hover {{ border-color: #818cf8; color: #818cf8; }}
    .spacer {{ flex: 1; }}
    .viz-id {{ font-size: 11px; color: #475569; }}
    #chart-container {{ width: 100%; min-height: 320px; border-radius: 6px; overflow: hidden; }}
    #insight-bar {{
      display: none; background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.3);
      border-radius: 6px; padding: 8px 12px; margin-top: 8px;
      font-size: 13px; color: #93c5fd; white-space: pre-line;
    }}
    #status {{ font-size: 11px; color: #475569; text-align: center; padding: 6px 0 2px; }}
    .loading {{
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 10px; min-height: 250px; color: #64748b; font-size: 13px;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .spinner {{
      width: 28px; height: 28px; border: 3px solid #334155;
      border-top-color: #818cf8; border-radius: 50%; animation: spin 0.8s linear infinite;
    }}
  </style>
</head>
<body>
  <div class="toolbar" id="toolbar" style="display:none">
    <button class="btn" id="btn-theme" onclick="toggleTheme()">Light Mode</button>
    <div class="spacer"></div>
    <span class="viz-id" id="viz-id"></span>
  </div>

  <div id="chart-container">
    <div class="loading"><div class="spinner"></div><span>Preparing chart...</span></div>
  </div>
  <div id="insight-bar"></div>
  <div id="status">holoviz-mrve ready</div>

  <script type="module">
    import {{ App }} from "{MCP_SDK}";
    const app = new App({{ name: "HoloViz MRVE", version: "0.1.0" }});
    let currentVizId = null;
    let currentTheme = "dark";

    // Bokeh cleanup before re-embed (avoids ghost documents)
    function clearChart() {{
      const el = document.getElementById("chart-container");
      if (window.Bokeh && Bokeh.index) {{
        for (const [id, view] of [...Bokeh.index]) {{
          if (el.contains(view.el)) {{ try {{ view.remove(); }} catch {{}} Bokeh.index.delete(id); }}
        }}
      }}
      el.innerHTML = "";
    }}

    // ── Chart click → bidirectional insight ─────────────────────────────────
    window.addEventListener("bokeh-tap", async (e) => {{
      if (!currentVizId) return;
      try {{
        const response = await app.callServerTool({{
          name: "handle_click",
          arguments: {{
            viz_id: currentVizId,
            point_index: e.detail.index || 0,
            x_value: String(e.detail.xValue || ""),
            y_value: Number(e.detail.yValue || 0),
          }},
        }});
        const t = response?.content?.find(c => c.type === "text");
        if (t) {{
          const r = JSON.parse(t.text);
          if (r.action === "insight" && r.message) {{
            const bar = document.getElementById("insight-bar");
            bar.textContent = r.message;
            bar.style.display = "block";
          }}
        }}
      }} catch (err) {{ console.log("Click handler:", err); }}
    }});

    // ── Theme toggle ─────────────────────────────────────────────────────────
    window.toggleTheme = async () => {{
      currentTheme = currentTheme === "dark" ? "light" : "dark";
      document.getElementById("btn-theme").textContent = currentTheme === "dark" ? "Light Mode" : "Dark Mode";
      if (!currentVizId) return;
      try {{
        const response = await app.callServerTool({{
          name: "set_theme",
          arguments: {{ viz_id: currentVizId, theme: currentTheme }},
        }});
        const t = response?.content?.find(c => c.type === "text");
        if (t) {{
          const r = JSON.parse(t.text);
          if (r.action === "theme_change" && r.figure) {{
            clearChart();
            await Bokeh.embed.embed_item(r.figure);
          }}
        }}
      }} catch (err) {{ console.log("Theme switch:", err); }}
    }};

    // ── Tool result handler ──────────────────────────────────────────────────
    app.ontoolresult = async ({{ content }}) => {{
      const tc = content?.find(c => c.type === "text");
      if (!tc) return;
      let r;
      try {{ r = JSON.parse(tc.text); }} catch {{ return; }}

      if (r.action === "create" || r.action === "update") {{
        currentVizId = r.id;
        document.getElementById("toolbar").style.display = "flex";
        document.getElementById("viz-id").textContent = "ID: " + r.id;
        clearChart();
        try {{
          await Bokeh.embed.embed_item(r.figure);
          document.getElementById("status").textContent = "Click any data point for insights";
          document.getElementById("insight-bar").style.display = "none";
        }} catch (err) {{
          document.getElementById("chart-container").innerHTML =
            '<div style="color:#f87171;text-align:center;padding:20px">Render error: ' + err.message + "</div>";
        }}
      }}

      if (r.action === "theme_change" && r.figure) {{
        clearChart();
        try {{ await Bokeh.embed.embed_item(r.figure); }} catch {{}}
      }}

      if (r.action === "insight" && r.message) {{
        const bar = document.getElementById("insight-bar");
        bar.textContent = r.message;
        bar.style.display = "block";
      }}

      if (r.action === "error") {{
        document.getElementById("chart-container").innerHTML =
          '<div style="color:#f87171;text-align:center;padding:20px">' + r.message + "</div>";
      }}
    }};

    await app.connect();
    document.getElementById("status").textContent = "Connected — ready for charts";
  </script>
</body>
</html>"""
