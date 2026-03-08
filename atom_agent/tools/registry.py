"""Tool registry for dynamic tool management."""

from typing import Any

from atom_agent.logging import get_logger
from atom_agent.tools.base import Tool

logger = get_logger("tools.registry")


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        params = list(tool.parameters.get("properties", {}).keys()) if tool.parameters else []
        desc = tool.description
        if len(desc) > 80:
            desc = desc[:80] + "..."
        logger.info(
            "Tool registered",
            extra={
                "tool_name": tool.name,
                "description": desc,
                "params": params,
            },
        )

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        if name in self._tools:
            self._tools.pop(name)
            logger.debug("Tool unregistered", extra={"tool_name": name})

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name with given parameters."""
        _HINT = "\n\n[Analyze the error above and try a different approach.]"

        tool = self._tools.get(name)
        if not tool:
            logger.warning(
                "Tool not found", extra={"tool_name": name, "available": self.tool_names}
            )
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            # Attempt to cast parameters to match schema types
            params = tool.cast_params(params)

            # Validate parameters
            errors = tool.validate_params(params)
            if errors:
                logger.warning(
                    "Tool validation failed",
                    extra={"tool_name": name, "errors": errors},
                )
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + _HINT
            result = await tool.execute(**params)
            if isinstance(result, str) and result.startswith("Error"):
                logger.warning(
                    "Tool returned error",
                    extra={"tool_name": name, "error": result[:100]},
                )
                return result + _HINT
            return result
        except Exception as e:
            logger.error(
                "Tool execution failed",
                extra={"tool_name": name, "error": str(e)},
            )
            return f"Error executing {name}: {str(e)}" + _HINT

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
