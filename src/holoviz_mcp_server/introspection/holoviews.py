"""HoloViews element introspection.

Pure Python functions for discovering HoloViews elements.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def list_elements() -> list[dict[str, str]]:
    """List all available HoloViews elements."""
    import holoviews as hv

    elements = []
    for name in sorted(dir(hv)):
        obj = getattr(hv, name, None)
        if isinstance(obj, type) and issubclass(obj, hv.Element) and obj is not hv.Element:
            doc = (obj.__doc__ or "").split("\n")[0].strip()
            elements.append({"name": name, "doc": doc})
    return elements


def get_element(name: str, backend: str = "bokeh") -> str:
    """Get documentation for a specific HoloViews element.

    Parameters
    ----------
    name : str
        Element name (e.g., 'Curve', 'Scatter', 'Points')
    backend : str
        Backend for options: 'bokeh', 'matplotlib', 'plotly'
    """
    import holoviews as hv

    element_cls = getattr(hv, name, None)
    if element_cls is None or not isinstance(element_cls, type) or not issubclass(element_cls, hv.Element):
        available = [
            n for n in dir(hv) if isinstance(getattr(hv, n, None), type) and issubclass(getattr(hv, n), hv.Element)
        ]
        raise ValueError(f"Element '{name}' not found. Available: {', '.join(sorted(available))}")

    doc = element_cls.__doc__ or f"No documentation for {name}"

    # Get plot and style options for the backend
    try:
        from holoviews.core.options import Store

        if backend in Store.registry:
            plot_cls = Store.registry[backend].get(element_cls)
            if plot_cls:
                plot_params = sorted(plot_cls.param.params().keys())
                doc += f"\n\nPlot options ({backend}): {', '.join(plot_params)}"
    except Exception:
        pass

    return doc
