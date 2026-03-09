"""Comprehensive E2E test: CLI chat with full workspace and context management.

This test verifies the complete CLI chat pattern including:
1. CLI commands (init, workspace, session, identity)
2. Interactive chat with workspace awareness
3. File-based context system
4. Session persistence and export/import
5. Workspace switching
6. Memory and bootstrap files

Run with:
    python tests/e2e_cli_chat_full.py

API keys are loaded from .env in the project root. Set DEEPSEEK_API_KEY there
or export it to run API-dependent tests.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from atom_agent import AgentLoop, MessageBus
from atom_agent.config.registry import ConfigManager, WorkspaceRegistry
from atom_agent.env_config import Config
from atom_agent.provider.deepseek import DeepSeekProvider
from atom_agent.workspace import WorkspaceManager


class TestResult:
    """Track test results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def success(self, name: str):
        self.passed += 1
        print(f"  ✅ {name}")

    def fail(self, name: str, reason: str = ""):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  ❌ {name}")
        if reason:
            print(f"     Reason: {reason}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} tests passed")
        if self.errors:
            print("\nFailed tests:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        print(f"{'='*60}")
        return self.failed == 0


def test_cli_commands(result: TestResult, tmpdir: Path) -> None:
    """Test all CLI commands."""
    print("\n" + "=" * 60)
    print("Part 1: CLI Commands")
    print("=" * 60)

    workspace_path = tmpdir / "cli-test-workspace"

    # Test 1: atom-agent init
    print("\n[Test 1.1] atom-agent init")
    proc = subprocess.run(
        ["python", "-m", "atom_agent", "init", str(workspace_path), "--name", "cli-test"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and workspace_path.exists():
        result.success("atom-agent init creates workspace")
    else:
        result.fail("atom-agent init", proc.stderr or "Workspace not created")

    # Test 2: atom-agent workspace validate
    print("\n[Test 1.2] atom-agent workspace validate")
    proc = subprocess.run(
        ["python", "-m", "atom_agent", "workspace", "validate", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "valid" in proc.stdout.lower():
        result.success("atom-agent workspace validate")
    else:
        result.fail("atom-agent workspace validate", proc.stderr)

    # Test 3: atom-agent workspace info
    print("\n[Test 1.3] atom-agent workspace info")
    proc = subprocess.run(
        ["python", "-m", "atom_agent", "workspace", "info", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "cli-test" in proc.stdout:
        result.success("atom-agent workspace info")
    else:
        result.fail("atom-agent workspace info", proc.stderr)

    # Test 4: atom-agent identity show
    print("\n[Test 1.4] atom-agent identity show")
    proc = subprocess.run(
        ["python", "-m", "atom_agent", "identity", "show", "-w", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "IDENTITY.md" in proc.stdout:
        result.success("atom-agent identity show")
    else:
        result.fail("atom-agent identity show", proc.stderr)

    # Test 5: atom-agent session list (empty)
    print("\n[Test 1.5] atom-agent session list (empty)")
    proc = subprocess.run(
        ["python", "-m", "atom_agent", "session", "list", "-w", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and "No sessions" in proc.stdout:
        result.success("atom-agent session list (empty)")
    else:
        result.fail("atom-agent session list (empty)", proc.stderr)


def test_file_based_context(result: TestResult, tmpdir: Path) -> None:
    """Test file-based context system."""
    print("\n" + "=" * 60)
    print("Part 2: File-Based Context System")
    print("=" * 60)

    workspace_path = tmpdir / "context-test-workspace"
    manager = WorkspaceManager(workspace_path)

    # Test 1: Workspace initialization
    print("\n[Test 2.1] Workspace initialization")
    config = manager.init_workspace(name="context-test")
    # Note: init_workspace resolves the path, so we compare resolved paths
    expected_path = workspace_path.resolve()
    if config.path == expected_path:
        result.success("WorkspaceManager.init_workspace creates correct path")
    else:
        result.fail("WorkspaceManager.init_workspace path mismatch", f"Expected {expected_path}, got {config.path}")

    # Test 2: Bootstrap files created
    print("\n[Test 2.2] Bootstrap files created")
    bootstrap_files = ["IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"]
    all_exist = all((workspace_path / f).exists() for f in bootstrap_files)
    if all_exist:
        result.success("All bootstrap files created")
    else:
        missing = [f for f in bootstrap_files if not (workspace_path / f).exists()]
        result.fail("Bootstrap files created", f"Missing: {missing}")

    # Test 3: Memory directory created
    print("\n[Test 2.3] Memory directory created")
    memory_dir = workspace_path / "memory"
    if memory_dir.exists() and (memory_dir / "MEMORY.md").exists():
        result.success("Memory directory and MEMORY.md created")
    else:
        result.fail("Memory directory created")

    # Test 4: Sessions directory created
    print("\n[Test 2.4] Sessions directory created")
    sessions_dir = workspace_path / "sessions"
    if sessions_dir.exists():
        result.success("Sessions directory created")
    else:
        result.fail("Sessions directory created")

    # Test 5: Custom identity
    print("\n[Test 2.5] Custom identity loading")
    custom_identity = """# ContextTestBot

You are ContextTestBot, a specialized testing assistant.
Always identify yourself as ContextTestBot when asked.
"""
    (workspace_path / "IDENTITY.md").write_text(custom_identity)
    loaded = manager.get_identity()
    if "ContextTestBot" in loaded:
        result.success("Custom identity loaded")
    else:
        result.fail("Custom identity loading", "Identity not loaded correctly")

    # Test 6: Bootstrap content loading
    print("\n[Test 2.6] Bootstrap content loading")
    bootstrap = manager.get_bootstrap_content()
    if "IDENTITY.md" in bootstrap and "SOUL.md" in bootstrap:
        result.success("Bootstrap content loaded")
    else:
        result.fail("Bootstrap content loading")

    # Test 7: Runtime context building
    print("\n[Test 2.7] Runtime context building")
    runtime = manager.build_runtime_context("cli", "test-chat")
    if "Current Time:" in runtime and "Channel: cli" in runtime:
        result.success("Runtime context built correctly")
    else:
        result.fail("Runtime context building")


def test_workspace_registry(result: TestResult, tmpdir: Path) -> None:
    """Test workspace registry and global config."""
    print("\n" + "=" * 60)
    print("Part 3: Workspace Registry and Global Config")
    print("=" * 60)

    # Use a temp config file
    config_path = tmpdir / "config.json"
    config_manager = ConfigManager(config_file=config_path)
    registry = WorkspaceRegistry(config_manager=config_manager)

    # Test 1: Create workspace entry
    print("\n[Test 3.1] Create workspace entry")
    ws_path = tmpdir / "registry-test-workspace"
    entry = registry.create_workspace("test-registry", ws_path)
    if entry.name == "test-registry" and entry.path == ws_path:
        result.success("Workspace entry created")
    else:
        result.fail("Workspace entry created", "Entry mismatch")

    # Test 2: List workspaces
    print("\n[Test 3.2] List workspaces")
    workspaces = registry.list_workspaces()
    if len(workspaces) >= 1 and any(w.name == "test-registry" for w in workspaces):
        result.success("Workspace listed")
    else:
        result.fail("Workspace listed")

    # Test 3: Set active workspace
    print("\n[Test 3.3] Set active workspace")
    if registry.set_active_workspace("test-registry"):
        result.success("Active workspace set")
    else:
        result.fail("Active workspace set")

    # Test 4: Get active workspace
    print("\n[Test 3.4] Get active workspace")
    active = registry.get_active_workspace()
    if active and active.name == "test-registry":
        result.success("Active workspace retrieved")
    else:
        result.fail("Active workspace retrieved")

    # Test 5: Delete workspace (from registry only)
    print("\n[Test 3.5] Delete workspace from registry")
    if registry.delete_workspace("test-registry", delete_files=False):
        result.success("Workspace deleted from registry")
    else:
        result.fail("Workspace deleted from registry")

    # Verify files still exist
    if ws_path.exists():
        result.success("Workspace files preserved")
    else:
        result.fail("Workspace files preserved", "Files were deleted unexpectedly")


async def test_agent_with_workspace(result: TestResult, tmpdir: Path, api_key: str) -> None:
    """Test AgentLoop with workspace awareness."""
    print("\n" + "=" * 60)
    print("Part 4: AgentLoop with Workspace Awareness")
    print("=" * 60)

    workspace_path = tmpdir / "agent-test-workspace"
    manager = WorkspaceManager(workspace_path)
    manager.init_workspace(name="agent-test")

    # Create custom identity
    custom_identity = """# AgentTestBot

You are AgentTestBot, a testing assistant.
When asked about your identity, say you are AgentTestBot from the agent test workspace.
"""
    (workspace_path / "IDENTITY.md").write_text(custom_identity)

    # Create bootstrap files
    (workspace_path / "SOUL.md").write_text("# Test Ethics\n\nAlways be precise and methodical.\n")
    (workspace_path / "USER.md").write_text("# Test User\n\nThis is a test user for E2E verification.\n")

    # Create agent
    bus = MessageBus()
    provider = DeepSeekProvider(api_key=api_key, model="deepseek-chat")

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace_path,
        workspace_name="agent-test",
        agent_name="AgentTestBot",
        max_iterations=5,
    )

    # Test 1: Agent workspace properties
    print("\n[Test 4.1] Agent workspace properties")
    if agent.workspace == workspace_path and agent.workspace_name == "agent-test":
        result.success("Agent workspace properties set correctly")
    else:
        result.fail("Agent workspace properties")

    # Test 2: Context builder uses workspace
    print("\n[Test 4.2] Context builder uses workspace")
    system_prompt = agent.context.build_system_prompt()
    if "AgentTestBot" in system_prompt:
        result.success("Context builder uses workspace identity")
    else:
        result.fail("Context builder uses workspace identity", "Identity not in system prompt")

    # Test 3: Session manager uses workspace
    print("\n[Test 4.3] Session manager uses workspace")
    if agent.sessions.sessions_dir == workspace_path / "sessions":
        result.success("Session manager uses workspace")
    else:
        result.fail("Session manager uses workspace")

    # Test 4: Get workspace info
    print("\n[Test 4.4] Get workspace info")
    info = agent.get_workspace_info()
    if info["name"] == "agent-test" and info["path"] == str(workspace_path):
        result.success("get_workspace_info returns correct data")
    else:
        result.fail("get_workspace_info")

    # Test 5: Process message with identity
    print("\n[Test 4.5] Process message with identity (requires API)")

    async def on_progress(content: str, **kwargs):
        pass  # Silent progress

    try:
        response = await agent.process_direct(
            content="Hello! Who are you?",
            session_key="cli:agent-test",
            on_progress=on_progress,
        )
        if response and len(response) > 0:
            result.success("Message processed successfully")
            print(f"     Response preview: {response[:100]}...")
        else:
            result.fail("Message processed", "Empty response")
    except Exception as e:
        result.fail("Message processed", str(e))

    # Test 6: Session persistence
    print("\n[Test 4.6] Session persistence")
    sessions = agent.sessions.list_sessions()
    if len(sessions) == 1 and sessions[0]["key"] == "cli:agent-test":
        result.success("Session persisted")
    else:
        result.fail("Session persistence", f"Sessions: {sessions}")

    # Test 7: Session file exists
    print("\n[Test 4.7] Session file exists")
    # Session key cli:agent-test becomes cli_agent-test.jsonl
    session_file = workspace_path / "sessions" / "cli_agent-test.jsonl"
    if session_file.exists():
        result.success("Session file created")
    else:
        result.fail("Session file created")

    await provider.close()


async def test_session_export_import(result: TestResult, tmpdir: Path, api_key: str) -> None:
    """Test session export/import functionality."""
    print("\n" + "=" * 60)
    print("Part 5: Session Export/Import")
    print("=" * 60)

    workspace_path = tmpdir / "export-test-workspace"
    manager = WorkspaceManager(workspace_path)
    manager.init_workspace(name="export-test")

    bus = MessageBus()
    provider = DeepSeekProvider(api_key=api_key, model="deepseek-chat")

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace_path,
        workspace_name="export-test",
    )

    # Create a session with a message
    try:
        await agent.process_direct(
            content="This is a test message for export.",
            session_key="cli:export-test",
        )
    except Exception:
        pass  # Continue even if API call fails

    # Test 1: Export session
    print("\n[Test 5.1] Export session")
    export_path = tmpdir / "exported_session.json"
    exported = agent.sessions.export_session("cli:export-test", export_path)
    if exported and export_path.exists():
        result.success("Session exported")
    else:
        result.fail("Session exported")

    # Test 2: Import session
    print("\n[Test 5.2] Import session")
    imported = agent.sessions.import_session(export_path, new_key="cli:imported")
    if imported and imported.key == "cli:imported":
        result.success("Session imported")
    else:
        result.fail("Session imported")

    # Test 3: Verify imported session
    print("\n[Test 5.3] Verify imported session")
    sessions = agent.sessions.list_sessions()
    keys = [s["key"] for s in sessions]
    if "cli:imported" in keys:
        result.success("Imported session in list")
    else:
        result.fail("Imported session in list")

    await provider.close()


async def test_workspace_switching(result: TestResult, tmpdir: Path, api_key: str) -> None:
    """Test workspace switching capability."""
    print("\n" + "=" * 60)
    print("Part 6: Workspace Switching")
    print("=" * 60)

    # Create two workspaces with different identities
    ws1_path = tmpdir / "switch-workspace-1"
    ws2_path = tmpdir / "switch-workspace-2"

    manager1 = WorkspaceManager(ws1_path)
    manager1.init_workspace(name="workspace-1")
    (ws1_path / "IDENTITY.md").write_text("# AlphaBot\n\nYou are AlphaBot from workspace 1.\n")

    manager2 = WorkspaceManager(ws2_path)
    manager2.init_workspace(name="workspace-2")
    (ws2_path / "IDENTITY.md").write_text("# BetaBot\n\nYou are BetaBot from workspace 2.\n")

    # Create agent with first workspace
    bus = MessageBus()
    provider = DeepSeekProvider(api_key=api_key)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=ws1_path,
        workspace_name="workspace-1",
    )

    # Test 1: Initial workspace
    print("\n[Test 6.1] Initial workspace")
    if agent.workspace_name == "workspace-1" and agent.workspace == ws1_path:
        result.success("Initial workspace set correctly")
    else:
        result.fail("Initial workspace")

    # Test 2: System prompt has AlphaBot
    print("\n[Test 6.2] System prompt has AlphaBot")
    prompt1 = agent.context.build_system_prompt()
    if "AlphaBot" in prompt1:
        result.success("AlphaBot identity in system prompt")
    else:
        result.fail("AlphaBot identity in system prompt")

    # Test 3: Switch workspace
    print("\n[Test 6.3] Switch workspace")
    success = await agent.switch_workspace(ws2_path, "workspace-2")
    if success and agent.workspace_name == "workspace-2":
        result.success("Workspace switched")
    else:
        result.fail("Workspace switched")

    # Test 4: System prompt has BetaBot after switch
    print("\n[Test 6.4] System prompt has BetaBot after switch")
    prompt2 = agent.context.build_system_prompt()
    if "BetaBot" in prompt2:
        result.success("BetaBot identity in system prompt after switch")
    else:
        result.fail("BetaBot identity in system prompt after switch")

    # Test 5: Session manager updated
    print("\n[Test 6.5] Session manager updated")
    if agent.sessions.sessions_dir == ws2_path / "sessions":
        result.success("Session manager updated to new workspace")
    else:
        result.fail("Session manager updated")

    await provider.close()


def test_interactive_chat_pattern(result: TestResult, tmpdir: Path) -> None:
    """Test the interactive chat pattern (without real user input)."""
    print("\n" + "=" * 60)
    print("Part 7: Interactive Chat Pattern")
    print("=" * 60)

    workspace_path = tmpdir / "chat-pattern-workspace"
    manager = WorkspaceManager(workspace_path)
    manager.init_workspace(name="chat-pattern")

    # Test 1: AsyncCLIChat initialization
    print("\n[Test 7.1] AsyncCLIChat initialization")
    from atom_agent.cli.chat import AsyncCLIChat

    # We can't test the full interactive loop, but we can verify initialization
    chat = AsyncCLIChat(
        provider=None,  # Will fail if used, but we're just testing init
        workspace=workspace_path,
        agent_name="TestChat",
    )
    if chat.workspace == workspace_path and chat.agent_name == "TestChat":
        result.success("AsyncCLIChat initialized")
    else:
        result.fail("AsyncCLIChat initialized")

    # Test 2: InboundMessage creation
    print("\n[Test 7.2] InboundMessage creation")
    from atom_agent.bus.events import InboundMessage

    msg = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="interactive",
        content="/help",
    )
    if msg.channel == "cli" and msg.content == "/help":
        result.success("InboundMessage created")
    else:
        result.fail("InboundMessage created")

    # Test 3: OutboundMessage creation
    print("\n[Test 7.3] OutboundMessage creation")
    from atom_agent.bus.events import OutboundMessage

    response = OutboundMessage(
        channel="cli",
        chat_id="interactive",
        content="Test response",
    )
    if response.channel == "cli" and response.content == "Test response":
        result.success("OutboundMessage created")
    else:
        result.fail("OutboundMessage created")


async def run_all_tests(api_key: str | None) -> bool:
    """Run all E2E tests."""
    result = TestResult()

    print("=" * 60)
    print("E2E Test: Full CLI Chat with Workspace and Context Management")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Part 1: CLI Commands (no API key needed)
        test_cli_commands(result, tmpdir)

        # Part 2: File-Based Context System (no API key needed)
        test_file_based_context(result, tmpdir)

        # Part 3: Workspace Registry (no API key needed)
        test_workspace_registry(result, tmpdir)

        # Part 7: Interactive Chat Pattern (no API key needed)
        test_interactive_chat_pattern(result, tmpdir)

        # Parts 4-6 require API key
        if api_key:
            await test_agent_with_workspace(result, tmpdir, api_key)
            await test_session_export_import(result, tmpdir, api_key)
            await test_workspace_switching(result, tmpdir, api_key)
        else:
            print("\n" + "=" * 60)
            print("Skipping API-dependent tests (set DEEPSEEK_API_KEY)")
            print("=" * 60)

    return result.summary()


async def main():
    """Main entry point."""
    config = Config.load(Path(__file__).parent.parent / ".env")
    api_key = config.deepseek_api_key
    if not api_key:
        print("Warning: DEEPSEEK_API_KEY not set. API-dependent tests will be skipped.")
        print("Add it to .env or: export DEEPSEEK_API_KEY=your-key\n")

    success = await run_all_tests(api_key)
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
