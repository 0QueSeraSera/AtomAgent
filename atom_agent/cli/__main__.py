"""
CLI entry point for AtomAgent.

Usage:
    python -m atom_agent.cli [options]

Environment Variables:
    DEEPSEEK_API_KEY - API key for DeepSeek provider
    ATOM_WORKSPACE   - Workspace directory (default: ./workspace)
    ATOM_MODEL       - Model to use (default: provider default)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Setup basic logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


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
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def get_provider(name: str, api_key: str):
    """Get a provider instance by name."""
    if name == "deepseek":
        from atom_agent.provider import DeepSeekProvider

        return DeepSeekProvider(api_key=api_key)

    raise ValueError(f"Unknown provider: {name}")


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get API key
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY environment variable not set", file=sys.stderr)
        return 1

    # Get workspace
    workspace = args.workspace or Path(os.environ.get("ATOM_WORKSPACE", "./workspace"))

    # Get model
    model = args.model or os.environ.get("ATOM_MODEL")

    # Create provider
    try:
        provider = get_provider(args.provider, api_key)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Run interactive chat
    from atom_agent.cli import run_interactive_chat

    try:
        asyncio.run(
            run_interactive_chat(
                provider=provider,
                workspace=workspace,
                model=model,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
