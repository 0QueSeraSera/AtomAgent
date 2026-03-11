# Tool Usage Guidelines

## General Principles
- Choose the right tool for the task
- Understand tool parameters and outputs
- Handle tool errors gracefully

## File Operations
- Always read files before modifying
- Preserve file formatting and structure
- Create backups for critical changes

## External Interactions
- Validate external inputs
- Handle network errors appropriately
- Respect rate limits and quotas

## Memory Retrieval Workflow
- Keep prompts brief-first: rely on compact memory briefs in context
- Use `memory_search` to discover relevant project/global memory handles
- Use `memory_read` only for the entries needed to complete the current task
