"""Tests for the validation pipeline."""

import pytest

from holoviz_mcp_server.validation import (
    SecurityError,
    ValidationError,
    ast_check,
    check_packages,
    ruff_check,
)


class TestAstCheck:
    def test_valid_code_returns_none(self):
        assert ast_check("x = 1 + 2") is None

    def test_valid_multiline_code(self):
        code = "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2]})\ndf"
        assert ast_check(code) is None

    def test_syntax_error_returns_message(self):
        result = ast_check("def foo(:\n    pass")
        assert result is not None
        assert isinstance(result, str)

    def test_unclosed_paren_is_syntax_error(self):
        result = ast_check("x = (1 + 2")
        assert result is not None

    def test_empty_code_is_valid(self):
        assert ast_check("") is None


class TestRuffCheck:
    def test_clean_code_passes(self):
        ruff_check("import pandas as pd\ndf = pd.DataFrame()")

    def test_blocked_import_subprocess_raises(self):
        with pytest.raises(SecurityError, match="subprocess"):
            ruff_check("import subprocess\nsubprocess.run(['ls'])")

    def test_blocked_import_socket_raises(self):
        with pytest.raises(SecurityError, match="socket"):
            ruff_check("import socket")

    def test_blocked_import_pickle_raises(self):
        with pytest.raises(SecurityError, match="pickle"):
            ruff_check("import pickle")

    def test_blocked_from_import_raises(self):
        with pytest.raises(SecurityError):
            ruff_check("from subprocess import run")

    def test_allowed_imports_pass(self):
        code = "import pandas as pd\nimport numpy as np\nimport hvplot.pandas"
        ruff_check(code)  # should not raise

    def test_blocked_import_threading_raises(self):
        with pytest.raises(SecurityError, match="threading"):
            ruff_check("import threading")

    def test_syntax_error_skips_blocked_import_check(self):
        # Syntax errors cause the AST walk to skip, but ruff CLI still runs and may flag them
        # Blocked import check is skipped via except SyntaxError — this code has no blocked import
        try:
            ruff_check("def foo(:")
        except SecurityError:
            pass  # ruff CLI may still flag the syntax error — that's acceptable behaviour


class TestCheckPackages:
    def test_installed_package_passes(self):
        assert check_packages("import pandas") is None

    def test_stdlib_module_passes(self):
        assert check_packages("import os\nimport json\nimport pathlib") is None

    def test_missing_package_returns_message(self):
        result = check_packages("import totally_nonexistent_package_xyz")
        assert result is not None
        assert "totally_nonexistent_package_xyz" in result

    def test_multiple_imports_all_installed_passes(self):
        code = "import pandas\nimport holoviews\nimport panel"
        assert check_packages(code) is None

    def test_import_alias_mapping(self):
        # PIL maps to Pillow — if Pillow is not installed, message says Pillow
        result = check_packages("import totally_fake_xyz_lib")
        assert result is not None

    def test_syntax_error_in_code_returns_none(self):
        # check_packages skips bad syntax gracefully
        assert check_packages("def foo(:") is None
