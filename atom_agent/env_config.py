"""Configuration management for AtomAgent.

Loads settings from .env file and environment variables.
Environment variables take precedence over .env file values.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import dotenv, provide fallback if not available
try:
    from dotenv import load_dotenv

    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def _default_workspace_path() -> Path:
    """Resolve default workspace from global registry."""
    try:
        from atom_agent.config import ConfigManager

        return ConfigManager().get_active_workspace_path()
    except Exception:
        return Path.home() / ".atom-agents" / "workspaces" / "default"


@dataclass
class Config:
    """
    AtomAgent configuration loaded from .env and environment variables.

    Environment variables take precedence over .env file values.

    Attributes:
        deepseek_api_key: API key for DeepSeek provider
        openai_api_key: API key for OpenAI provider (future use)
        anthropic_api_key: API key for Anthropic provider (future use)
        workspace: Default workspace directory
        model: Default model to use
        debug: Enable debug logging
    """

    # API Keys
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # General settings
    workspace: Path = field(default_factory=_default_workspace_path)
    model: str | None = None
    debug: bool = False

    @classmethod
    def load(cls, env_file: str | Path | None = None, *, override: bool = False) -> "Config":
        """
        Load configuration from .env file and environment variables.

        Args:
            env_file: Path to .env file. If None, searches for .env in current
                      directory and parent directories.
            override: If True, environment variables override .env values even
                      if already set (requires python-dotenv).

        Returns:
            Config instance with loaded settings.
        """
        import os

        # Load .env file if dotenv is available
        if DOTENV_AVAILABLE:
            if env_file:
                load_dotenv(env_file, override=override)
            else:
                # Search for .env in current and parent directories
                load_dotenv(override=override)
            logger.debug("Loaded .env file via python-dotenv")
        else:
            logger.debug("python-dotenv not available, skipping .env file")

        # Read from environment variables
        workspace_env = os.environ.get("ATOMAGENT_WORKSPACE") or os.environ.get("ATOM_WORKSPACE")
        config = cls(
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            workspace=Path(workspace_env) if workspace_env else _default_workspace_path(),
            model=os.environ.get("ATOM_MODEL"),
            debug=os.environ.get("ATOM_DEBUG", "").lower() in ("1", "true", "yes"),
        )

        return config

    def get_api_key(self, provider: str) -> str | None:
        """
        Get API key for a specific provider.

        Args:
            provider: Provider name (e.g., "deepseek", "openai", "anthropic")

        Returns:
            API key if configured, None otherwise.
        """
        key_map = {
            "deepseek": self.deepseek_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return key_map.get(provider.lower())

    def validate(self, provider: str) -> list[str]:
        """
        Validate configuration for a specific provider.

        Args:
            provider: Provider name to validate for

        Returns:
            List of error messages, empty if valid.
        """
        errors = []

        api_key = self.get_api_key(provider)
        if not api_key:
            errors.append(f"{provider.upper()}_API_KEY not set (check .env or environment)")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary (masking sensitive values)."""
        return {
            "deepseek_api_key": "***" if self.deepseek_api_key else None,
            "openai_api_key": "***" if self.openai_api_key else None,
            "anthropic_api_key": "***" if self.anthropic_api_key else None,
            "workspace": str(self.workspace),
            "model": self.model,
            "debug": self.debug,
        }


# Global config instance (lazy loaded)
_config: Config | None = None


def get_config(reload: bool = False) -> Config:
    """
    Get the global configuration instance.

    Args:
        reload: If True, reload configuration from environment.

    Returns:
        Global Config instance.
    """
    global _config
    if _config is None or reload:
        _config = Config.load()
    return _config
