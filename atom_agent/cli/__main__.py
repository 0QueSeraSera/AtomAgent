"""
CLI entry point for AtomAgent.

Usage:
    python -m atom_agent [options]
    python -m atom_agent.cli [options]

    # Workspace management
    atom-agent init [path]           Initialize a new workspace
    atom-agent identity show         Display current identity
    atom-agent workspace validate    Check workspace health
    atom-agent workspace list        List all workspaces with session counts
    atom-agent workspace overview    Workspace/session overview table
    atom-agent workspace switch <name> Switch active workspace
    atom-agent workspace create <name> Create new workspace
    atom-agent proactive validate    Validate PROACTIVE.md configuration
    atom-agent proactive show        Show normalized proactive task summary
    atom-agent gateway run          Run gateway host runtime
    atom-agent gateway run --once   Start/stop gateway once for readiness checks
    atom-agent daemon run --once    Run one proactive daemon cycle
    atom-agent daemon run           Run daemon polling loop

    # Session management
    atom-agent session list          List sessions in current workspace
    atom-agent session export <key>  Export session to file
    atom-agent session import <file> Import session from file

Configuration:
    Settings are loaded from .env file in the current directory (or parent dirs).
    Environment variables take precedence over .env file values.

    DEEPSEEK_API_KEY - API key for DeepSeek provider
    OPENAI_API_KEY   - API key for OpenAI provider (future use)
    ANTHROPIC_API_KEY - API key for Anthropic provider (future use)
    ATOMAGENT_WORKSPACE - Workspace directory (active workspace by default)
    ATOM_WORKSPACE   - Legacy workspace env var (still supported)
    ATOM_MODEL       - Model to use (default: provider default)
    ATOM_DEBUG       - Enable debug logging (1, true, yes)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from atom_agent.env_config import Config
from atom_agent.logging import LoggingConfig, get_logger, setup_logging

logger = get_logger("cli.main")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="atom-agent",
        description="Interactive CLI chat with AtomAgent",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Main chat command (default when no subcommand)
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
        help="Workspace directory (default: active workspace in ~/.atom-agents)",
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
        help="Enable DEBUG level logging (full content)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Use JSON log format (for machine parsing)",
    )

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize a new workspace")
    init_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Workspace path (default: active workspace in ~/.atom-agents)",
    )
    init_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing files",
    )
    init_parser.add_argument(
        "--name",
        "-n",
        default="default",
        help="Name for the workspace",
    )

    # identity subcommand
    identity_parser = subparsers.add_parser("identity", help="Manage agent identity")
    identity_parser.add_argument(
        "action",
        choices=["show"],
        help="Action to perform",
    )
    identity_parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory",
    )

    # workspace subcommand
    workspace_parser = subparsers.add_parser("workspace", help="Manage workspaces")
    workspace_parser.add_argument(
        "action",
        choices=["validate", "list", "overview", "info", "switch", "create", "delete"],
        help="Action to perform",
    )
    workspace_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Workspace name (for switch/create/delete)",
    )
    workspace_parser.add_argument(
        "--path",
        "-p",
        type=Path,
        default=None,
        help="Path for new workspace (for create)",
    )
    workspace_parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Also delete workspace files (for delete)",
    )

    # proactive subcommand
    proactive_parser = subparsers.add_parser("proactive", help="Manage proactive configuration")
    proactive_parser.add_argument(
        "action",
        choices=["validate", "show"],
        help="Action to perform",
    )
    proactive_parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory",
    )

    # gateway subcommand
    gateway_parser = subparsers.add_parser("gateway", help="Run gateway host runtime")
    gateway_parser.add_argument(
        "action",
        choices=["run"],
        nargs="?",
        default="run",
        help="Action to perform",
    )
    gateway_parser.add_argument(
        "--once",
        action="store_true",
        help="Start and stop gateway once after readiness checks",
    )
    gateway_parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory",
    )
    gateway_parser.add_argument(
        "--channel",
        action="append",
        choices=["feishu"],
        default=[],
        help="Enabled channel adapter (repeatable, default: feishu)",
    )
    gateway_parser.add_argument(
        "--feishu-app-id",
        type=str,
        default=None,
        help="Feishu app id (fallback: FEISHU_APP_ID)",
    )
    gateway_parser.add_argument(
        "--feishu-app-secret",
        type=str,
        default=None,
        help="Feishu app secret (fallback: FEISHU_APP_SECRET)",
    )
    gateway_parser.add_argument(
        "--feishu-verification-token",
        type=str,
        default=None,
        help="Feishu webhook verification token (fallback: FEISHU_VERIFICATION_TOKEN)",
    )
    gateway_parser.add_argument(
        "--feishu-signing-secret",
        type=str,
        default=None,
        help="Feishu webhook signing secret (fallback: FEISHU_SIGNING_SECRET)",
    )
    gateway_parser.add_argument(
        "--feishu-allow-user",
        action="append",
        default=[],
        help="Allowlisted Feishu sender open_id/user_id (repeatable)",
    )
    gateway_parser.add_argument(
        "--feishu-deny-group",
        action="store_true",
        help="Only allow p2p chat messages from Feishu",
    )

    # daemon subcommand
    daemon_parser = subparsers.add_parser("daemon", help="Run proactive daemon service")
    daemon_parser.add_argument(
        "action",
        choices=["run"],
        nargs="?",
        default="run",
        help="Action to perform",
    )
    daemon_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one daemon cycle and exit",
    )
    daemon_parser.add_argument(
        "--poll-sec",
        type=float,
        default=30.0,
        help="Polling interval in seconds for loop mode",
    )
    daemon_parser.add_argument(
        "--workspace-path",
        type=Path,
        default=None,
        help="Optional single workspace path override",
    )

    # session subcommand
    session_parser = subparsers.add_parser("session", help="Manage sessions")
    session_parser.add_argument(
        "action",
        choices=["list", "export", "import", "delete"],
        help="Action to perform",
    )
    session_parser.add_argument(
        "key_or_path",
        nargs="?",
        default=None,
        help="Session key (for export/delete) or file path (for import)",
    )
    session_parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory",
    )
    session_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file path (for export)",
    )
    session_parser.add_argument(
        "--new-key",
        type=str,
        default=None,
        help="New session key (for import)",
    )

    # tui subcommand
    tui_parser = subparsers.add_parser("tui", help="Interactive workspace/session manager")
    tui_parser.add_argument(
        "--once",
        action="store_true",
        help="Print dashboard once and exit",
    )
    tui_parser.add_argument(
        "--include-path",
        type=Path,
        action="append",
        default=[],
        help="Extra workspace path(s) to include in dashboard",
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


def _resolve_workspace_path(explicit: Path | None) -> Path:
    """Resolve workspace path with global-registry defaults."""
    if explicit:
        return explicit.expanduser()

    from atom_agent.config import ConfigManager

    return ConfigManager().get_active_workspace_path().expanduser()


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new workspace."""
    from atom_agent.workspace import WorkspaceManager

    path = _resolve_workspace_path(args.path)
    manager = WorkspaceManager(path)

    try:
        config = manager.init_workspace(path, force=args.force, name=args.name)
        print(f"✓ Workspace initialized at: {config.path}")
        print("\nCreated files:")
        print(f"  - {config.path}/IDENTITY.md  (agent identity)")
        print(f"  - {config.path}/SOUL.md      (values and ethics)")
        print(f"  - {config.path}/AGENTS.md    (technical guidelines)")
        print(f"  - {config.path}/USER.md      (user preferences)")
        print(f"  - {config.path}/TOOLS.md     (tool usage guidelines)")
        print(f"  - {config.path}/PROACTIVE.md (proactive task configuration)")
        print(f"  - {config.path}/memory/      (MEMORY.md, HISTORY.md)")
        print(f"  - {config.path}/sessions/    (conversation history)")
        return 0
    except Exception as e:
        print(f"Error: Failed to initialize workspace: {e}", file=sys.stderr)
        return 1


