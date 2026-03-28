---
name: charting
description: Recipes for chart types not supported by hvPlot (pie, donut, gauge, polar) using Bokeh directly.
metadata:
  version: "1.0.0"
  author: holoviz
  category: data-visualization
  difficulty: beginner
---

# Charting Recipes

Patterns for chart types that hvPlot does **not** support. Use these Bokeh recipes directly.

## Pie Chart

`hvPlot` has no `.pie()` method. Use Bokeh `figure.wedge()` with `cumsum()`:

```python
import numpy as np
import pandas as pd
from bokeh.plotting import figure
from bokeh.transform import cumsum
from bokeh.palettes import Category10

df = pd.DataFrame({
    'label': ['Apples', 'Bananas', 'Oranges', 'Grapes', 'Mangoes'],
    'value': [4200, 3100, 2800, 1950, 2400],
})
df['angle'] = df['value'] / df['value'].sum() * 2 * np.pi
df['color'] = Category10[len(df)]

p = figure(
    height=400, width=500, title="Fruit Sales",
    toolbar_location=None,
    tools="hover", tooltips="@label: @value",
)
p.wedge(
    x=0, y=1, radius=0.4,
    start_angle=cumsum('angle', include_zero=True),
    end_angle=cumsum('angle'),
    line_color="white", fill_color='color',
    legend_field='label', source=df,
)
p.axis.visible = False
p.grid.visible = False
p
```

## Donut Chart

Same as pie but with an inner radius:

```python
p.annular_wedge(
    x=0, y=1, inner_radius=0.2, outer_radius=0.4,
    start_angle=cumsum('angle', include_zero=True),
    end_angle=cumsum('angle'),
    line_color="white", fill_color='color',
    legend_field='label', source=df,
)
```

## Rules

- Always use `from bokeh.palettes import Category10` for colors — index by `len(df)` (max 10 slices)
- For > 10 slices use `from bokeh.palettes import turbo` and slice it: `turbo(len(df))`
- Last expression must be the Bokeh `figure` object `p` so Panel can render it
- Do NOT call `show(p)` — just return `p` as the last expression

## Tile Maps (OpenStreetMap, CartoDB, etc.)

**NEVER use `bokeh.tile_providers`** — removed in Bokeh 3.x. Use hvPlot with `tiles=` instead:

```python
import pandas as pd
import hvplot.pandas

df = pd.DataFrame({
    'lat': [40.7128, 40.7580, 40.6892],
    'lon': [-74.0060, -73.9855, -74.0445],
    'label': ['City Hall', 'Times Square', 'Statue of Liberty'],
})

plot = df.hvplot.points(
    x='lon', y='lat',
    geo=True,
    tiles='OSM',          # OpenStreetMap tiles
    color='red',
    size=10,
    hover_cols=['label'],
    title='New York City',
    width=700, height=500,
)
plot
```

**Available tile options:** `'OSM'`, `'CartoDark'`, `'CartoLight'`, `'EsriImagery'`, `'EsriNatGeo'`

- Use `geo=True` with real lat/lon coordinates (WGS84)
- Do NOT import `geoviews` explicitly — hvPlot handles it
- Do NOT use `from bokeh.tile_providers import get_provider` — that module is gone
