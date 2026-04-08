"""Code execution utilities."""

from __future__ import annotations

import concurrent.futures
import logging
import sys
import traceback
import types

logger = logging.getLogger(__name__)

_EXECUTION_TIMEOUT = 30


def execute_in_module(
    code: str,
    module_name: str,
    *,
    cleanup: bool = True,
) -> dict:
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
    import ast

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
