"""Unit tests for the native_skills public API and built-in skill files.

Tests cover:
  - list_skills()         — discovery, structure, sort order
  - load_skill()          — content loading, FileNotFoundError cases
  - get_skill_metadata()  — front-matter parsing
  - compose_skills()      — super-power composition
  - write_tests skill     — contract compliance (front-matter + sections)
  - code_review skill     — contract compliance (front-matter + sections)
"""

import sys
from pathlib import Path

import pytest

# Ensure the agent package root is on sys.path regardless of working directory.
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from native_skills import (
    compose_skills,
    get_skill_metadata,
    list_skills,
    load_skill,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_REQUIRED_FM_FIELDS = {"contract_version", "name", "version", "description"}
_REQUIRED_SECTIONS = {"## Description", "## Inputs", "## Outputs", "## Usage"}
_BUILTIN_SKILLS = {"write_tests", "code_review"}


# ── list_skills() ─────────────────────────────────────────────────────────────


def test_list_skills_returns_list():
    result = list_skills()
    assert isinstance(result, list)


def test_list_skills_contains_builtin_skills():
    names = {s["name"] for s in list_skills()}
    assert _BUILTIN_SKILLS <= names, f"Missing built-in skills: {_BUILTIN_SKILLS - names}"


def test_list_skills_excludes_reserved_names():
    names = {s["name"] for s in list_skills()}
    assert "README" not in names
    assert "SKILL_TEMPLATE" not in names


def test_list_skills_entry_has_required_keys():
    for skill in list_skills():
        assert "name" in skill
        assert "filename" in skill
        assert "path" in skill


def test_list_skills_filename_matches_name():
    for skill in list_skills():
        assert skill["filename"] == f"{skill['name']}.md"


def test_list_skills_path_is_absolute_and_exists():
    for skill in list_skills():
        p = Path(skill["path"])
        assert p.is_absolute(), f"{skill['path']!r} is not absolute"
        assert p.exists(), f"{skill['path']!r} does not exist"


def test_list_skills_sorted_alphabetically():
    skills = list_skills()
    names = [s["name"] for s in skills]
    assert names == sorted(names)


# ── load_skill() ──────────────────────────────────────────────────────────────


def test_load_skill_returns_string():
    content = load_skill("write_tests")
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_skill_content_starts_with_front_matter():
    content = load_skill("write_tests")
    assert content.startswith("---"), "Skill content must open with '---' front-matter delimiter"


def test_load_skill_unknown_name_raises():
    with pytest.raises(FileNotFoundError):
        load_skill("this_skill_does_not_exist")


def test_load_skill_readme_reserved_raises():
    with pytest.raises(FileNotFoundError):
        load_skill("README")


def test_load_skill_skill_template_reserved_raises():
    with pytest.raises(FileNotFoundError):
        load_skill("SKILL_TEMPLATE")


def test_load_skill_each_builtin_is_loadable():
    for name in _BUILTIN_SKILLS:
        content = load_skill(name)
        assert content, f"load_skill({name!r}) returned empty content"


# ── get_skill_metadata() ──────────────────────────────────────────────────────


def test_get_skill_metadata_returns_dict():
    meta = get_skill_metadata("write_tests")
    assert isinstance(meta, dict)


def test_get_skill_metadata_required_fields_present():
    for name in _BUILTIN_SKILLS:
        meta = get_skill_metadata(name)
        missing = _REQUIRED_FM_FIELDS - meta.keys()
        assert not missing, f"{name}: missing front-matter fields {missing}"


def test_get_skill_metadata_name_matches_filename():
    for skill in list_skills():
        meta = get_skill_metadata(skill["name"])
        assert meta.get("name") == skill["name"], (
            f"Front-matter 'name' field {meta.get('name')!r} "
            f"does not match filename stem {skill['name']!r}"
        )


def test_get_skill_metadata_contract_version_is_semver():
    for name in _BUILTIN_SKILLS:
        meta = get_skill_metadata(name)
        version = meta.get("contract_version", "")
        parts = version.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), (
            f"{name}: contract_version {version!r} is not a valid semver string"
        )


def test_get_skill_metadata_unknown_name_raises():
    with pytest.raises(FileNotFoundError):
        get_skill_metadata("nonexistent_skill")


def test_get_skill_metadata_write_tests_description_non_empty():
    meta = get_skill_metadata("write_tests")
    assert meta.get("description", "").strip()


def test_get_skill_metadata_code_review_description_non_empty():
    meta = get_skill_metadata("code_review")
    assert meta.get("description", "").strip()


# ── compose_skills() ──────────────────────────────────────────────────────────


def test_compose_skills_single_equals_load():
    composed = compose_skills(["write_tests"])
    assert composed == load_skill("write_tests")


def test_compose_skills_two_skills_contains_both():
    composed = compose_skills(["code_review", "write_tests"])
    assert load_skill("code_review") in composed
    assert load_skill("write_tests") in composed


def test_compose_skills_separator_present():
    composed = compose_skills(["code_review", "write_tests"])
    # Skills are joined by "\n\n---\n\n"
    assert "\n\n---\n\n" in composed


