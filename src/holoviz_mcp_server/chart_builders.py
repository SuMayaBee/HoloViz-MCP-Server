"""Chart building helpers — Bokeh figure construction, theming, annotations.

Used by the interactive tools (update_viz, set_theme, annotate_viz) to
rebuild Bokeh figures from structured viz-store state without re-executing
arbitrary Python code.
"""

import math

import holoviews as hv
import hvplot.pandas  # noqa: F401
import pandas as pd
from bokeh.embed import json_item
from bokeh.models import Arrow
from bokeh.models import BoxAnnotation
from bokeh.models import ColumnDataSource
from bokeh.models import CustomJS
from bokeh.models import FixedTicker
from bokeh.models import HoverTool
from bokeh.models import Label
from bokeh.models import NormalHead
from bokeh.models import NumeralTickFormatter
from bokeh.models import Span
from bokeh.models import TapTool
from bokeh.palettes import Category10
from bokeh.plotting import figure as bokeh_figure
from bokeh.transform import cumsum

from holoviz_mcp_server.themes import THEME_COLORS

hv.extension("bokeh")

hv.extension("bokeh")

CHART_PALETTE = [
    "#818cf8",
    "#4ade80",
    "#f59e0b",
    "#f87171",
    "#38bdf8",
    "#c084fc",
    "#fb923c",
    "#2dd4bf",
    "#e879f9",
    "#a3e635",
]
CHART_TYPES = [
    "bar",
    "line",
    "scatter",
    "area",
    "pie",
    "histogram",
    "box",
    "violin",
    "kde",
    "step",
    "heatmap",
    "hexbin",
]
ANNOTATION_TYPES = ["text", "hline", "vline", "band", "arrow"]
MAX_CHART_ROWS = 10_000


def _apply_theme(fig, theme: str = "dark") -> None:
    """Apply dark/light theme styling to a Bokeh figure."""
    colors = THEME_COLORS.get(theme, THEME_COLORS["dark"])
    fig.background_fill_alpha = 0
    fig.border_fill_alpha = 0
    fig.outline_line_alpha = 0

    for axis in fig.axis:
        axis.axis_label_text_color = colors["label"]
        axis.major_label_text_color = colors["label"]
        axis.major_tick_line_color = colors["tick"]
        axis.minor_tick_line_color = None
        axis.axis_line_color = colors["tick"]

    for grid in fig.grid:
        grid.grid_line_color = colors["grid"]
        grid.grid_line_alpha = colors["grid_alpha"]

    if fig.title:
        fig.title.text_color = colors["title"]
        fig.title.text_font_size = "14px"

    if fig.legend:
        fig.legend.label_text_color = colors["legend_text"]
        fig.legend.background_fill_alpha = 0
        fig.legend.border_line_alpha = 0


def build_bokeh_figure(
    kind: str,
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    color: str | None = None,
    target_id: str = "chart-container",
    theme: str = "dark",
) -> dict:
    """Build a Bokeh figure and serialize to json_item dict."""
    if kind not in CHART_TYPES:
        raise ValueError(f"Unsupported chart type: {kind}. Supported: {CHART_TYPES}")
    if x not in df.columns:
        raise ValueError(f"Column '{x}' not found. Available: {list(df.columns)}")
    if y not in df.columns:
        raise ValueError(f"Column '{y}' not found. Available: {list(df.columns)}")
    if color and color not in df.columns:
        raise ValueError(f"Color column '{color}' not found. Available: {list(df.columns)}")

    if len(df) > MAX_CHART_ROWS and kind not in ("pie", "heatmap"):
        df = df.sample(n=MAX_CHART_ROWS, random_state=42).sort_index()

    if kind == "pie":
        fig = _build_pie_chart(df, x, y, title, theme)
    else:
        fig = _build_hvplot_chart(kind, df, x, y, title, color)
        _apply_theme(fig, theme)

    fig.sizing_mode = "stretch_width"

    for axis in fig.yaxis:
        if hasattr(axis, "formatter"):
            try:
                axis.formatter = NumeralTickFormatter(format="0,0.[00]")
            except Exception:  # noqa: S110
                pass

    fig.add_tools(TapTool())
    _add_click_callbacks(fig, x, y)

    return json_item(fig, target_id)


