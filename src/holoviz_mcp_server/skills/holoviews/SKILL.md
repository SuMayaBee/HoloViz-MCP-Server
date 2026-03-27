---
name: holoviews
description: Best practices for advanced, interactive, publication-quality data visualizations using HoloViz HoloViews.
metadata:
  version: "1.0.0"
  author: holoviz
  category: data-visualization
  difficulty: intermediate
---

# HoloViews Development Skills

Best practices for developing visualizations with HoloViz HoloViews.

## Dependencies

- **holoviews**: Declarative composable visualization library
- **bokeh**: Default interactive backend
- **panel**: For serving plots
- **param**: Reactive programming
- **pandas**: DataFrames

Optional:
- **hvplot**: Simpler API built on HoloViews
- **datashader**: Large dataset rendering
- **geoviews**: Geographic visualizations
- **colorcet**: Perceptually uniform colormaps

## Installation

```bash
pip install holoviews panel watchfiles
```

## Quick Start

```python
import holoviews as hv
hv.extension("bokeh")

data = {"x": [1, 2, 3], "y": [4, 5, 6]}
plot = hv.Bars(data, kdims="x", vdims="y").opts(title="My Chart")
```

## Key Concepts

### Elements

HoloViews elements are building blocks:

```python
# Specify key dimensions (independent) and value dimensions (dependent)
bars = hv.Bars(df, kdims="category", vdims="count")
curve = hv.Curve(df, kdims="time", vdims="value")
scatter = hv.Scatter(df, kdims="x", vdims=["y", "size"])
```

### Composition

```python
# Overlay (same axes): *
combined = curve1 * curve2

# Layout (side by side): +
side_by_side = bars + scatter

# GroupBy with widget
grouped = hv.Bars(df, kdims=["cat", "group"], vdims="val").groupby("group")
```

### Styling with .opts()

```python
bars.opts(
    title="My Chart",
    xlabel="Category",
    ylabel="Count",
    color="#007ACC",
    line_color=None,
    width=800,
    height=400,
)
```

### Custom Bokeh Theme

```python
from bokeh.themes import Theme

theme = Theme(json={
    "attrs": {
        "Title": {"text_font": "Roboto", "text_font_size": "16pt"},
        "Axis": {"axis_label_text_font_size": "12pt"},
    }
})
hv.renderer("bokeh").theme = theme
```

### Axis Formatting

```python
from bokeh.models.formatters import NumeralTickFormatter

plot.opts(yformatter=NumeralTickFormatter(format="0.0a"))
# 1230974 → 1.2m
```

## Recommended Plot Types

- **Curve** — time series, continuous data
- **Scatter** — relationships between variables
- **Bars** — categorical comparisons
- **Histogram** — distribution analysis
- **Area** — stacked or filled visualizations

## Publication-Quality Pattern

```python
import holoviews as hv
import panel as pn
from bokeh.models.formatters import NumeralTickFormatter

hv.extension("bokeh")

# Separate: Extract → Transform → Plot
def get_data():
    return pd.read_csv("data.csv")

def aggregate(df):
    return df.groupby("category").agg(count=("id", "size")).reset_index()

def create_chart(agg):
    return hv.Bars(agg, kdims="category", vdims="count").opts(
        title="Distribution",
        color="#007ACC",
        line_color=None,
        yformatter=NumeralTickFormatter(format="0a"),
    )

if pn.state.served:
    pn.extension()
    plot = create_chart(aggregate(get_data()))
    pn.panel(plot, sizing_mode="stretch_both").servable()
```

## Serving

```bash
panel serve chart.py --dev --show
```

DON'T use `python chart.py` or `if __name__ == "__main__"`.

## Testing

- Separate data extraction/transformation from plotting
- Test data functions with pytest
- Serve with `--dev` for manual testing
