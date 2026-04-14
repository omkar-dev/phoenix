"""Tests for the native_skills discovery and attachment API."""

import pytest
from pathlib import Path

import native_skills
from native_skills import attach_skills, load_skill


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def skill_dir(tmp_path, monkeypatch):
    """Redirect _SKILLS_DIR to a temporary directory and return it."""
    monkeypatch.setattr(native_skills, "_SKILLS_DIR", tmp_path)
    return tmp_path


def _write_skill(skill_dir: Path, name: str, content: str) -> Path:
    p = skill_dir / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


# ── list_skills ───────────────────────────────────────────────────────────────

def test_list_skills_empty_dir(skill_dir):
    assert native_skills.list_skills() == []


def test_list_skills_excludes_meta_files(skill_dir):
    (skill_dir / "README.md").write_text("# README", encoding="utf-8")
    (skill_dir / "SKILL_TEMPLATE.md").write_text("# Template", encoding="utf-8")
    assert native_skills.list_skills() == []


def test_list_skills_returns_descriptor_fields(skill_dir):
    _write_skill(skill_dir, "write_tests", "# Skill: Write Tests\n\nContent.")
    skills = native_skills.list_skills()
    assert len(skills) == 1
    s = skills[0]
    assert s["name"] == "write_tests"
    assert s["filename"] == "write_tests.md"
    assert s["path"] == str(skill_dir / "write_tests.md")
    assert s["title"] == "Write Tests"


def test_list_skills_sorted_alphabetically(skill_dir):
    for name in ("zebra", "alpha", "middle"):
        _write_skill(skill_dir, name, f"# Skill: {name.title()}\n")
    names = [s["name"] for s in native_skills.list_skills()]
    assert names == ["alpha", "middle", "zebra"]


def test_list_skills_title_plain_heading_fallback(skill_dir):
    _write_skill(skill_dir, "plain", "# Plain Heading\n\nNo 'Skill:' prefix.")
    skills = native_skills.list_skills()
    assert skills[0]["title"] == "Plain Heading"


def test_list_skills_title_stem_fallback_when_no_heading(skill_dir):
    _write_skill(skill_dir, "headless", "Just prose, no heading.")
    skills = native_skills.list_skills()
    assert skills[0]["title"] == "headless"


def test_list_skills_ignores_non_md_files(skill_dir):
    _write_skill(skill_dir, "real_skill", "# Skill: Real\n")
    (skill_dir / "notes.txt").write_text("ignore me")
    (skill_dir / "data.json").write_text("{}")
    assert len(native_skills.list_skills()) == 1


# ── load_skill ────────────────────────────────────────────────────────────────

def test_load_skill_returns_content(skill_dir):
    _write_skill(skill_dir, "my_skill", "# Skill: My Skill\n\nStep one.")
    content = native_skills.load_skill("my_skill")
    assert "Step one." in content


def test_load_skill_unknown_name_raises(skill_dir):
    with pytest.raises(FileNotFoundError, match="no_such_skill"):
        native_skills.load_skill("no_such_skill")


def test_load_skill_readme_reserved(skill_dir):
    (skill_dir / "README.md").write_text("# README")
    with pytest.raises(FileNotFoundError, match="README"):
        native_skills.load_skill("README")


def test_load_skill_template_reserved(skill_dir):
    (skill_dir / "SKILL_TEMPLATE.md").write_text("# Template")
    with pytest.raises(FileNotFoundError, match="SKILL_TEMPLATE"):
        native_skills.load_skill("SKILL_TEMPLATE")


def test_load_skill_path_traversal_rejected(skill_dir):
    with pytest.raises(FileNotFoundError):
        native_skills.load_skill("../../etc/shadow")

    with pytest.raises(FileNotFoundError):
        native_skills.load_skill("subdir/skill")


# ── attach_skills ─────────────────────────────────────────────────────────────

def test_attach_skills_single(skill_dir):
    _write_skill(skill_dir, "alpha", "# Skill: Alpha\n\nAlpha content.")
    result = native_skills.attach_skills("alpha")
    assert "Alpha content." in result
    assert "\n\n---\n\n" not in result


def test_attach_skills_two_skills_stacked(skill_dir):
    _write_skill(skill_dir, "alpha", "# Skill: Alpha\n\nAlpha content.")
    _write_skill(skill_dir, "beta", "# Skill: Beta\n\nBeta content.")
    result = native_skills.attach_skills("alpha", "beta")
    assert "Alpha content." in result
    assert "Beta content." in result
    # Skills are separated by a Markdown horizontal rule
    assert "---" in result
    # Order is preserved
    assert result.index("Alpha") < result.index("Beta")


def test_attach_skills_three_skills_stacked(skill_dir):
    for name in ("one", "two", "three"):
        _write_skill(skill_dir, name, f"# Skill: {name.title()}\n\n{name} content.")
    result = native_skills.attach_skills("one", "two", "three")
    for name in ("one", "two", "three"):
        assert f"{name} content." in result
    # Two separators for three skills
    assert result.count("---") == 2


def test_attach_skills_unknown_name_raises(skill_dir):
    _write_skill(skill_dir, "good", "# Skill: Good\n\nOK.")
    with pytest.raises(FileNotFoundError, match="missing"):
        native_skills.attach_skills("good", "missing")


def test_attach_skills_strips_surrounding_whitespace(skill_dir):
    _write_skill(skill_dir, "padded", "\n\n# Skill: Padded\n\nContent.\n\n\n")
    result = native_skills.attach_skills("padded")
    assert not result.startswith("\n")
    assert not result.endswith("\n")


def test_attach_skills_output_is_valid_markdown_separator(skill_dir):
    _write_skill(skill_dir, "a", "# Skill: A\n\nA body.")
    _write_skill(skill_dir, "b", "# Skill: B\n\nB body.")
    result = native_skills.attach_skills("a", "b")
    assert "\n\n---\n\n" in result


# ── Composition correctness (real skill files) ────────────────────────────────

def test_compose_skills_separator_present():
    """Verify the separator appears *between* the two skill blobs, not just anywhere."""
    code_review_content = load_skill("code_review").strip()
    write_tests_content = load_skill("write_tests").strip()
    composed = attach_skills("code_review", "write_tests")
    expected = code_review_content + "\n\n---\n\n" + write_tests_content
    assert composed == expected, "Skills must be joined by the '\\n\\n---\\n\\n' separator"


# ── Per-skill content contracts ───────────────────────────────────────────────

class TestCodeReviewSkill:
    """Verify the code_review skill satisfies the skill content contract."""

    @pytest.fixture()
    def content(self):
        return load_skill("code_review")

    def test_skill_loadable(self, content):
        assert content

    def test_has_description_section(self, content):
        assert "## Description" in content

    def test_has_usage_section(self, content):
        assert "## Usage" in content

    def test_has_limitations_section(self, content):
        assert "## Limitations" in content

    def test_has_examples_section(self, content):
        assert "## Examples" in content


class TestWriteTestsSkill:
    """Verify the write_tests skill satisfies the skill content contract."""

    @pytest.fixture()
    def content(self):
        return load_skill("write_tests")

    def test_skill_loadable(self, content):
        assert content

    def test_has_description_section(self, content):
        assert "## Description" in content

    def test_has_usage_section(self, content):
        assert "## Usage" in content

    def test_has_limitations_section(self, content):
        assert "## Limitations" in content

    def test_has_examples_section(self, content):
        assert "## Examples" in content