def _build_hvplot_chart(
    kind: str,
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    color: str | None = None,
):
    """Create a chart with hvPlot and convert to a Bokeh figure."""
    base = {"title": title, "height": 350, "responsive": True}
    has_grouping = color and color in df.columns

    if kind == "step" and not pd.api.types.is_numeric_dtype(df[x]):
        df = df.copy()
        x_labels = df[x].tolist()
        df["_step_x"] = range(len(df))
        kwargs = {**base, "x": "_step_x", "y": y}
        if has_grouping:
            kwargs["by"] = color
        else:
            kwargs["color"] = CHART_PALETTE[0]
        plot = df.hvplot.step(**kwargs)
        fig = hv.render(plot, backend="bokeh")
        fig.xaxis[0].ticker = FixedTicker(ticks=list(range(len(x_labels))))
        fig.xaxis[0].major_label_overrides = {i: str(v) for i, v in enumerate(x_labels)}
        return fig

    simple_methods = {
        "bar": df.hvplot.bar,
        "line": df.hvplot.line,
        "scatter": df.hvplot.scatter,
        "area": df.hvplot.area,
        "step": df.hvplot.step,
    }

    if kind in simple_methods:
        kwargs = {**base, "x": x, "y": y}
        if has_grouping:
            kwargs["by"] = color
        else:
            kwargs["color"] = CHART_PALETTE[0]
            kwargs["hover_cols"] = "all"
        plot = simple_methods[kind](**kwargs)

    elif kind == "histogram":
        kwargs = {**base, "y": y}
        if has_grouping:
            kwargs["by"] = color
        else:
            kwargs["color"] = CHART_PALETTE[0]
        plot = df.hvplot.hist(**kwargs)

    elif kind == "box":
        kwargs = {**base, "y": y, "color": CHART_PALETTE[0]}
        if x and x in df.columns and not pd.api.types.is_numeric_dtype(df[x]):
            kwargs["by"] = x
        plot = df.hvplot.box(**kwargs)

    elif kind == "violin":
        kwargs = {**base, "y": y, "color": CHART_PALETTE[0]}
        if x and x in df.columns and not pd.api.types.is_numeric_dtype(df[x]):
            kwargs["by"] = x
        plot = df.hvplot.violin(**kwargs)

    elif kind == "kde":
        kwargs = {**base, "y": y}
        if has_grouping:
            kwargs["by"] = color
        else:
            kwargs["color"] = CHART_PALETTE[0]
        plot = df.hvplot.kde(**kwargs)

    elif kind == "heatmap":
        kwargs = {**base, "x": x, "y": y}
        if color and color in df.columns:
            kwargs["C"] = color
        plot = df.hvplot.heatmap(**kwargs)

    elif kind == "hexbin":
        plot = df.hvplot.hexbin(**{**base, "x": x, "y": y})

    else:
        raise ValueError(f"Unsupported chart type: {kind}")

    fig = hv.render(plot, backend="bokeh")

    for tool in fig.tools:
        if isinstance(tool, HoverTool) and tool.tooltips:
            formatted = []
            for label, field in tool.tooltips:
                if field.startswith("@") and pd.api.types.is_numeric_dtype(df.get(label, pd.Series(dtype="object"))):
                    formatted.append((label, f"{field}{{0,0.[00]}}"))
                else:
                    formatted.append((label, field))
            tool.tooltips = formatted

    return fig


def _build_pie_chart(df: pd.DataFrame, names_col: str, values_col: str, title: str, theme: str = "dark"):
    """Build a pie/donut chart using raw Bokeh (hvPlot lacks pie support)."""
    data = df.groupby(names_col)[values_col].sum().reset_index()
    data["angle"] = data[values_col] / data[values_col].sum() * 2 * math.pi
    data["pct"] = (data[values_col] / data[values_col].sum() * 100).round(1)
    n = len(data)
    data["color"] = CHART_PALETTE[:n] if n <= len(CHART_PALETTE) else list(Category10[min(n, 10)][:n])
    source = ColumnDataSource(data)
    fig = bokeh_figure(
        title=title,
        toolbar_location=None,
        tools="hover",
        tooltips=f"@{names_col}: @{values_col}{{0,0}} (@pct%)",
        x_range=(-0.5, 1.0),
        height=350,
    )
    fig.wedge(
        x=0,
        y=1,
        radius=0.4,
        start_angle=cumsum("angle", include_zero=True),
        end_angle=cumsum("angle"),
        line_color="white",
        line_width=2,
        fill_color="color",
        legend_field=names_col,
        source=source,
    )
    fig.axis.visible = False
    fig.grid.grid_line_color = None
    fig.background_fill_alpha = 0
    fig.border_fill_alpha = 0
    fig.outline_line_alpha = 0
    tc = THEME_COLORS.get(theme, THEME_COLORS["dark"])
    if fig.title:
        fig.title.text_color = tc["title"]
        fig.title.text_font_size = "14px"
    if fig.legend:
        fig.legend.label_text_color = tc["legend_text"]
        fig.legend.background_fill_alpha = 0
        fig.legend.border_line_alpha = 0
    return fig


