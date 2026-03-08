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
import sys
from pathlib import Path

from atom_agent.config import Config
from atom_agent.logging import LoggingConfig, get_logger, setup_logging

logger = get_logger("cli.main")


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
    parser.add_argument(
        "--log-level",
        choices=["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Log level override",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        default=None,
        help="Log format override",
    )
    parser.add_argument(
        "--log-output",
        choices=["stderr", "stdout", "file"],
        default=None,
        help="Log output destination override",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Log file path (implies --log-output file)",
    )
    parser.add_argument(
        "--log-content",
        action="store_true",
        help="Enable verbose content logging (includes full prompts, responses, tool results)",
    )
    parser.add_argument(
        "--log-separate-channels",
        action="store_true",
        help="Enable separate log files per channel (cli, proactive, system, etc.)",
    )
    parser.add_argument(
        "--log-channels",
        type=str,
        default=None,
        help="Comma-separated list of channels to log (e.g., cli,proactive,system)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Directory for log files (default: ./logs)",
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

    # Configure AtomAgent structured logging
    log_config = LoggingConfig()
    if args.log_level:
        log_config.level = args.log_level
    elif config.debug:
        log_config.level = "DEBUG"

    if args.log_format:
        log_config.format = args.log_format

    if args.log_output:
        log_config.output = args.log_output

    if args.log_file:
        log_config.output = "file"
        log_config.file_path = args.log_file

    if args.log_content:
        log_config.log_content = True
        # Increase max content length for verbose logging
        log_config.max_content_length = 10000

    if args.log_separate_channels:
        log_config.separate_channels = True

    if args.log_channels:
        log_config.channels_to_log = [c.strip() for c in args.log_channels.split(",") if c.strip()]

    if args.log_dir:
        log_config.log_dir = args.log_dir

    setup_logging(log_config)

    if config.debug:
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
