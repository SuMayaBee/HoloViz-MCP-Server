"""hvPlot plot type introspection.

Pure Python functions for discovering available hvPlot chart types.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def list_plot_types() -> list[dict[str, str]]:
    """List all available hvPlot plot types."""
    import hvplot

    accessor = hvplot.hvPlotTabular
    plot_types = []

    for name in sorted(dir(accessor)):
        if name.startswith("_"):
            continue
        attr = getattr(accessor, name, None)
        if callable(attr) and not isinstance(attr, type):
            doc = (getattr(attr, "__doc__", "") or "").split("\n")[0].strip()
            plot_types.append({"name": name, "doc": doc})

    return plot_types


def get_plot_type(name: str, info: str = "docstring") -> str:
    """Get documentation or signature for a specific hvPlot plot type.

    Parameters
    ----------
    name : str
        Plot type name (e.g., 'bar', 'line', 'scatter')
    info : str
        What to return: 'docstring' or 'signature'
    """
    import hvplot

    accessor = hvplot.hvPlotTabular
    method = getattr(accessor, name, None)

    if method is None:
        available = [n for n in dir(accessor) if not n.startswith("_")]
        raise ValueError(f"Plot type '{name}' not found. Available: {', '.join(available)}")

    if info == "signature":
        import inspect

        try:
            sig = inspect.signature(method)
            return f"{name}{sig}"
        except (ValueError, TypeError):
            return f"{name}(...)"

    return getattr(method, "__doc__", "") or f"No documentation for {name}"
