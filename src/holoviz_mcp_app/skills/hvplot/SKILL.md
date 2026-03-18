---
name: hvplot
description: Best practices for quick exploratory data analysis with minimal code using HoloViz hvPlot's Pandas .plot-like API.
metadata:
  version: "1.0.0"
  author: holoviz
  category: data-visualization
  difficulty: intermediate
---

# hvPlot Development Skills

Best practices for developing plots and charts with HoloViz hvPlot.

## Dependencies

- **hvplot**: Core visualization framework
- **holoviews**: Underlying declarative visualization library
- **pandas**: Default DataFrame backend
- **panel**: For serving interactive plots
- **param**: Reactive programming model

Optional:
- **polars**: Fast Rust-based DataFrame alternative
- **datashader**: Render millions+ of points
- **geoviews**: Geographic projections and tile sources

## Installation

```bash
pip install hvplot panel watchfiles
```

## Quick Start

```python
import hvplot.pandas  # Adds .hvplot to DataFrames
import panel as pn

pn.extension()

data = pd.read_csv("data.csv")
plot = data.hvplot.bar(x="category", y="value", title="My Chart")

if pn.state.served:
    pn.panel(plot, sizing_mode="stretch_both").servable()
```

Serve: `panel serve plot.py --dev --show`

## General Instructions

- Import hvplot for your backend: `import hvplot.pandas` or `import hvplot.polars`
- Prefer Bokeh backend for interactivity
- Use bar charts over pie charts (pie not supported)
- Use `NumeralTickFormatter` for axis formatting:

```python
from bokeh.models.formatters import NumeralTickFormatter

df.hvplot(yformatter=NumeralTickFormatter(format='0.00a'))
# 1230974 → 1.2m, 1460 → 1 k
```

## Recommended Plot Types

- **line** — time series, continuous data
- **scatter** — relationships between variables
- **bar** — categorical comparisons
- **hist** — distribution analysis
- **area** — stacked or filled visualizations

## Data Exploration Pattern

```python
import hvplot.pandas
import panel as pn

pn.extension()

# Extract
data = pd.read_csv("earthquakes.csv")

# Transform
counts = data.groupby("mag_class").size().reset_index(name="count")

# Plot
plot = counts.hvplot.bar(x="mag_class", y="count", title="Earthquakes by Magnitude")

if pn.state.served:
    pn.panel(plot, sizing_mode="stretch_both").servable()
```

## Serving & Testing

- Serve: `panel serve file.py --dev --show`
- DON'T use `python file.py`
- The `--dev` flag enables hot-reload
- Use `pn.Column`, `pn.Tabs` to layout multiple plots
- Test data extraction/transformation separately with pytest
