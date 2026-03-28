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
