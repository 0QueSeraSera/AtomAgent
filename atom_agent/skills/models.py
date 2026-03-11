"""Data models for workspace skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillManifestEntry:
    """Persisted manifest state for one installed skill."""

    enabled: bool = True
    source: str | None = None
    installed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifestEntry":
        """Build a manifest entry from untrusted JSON data."""
        return cls(
            enabled=bool(data.get("enabled", True)),
            source=data.get("source"),
            installed_at=data.get("installed_at"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry for manifest persistence."""
        return {
            "enabled": self.enabled,
            "source": self.source,
            "installed_at": self.installed_at,
            "metadata": self.metadata,
        }


@dataclass
class SkillsManifest:
    """Workspace skills manifest file."""

    version: int = 1
    skills: dict[str, SkillManifestEntry] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillsManifest":
        """Build manifest from untrusted JSON data."""
        raw_skills = data.get("skills")
        skills: dict[str, SkillManifestEntry] = {}
        if isinstance(raw_skills, dict):
            for name, entry in raw_skills.items():
                if isinstance(name, str) and isinstance(entry, dict):
                    skills[name] = SkillManifestEntry.from_dict(entry)
        return cls(version=int(data.get("version", 1)), skills=skills)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest to JSON-compatible dict."""
        return {
            "version": self.version,
            "skills": {name: entry.to_dict() for name, entry in self.skills.items()},
        }


@dataclass
class SkillRecord:
    """Discovered skill metadata in workspace."""

    name: str
    path: Path
    enabled: bool = True
    description: str = ""
    always: bool = False
