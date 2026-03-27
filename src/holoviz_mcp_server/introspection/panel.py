"""Panel component introspection.

Pure Python functions for discovering Panel widgets, panes, layouts, and templates.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_components_cache: dict[str, dict] | None = None


def _get_all_components() -> dict[str, dict]:
    """Get all Panel components with metadata. Cached after first call."""
    global _components_cache
    if _components_cache is not None:
        return _components_cache

    import panel as pn

    components: dict[str, dict] = {}

    def _collect(cls, category: str):
        for sub in cls.__subclasses__():
            name = f"{sub.__module__}.{sub.__qualname__}"
            if name.startswith("panel."):
                short_name = name.replace("panel.", "pn.")
                components[short_name] = {
                    "name": short_name,
                    "full_name": name,
                    "category": category,
                    "doc": (sub.__doc__ or "").split("\n")[0].strip(),
                }
            _collect(sub, category)

    _collect(pn.widgets.Widget, "widget")
    _collect(pn.pane.PaneBase, "pane")
    _collect(pn.layout.ListLike, "layout")
    _collect(pn.layout.Panel, "layout")

    _components_cache = components
    return components


def list_components(category: str | None = None) -> list[dict[str, str]]:
    """List Panel components, optionally filtered by category."""
    components = _get_all_components()
    results = []
    for comp in sorted(components.values(), key=lambda c: c["name"]):
        if category and comp["category"] != category:
            continue
        results.append(
            {
                "name": comp["name"],
                "category": comp["category"],
                "doc": comp["doc"],
            }
        )
    return results


def get_component(name: str) -> dict:
    """Get detailed information about a specific Panel component."""
    components = _get_all_components()

    for comp_name, comp in components.items():
        if name.lower() in comp_name.lower() or name.lower() in comp["full_name"].lower():
            # Get the actual class
            parts = comp["full_name"].split(".")
            module_path = ".".join(parts[:-1])
            class_name = parts[-1]

            try:
                import importlib

                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                params = {}
                for pname, param in cls.param.params().items():
                    if pname == "name":
                        continue
                    params[pname] = {
                        "type": type(param).__name__,
                        "default": repr(param.default) if param.default is not None else None,
                        "doc": param.doc or "",
                    }
                return {
                    "name": comp_name,
                    "category": comp["category"],
                    "docstring": cls.__doc__ or "",
                    "parameters": params,
                }
            except Exception:
                return comp

    raise ValueError(f"Component '{name}' not found")


def search_components(query: str, limit: int = 10) -> list[dict]:
    """Search Panel components by name or description."""
    components = _get_all_components()
    query_lower = query.lower()

    scored = []
    for comp in components.values():
        score = 0
        if query_lower in comp["name"].lower():
            score += 10
        if query_lower in comp["doc"].lower():
            score += 5
        if score > 0:
            scored.append((score, comp))

    scored.sort(key=lambda x: -x[0])
    return [{"name": c["name"], "category": c["category"], "doc": c["doc"], "score": s} for s, c in scored[:limit]]


def get_component_params(name: str) -> dict:
    """Get parameter details for a specific component."""
    info = get_component(name)
    return info.get("parameters", {})
