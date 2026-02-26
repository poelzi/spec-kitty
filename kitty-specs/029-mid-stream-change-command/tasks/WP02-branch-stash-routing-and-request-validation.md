---
work_package_id: WP02
title: Branch Stash Routing and Request Validation
lane: "done"
dependencies:
- WP01
base_branch: 029-mid-stream-change-command-WP01
base_commit: 12d65682f2e2accf07ec1b2e209d0c33d0da12fc
created_at: '2026-02-09T10:50:59.283088+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
- T012
phase: Phase 1 - Foundation
assignee: ''
agent: "claude-opus"
shell_pid: "1340687"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 - Branch Stash Routing and Request Validation

**Implementation command:**
```bash
spec-kitty implement WP02 --base WP01
```

## Objectives and Success Criteria

- Resolve stash target from active branch:
  - `main` or `master` -> `kitty-specs/change-stack/main/`
  - feature branch -> `kitty-specs/<feature>/tasks/`
- Fail fast for ambiguous requests before file writes.
- Enforce closed/done reference link-only policy.

## Context and Constraints

- Spec references: FR-002A, FR-003, FR-016.
- Plan references: Architecture sections "Branch and Stash Routing" and "Dependency and Execution Semantics".
- Do not add pseudo-feature main stash directories.

## Subtasks and Detailed Guidance

### Subtask T007 - Implement stash resolver
- **Purpose**: Canonical stash path resolution.
- **Steps**:
  1. Create resolver in `src/specify_cli/core/change_stack.py`.
  2. Map `main/master` to embedded path.
  3. Map feature branches to feature tasks path.
  4. Return typed result with scope and absolute path.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T008 - Extend feature detection helpers
- **Purpose**: Make embedded main stash compatible with existing detection flows.
- **Steps**:
  1. Update `src/specify_cli/core/feature_detection.py` with change stash resolution helpers.
  2. Keep current feature detection behavior unchanged for non-change commands.
  3. Add guardrails to avoid accidental auto-selection of wrong feature for change commands.
- **Files**: `src/specify_cli/core/feature_detection.py`
- **Parallel?**: Yes

### Subtask T009 - Enforce contributor/context validation
- **Purpose**: Apply clarified access model and repo checks.
- **Steps**:
  1. Validate command runs inside initialized repository.
  2. Validate contributor-level access assumptions are represented in command checks.
  3. Return explicit errors when context is invalid.
- **Files**: `src/specify_cli/cli/commands/change.py`, `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: Yes

### Subtask T010 - Implement ambiguity fail-fast gate
- **Purpose**: Block writes for unclear requests such as "change this block" without target.
- **Steps**:
  1. Add validator that classifies request target clarity.
  2. On ambiguous input, return clarification-needed response.
  3. Ensure no WP files or tasks.md updates happen in this path.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: No

### Subtask T011 - Enforce closed/done link-only policy
- **Purpose**: Never reopen closed/done WPs from change command.
- **Steps**:
  1. Detect references to closed/done WPs.
  2. Allow historical linkage metadata only.
  3. Block any path that mutates lane/status of closed/done WPs.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T012 - Add validation unit tests
- **Purpose**: Lock behavior for routing and validation outcomes.
- **Steps**:
  1. Add tests for main vs feature stash routing.
  2. Add tests for ambiguous request fail-fast behavior.
  3. Add tests for closed/done policy enforcement.
- **Files**: `tests/unit/test_change_stack.py`, `tests/unit/agent/test_change_command.py`
- **Parallel?**: No

## Test Strategy

- `pytest tests/unit/test_change_stack.py -k "stash or ambiguous or closed"`
- `pytest tests/unit/agent/test_change_command.py -k "preview or validation"`

## Risks and Mitigations

- Risk: route to wrong stash on unusual branch names.
  - Mitigation: include branch-name fixture matrix in tests.
- Risk: ambiguous detector blocks clear requests.
  - Mitigation: include positive and negative fixtures.

## Review Guidance

- Verify no writes occur on ambiguity path.
- Verify closed/done lanes remain unchanged after request processing.
- Verify main stash path is embedded root path.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:02:45Z – unknown – shell_pid=635875 – lane=for_review – All 6 subtasks done (T007-T012): stash resolver, feature detection helpers, context validation, ambiguity fail-fast, closed-reference policy, and 50 unit tests. 200 integration tests green.
- 2026-02-09T12:13:42Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T12:20:10Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:12:44Z – claude-opus – shell_pid=1340687 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:19:05Z – claude-opus – shell_pid=1340687 – lane=for_review – Review fix: replaced find_repo_root with locate_project_root for .kittify validation. Added regression test for non-initialized repos. All 70 tests pass.
- 2026-02-10T19:47:22Z – claude-opus – shell_pid=1340687 – lane=done – Moved to done