def cmd_identity(args: argparse.Namespace) -> int:
    """Manage agent identity."""
    from atom_agent.workspace import WorkspaceManager

    if args.action == "show":
        workspace = _resolve_workspace_path(args.workspace)
        manager = WorkspaceManager(workspace)

        if errors := manager.validate_workspace():
            print(f"Error: Invalid workspace: {errors[0]}", file=sys.stderr)
            return 1

        identity = manager.get_identity()
        print(f"=== Identity from {workspace}/IDENTITY.md ===\n")
        print(identity)
        return 0

    return 1


def cmd_workspace(args: argparse.Namespace) -> int:
    """Manage workspaces."""
    from atom_agent.cli.management import collect_workspace_snapshots, format_workspace_overview
    from atom_agent.config import ConfigManager, WorkspaceRegistry
    from atom_agent.workspace import WorkspaceManager

    if args.action == "validate":
        path = Path(args.name) if args.name else _resolve_workspace_path(None)
        manager = WorkspaceManager(path)

        errors = manager.validate_workspace()
        if errors:
            print(f"✗ Workspace validation failed for {path}:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print(f"✓ Workspace is valid: {path}")
            return 0

    elif args.action == "info":
        path = Path(args.name) if args.name else _resolve_workspace_path(None)
        manager = WorkspaceManager(path)

        errors = manager.validate_workspace()
        print(f"Workspace: {path}")
        print(f"Status: {'Valid' if not errors else 'Invalid'}")

        if errors:
            print("Errors:")
            for error in errors:
                print(f"  - {error}")

        # Show bootstrap files status
        print("\nBootstrap files:")
        for filename in ["IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"]:
            file_path = path / filename
            status = "✓" if file_path.exists() else "✗"
            print(f"  {status} {filename}")

        # Show sessions
        sessions = manager.list_sessions()
        print(f"\nSessions: {len(sessions)}")
        for session in sessions[:5]:  # Show max 5
            print(f"  - {session['key']}")

        return 0 if not errors else 1

    elif args.action in {"list", "overview"}:
        config_manager = ConfigManager()
        snapshots = collect_workspace_snapshots(config_manager)
        print(format_workspace_overview(snapshots))
        return 0

    elif args.action == "switch":
        if not args.name:
            print("Error: Workspace name required", file=sys.stderr)
            return 1

        config_manager = ConfigManager()
        if config_manager.set_active_workspace(args.name):
            print(f"✓ Switched to workspace: {args.name}")
            return 0
        else:
            print(f"Error: Workspace '{args.name}' not found", file=sys.stderr)
            return 1

    elif args.action == "create":
        if not args.name:
            print("Error: Workspace name required", file=sys.stderr)
            return 1

        registry = WorkspaceRegistry()
        try:
            entry = registry.create_workspace(args.name, args.path)
            print(f"✓ Created workspace: {entry.name}")
            print(f"  Path: {entry.path}")
            return 0
        except Exception as e:
            print(f"Error: Failed to create workspace: {e}", file=sys.stderr)
            return 1

    elif args.action == "delete":
        if not args.name:
            print("Error: Workspace name required", file=sys.stderr)
            return 1

        registry = WorkspaceRegistry()
        if registry.delete_workspace(args.name, delete_files=args.delete_files):
            print(f"✓ Deleted workspace: {args.name}")
            if args.delete_files:
                print("  (files also deleted)")
            return 0
        else:
            print(f"Error: Could not delete workspace '{args.name}'", file=sys.stderr)
            return 1

    return 1


def _proactive_schedule_label(task) -> str:
    if task.kind == "once":
        return f"once at {task.at.isoformat() if task.at else '<missing>'}"
    if task.kind == "cron":
        return f"cron {task.cron}"
    return f"every {task.every_sec}s"


def cmd_proactive(args: argparse.Namespace) -> int:
    """Manage proactive task configuration."""
    from atom_agent.proactive import ProactiveValidationError, parse_proactive_file

    workspace = _resolve_workspace_path(args.workspace)
    proactive_path = workspace / "PROACTIVE.md"

    if not proactive_path.exists():
        print(
            f"Error: Missing proactive config file: {proactive_path}\n"
            "Run `atom-agent init <workspace>` to create default workspace files.",
            file=sys.stderr,
        )
        return 1

    try:
        config = parse_proactive_file(proactive_path)
    except ProactiveValidationError as err:
        print(f"✗ PROACTIVE config invalid: {proactive_path}", file=sys.stderr)
        for issue in err.issues:
            print(f"  - [{issue.code}] {issue.path}: {issue.message}", file=sys.stderr)
        return 1

    if args.action == "validate":
        print(f"✓ PROACTIVE config is valid: {proactive_path}")
        print(f"  Version: {config.version}")
        print(f"  Enabled: {config.enabled}")
        print(f"  Timezone: {config.timezone}")
        print(f"  Tasks: {len(config.tasks)} total, {len(config.active_tasks)} enabled")
        return 0

    if args.action == "show":
        print(f"Workspace: {workspace}")
        print(f"Config: {proactive_path}")
        print(f"Enabled: {config.enabled}")
        print(f"Timezone: {config.timezone}")
        print(f"Tasks: {len(config.tasks)} total, {len(config.active_tasks)} enabled")
        if not config.tasks:
            print("\n(no tasks)")
            return 0

        print("\nTask Summary:")
        for task in config.tasks:
            status = "enabled" if task.enabled else "disabled"
            schedule = _proactive_schedule_label(task)
            jitter = f", jitter={task.jitter_sec}s" if task.jitter_sec else ""
            print(f"- {task.task_id} [{task.kind}] ({status})")
            print(f"  session_key: {task.session_key}")
            print(f"  schedule: {schedule}{jitter}")
        return 0

    return 1


def _resolve_feishu_config(args: argparse.Namespace):
    from atom_agent.channels import FeishuConfig

    env_cfg = FeishuConfig.from_env()

    allow_users = set(env_cfg.allow_user_ids)
    for value in args.feishu_allow_user or []:
        clean = value.strip()
        if clean:
            allow_users.add(clean)

    app_id = (args.feishu_app_id or env_cfg.app_id).strip()
    app_secret = (args.feishu_app_secret or env_cfg.app_secret).strip()
    verification_token = (
        (args.feishu_verification_token or env_cfg.verification_token or "").strip() or None
    )
    signing_secret = ((args.feishu_signing_secret or env_cfg.signing_secret or "").strip() or None)
    allow_group_chats = env_cfg.allow_group_chats and not args.feishu_deny_group

    dedup_cache_size_raw = os.environ.get("FEISHU_DEDUP_CACHE_SIZE")
    dedup_cache_size = env_cfg.dedup_cache_size
    if dedup_cache_size_raw:
        try:
            dedup_cache_size = int(dedup_cache_size_raw)
        except ValueError:
            dedup_cache_size = env_cfg.dedup_cache_size

    return FeishuConfig(
        app_id=app_id,
        app_secret=app_secret,
        verification_token=verification_token,
        signing_secret=signing_secret,
        allow_user_ids=allow_users,
        allow_group_chats=allow_group_chats,
        dedup_cache_size=dedup_cache_size,
    )


async def _run_gateway(runtime, *, once: bool) -> None:
    await runtime.start()
    try:
        if once:
            return
        await asyncio.Event().wait()
    finally:
        await runtime.stop()


def cmd_gateway(args: argparse.Namespace) -> int:
    """Run gateway runtime for channel integrations."""
    from atom_agent.channels import FeishuAdapter, FeishuConfigError
    from atom_agent.cli.management import ensure_workspace_initialized
    from atom_agent.gateway import GatewayRuntime

    config = Config.load(env_file=args.env_file)
    if args.debug:
        config.debug = True
    if args.model:
        config.model = args.model
    if args.workspace:
        config.workspace = args.workspace

    log_config = LoggingConfig(
        level="DEBUG" if args.debug else "INFO",
        format="json" if args.json else "text",
        output="file",
        log_content=args.debug,
    )
    setup_logging(log_config)

    errors = config.validate(args.provider)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        provider = get_provider(args.provider, config)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    workspace = _resolve_workspace_path(config.workspace)
    initialized, workspace_errors = ensure_workspace_initialized(workspace, name=workspace.name)
    if workspace_errors:
        print(f"Error: Invalid workspace: {workspace_errors[0]}", file=sys.stderr)
        return 1
    if initialized:
        print(f"ℹ Initialized workspace context files at: {workspace}")

    runtime = GatewayRuntime(
        provider=provider,
        workspace=workspace,
        workspace_name=workspace.name,
        model=config.model,
    )

    channels = args.channel or ["feishu"]
    if "feishu" in channels:
        feishu_cfg = _resolve_feishu_config(args)
        adapter = FeishuAdapter(feishu_cfg)
        try:
            adapter.validate_readiness()
        except FeishuConfigError as err:
            print("Error: Feishu adapter is not ready.", file=sys.stderr)
            print(f"  {err}", file=sys.stderr)
            print(
                "  Set FEISHU_APP_ID and FEISHU_APP_SECRET or pass --feishu-app-id/--feishu-app-secret.",
                file=sys.stderr,
            )
            return 1
        runtime.register_adapter(adapter)
        print("Feishu readiness:")
        print(f"  app_id: {'set' if feishu_cfg.app_id else 'missing'}")
        print(f"  app_secret: {'set' if feishu_cfg.app_secret else 'missing'}")
        print(
            f"  verification_token: {'set' if feishu_cfg.verification_token else 'not_set (optional)'}"
        )
        print(f"  allow_group_chats: {feishu_cfg.allow_group_chats}")
        print(f"  allow_user_ids: {len(feishu_cfg.allow_user_ids)}")

    try:
        if args.once:
            print("Starting gateway once for readiness check...")
        else:
            print("Starting gateway loop. Press Ctrl+C to stop.")
        asyncio.run(_run_gateway(runtime, once=args.once))
    except KeyboardInterrupt:
        print("\nGateway interrupted.")
        return 130
    except Exception as err:
        print(f"Error: Gateway failed to start: {err}", file=sys.stderr)
        return 1

    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run daemon service for proactive scheduling."""
    from atom_agent.daemon import DaemonService

    # Subcommands usually skip logging setup in main(), so daemon configures it here.
    config = Config.load(env_file=args.env_file)
    if args.debug:
        config.debug = True
    if args.model:
        config.model = args.model
    if args.workspace:
        config.workspace = args.workspace

    log_config = LoggingConfig(
        level="DEBUG" if args.debug else "INFO",
        format="json" if args.json else "text",
        output="file",
        log_content=args.debug,
    )
    setup_logging(log_config)

    errors = config.validate(args.provider)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        provider = get_provider(args.provider, config)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    workspace_paths = [args.workspace_path] if args.workspace_path else None
    service = DaemonService(
        provider=provider,
        model=config.model,
        poll_sec=args.poll_sec,
        workspace_paths=workspace_paths,
    )

    if args.once:
        reports = asyncio.run(service.run_once())
        if not reports:
            print("No due proactive tasks.")
            return 0

        for report in reports:
            if report.status == "success":
                print(
                    f"[{report.workspace}] {report.task_id}: success "
                    f"(outputs={report.output_count})"
                )
            else:
                print(
                    f"[{report.workspace}] {report.task_id}: failed ({report.error})",
                    file=sys.stderr,
                )
        return 1 if any(report.status != "success" for report in reports) else 0

    print(f"Starting daemon loop (poll={args.poll_sec}s). Press Ctrl+C to stop.")
    try:
        asyncio.run(service.run_forever())
    except KeyboardInterrupt:
        print("\nDaemon interrupted.")
        return 130

    return 0


def cmd_session(args: argparse.Namespace) -> int:
    """Manage sessions."""
    from atom_agent.cli.management import ensure_workspace_initialized
    from atom_agent.session.manager import SessionManager
    workspace = _resolve_workspace_path(args.workspace)

    initialized, errors = ensure_workspace_initialized(workspace, name=workspace.name)
    if errors:
        print(f"Error: Invalid workspace: {errors[0]}", file=sys.stderr)
        return 1
    if initialized:
        print(f"ℹ Initialized workspace context files at: {workspace}")

    session_manager = SessionManager(workspace, workspace.name)

    if args.action == "list":
        sessions = session_manager.list_sessions()
        if not sessions:
            print("No sessions found.")
            return 0

        print(f"Sessions in {workspace}:")
        for session in sessions:
            print(f"  - {session['key']}")
            print(f"    Created: {session.get('created_at', 'unknown')}")
            print(f"    Updated: {session.get('updated_at', 'unknown')}")
            if session.get('workspace_name'):
                print(f"    Workspace: {session['workspace_name']}")

        return 0

    elif args.action == "export":
        if not args.key_or_path:
            print("Error: Session key required", file=sys.stderr)
            return 1

        export_path = session_manager.export_session(args.key_or_path, args.output)
        if export_path:
            print(f"✓ Exported session '{args.key_or_path}' to: {export_path}")
            return 0
        else:
            print(f"Error: Session '{args.key_or_path}' not found", file=sys.stderr)
            return 1

    elif args.action == "import":
        if not args.key_or_path:
            print("Error: Import file path required", file=sys.stderr)
            return 1

        import_path = Path(args.key_or_path)
        if not import_path.exists():
            print(f"Error: File not found: {import_path}", file=sys.stderr)
            return 1

        session = session_manager.import_session(import_path, args.new_key)
        if session:
            print(f"✓ Imported session: {session.key}")
            print(f"  Messages: {len(session.messages)}")
            return 0
        else:
            print(f"Error: Failed to import session from {import_path}", file=sys.stderr)
            return 1

    elif args.action == "delete":
        if not args.key_or_path:
            print("Error: Session key required", file=sys.stderr)
            return 1

        if session_manager.delete(args.key_or_path):
            print(f"✓ Deleted session: {args.key_or_path}")
            return 0
        else:
            print(f"Error: Session '{args.key_or_path}' not found", file=sys.stderr)
            return 1

    return 1


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch workspace/session management TUI."""
    from atom_agent.cli.management import WorkspaceSessionTUI

    tui = WorkspaceSessionTUI(include_paths=args.include_path)
    return tui.run(once=args.once)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Handle subcommands
    if args.command == "init":
        return cmd_init(args)
    elif args.command == "identity":
        return cmd_identity(args)
    elif args.command == "workspace":
        return cmd_workspace(args)
    elif args.command == "proactive":
        return cmd_proactive(args)
    elif args.command == "gateway":
        return cmd_gateway(args)
    elif args.command == "daemon":
        return cmd_daemon(args)
    elif args.command == "session":
        return cmd_session(args)
    elif args.command == "tui":
        return cmd_tui(args)

    # Default: run interactive chat
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
    # Simple defaults: INFO level, text format, file output to ./logs/
    log_config = LoggingConfig(
        level="DEBUG" if args.debug else "INFO",
        format="json" if args.json else "text",
        output="file",
        log_content=args.debug,  # Enable full content logging in debug mode
    )
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
