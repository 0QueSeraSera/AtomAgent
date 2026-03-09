"""Proactive configuration parsing and scheduling primitives."""

from atom_agent.proactive.models import (
    DueTask,
    ProactiveConfig,
    ProactiveRuntimeState,
    ProactiveTaskConfig,
    ProactiveTaskRuntimeState,
    ProactiveValidationError,
    ProactiveValidationIssue,
    TaskKind,
)
from atom_agent.proactive.parser import (
    parse_proactive_file,
    parse_proactive_markdown,
    validate_proactive_markdown,
)
from atom_agent.proactive.scheduler import evaluate_due_tasks, mark_task_finished, mark_task_started
from atom_agent.proactive.state import (
    get_state_dir,
    get_state_path,
    load_runtime_state,
    save_runtime_state,
)

__all__ = [
    "TaskKind",
    "DueTask",
    "ProactiveConfig",
    "ProactiveRuntimeState",
    "ProactiveTaskConfig",
    "ProactiveTaskRuntimeState",
    "ProactiveValidationIssue",
    "ProactiveValidationError",
    "parse_proactive_file",
    "parse_proactive_markdown",
    "validate_proactive_markdown",
    "evaluate_due_tasks",
    "mark_task_started",
    "mark_task_finished",
    "get_state_dir",
    "get_state_path",
    "load_runtime_state",
    "save_runtime_state",
]
