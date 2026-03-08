"""Bash tool for executing shell commands."""

import asyncio
from typing import Any

from atom_agent.logging import get_logger
from atom_agent.tools.base import Tool

logger = get_logger("tools.bash")


class BashTool(Tool):
    """Tool for executing bash/shell commands.

    Provides safe command execution with timeout, working directory control,
    and output capture.
    """

    def __init__(
        self,
        default_timeout: float = 60.0,
        max_output_size: int = 50_000,
        allowed_commands: list[str] | None = None,
        blocked_commands: list[str] | None = None,
        default_cwd: str | None = None,
    ):
        self._default_timeout = default_timeout
        self._max_output_size = max_output_size
        self._allowed_commands = allowed_commands
        self._blocked_commands = blocked_commands or []
        self._default_cwd = default_cwd

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute bash/shell commands. "
            "Returns stdout, stderr, and exit code. "
            "Use with caution - commands run in a subprocess."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Timeout in seconds (default: {self._default_timeout})",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution",
                },
                "env": {
                    "type": "object",
                    "description": "Environment variables as key-value pairs",
                },
                "shell": {
                    "type": "boolean",
                    "description": "Run command in shell (default: true)",
                },
            },
            "required": ["command"],
        }

    def _validate_command(self, command: str) -> str | None:
        """Validate command against allowlist/blocklist. Returns error message or None."""
        # Get the base command (first word)
        base_cmd = command.strip().split()[0] if command.strip() else ""

        # Check blocklist first
        for blocked in self._blocked_commands:
            if base_cmd == blocked or command.startswith(blocked + " "):
                return f"Command '{blocked}' is blocked"

        # Check allowlist if configured
        if self._allowed_commands is not None:
            if base_cmd not in self._allowed_commands:
                return (
                    f"Command '{base_cmd}' is not in allowed list. "
                    f"Allowed: {', '.join(self._allowed_commands)}"
                )

        return None

    async def execute(
        self,
        command: str,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = True,
        **kwargs: Any,
    ) -> str:
        timeout = timeout or self._default_timeout
        cwd = cwd or self._default_cwd

        # Validate command
        validation_error = self._validate_command(command)
        if validation_error:
            logger.warning(
                "Command blocked",
                extra={"command": command[:100], "reason": validation_error},
            )
            return f"Error: {validation_error}"

        logger.info(
            "Executing command",
            extra={
                "command": command[:100],
                "timeout": timeout,
                "cwd": cwd,
            },
        )

        try:
            # Prepare environment
            import os

            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            # Create subprocess
            if shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=process_env,
                )
            else:
                # Split command for non-shell execution
                args = command.split()
                process = await asyncio.create_subprocess_exec(
                    args[0],
                    *args[1:],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=process_env,
                )

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.warning(
                    "Command timed out",
                    extra={"command": command[:100], "timeout": timeout},
                )
                return f"Error: Command timed out after {timeout} seconds"

            # Decode output
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Truncate if necessary
            stdout_truncated = False
            stderr_truncated = False

            if len(stdout_text) > self._max_output_size:
                stdout_text = stdout_text[: self._max_output_size]
                stdout_truncated = True

            if len(stderr_text) > self._max_output_size:
                stderr_text = stderr_text[: self._max_output_size]
                stderr_truncated = True

            # Build result
            result_parts = [f"Exit code: {process.returncode}"]

            if stdout_text:
                result_parts.append(f"\nStdout:\n{stdout_text}")
                if stdout_truncated:
                    result_parts.append(f"\n[Stdout truncated to {self._max_output_size} chars]")

            if stderr_text:
                result_parts.append(f"\nStderr:\n{stderr_text}")
                if stderr_truncated:
                    result_parts.append(f"\n[Stderr truncated to {self._max_output_size} chars]")

            return "\n".join(result_parts)

        except FileNotFoundError as e:
            logger.error(
                "Command not found",
                extra={"command": command[:100], "error": str(e)},
            )
            return f"Error: Command not found - {str(e)}"
        except PermissionError as e:
            logger.error(
                "Permission denied",
                extra={"command": command[:100], "error": str(e)},
            )
            return f"Error: Permission denied - {str(e)}"
        except Exception as e:
            logger.error(
                "Command execution failed",
                extra={"command": command[:100], "error": str(e)},
            )
            return f"Error: {str(e)}"
