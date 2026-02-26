---
work_package_id: WP06
title: Reconciliation and Merge Coordination Jobs
lane: "done"
dependencies:
- WP05
base_branch: 029-mid-stream-change-command-WP05
base_commit: 7f86b76c59040947e29a2021a0d7c74206d235d4
created_at: '2026-02-09T11:29:04.029906+00:00'
subtasks:
- T030
- T031
- T032
- T033
- T034
- T035
phase: Phase 3 - Integration
assignee: ''
agent: "claude-opus"
shell_pid: "1362738"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP06 - Reconciliation and Merge Coordination Jobs

**Implementation command:**
```bash
spec-kitty implement WP06 --base WP05
```

## Objectives and Success Criteria

- Reconcile `tasks.md` and prompt links after generated change WPs.
- Produce consistency reports for automated validation.
- Create merge coordination jobs only when deterministic risk heuristics trigger.

## Context and Constraints

- Spec references: FR-007, FR-013, SC-001, SC-004.
- Plan references: "Consistency and Merge Coordination".
- Reconciliation should be idempotent on repeated runs.

## Subtasks and Detailed Guidance

### Subtask T030 - Implement tasks.md reconciliation
- **Purpose**: Keep high-level task docs aligned with generated WPs.
- **Steps**:
  1. Insert or update WP sections and prompt links.
  2. Preserve existing checklist state for unrelated subtasks.
  3. Ensure deterministic ordering by WP ID.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T031 - Implement consistency report output
- **Purpose**: Provide machine-readable reconciliation status.
- **Steps**:
  1. Emit report fields for doc updates, link fixes, and issues.
  2. Attach report to apply/reconcile responses.
  3. Surface summary in human CLI output.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: No

### Subtask T032 - Implement merge coordination heuristics
- **Purpose**: Detect when cross-stream merge coordination work is required.
- **Steps**:
  1. Define deterministic trigger conditions from dependency and conflict risk indicators.
  2. Generate merge coordination job records.
  3. Include reason and target WPs in each job.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/core/dependency_resolver.py`
- **Parallel?**: Yes

### Subtask T033 - Persist merge coordination artifacts
- **Purpose**: Make generated coordination jobs visible for downstream work.
- **Steps**:
  1. Persist jobs in planning artifacts.
  2. Ensure jobs are discoverable in command output and docs.
  3. Keep schema consistent with contract.
- **Files**: `src/specify_cli/core/change_stack.py`, `kitty-specs/029-mid-stream-change-command/contracts/change-command.openapi.yaml` if updates needed
- **Parallel?**: No

### Subtask T034 - Add integration tests for reconciliation and merge jobs
- **Purpose**: Validate end-to-end write/reconcile behavior.
- **Steps**:
  1. Add tests for successful reconciliation with zero issues.
  2. Add tests for merge job trigger and no-trigger paths.
  3. Verify consistency report fields and values.
- **Files**: `tests/integration/test_change_main_stash_flow.py`, `tests/integration/test_change_stack_priority.py`
- **Parallel?**: Yes

### Subtask T035 - Run regression tests for reconciliation package
- **Purpose**: Ensure no regressions before lane transition.
- **Steps**:
  1. Run focused unit and integration tests for reconciliation modules.
  2. Fix failures caused by ordering or doc rewrites.
  3. Record final pass status for review.
- **Files**: test suites and touched source files
- **Parallel?**: No

## Test Strategy

- `pytest tests/integration/test_change_main_stash_flow.py`
- `pytest tests/integration/test_change_stack_priority.py -k "reconcile or merge"`

## Risks and Mitigations

- Risk: reconciliation accidentally reorders or edits unrelated task content.
  - Mitigation: use scoped updates and fixture snapshots for unchanged sections.

## Review Guidance

- Verify consistency report is complete and accurate.
- Verify merge coordination jobs appear only when conditions are met.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:35:29Z – unknown – shell_pid=635875 – lane=for_review – WP06 complete: Reconciliation (tasks.md + deps), consistency report, 3 merge coordination heuristics, JSON artifact persistence. 42 new tests, 779 unit + 200 integration pass.
- 2026-02-09T16:02:29Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T16:20:38Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:42:42Z – claude-opus – shell_pid=1362738 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:46:38Z – claude-opus – shell_pid=1362738 – lane=for_review – Review fixes: (1) _fix_broken_prompt_links now actually removes broken link lines from tasks.md, (2) Added 12 integration tests in test_change_main_stash_flow.py and test_change_stack_priority.py. All 169 tests pass.
- 2026-02-10T19:47:26Z – claude-opus – shell_pid=1362738 – lane=done – Moved to done
