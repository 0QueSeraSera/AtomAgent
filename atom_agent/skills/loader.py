"""Workspace skills loader and summary builder."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from atom_agent.skills.models import SkillRecord, SkillsManifest

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


class SkillsLoader:
    """Load skills from `workspace/skills/`."""

    DEFAULT_SUMMARY_SKILLS = 20
    DEFAULT_SUMMARY_DESC_CHARS = 160

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.skills_dir = workspace / "skills"
        self.manifest_path = self.skills_dir / "manifest.json"

    def list_skills(self, *, include_disabled: bool = False) -> list[SkillRecord]:
        """List skills discovered in workspace, optionally including disabled ones."""
        if not self.skills_dir.is_dir():
            return []

        manifest = self.load_manifest()
        records: list[SkillRecord] = []

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            metadata = self._parse_frontmatter(skill_file.read_text(encoding="utf-8"))
            entry = manifest.skills.get(skill_dir.name)
            enabled = True if entry is None else entry.enabled

            record = SkillRecord(
                name=skill_dir.name,
                path=skill_file,
                enabled=enabled,
                description=self._coerce_str(metadata.get("description")),
                always=self._coerce_bool(metadata.get("always")),
            )
            if include_disabled or record.enabled:
                records.append(record)

        return records

    def load_skill(self, name: str, *, include_frontmatter: bool = False) -> str | None:
        """Load one skill's markdown body by name."""
        skill_file = self.skills_dir / name / "SKILL.md"
        if not skill_file.exists():
            return None

        content = skill_file.read_text(encoding="utf-8")
        if include_frontmatter:
            return content
        return self._strip_frontmatter(content).strip()

    def build_skills_summary(
        self,
        *,
        max_skills: int = DEFAULT_SUMMARY_SKILLS,
        max_description_chars: int = DEFAULT_SUMMARY_DESC_CHARS,
    ) -> str:
        """Build bounded skills summary for prompt injection."""
        skills = self.list_skills(include_disabled=False)
        if not skills:
            return ""

        lines = [f"enabled_skills: {len(skills)}"]
        for skill in skills[:max_skills]:
            description = (skill.description or "No description provided.").strip()
            if len(description) > max_description_chars:
                description = description[: max_description_chars - 3] + "..."
            lines.append(f"- {skill.name}: {description}")

        if len(skills) > max_skills:
            lines.append(f"- ... {len(skills) - max_skills} more skill(s) not shown")

        return "## Skills (brief)\n\n" + "\n".join(lines)

    def load_manifest(self) -> SkillsManifest:
        """Load manifest file if present; returns empty manifest on parse errors."""
        if not self.manifest_path.exists():
            return SkillsManifest()

        try:
            raw = self.manifest_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return SkillsManifest()
            return SkillsManifest.from_dict(data)
        except Exception:
            return SkillsManifest()

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """Remove YAML-like markdown frontmatter when present."""
        match = _FRONTMATTER_PATTERN.match(content)
        if not match:
            return content
        return content[match.end() :]

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, Any]:
        """Parse simple top-level `key: value` entries from frontmatter."""
        match = _FRONTMATTER_PATTERN.match(content)
        if not match:
            return {}

        metadata: dict[str, Any] = {}
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
        return metadata

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """Convert common textual boolean values to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _coerce_str(value: Any) -> str:
        """Convert scalar metadata values to strings safely."""
        if value is None:
            return ""
        return str(value)
