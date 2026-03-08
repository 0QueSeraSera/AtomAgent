"""E2E test: Agent uses BashTool to get git logs and save to file."""

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
        blocked_commands=["rm -rf", "sudo", "mkfs"],  # Block dangerous commands
    ))

    print("=" * 60)
    print("E2E Test: Git Logs to File")
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
        "Please get all git commit logs from the repository at "
        "'/Users/alive/workspace/OSS_contribute/AtomAgent-Workspace/atomAgent-worktree-feat-fetch-bash-tools' "
        "and save them to a file named 'git_commits.txt' in the current directory. "
        "Include the commit hash, author, date, and message for each commit."
    )

    print(f"Instruction: {instruction}")
    print("-" * 60)

    # Process the instruction
    try:
        result = await agent.process_direct(
            content=instruction,
            session_key="cli:e2e-git-test",
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
    output_file = workspace / "git_commits.txt"
    if output_file.exists():
        print()
        print("=" * 60)
        print("✅ SUCCESS: File was created!")
        print(f"   File: {output_file.absolute()}")
        print(f"   Size: {output_file.stat().st_size} bytes")
        print(f"   Content:")
        print("-" * 40)
        print(output_file.read_text())
        print("-" * 40)
    else:
        print()
        print("❌ FAILED: File was not created")


if __name__ == "__main__":
    asyncio.run(main())
