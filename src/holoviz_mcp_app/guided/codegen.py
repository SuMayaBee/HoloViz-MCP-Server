"""Code generators — produce Panel/hvPlot Python code from structured config.

Each function takes tool parameters and returns complete Python code
that can be passed to show() or sent to the display server.
"""


def generate_viz_code(
    kind: str,
    data: dict[str, list],
    x: str,
    y: str,
    title: str = "Visualization",
    color: str | None = None,
) -> str:
    """Generate hvPlot visualization code from config."""
    data_repr = repr(data)
    opts = [f'x="{x}"', f'y="{y}"', f'title="{title}"', "responsive=True", "height=400"]

    if color:
        opts.append(f'by="{color}"')

    opts_str = ", ".join(opts)

    return f"""import hvplot.pandas
import pandas as pd

df = pd.DataFrame({data_repr})
df.hvplot.{kind}({opts_str})
"""


def generate_dashboard_code(
    title: str,
    data: dict[str, list],
    x: str,
    y: str,
    chart_kind: str = "bar",
    color: str | None = None,
) -> str:
    """Generate a full Panel dashboard with chart, stats, and data table."""
    data_repr = repr(data)
    color_opt = f', by="{color}"' if color else ""

    return f"""import hvplot.pandas
import pandas as pd
import panel as pn

pn.extension("tabulator")

df = pd.DataFrame({data_repr})

chart = df.hvplot.{chart_kind}(x="{x}", y="{y}", title="{title}"{color_opt}, responsive=True, height=350)

stats = pn.Column(
    pn.indicators.Number(name="Count", value=len(df), format="{{value:,}}"),
    pn.indicators.Number(name="Mean {y}", value=round(df["{y}"].mean(), 2), format="{{value:,.2f}}"),
    pn.indicators.Number(name="Max {y}", value=round(df["{y}"].max(), 2), format="{{value:,.2f}}"),
)

table = pn.widgets.Tabulator(df, sizing_mode="stretch_width", height=300)

template = pn.template.FastListTemplate(
    title="{title}",
    main=[pn.Row(chart, stats), table],
)
template.servable()
"""


def generate_stream_code(
    title: str = "Live Stream",
    metric_name: str = "value",
    interval_ms: int = 1000,
) -> str:
    """Generate streaming Panel code with periodic callback."""
    return f"""import numpy as np
import pandas as pd
import panel as pn
import holoviews as hv
from holoviews.streams import Buffer

pn.extension()
hv.extension("bokeh")

# Create buffer for streaming data
buffer = Buffer(pd.DataFrame({{"{metric_name}": [], "timestamp": []}}), length=100)

def update():
    import datetime
    new_data = pd.DataFrame({{
        "{metric_name}": [np.random.randn()],
        "timestamp": [datetime.datetime.now()],
    }})
    buffer.send(new_data)

# Create dynamic plot
plot = hv.DynamicMap(
    lambda data: hv.Curve(data, "timestamp", "{metric_name}").opts(
        title="{title}", responsive=True, height=400
    ),
    streams=[buffer],
)

pn.state.add_periodic_callback(update, period={interval_ms})

pn.panel(plot, sizing_mode="stretch_width").servable()
"""


def generate_multi_chart_code(
    title: str,
    data: dict[str, list],
    charts: list[dict],
) -> str:
    """Generate multi-chart Panel code with linked selections."""
    data_repr = repr(data)

    chart_code_parts = []
    for i, chart in enumerate(charts):
        kind = chart.get("kind", "bar")
        x = chart.get("x", "")
        y = chart.get("y", "")
        chart_title = chart.get("title", f"Chart {i + 1}")
        chart_code_parts.append(
            f'    df.hvplot.{kind}(x="{x}", y="{y}", title="{chart_title}", responsive=True, height=300)'
        )

    charts_list = ",\n".join(chart_code_parts)

    return f"""import hvplot.pandas
import holoviews as hv
import pandas as pd
import panel as pn

pn.extension()
hv.extension("bokeh")

df = pd.DataFrame({data_repr})

ls = hv.link_selections.instance()

charts = [
{charts_list}
]

linked = ls(hv.Layout(charts).cols(2))
pn.panel(linked, sizing_mode="stretch_width").servable()
"""
