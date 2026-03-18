"""Skills core functions.

Pure Python functions for accessing skill/best-practice documents.
Skills are stored in: skills/<name>/SKILL.md

Two sources scanned with precedence (most specific wins):
1. Project-level — ./skills/ in cwd
2. Built-in — Skills embedded in the package
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _skills_search_paths() -> list[Path]:
    """Return ordered skill directories (highest precedence first)."""
    from holoviz_mcp_app.config import get_config

    config = get_config()
    return [
        Path.cwd() / "skills",  # project-level
        config.skills_dir,  # built-in
    ]


def _find_skill_file(skill_dir: Path, name: str) -> Path | None:
    """Locate the SKILL.md file for a given skill name."""
    # New format: <name>/SKILL.md
    candidate = skill_dir / name / "SKILL.md"
    if candidate.exists():
        return candidate

    # Legacy flat format: <name>.md
    candidate = skill_dir / f"{name}.md"
    if candidate.exists():
        return candidate

    return None


def _scan_skills_in_dir(skill_dir: Path) -> dict[str, Path]:
    """Scan a directory for skills."""
    skills: dict[str, Path] = {}
    if not skill_dir.exists():
        return skills

    for sub in sorted(skill_dir.iterdir()):
        if sub.is_dir():
            skill_file = sub / "SKILL.md"
            if skill_file.exists():
                skills[sub.name] = skill_file

    for md_file in sorted(skill_dir.glob("*.md")):
        name = md_file.stem
        if name not in skills:
            skills[name] = md_file

    return skills


def _extract_description(path: Path) -> str:
    """Extract the description field from a skill file's YAML frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    frontmatter = text[3:end]
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("description:"):
            return stripped[len("description:"):].strip().strip("\"'")
    return ""


def list_skills() -> list[dict[str, str]]:
    """List all available skills with their descriptions."""
    merged: dict[str, str] = {}

    for search_dir in reversed(_skills_search_paths()):
        for name, path in _scan_skills_in_dir(search_dir).items():
            merged[name] = _extract_description(path)

    return [{"name": name, "description": merged[name]} for name in sorted(merged)]


def get_skill(name: str) -> str:
    """Get skill content by name."""
    name = name.replace("_", "-")

    for search_dir in _skills_search_paths():
        skill_file = _find_skill_file(search_dir, name)
        if skill_file is not None:
            return skill_file.read_text(encoding="utf-8")

    available: set[str] = set()
    for search_dir in _skills_search_paths():
        available.update(_scan_skills_in_dir(search_dir).keys())

    available_str = ", ".join(sorted(available)) if available else "None"
    raise FileNotFoundError(f"Skill '{name}' not found. Available: {available_str}")
