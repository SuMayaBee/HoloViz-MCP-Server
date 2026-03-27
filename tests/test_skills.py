"""Tests for skill discovery and retrieval."""

import pytest

from holoviz_mcp_server.introspection.skills import get_skill, list_skills


class TestListSkills:
    def test_returns_list(self):
        skills = list_skills()
        assert isinstance(skills, list)

    def test_each_skill_has_name_and_description(self):
        for skill in list_skills():
            assert "name" in skill
            assert "description" in skill

    def test_builtin_skills_present(self):
        names = {s["name"] for s in list_skills()}
        assert "panel" in names
        assert "hvplot" in names
        assert "holoviews" in names

    def test_skills_sorted_alphabetically(self):
        skills = list_skills()
        names = [s["name"] for s in skills]
        assert names == sorted(names)


class TestGetSkill:
    def test_get_panel_skill(self):
        content = get_skill("panel")
        assert len(content) > 0
        assert "panel" in content.lower()

    def test_get_hvplot_skill(self):
        content = get_skill("hvplot")
        assert len(content) > 0

    def test_get_holoviews_skill(self):
        content = get_skill("holoviews")
        assert len(content) > 0

    def test_skill_content_has_frontmatter(self):
        content = get_skill("panel")
        assert content.startswith("---")

    def test_nonexistent_skill_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            get_skill("totally_nonexistent_skill_xyz")

    def test_underscore_normalized_to_dash(self):
        # Skills stored as holoviews but get_skill("holoviews") should work
        content = get_skill("holoviews")
        assert content
