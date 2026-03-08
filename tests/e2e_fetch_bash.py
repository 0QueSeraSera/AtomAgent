"""E2E test: Agent uses FetchTool and BashTool to fetch URL and save to file."""

import asyncio
import os
from pathlib import Path

from atom_agent import AgentLoop, MessageBus
from atom_agent.provider.deepseek import DeepSeekProvider
from atom_agent.tools.bash import BashTool
from atom_agent.tools.fetch import FetchTool


async def main():
    """Run E2E test with real LLM."""
    # Check for API key
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY environment variable not set")
        return

    # Setup workspace
    workspace = Path("./workspace_e2e")
    workspace.mkdir(exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "sessions").mkdir(exist_ok=True)

    # Create message bus and provider
    bus = MessageBus()
    provider = DeepSeekProvider(api_key=api_key, model="deepseek-chat")

    # Create agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        agent_name="E2ETestAgent",
        max_iterations=10,
    )

    # Register the new tools
    agent.register_tool(FetchTool(default_timeout=30.0))
    agent.register_tool(BashTool(
        default_timeout=30.0,
        blocked_commands=["rm", "sudo", "mkfs"],  # Block dangerous commands
    ))

    print("=" * 60)
    print("E2E Test: Fetch URL and Save to File")
    print("=" * 60)
    print(f"Tools available: {agent.tools.tool_names}")
    print()

    # Define progress callback
    async def on_progress(content: str, **kwargs):
        if kwargs.get("tool_hint"):
            print(f"  🔧 Tool: {content}")
        else:
            print(f"  💭 {content[:100]}..." if len(content) > 100 else f"  💭 {content}")

    # Test instruction
    instruction = (
        "Please fetch the content from https://chat.deepseek.com/ "
        "and save it to a local file named 'deepseek_page.html' in the current directory. "
        "After saving, confirm the file was created."
    )

    print(f"Instruction: {instruction}")
    print("-" * 60)

    # Process the instruction
    try:
        result = await agent.process_direct(
            content=instruction,
            session_key="cli:e2e-test",
            on_progress=on_progress,
        )
        print("-" * 60)
        print(f"Result:\n{result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await provider.close()

    # Verify the file was created (in workspace directory)
    output_file = workspace / "deepseek_page.html"
    if output_file.exists():
        print()
        print("=" * 60)
        print("✅ SUCCESS: File was created!")
        print(f"   File: {output_file.absolute()}")
        print(f"   Size: {output_file.stat().st_size} bytes")
        print(f"   First 500 chars:")
        print("-" * 40)
        print(output_file.read_text()[:500])
        print("-" * 40)
        # Cleanup
        output_file.unlink()
    else:
        print()
        print("❌ FAILED: File was not created")


if __name__ == "__main__":
    asyncio.run(main())
