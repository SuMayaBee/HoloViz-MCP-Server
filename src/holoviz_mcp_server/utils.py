"""Utilities for code execution, package/extension detection."""

import ast
import concurrent.futures
import importlib.util
import logging
import os
import sys
import traceback
import types
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EXECUTION_TIMEOUT = 30

_DLL_DIR_HANDLES: dict[str, Any] = {}

_PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None


def prepend_env_dll_paths(env: dict[str, str]) -> dict[str, str]:
    """Prepend conda/pixi environment DLL directories to PATH (Windows only)."""
    if sys.platform != "win32":
        return env

    env_root = Path(sys.executable).resolve().parent
    candidate_dirs = [
        env_root,
        env_root / "Scripts",
        env_root / "Library" / "bin",
        env_root / "DLLs",
    ]

    existing_path = env.get("PATH", "")
    existing_entries: set[str] = set(existing_path.split(os.pathsep)) if existing_path else set()

    new_prefixes = [str(d) for d in candidate_dirs if d.exists() and str(d) not in existing_entries]
    if new_prefixes:
        env["PATH"] = os.pathsep.join(new_prefixes + ([existing_path] if existing_path else []))

    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is not None:
        for d in candidate_dirs:
            resolved = str(d.resolve())
            if d.exists() and resolved not in _DLL_DIR_HANDLES:
                try:
                    _DLL_DIR_HANDLES[resolved] = add_dll(str(d))
                except OSError:
                    pass

    return env


def find_extensions(code: str, namespace: dict[str, Any] | None = None) -> list[str]:
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


class ExtensionError(Exception):
    """Custom exception for missing Panel extensions."""


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


def execute_in_module(
    code: str,
    module_name: str,
    *,
    cleanup: bool = True,
) -> dict[str, Any]:
    """Execute Python code in a proper module namespace."""
    module = types.ModuleType(module_name)
    module.__dict__["__file__"] = f"<{module_name}>"
    sys.modules[module_name] = module

    try:
        exec(code, module.__dict__)  # noqa: S102
        return module.__dict__
    except Exception:
        if cleanup:
            sys.modules.pop(module_name, None)
        raise
    finally:
        if cleanup:
            sys.modules.pop(module_name, None)


def extract_last_expression(code: str) -> tuple[str, str]:
    """Extract the last expression from code for jupyter method."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in code: {e}") from e

    if not tree.body:
        return "", ""

    last_node = tree.body[-1]
    if isinstance(last_node, ast.Expr):
        lines = code.split("\n")
        last_line_start = last_node.lineno - 1
        last_line_end = last_node.end_lineno if last_node.end_lineno else last_line_start + 1
        statements = "\n".join(lines[:last_line_start])
        last_expr = "\n".join(lines[last_line_start:last_line_end])
        return statements, last_expr
    else:
        return code, ""


def get_relative_view_url(id: str) -> str:
    """Generate a relative URL for viewing a visualization by ID."""
    return f"./view?id={id}"


def _run_execution(code: str) -> str:
    """Execute code in an isolated module namespace. Returns error string or ''."""
    try:
        execute_in_module(code, module_name="bokeh_app_validation", cleanup=True)
        return ""
    except Exception as e:
        tb = e.__traceback__.tb_next if e.__traceback__ is not None else None
        return "".join(traceback.format_exception(type(e), e, tb)).strip()


def validate_code(code: str) -> str:
    """Execute code in a thread with a timeout to catch runtime errors."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_execution, code)
        try:
            return future.result(timeout=_EXECUTION_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logger.warning("Code execution timed out after %ss", _EXECUTION_TIMEOUT)
            return f"Code execution timed out after {_EXECUTION_TIMEOUT}s."
        except Exception as e:
            return f"Execution failed: {e}"