def _add_click_callbacks(fig, x_col: str, y_col: str) -> None:
    """Wire BokehJS TapTool → window.dispatchEvent('bokeh-tap') for the MCP App."""
    for renderer in fig.renderers:
        if hasattr(renderer, "data_source"):
            source = renderer.data_source
            cols = list(source.data.keys())
            x_key = x_col if x_col in source.data else (cols[0] if cols else "x")
            y_key = y_col if y_col in source.data else (cols[1] if len(cols) > 1 else "y")
            callback = CustomJS(
                args=dict(source=source),
                code=(
                    "try {"
                    "const idx = source.selected.indices;"
                    "if (!idx.length) return;"
                    "const i = idx[0];"
                    "const xd = source.data['" + x_key + "'];"
                    "const yd = source.data['" + y_key + "'];"
                    "if (!xd || !yd) return;"
                    "window.dispatchEvent(new CustomEvent('bokeh-tap', {"
                    "  detail: { index: i, xValue: String(xd[i]), yValue: Number(yd[i]) }"
                    "}));"
                    "} catch(e) { console.warn('Click callback error:', e); }"
                ),
            )
            source.selected.js_on_change("indices", callback)
            break


def add_annotation(fig, annotation_type: str, config: dict) -> None:
    """Add a Bokeh annotation (hline, vline, text, band, arrow) to an existing figure."""
    if annotation_type == "hline":
        span = Span(
            location=config.get("y_value", 0),
            dimension="width",
            line_color=config.get("color", "#ef4444"),
            line_dash=config.get("dash", "dashed"),
            line_width=2,
        )
        fig.add_layout(span)
        if config.get("label"):
            fig.add_layout(
                Label(
                    x=10,
                    y=config["y_value"],
                    text=config["label"],
                    text_color=config.get("color", "#ef4444"),
                    text_font_size="11px",
                    x_units="screen",
                )
            )

    elif annotation_type == "vline":
        fig.add_layout(
            Span(
                location=config.get("x_value", 0),
                dimension="height",
                line_color=config.get("color", "#6366f1"),
                line_dash=config.get("dash", "dotted"),
                line_width=2,
            )
        )

    elif annotation_type == "text":
        fig.add_layout(
            Label(
                x=config.get("x", 0),
                y=config.get("y", 0),
                text=config.get("text", ""),
                text_color=config.get("color", "#e0e0e0"),
                text_font_size=config.get("font_size", "12px"),
            )
        )

    elif annotation_type == "band":
        fig.add_layout(
            BoxAnnotation(
                bottom=config.get("lower", 0),
                top=config.get("upper", 100),
                fill_color=config.get("color", "#4ade80"),
                fill_alpha=config.get("alpha", 0.1),
            )
        )

    elif annotation_type == "arrow":
        fig.add_layout(
            Arrow(
                end=NormalHead(fill_color=config.get("color", "#f59e0b"), size=10),
                x_start=config.get("x_start", 0),
                y_start=config.get("y_start", 0),
                x_end=config.get("x_end", 1),
                y_end=config.get("y_end", 1),
                line_color=config.get("color", "#f59e0b"),
                line_width=2,
            )
        )


def build_widget_config(df: pd.DataFrame) -> list[dict]:
    """Generate filter widget config from a DataFrame — dropdowns for categorical, sliders for numeric."""
    widgets = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            col_min = float(df[col].min())
            col_max = float(df[col].max())
            rng = col_max - col_min
            if rng == 0:
                step = 1.0
            elif pd.api.types.is_integer_dtype(df[col]):
                step = max(1, int(rng / 100))
            else:
                step = round(rng / 100, 4)
            widgets.append({"column": col, "type": "range", "min": col_min, "max": col_max, "step": step})
        elif pd.api.types.is_string_dtype(df[col]) or df[col].dtype.name == "category":
            unique_vals = sorted(df[col].dropna().unique().tolist())
            if len(unique_vals) <= 50:
                widgets.append({"column": col, "type": "select", "options": unique_vals})
    return widgets


def rebuild_figure(viz: dict, target_id: str = "chart-container") -> dict:
    """Rebuild a Bokeh figure from viz-store state, reapplying all annotations."""
    df = pd.DataFrame(viz["data"])
    theme = viz.get("theme", "dark")
    target_id = viz.get("target_id", target_id)

    if viz["kind"] == "pie":
        fig = _build_pie_chart(df, viz["x"], viz["y"], viz["title"], theme)
    else:
        fig = _build_hvplot_chart(viz["kind"], df, viz["x"], viz["y"], viz["title"], viz.get("color"))
        _apply_theme(fig, theme)

    fig.sizing_mode = "stretch_width"
    fig.add_tools(TapTool())
    _add_click_callbacks(fig, viz["x"], viz["y"])

    for ann in viz.get("annotations", []):
        add_annotation(fig, ann["type"], ann["config"])

    return json_item(fig, target_id)
