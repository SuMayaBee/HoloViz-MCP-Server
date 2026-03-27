"""Tests for code generators."""

import ast

import pytest

from holoviz_mcp_server.codegen.codegen import (
    generate_dashboard_code,
    generate_multi_chart_code,
    generate_stream_code,
    generate_viz_code,
)


def _is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


class TestGenerateVizCode:
    def test_basic_bar_chart(self):
        code = generate_viz_code(kind="bar", data={"x": [1, 2], "y": [3, 4]}, x="x", y="y")
        assert "hvplot" in code
        assert ".bar(" in code
        assert 'x="x"' in code
        assert 'y="y"' in code

    def test_line_chart_kind(self):
        code = generate_viz_code(kind="line", data={"a": [1], "b": [2]}, x="a", y="b")
        assert ".line(" in code

    def test_scatter_chart_kind(self):
        code = generate_viz_code(kind="scatter", data={"a": [1], "b": [2]}, x="a", y="b")
        assert ".scatter(" in code

    def test_title_is_included(self):
        code = generate_viz_code(kind="bar", data={"x": [1], "y": [2]}, x="x", y="y", title="My Chart")
        assert "My Chart" in code

    def test_color_adds_by_option(self):
        code = generate_viz_code(kind="bar", data={"x": [1], "y": [2], "c": ["a"]}, x="x", y="y", color="c")
        assert 'by="c"' in code

    def test_no_color_excludes_by_option(self):
        code = generate_viz_code(kind="bar", data={"x": [1], "y": [2]}, x="x", y="y")
        assert "by=" not in code

    def test_generated_code_is_valid_python(self):
        code = generate_viz_code(kind="bar", data={"x": [1, 2, 3], "y": [4, 5, 6]}, x="x", y="y", title="Test")
        assert _is_valid_python(code)

    def test_responsive_option_included(self):
        code = generate_viz_code(kind="bar", data={"x": [1], "y": [2]}, x="x", y="y")
        assert "responsive=True" in code


class TestGenerateDashboardCode:
    def test_contains_panel_import(self):
        code = generate_dashboard_code(title="T", data={"x": [1], "y": [2]}, x="x", y="y")
        assert "import panel as pn" in code

    def test_contains_servable(self):
        code = generate_dashboard_code(title="T", data={"x": [1], "y": [2]}, x="x", y="y")
        assert ".servable()" in code

    def test_title_in_code(self):
        code = generate_dashboard_code(title="Sales Dashboard", data={"x": [1], "y": [2]}, x="x", y="y")
        assert "Sales Dashboard" in code

    def test_tabulator_extension_loaded(self):
        code = generate_dashboard_code(title="T", data={"x": [1], "y": [2]}, x="x", y="y")
        assert "tabulator" in code

    def test_color_grouping(self):
        code = generate_dashboard_code(title="T", data={"x": [1], "y": [2], "c": ["a"]}, x="x", y="y", color="c")
        assert 'by="c"' in code

    def test_generated_code_is_valid_python(self):
        code = generate_dashboard_code(title="T", data={"x": [1, 2], "y": [3, 4]}, x="x", y="y")
        assert _is_valid_python(code)


class TestGenerateStreamCode:
    def test_contains_periodic_callback(self):
        code = generate_stream_code()
        assert "add_periodic_callback" in code

    def test_custom_metric_name(self):
        code = generate_stream_code(metric_name="temperature")
        assert "temperature" in code

    def test_custom_interval(self):
        code = generate_stream_code(interval_ms=500)
        assert "500" in code

    def test_contains_buffer(self):
        code = generate_stream_code()
        assert "Buffer" in code

    def test_generated_code_is_valid_python(self):
        code = generate_stream_code(title="Live", metric_name="val", interval_ms=1000)
        assert _is_valid_python(code)


class TestGenerateMultiChartCode:
    def test_multiple_charts_rendered(self):
        charts = [
            {"kind": "bar", "x": "x", "y": "y", "title": "Chart 1"},
            {"kind": "line", "x": "x", "y": "y", "title": "Chart 2"},
        ]
        code = generate_multi_chart_code(title="Multi", data={"x": [1], "y": [2]}, charts=charts)
        assert ".bar(" in code
        assert ".line(" in code

    def test_link_selections_used(self):
        code = generate_multi_chart_code(title="T", data={"x": [1], "y": [2]}, charts=[])
        assert "link_selections" in code

    def test_generated_code_is_valid_python(self):
        charts = [{"kind": "scatter", "x": "x", "y": "y", "title": "S"}]
        code = generate_multi_chart_code(title="T", data={"x": [1, 2], "y": [3, 4]}, charts=charts)
        assert _is_valid_python(code)
