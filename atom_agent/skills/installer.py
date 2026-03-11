"""Installer for workspace-local skills."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from atom_agent.skills.loader import SkillsLoader
from atom_agent.skills.models import SkillManifestEntry


class SkillInstaller:
    """Install skills into `workspace/skills/`."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.loader = SkillsLoader(workspace)

    def install(self, source: Path, *, name: str | None = None, enabled: bool = True) -> Path:
        """Install a skill from local file or directory.

        Args:
            source: Path to a skill directory (must contain SKILL.md) or SKILL.md file.
            name: Optional destination skill name (defaults to source directory name).
            enabled: Whether skill should be enabled in manifest.

        Returns:
            Installed SKILL.md path.
        """
        source_path = source.expanduser().resolve()
        source_kind, source_skill_file = self._resolve_source(source_path)

        skill_name = self._normalize_name(name or source_path.parent.name if source_kind == "file" else name or source_path.name)
        target_dir = self.loader.skills_dir / skill_name
        target_file = target_dir / "SKILL.md"

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if source_kind == "dir":
            shutil.copytree(source_path, target_dir, dirs_exist_ok=True)
        else:
            shutil.copy2(source_skill_file, target_file)

        if not target_file.exists():
            raise ValueError("Installed skill is missing SKILL.md")

        manifest = self.loader.load_manifest()
        previous = manifest.skills.get(skill_name)
        manifest.skills[skill_name] = SkillManifestEntry(
            enabled=enabled,
            source=str(source_path),
            installed_at=datetime.now(timezone.utc).isoformat(),
            metadata=previous.metadata if previous is not None else {},
        )
        self.loader.save_manifest(manifest)
        return target_file

    @staticmethod
    def _resolve_source(source: Path) -> tuple[str, Path]:
        """Return source kind (`dir` or `file`) and canonical SKILL.md path."""
        if source.is_dir():
            skill_file = source / "SKILL.md"
            if not skill_file.exists():
                raise ValueError(f"Missing SKILL.md in source directory: {source}")
            return "dir", skill_file

        if source.is_file():
            if source.name != "SKILL.md":
                raise ValueError("Source file must be named SKILL.md")
            return "file", source

        raise ValueError(f"Source path does not exist: {source}")

    @staticmethod
    def _normalize_name(name: str) -> str:
        clean = name.strip()
        if not clean:
            raise ValueError("Skill name cannot be empty")
        if "/" in clean or "\\" in clean:
            raise ValueError("Skill name cannot contain path separators")
        return clean
