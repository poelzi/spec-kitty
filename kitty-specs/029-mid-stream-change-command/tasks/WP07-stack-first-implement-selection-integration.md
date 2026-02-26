---
work_package_id: WP07
title: Stack-First Implement Selection Integration
lane: "done"
dependencies:
- WP05
base_branch: 029-mid-stream-change-command-WP05
base_commit: 7f86b76c59040947e29a2021a0d7c74206d235d4
created_at: '2026-02-09T11:35:37.734436+00:00'
subtasks:
- T036
- T037
- T038
- T039
- T040
phase: Phase 3 - Integration
assignee: ''
agent: "claude-opus"
shell_pid: "1364087"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP07 - Stack-First Implement Selection Integration

**Implementation command:**
```bash
spec-kitty implement WP07 --base WP05
```

## Objectives and Success Criteria

- Integrate stack-first selection into implement workflow.
- Prefer ready change WPs before normal backlog.
- Block normal progression when change stack is pending but no item is ready.

## Context and Constraints

- Spec references: FR-017 and user clarification on blocked vs ready change items.
- Plan references: "Dependency and Execution Semantics".
- Preserve existing workflow command interface.

## Subtasks and Detailed Guidance

### Subtask T036 - Prioritize ready change WPs in implement selection
- **Purpose**: Make change stack first-class in auto-selection.
- **Steps**:
  1. Update selection logic in workflow implement command.
  2. Query change stack for dependency-ready planned items.
  3. Select by deterministic order (`stack_rank`, then WP ID).
- **Files**: `src/specify_cli/cli/commands/agent/workflow.py`
- **Parallel?**: No

### Subtask T037 - Enforce blocked-stack stop behavior
- **Purpose**: Halt when change work exists but none is ready.
- **Steps**:
  1. Detect pending but blocked change stack state.
  2. Return clear blocker list.
  3. Prevent fallback to normal planned WPs in this state.
- **Files**: `src/specify_cli/cli/commands/agent/workflow.py`
- **Parallel?**: No

### Subtask T038 - Permit normal fallback only when stack empty
- **Purpose**: Keep legacy backlog progression when change stack is clear.
- **Steps**:
  1. Add explicit check for stack emptiness.
  2. Reuse existing normal planned-WP auto-detection when empty.
  3. Keep behavior unchanged for features without change stack entries.
- **Files**: `src/specify_cli/cli/commands/agent/workflow.py`
- **Parallel?**: No

### Subtask T039 - Update workflow output guidance
- **Purpose**: Make selected source transparent to users.
- **Steps**:
  1. Print whether selection came from `change_stack` or `normal_backlog`.
  2. Print blocker guidance when stopped.
  3. Keep output parsable for automation when JSON mode is used.
- **Files**: `src/specify_cli/cli/commands/agent/workflow.py`
- **Parallel?**: Yes

### Subtask T040 - Add integration tests for selection matrix
- **Purpose**: Validate ready/blocked/empty stack behavior.
- **Steps**:
  1. Add tests for ready change item selection.
  2. Add tests for blocked stack stop.
  3. Add tests for normal fallback when stack empty.
- **Files**: `tests/integration/test_change_stack_priority.py`
- **Parallel?**: No

## Test Strategy

- `pytest tests/integration/test_change_stack_priority.py`

## Risks and Mitigations

- Risk: regression in existing implement auto-selection.
  - Mitigation: include coverage for both change-enabled and change-free features.

## Review Guidance

- Verify blocker path does not continue normal backlog.
- Verify output clearly reports selection source and blockers.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:40:17Z – unknown – shell_pid=635875 – lane=for_review – WP07 complete: Stack-first implement selection with blocker output, normal fallback, selection source output. 14 new tests, 951 total pass.
- 2026-02-09T16:43:49Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T16:45:43Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:47:14Z – claude-opus – shell_pid=1364087 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:52:50Z – claude-opus – shell_pid=1364087 – lane=for_review – Moved to for_review
- 2026-02-10T19:47:27Z – claude-opus – shell_pid=1364087 – lane=done – Moved to done
