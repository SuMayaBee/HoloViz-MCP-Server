"""Code analysis — Panel extension detection and package requirement discovery."""

from __future__ import annotations

import ast
import logging

logger = logging.getLogger(__name__)


class ExtensionError(Exception):
    """Custom exception for missing Panel extensions."""


def find_extensions(code: str) -> list[str]:
    """Infer Panel extensions required for code execution."""
    code_lower = code.lower()
    extensions = []

    if "plotly" in code_lower:
        extensions.append("plotly")
    if "altair" in code_lower or "vega" in code_lower:
        extensions.append("vega")
    if "pydeck" in code_lower or "deck" in code_lower:
        extensions.append("deckgl")
    if "tabulator" in code_lower:
        extensions.append("tabulator")
    if "echarts" in code_lower:
        extensions.append("echarts")
    if "ipywidgets" in code_lower:
        extensions.append("ipywidgets")
    if "perspective" in code_lower:
        extensions.append("perspective")
    if "terminal" in code_lower or "textual" in code_lower:
        extensions.append("terminal")
    if "vtk" in code_lower:
        extensions.append("vtk")
    if "vizzu" in code_lower:
        extensions.append("vizzu")

    return list(set(extensions))


def _extract_extension_calls(code: str) -> set[str]:
    """Extract extension names from pn.extension() calls using AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()

    declared = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "extension":
                if isinstance(node.func.value, ast.Name) and node.func.value.id in ("pn", "panel"):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            declared.add(arg.value)
    return declared


def validate_extension_availability(code: str) -> None:
    """Validate that required Panel extensions are loaded in the code."""
    extensions = find_extensions(code)
    if not extensions:
        return

    declared = _extract_extension_calls(code)
    missing = set(extensions) - declared

    if missing:
        missing_sorted = sorted(missing)
        missing_args = ", ".join(f"'{ext}'" for ext in missing_sorted)
        raise ExtensionError(
            f"Required Panel extension(s) not loaded: {missing_args}. Add pn.extension({missing_args}) to your code."
        )


def find_requirements(code: str) -> list[str]:
    """Find package requirements from code."""
    try:
        from panel.io.mime_render import find_requirements as panel_find_requirements

        return panel_find_requirements(code)
    except (ImportError, AttributeError):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        return list(imports)