def test_compose_skills_preserves_order():
    composed_cr_wt = compose_skills(["code_review", "write_tests"])
    composed_wt_cr = compose_skills(["write_tests", "code_review"])
    cr_pos = composed_cr_wt.index(load_skill("code_review"))
    wt_pos = composed_cr_wt.index(load_skill("write_tests"))
    assert cr_pos < wt_pos, "code_review should appear before write_tests when listed first"

    # Reversed order
    wt_pos2 = composed_wt_cr.index(load_skill("write_tests"))
    cr_pos2 = composed_wt_cr.index(load_skill("code_review"))
    assert wt_pos2 < cr_pos2, "write_tests should appear before code_review when listed first"


def test_compose_skills_unknown_name_raises():
    with pytest.raises(FileNotFoundError):
        compose_skills(["write_tests", "skill_that_does_not_exist"])


def test_compose_skills_empty_list_returns_empty_string():
    assert compose_skills([]) == ""


def test_compose_skills_duplicate_names_allowed():
    composed = compose_skills(["write_tests", "write_tests"])
    content = load_skill("write_tests")
    assert composed.count(content) == 2


# ── write_tests skill: contract compliance ────────────────────────────────────


class TestWriteTestsSkill:
    """Verify write_tests.md fully conforms to the skill contract."""

    @pytest.fixture(scope="class")
    def content(self):
        return load_skill("write_tests")

    @pytest.fixture(scope="class")
    def metadata(self):
        return get_skill_metadata("write_tests")

    def test_has_front_matter_delimiter(self, content):
        assert content.startswith("---")

    def test_required_front_matter_fields(self, metadata):
        assert _REQUIRED_FM_FIELDS <= metadata.keys()

    def test_name_is_snake_case(self, metadata):
        name = metadata["name"]
        assert name == name.lower().replace("-", "_")
        assert " " not in name

    def test_has_description_section(self, content):
        assert "## Description" in content

    def test_has_inputs_section(self, content):
        assert "## Inputs" in content

    def test_has_outputs_section(self, content):
        assert "## Outputs" in content

    def test_has_usage_section(self, content):
        assert "## Usage" in content

    def test_sections_in_correct_order(self, content):
        positions = {s: content.index(s) for s in _REQUIRED_SECTIONS}
        assert positions["## Description"] < positions["## Inputs"]
        assert positions["## Inputs"] < positions["## Outputs"]
        assert positions["## Outputs"] < positions["## Usage"]

    def test_inputs_table_or_none(self, content):
        after_inputs = content[content.index("## Inputs"):]
        next_section = after_inputs.index("##", 2)
        inputs_body = after_inputs[:next_section]
        has_table = "|" in inputs_body
        has_none = "_None._" in inputs_body
        assert has_table or has_none, "## Inputs must contain a table or '_None._'"

    def test_outputs_table_or_none(self, content):
        after_outputs = content[content.index("## Outputs"):]
        next_section = after_outputs.index("##", 2)
        outputs_body = after_outputs[:next_section]
        has_table = "|" in outputs_body
        has_none = "_None._" in outputs_body
        assert has_table or has_none, "## Outputs must contain a table or '_None._'"

    def test_usage_has_code_block(self, content):
        after_usage = content[content.index("## Usage"):]
        assert "```" in after_usage, "## Usage must contain at least one code block"

    def test_has_examples_section(self, content):
        assert "## Examples" in content

    def test_has_limitations_section(self, content):
        assert "## Limitations" in content


# ── code_review skill: contract compliance ────────────────────────────────────


class TestCodeReviewSkill:
    """Verify code_review.md fully conforms to the skill contract."""

    @pytest.fixture(scope="class")
    def content(self):
        return load_skill("code_review")

    @pytest.fixture(scope="class")
    def metadata(self):
        return get_skill_metadata("code_review")

    def test_has_front_matter_delimiter(self, content):
        assert content.startswith("---")

    def test_required_front_matter_fields(self, metadata):
        assert _REQUIRED_FM_FIELDS <= metadata.keys()

    def test_name_is_snake_case(self, metadata):
        name = metadata["name"]
        assert name == name.lower().replace("-", "_")
        assert " " not in name

    def test_has_description_section(self, content):
        assert "## Description" in content

    def test_has_inputs_section(self, content):
        assert "## Inputs" in content

    def test_has_outputs_section(self, content):
        assert "## Outputs" in content

    def test_has_usage_section(self, content):
        assert "## Usage" in content

    def test_sections_in_correct_order(self, content):
        positions = {s: content.index(s) for s in _REQUIRED_SECTIONS}
        assert positions["## Description"] < positions["## Inputs"]
        assert positions["## Inputs"] < positions["## Outputs"]
        assert positions["## Outputs"] < positions["## Usage"]

    def test_inputs_table_or_none(self, content):
        after_inputs = content[content.index("## Inputs"):]
        next_section = after_inputs.index("##", 2)
        inputs_body = after_inputs[:next_section]
        has_table = "|" in inputs_body
        has_none = "_None._" in inputs_body
        assert has_table or has_none, "## Inputs must contain a table or '_None._'"

    def test_outputs_table_or_none(self, content):
        after_outputs = content[content.index("## Outputs"):]
        next_section = after_outputs.index("##", 2)
        outputs_body = after_outputs[:next_section]
        has_table = "|" in outputs_body
        has_none = "_None._" in outputs_body
        assert has_table or has_none, "## Outputs must contain a table or '_None._'"

    def test_usage_has_code_block(self, content):
        after_usage = content[content.index("## Usage"):]
        assert "```" in after_usage, "## Usage must contain at least one code block"

    def test_has_limitations_section(self, content):
        assert "## Limitations" in content
