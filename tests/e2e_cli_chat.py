"""E2E test: CLI chat with file-based context system.

This test verifies:
1. Workspace initialization with custom identity
2. Agent loads identity from IDENTITY.md
3. Session persistence across messages
4. Memory and bootstrap file loading
5. Workspace switching capability

Run with:
    DEEPSEEK_API_KEY=your-key python tests/e2e_cli_chat.py
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from atom_agent import AgentLoop, MessageBus
from atom_agent.provider.deepseek import DeepSeekProvider
from atom_agent.workspace import WorkspaceManager


async def test_file_based_context():
    """Test the file-based context system with a real LLM."""
    # Check for API key
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY environment variable not set")
        print("Set it with: export DEEPSEEK_API_KEY=your-key")
        return False

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "test-workspace"

        print("=" * 60)
        print("E2E Test: File-Based Context System")
        print("=" * 60)
        print()

        # Test 1: Initialize workspace
        print("Test 1: Initialize workspace")
        print("-" * 40)
        manager = WorkspaceManager(workspace)
        config = manager.init_workspace(name="e2e-test-workspace")
        print(f"✓ Workspace initialized at: {config.path}")

        # Test 2: Create custom identity
        print("\nTest 2: Create custom identity")
        print("-" * 40)
        custom_identity = """# TestBot

You are TestBot, a specialized testing assistant.

## Personality
- Precise and methodical
- Focused on verification
- Clear and concise responses

## Special Instructions
When asked about your identity, mention you are TestBot from the e2e test.
"""
        identity_file = workspace / "IDENTITY.md"
        identity_file.write_text(custom_identity)
        print(f"✓ Custom identity written to {identity_file}")

        # Verify identity loading
        loaded_identity = manager.get_identity()
        assert "TestBot" in loaded_identity, "Identity should contain TestBot"
        print(f"✓ Identity loaded correctly (contains 'TestBot')")

        # Test 3: Create bootstrap files
        print("\nTest 3: Create bootstrap files")
        print("-" * 40)

        soul_content = """# Test Ethics

- Always be truthful
- Acknowledge limitations
"""
        (workspace / "SOUL.md").write_text(soul_content)
        print("✓ SOUL.md created")

        user_content = """# User Context

