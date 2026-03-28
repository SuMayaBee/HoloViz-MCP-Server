---
name: panel
description: Best practices for developing tools, dashboards and interactive data apps with HoloViz Panel. Create reactive, component-based UIs with widgets, layouts, templates, and real-time updates.
metadata:
  version: "1.0.0"
  author: holoviz
  category: web-development
  difficulty: intermediate
---

# Panel Development Skills

Best practices for developing dashboards and data apps with HoloViz Panel.

## Dependencies

Core:
- **panel**: Application framework
- **param**: Declarative typed parameters, reactive programming

Optional HoloViz:
- **hvplot**: High-level plotting with Pandas `.plot()`-like API
- **holoviews**: Declarative composable visualizations
- **datashader**: Large dataset rendering (millions+ points)
- **colorcet**: Perceptually uniform colormaps

Optional PyData:
- **bokeh**: Default rendering backend
- **pandas** / **polars**: DataFrames
- **plotly**: 3D plots, animations
- **matplotlib**: Publication-quality static plots

## Installation

```bash
pip install panel watchfiles hvplot
```

Always include `watchfiles` for hot-reload during development.

## Best Practice Hello World

```python
import panel as pn
import param

pn.extension(throttled=True)

@pn.cache(max_items=3)
def extract(n=5):
    return "Hello World" + "⭐" * n

text = extract()

@pn.cache(max_items=3)
def transform(data: str, count: int = 5) -> str:
    return data[:min(count, len(data))]

class HelloWorld(pn.viewable.Viewer):
    characters = param.Integer(default=len(text), bounds=(0, len(text)))

    def __init__(self, **params):
        super().__init__(**params)
        with pn.config.set(sizing_mode="stretch_width"):
            self._inputs = pn.Column(
                pn.widgets.IntSlider.from_param(self.param.characters, margin=(10, 20)),
                max_width=300,
            )
            self._output_pane = pn.pane.Markdown(self.model)
            self._outputs = pn.Column(self._output_pane)
            self._panel = pn.Row(self._inputs, self._outputs)

    @pn.cache(max_items=3)
    @param.depends("characters")
    def model(self):
        return transform(text, self.characters)

    def __panel__(self):
        return self._panel

    @classmethod
    def create_app(cls, **params):
        instance = cls(**params)
        return pn.template.FastListTemplate(
            title="Hello World App",
            sidebar=[instance._inputs],
            main=[instance._outputs],
            main_layout=None,
        )

if pn.state.served:
    HelloWorld.create_app().servable()
```

Serve with: `panel serve app.py --show --dev`

## Key Patterns

### Parameter-Driven Architecture

- Use `param.Parameterized` or `pn.viewable.Viewer` for state
- Create widgets with `.from_param()` method
- Use `@param.depends()` for reactive methods
- Use `@param.depends(..., watch=True)` for side effects only

### Static Layout with Reactive Content (CRITICAL)

Create layout ONCE in `__init__`, bind reactive content to panes:

```python
class Dashboard(pn.viewable.Viewer):
    filter_value = param.String(default="all")

    def __init__(self, **params):
        super().__init__(**params)
        # Create panes ONCE
        self._summary = pn.pane.Markdown(self._summary_text)
        self._layout = pn.Column("# Dashboard", self._summary)

    @param.depends("filter_value")
    def _summary_text(self):
        return f"Filter: {self.filter_value}"  # Return content, NOT pane

    def __panel__(self):
        return self._layout
```

**DON'T** recreate panes in `@param.depends` methods — causes flickering.

### Responsive Design

- Use `sizing_mode="stretch_width"` by default on individual components and layouts
- **NEVER use `sizing_mode="stretch_both"` on `pn.Column` or the top-level layout** — it distributes the full page height equally across all children, creating huge empty gaps below small text components
- Use `FlexBox` or `GridSpec` for complex layouts
- Set `min_width`, `max_width` to prevent collapse

### Avoiding Empty Gaps (CRITICAL)

Large blank spaces between components happen when the layout tries to fill the full page height.

**DON'T:**
```python
pn.Column(
    pn.pane.Markdown("# Title"),      # Gets 33% of page height → huge gap
    pn.pane.Markdown("subtitle"),     # Gets 33% of page height → huge gap
    chart,                            # Gets 33% of page height
    sizing_mode="stretch_both",       # ← this is the culprit
).servable()
```

**DO:**
```python
pn.Column(
    pn.pane.Markdown("# Title"),
    pn.pane.Markdown("subtitle"),
    chart,
    sizing_mode="stretch_width",      # ← width only, height is natural
).servable()
```

Rule: only the chart/plot pane should have a fixed `height=` or `min_height=`. Text and widget panes should have no explicit height.

### Extensions

```python
pn.extension("tabulator", "plotly")  # Load needed JS
# DON'T add "bokeh" — already loaded
```

### Templates

```python
pn.template.FastListTemplate(
    title="My App",
    sidebar=[inputs],
    main=[outputs],
    main_layout=None,  # Modern styling
)
```

### Performance

- `pn.extension(defer_load=True, loading_indicator=True)`
- `@pn.cache` for expensive computations
- Use async/await for I/O
- Profile with `@pn.io.profiler`

## Serving

```python
if pn.state.served:
    main().servable()
```

```bash
panel serve app.py --dev --show
```

DON'T use `python app.py` or `if __name__ == "__main__"`.

## Testing

```python
def test_reactivity():
    hw = HelloWorld()
    assert hw.model() == text[:hw.characters]
    hw.characters = 5
    assert hw.model() == text[:5]
```

Run: `pytest tests/`
