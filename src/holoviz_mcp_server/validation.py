"""Code validation pipeline.

Provides four static validation layers that run before code is stored:

- Layer 1  ``ast_check``       — syntax via ``ast.parse()``
- Layer 2  ``ruff_check``      — security rules via ``ruff`` (raises ``SecurityError``)
- Layer 3  ``check_packages``  — all imports are installed
- Formatting  ``ruff_format``  — autoformat via ``ruff format``

Runtime execution (Layer 5) lives in ``utils.validate_code``.
"""

import ast
import importlib.util
import json
import logging
import subprocess
import sys

from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

_RUFF_TIMEOUT_SECONDS = 5

_RUFF_SELECT = (
    "F821,S102,S103,S104,S108,S113,S202,S301,S302,S306,S307,S310,S323,S501,S506,S602,S605,S608"
)

IMPORT_TO_PACKAGE: dict[str, str] = {
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "skimage": "scikit-image",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "attr": "attrs",
}


class ValidationError(ToolError):
    """Raised when code fails a non-security validation check."""


class SecurityError(ToolError):
    """Raised when code contains a security violation."""


BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        "pickle",
        "marshal",
        "shelve",
        "subprocess",
        "multiprocessing",
        "threading",
        "socket",
        "ctypes",
        "importlib",
        "ftplib",
        "smtplib",
        "telnetlib",
        "webbrowser",
        "xmlrpc",
        "pty",
        "signal",
        "resource",
        "fcntl",
        "termios",
        "tty",
    }
)


def ast_check(code: str) -> str | None:
    """Return an error string if code has a syntax error, else None."""
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return f"{exc.msg} (line {exc.lineno}, col {exc.offset})"
    return None


def ruff_check(code: str) -> None:
    """Run import blocklist and ruff security checks on code.

    Raises SecurityError if any violations are found.
    """
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in BLOCKED_IMPORTS:
                        raise SecurityError(
                            f"line {node.lineno}: import '{alias.name}' is not allowed in visualization code."
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in BLOCKED_IMPORTS:
                    raise SecurityError(
                        f"line {node.lineno}: 'from {node.module} import ...' is not allowed in visualization code."
                    )
    except SecurityError:
        raise
    except SyntaxError:
        pass

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                _RUFF_SELECT,
                "--no-fix",
                "--output-format",
                "json",
                "--stdin-filename",
                "snippet.py",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=code,
            timeout=_RUFF_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("ruff not found — security check skipped")
        return
    except subprocess.TimeoutExpired:
        logger.warning("ruff timed out after %ss — security check skipped", _RUFF_TIMEOUT_SECONDS)
        return

    if "No module named ruff" in (result.stderr or ""):
        logger.warning("ruff not found — security check skipped")
        return

    if result.returncode == 0 or not result.stdout.strip():
        return

    try:
        diagnostics: list[dict] = json.loads(result.stdout)
    except json.JSONDecodeError:
        return

    errors: list[str] = []
    for diag in diagnostics:
        loc = diag.get("location", {})
        errors.append(f"line {loc.get('row', '?')}: {diag.get('message', '')}")

    if errors:
        raise SecurityError("\n".join(errors))


def check_packages(code: str) -> str | None:
    """Check that all packages imported by code are installed."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    stdlib: frozenset[str] = frozenset(sys.stdlib_module_names)

    top_level: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])

    for import_name in sorted(top_level):
        if import_name in stdlib:
            continue
        if importlib.util.find_spec(import_name) is None:
            package_name = IMPORT_TO_PACKAGE.get(import_name, import_name)
            return (
                f"Package '{package_name}' is not installed. "
                f"Call list_packages to see what IS available, "
                f"then rewrite the code using an installed library."
            )

    return None


def ruff_format(code: str) -> str:
    """Autoformat code via ruff format and return the result."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--stdin-filename", "snippet.py", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=code,
            timeout=_RUFF_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return code
    return result.stdout if result.returncode == 0 else code
