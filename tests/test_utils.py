"""Tests for display utilities."""

import pytest

from holoviz_mcp_server.analysis import (
    ExtensionError,
    find_extensions,
    validate_extension_availability,
)
from holoviz_mcp_server.utils import extract_last_expression


class TestFindExtensions:
    def test_no_extensions_returns_empty(self):
        assert find_extensions("import pandas as pd") == []

    def test_plotly_detected(self):
        assert "plotly" in find_extensions("import plotly.express as px")

    def test_tabulator_detected(self):
        assert "tabulator" in find_extensions("pn.widgets.Tabulator(df)")

    def test_vega_detected(self):
        assert "vega" in find_extensions("import altair as alt")

    def test_multiple_extensions_detected(self):
        code = "import plotly\nimport altair"
        exts = find_extensions(code)
        assert "plotly" in exts
        assert "vega" in exts


class TestValidateExtensionAvailability:
    def test_no_extension_needed_passes(self):
        validate_extension_availability("import pandas as pd")  # no raise

    def test_plotly_without_extension_raises(self):
        with pytest.raises(ExtensionError, match="plotly"):
            validate_extension_availability("import plotly.express as px")

    def test_plotly_with_extension_declared_passes(self):
        code = "import panel as pn\npn.extension('plotly')\nimport plotly.express as px"
        validate_extension_availability(code)  # no raise

    def test_tabulator_without_extension_raises(self):
        with pytest.raises(ExtensionError, match="tabulator"):
            validate_extension_availability("pn.widgets.Tabulator(df)")

    def test_tabulator_with_extension_passes(self):
        code = "import panel as pn\npn.extension('tabulator')\npn.widgets.Tabulator(df)"
        validate_extension_availability(code)


class TestExtractLastExpression:
    def test_single_expression(self):
        statements, expr = extract_last_expression("x = 1\nx + 2")
        assert "x + 2" in expr
        assert "x = 1" in statements

    def test_no_expression_returns_full_code(self):
        code = "x = 1\ny = 2"
        statements, expr = extract_last_expression(code)
        assert expr == ""

    def test_empty_code(self):
        statements, expr = extract_last_expression("")
        assert statements == ""
        assert expr == ""

    def test_single_expression_only(self):
        statements, expr = extract_last_expression("1 + 2")
        assert "1 + 2" in expr

    def test_function_call_as_last_expression(self):
        code = "import pandas as pd\npd.DataFrame({'a': [1]})"
        statements, expr = extract_last_expression(code)
        assert "pd.DataFrame" in expr

    def test_syntax_error_raises_value_error(self):
        with pytest.raises(ValueError, match="Syntax error"):
            extract_last_expression("def foo(:")