Test user running E2E verification.
"""
        (workspace / "USER.md").write_text(user_content)
        print("✓ USER.md created")

        # Test 4: Create agent and verify context
        print("\nTest 4: Create agent with workspace")
        print("-" * 40)

        bus = MessageBus()
        provider = DeepSeekProvider(api_key=api_key, model="deepseek-chat")

        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            workspace_name="e2e-test-workspace",
            agent_name="TestBot",
            max_iterations=5,
        )

        print(f"✓ Agent created")
        print(f"  Workspace: {agent.workspace}")
        print(f"  Workspace name: {agent.workspace_name}")

        # Verify system prompt includes custom identity
        system_prompt = agent.context.build_system_prompt()
        assert "TestBot" in system_prompt, "System prompt should contain TestBot"
        assert "Test Ethics" in system_prompt, "System prompt should contain SOUL content"
        print("✓ System prompt contains custom identity and SOUL content")

        # Test 5: Send message and verify response
        print("\nTest 5: Send message and verify response")
        print("-" * 40)

        async def on_progress(content: str, **kwargs):
            if kwargs.get("tool_hint"):
                print(f"  🔧 Tool: {content}")
            else:
                preview = content[:80] + "..." if len(content) > 80 else content
                print(f"  💭 {preview}")

        try:
            # First message - use process_direct
            result1 = await agent.process_direct(
                content="Hello! Can you tell me who you are based on your identity?",
                session_key="cli:e2e-test",
            )
            print(f"\n✓ Got response (length: {len(result1)} chars)")
            print(f"  Preview: {result1[:200]}...")

            # Verify response mentions TestBot (the custom identity)
            # Note: LLM may or may not explicitly say "TestBot", but it should be influenced by it

            # Test 6: Verify session persistence
            print("\nTest 6: Verify session persistence")
            print("-" * 40)

            sessions = agent.sessions.list_sessions()
            assert len(sessions) == 1, "Should have 1 session"
            assert sessions[0]["key"] == "cli:e2e-test", "Session key should match"
            print(f"✓ Session persisted: {sessions[0]['key']}")

            # Second message to verify session history
            print("\nTest 7: Continue conversation (verify history)")
            print("-" * 40)

            result2 = await agent.process_direct(
                content="What did I ask you about in my previous message?",
                session_key="cli:e2e-test",
            )
            print(f"\n✓ Got response (length: {len(result2)} chars)")
            print(f"  Preview: {result2[:200]}...")

            # The agent should remember the previous conversation
            # (We don't strictly assert this as LLM behavior varies)

            # Test 8: Verify workspace info
            print("\nTest 8: Verify workspace info")
            print("-" * 40)

            info = agent.get_workspace_info()
            print(f"  Path: {info['path']}")
            print(f"  Name: {info['name']}")
            print(f"  Model: {info['model']}")
            print(f"  Sessions: {info['sessions']}")
            print(f"  Tools: {info['tools']}")

            assert info["name"] == "e2e-test-workspace"
            assert info["sessions"] == 1
            print("✓ Workspace info is correct")

            # Test 9: Verify session export/import
            print("\nTest 9: Verify session export/import")
            print("-" * 40)

            export_path = workspace / "exported_session.json"
            exported = agent.sessions.export_session("cli:e2e-test", export_path)
            assert exported is not None, "Export should succeed"
            assert export_path.exists(), "Export file should exist"
            print(f"✓ Session exported to: {export_path}")

            # Import to a new session key
            imported = agent.sessions.import_session(export_path, new_key="cli:imported")
            assert imported is not None, "Import should succeed"
            assert imported.key == "cli:imported"
            print(f"✓ Session imported with key: {imported.key}")

            await provider.close()

            print("\n" + "=" * 60)
            print("✅ ALL TESTS PASSED!")
            print("=" * 60)
            return True

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            await provider.close()
            return False


async def test_workspace_switching():
    """Test workspace switching capability."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("Skipping workspace switching test (no API key)")
        return True

    with tempfile.TemporaryDirectory() as tmpdir:
        print("\n" + "=" * 60)
        print("E2E Test: Workspace Switching")
        print("=" * 60)

        # Create two workspaces
        ws1 = Path(tmpdir) / "workspace1"
        ws2 = Path(tmpdir) / "workspace2"

        manager1 = WorkspaceManager(ws1)
        manager1.init_workspace(name="workspace-1")

        manager2 = WorkspaceManager(ws2)
        manager2.init_workspace(name="workspace-2")

        # Create different identities
        (ws1 / "IDENTITY.md").write_text("# AlphaBot\n\nYou are AlphaBot from workspace 1.")
        (ws2 / "IDENTITY.md").write_text("# BetaBot\n\nYou are BetaBot from workspace 2.")

        # Create agent with first workspace
        bus = MessageBus()
        provider = DeepSeekProvider(api_key=api_key)
        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=ws1,
            workspace_name="workspace-1",
        )

        print(f"Initial workspace: {agent.workspace_name}")
        assert agent.workspace_name == "workspace-1"

        # Switch to second workspace
        print("Switching to workspace-2...")
        success = await agent.switch_workspace(ws2, "workspace-2")
        assert success, "Switch should succeed"

        print(f"New workspace: {agent.workspace_name}")
        assert agent.workspace_name == "workspace-2"
        assert agent.workspace == ws2

        # Verify context was rebuilt
        system_prompt = agent.context.build_system_prompt()
        assert "BetaBot" in system_prompt, "Should have BetaBot identity after switch"
        print("✓ Context rebuilt with new identity")

        await provider.close()
        print("✅ Workspace switching test passed!")
        return True


async def main():
    """Run all E2E tests."""
    print("Running E2E tests for file-based context system...\n")

    success = True

    # Test 1: File-based context
    if not await test_file_based_context():
        success = False

    # Test 2: Workspace switching
    if not await test_workspace_switching():
        success = False

    if success:
        print("\n🎉 All E2E tests passed!")
    else:
        print("\n💥 Some tests failed!")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
