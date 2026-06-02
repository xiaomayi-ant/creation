"""Project style skill package tests."""

import importlib.util
import json
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
STYLE_SKILLS = [
    "douyin_short_drama_style",
    "xiaohongshu_story_style",
]


def _read_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---", 2)
    assert body.strip()

    fields: dict[str, str] = {}
    for line in frontmatter.strip().splitlines():
        if ":" not in line or line.startswith("  "):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _load_fetch_samples(script_path: Path):
    spec = importlib.util.spec_from_file_location("skill_fetch_samples", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fetch_samples


def test_style_skill_packages_follow_project_skill_contract():
    for skill_name in STYLE_SKILLS:
        skill_dir = SKILLS_ROOT / skill_name
        skill_md = skill_dir / "SKILL.md"
        script_path = skill_dir / "scripts" / "fetch_samples.py"
        schema_path = skill_dir / "references" / "sample_schema.json"

        assert skill_md.exists()
        assert script_path.exists()
        assert schema_path.exists()

        fields = _read_frontmatter(skill_md)
        assert fields["name"] == skill_name
        assert fields["description"]
        assert "allowed-tools" in fields

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert "source_url" in schema["required"]

        fetch_samples = _load_fetch_samples(script_path)
        assert fetch_samples("test", limit=2) == []
