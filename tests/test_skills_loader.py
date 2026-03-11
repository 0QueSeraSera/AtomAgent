"""Tests for workspace skills loader and prompt summary behavior."""

from __future__ import annotations

import json
import textwrap

from atom_agent.agent.context import ContextBuilder
from atom_agent.skills import SkillsLoader
from atom_agent.workspace import WorkspaceManager


def _write_skill(workspace, name: str, content: str) -> None:
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_skills_loader_parses_frontmatter_metadata(tmp_path) -> None:
    workspace = tmp_path / "skills-meta"
    WorkspaceManager(workspace).init_workspace(name="skills-meta")
    _write_skill(
        workspace,
        "repo-map",
        textwrap.dedent(
            """
            ---
            description: "Map the repository quickly."
            always: true
            ---

            # Repo Map

            Use this skill to map repo structure.
            """
        ).strip(),
    )

    skills = SkillsLoader(workspace).list_skills()
    assert len(skills) == 1
    assert skills[0].name == "repo-map"
    assert skills[0].description == "Map the repository quickly."
    assert skills[0].always is True
    assert skills[0].enabled is True


def test_skills_loader_load_skill_strips_frontmatter(tmp_path) -> None:
    workspace = tmp_path / "skills-load"
    WorkspaceManager(workspace).init_workspace(name="skills-load")
    _write_skill(
        workspace,
        "code-review",
        textwrap.dedent(
            """
            ---
            description: Review code changes.
            ---

            # Code Review

            Focus on bugs and regression risk.
            """
        ).strip(),
    )

    content = SkillsLoader(workspace).load_skill("code-review")
    assert content is not None
    assert content.startswith("# Code Review")
    assert "description:" not in content


def test_skills_loader_summary_ignores_disabled_manifest_skills(tmp_path) -> None:
    workspace = tmp_path / "skills-manifest"
    WorkspaceManager(workspace).init_workspace(name="skills-manifest")
    _write_skill(workspace, "enabled-one", "# Enabled one\n")
    _write_skill(workspace, "disabled-one", "# Disabled one\n")
    (workspace / "skills" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skills": {
                    "disabled-one": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )

    loader = SkillsLoader(workspace)
    summary = loader.build_skills_summary()
    assert "enabled-one" in summary
    assert "disabled-one" not in summary

    all_skills = loader.list_skills(include_disabled=True)
    assert len(all_skills) == 2
    disabled = [item for item in all_skills if item.name == "disabled-one"][0]
    assert disabled.enabled is False


def test_context_builder_injects_skills_brief_not_full_body(tmp_path) -> None:
    workspace = tmp_path / "ctx-skills"
    WorkspaceManager(workspace).init_workspace(name="ctx-skills")
    _write_skill(
        workspace,
        "repo-map",
        textwrap.dedent(
            """
            ---
            description: "Understand repo layout and key modules."
            ---

            # Repo Mapping Skill

            INTERNAL-SKILL-BODY-LINE-SHOULD-NOT-BE-IN-SYSTEM-PROMPT
            """
        ).strip(),
    )

    prompt = ContextBuilder(workspace).build_system_prompt()
    assert "## Skills (brief)" in prompt
    assert "- repo-map: Understand repo layout and key modules." in prompt
    assert "INTERNAL-SKILL-BODY-LINE-SHOULD-NOT-BE-IN-SYSTEM-PROMPT" not in prompt
