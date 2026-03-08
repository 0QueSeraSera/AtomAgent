"""
CLI entry point for AtomAgent.

Usage:
    python -m atom_agent [options]
    python -m atom_agent.cli [options]

Configuration:
    Settings are loaded from .env file in the current directory (or parent dirs).
    Environment variables take precedence over .env file values.

    DEEPSEEK_API_KEY - API key for DeepSeek provider
    OPENAI_API_KEY   - API key for OpenAI provider (future use)
    ANTHROPIC_API_KEY - API key for Anthropic provider (future use)
    ATOM_WORKSPACE   - Workspace directory (default: ./workspace)
    ATOM_MODEL       - Model to use (default: provider default)
    ATOM_DEBUG       - Enable debug logging (1, true, yes)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from atom_agent.config import Config

# Setup basic logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="atom-agent",
        description="Interactive CLI chat with AtomAgent",
    )

    parser.add_argument(
        "--provider",
        "-p",
        choices=["deepseek"],
        default="deepseek",
        help="LLM provider to use (default: deepseek)",
    )

    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Model to use (default: provider default)",
    )

    parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory (default: ./workspace)",
    )

    parser.add_argument(
        "--env-file",
        "-e",
        type=Path,
        default=None,
        help="Path to .env file (default: search for .env in current/parent dirs)",
    )

    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def get_provider(name: str, config: Config):
    """Get a provider instance by name using config."""
    api_key = config.get_api_key(name)
    if not api_key:
        raise ValueError(f"{name.upper()}_API_KEY not configured")

    if name == "deepseek":
        from atom_agent.provider import DeepSeekProvider

        return DeepSeekProvider(api_key=api_key)

    raise ValueError(f"Unknown provider: {name}")


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Load configuration from .env and environment
    config = Config.load(env_file=args.env_file)

    # Apply CLI overrides
    if args.debug:
        config.debug = True
    if args.workspace:
        config.workspace = args.workspace
    if args.model:
        config.model = args.model

    # Configure logging level
    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug(f"Config: {config.to_dict()}")

    # Validate provider configuration
    errors = config.validate(args.provider)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        print("\nCreate a .env file with your API key:", file=sys.stderr)
        print(f"  {args.provider.upper()}_API_KEY=your-api-key-here", file=sys.stderr)
        return 1

    # Create provider
    try:
        provider = get_provider(args.provider, config)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Run interactive chat
    from atom_agent.cli import run_interactive_chat

    try:
        asyncio.run(
            run_interactive_chat(
                provider=provider,
                workspace=config.workspace,
                model=config.model,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
