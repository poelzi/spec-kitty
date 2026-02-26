---
work_package_id: WP03
title: Deterministic Complexity Scoring and Gating
lane: "done"
dependencies:
- WP02
base_branch: 029-mid-stream-change-command-WP02
base_commit: 0737fea6ebfbf67ee8155a4cab43bcf9288d57ff
created_at: '2026-02-09T11:03:01.553019+00:00'
subtasks:
- T013
- T014
- T015
- T016
- T017
phase: Phase 2 - Core Behavior
assignee: ''
agent: "claude-opus"
shell_pid: "1344620"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP03 - Deterministic Complexity Scoring and Gating

**Implementation command:**
```bash
spec-kitty implement WP03 --base WP02
```

## Objectives and Success Criteria

- Implement deterministic complexity scoring rubric with fixed thresholds.
- Produce stable preview output with score breakdown.
- Enforce explicit continue/stop behavior for high complexity requests.

## Context and Constraints

- Spec references: FR-009, FR-010, FR-011, SC-003.
- Plan references: "Deterministic Complexity Model".
- Prohibit probabilistic classifier paths.

## Subtasks and Detailed Guidance

### Subtask T013 - Build deterministic classifier module
- **Purpose**: Central scoring logic.
- **Steps**:
  1. Add `src/specify_cli/core/change_classifier.py`.
  2. Implement weighted component scoring.
  3. Implement threshold mapping to `simple`, `complex`, `high`.
  4. Return full score breakdown object.
- **Files**: `src/specify_cli/core/change_classifier.py`
- **Parallel?**: No

### Subtask T014 - Integrate score breakdown into preview output
- **Purpose**: Make decision rationale visible and testable.
- **Steps**:
  1. Wire classifier into preview endpoint/command.
  2. Include per-factor and total score in JSON response.
  3. Print concise human summary in CLI mode.
- **Files**: `src/specify_cli/cli/commands/change.py`, `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: Yes

### Subtask T015 - Add explicit continue/stop gate
- **Purpose**: Enforce user decision when score is high.
- **Steps**:
  1. Add high-complexity warning path.
  2. Require explicit continue flag/confirmation before apply.
  3. Block apply when confirmation is absent.
- **Files**: `src/specify_cli/cli/commands/agent/change.py`
- **Parallel?**: No

### Subtask T016 - Persist scoring metadata
- **Purpose**: Keep traceability for audits/debugging.
- **Steps**:
  1. Store scoring snapshot on change request context.
  2. Ensure metadata is available to apply/reconcile stages.
  3. Keep persisted schema forward-compatible.
- **Files**: `src/specify_cli/core/change_stack.py`, `src/specify_cli/core/change_classifier.py`
- **Parallel?**: Yes

### Subtask T017 - Add threshold and determinism tests
- **Purpose**: Guarantee repeatable outcomes.
- **Steps**:
  1. Add threshold boundary tests around 3/4 and 6/7 splits.
  2. Add repeated-run determinism checks for identical inputs.
  3. Add tests for warning and continue/stop behavior.
- **Files**: `tests/unit/test_change_classifier.py`, `tests/unit/agent/test_change_command.py`
- **Parallel?**: No

## Test Strategy

- `pytest tests/unit/test_change_classifier.py`
- `pytest tests/unit/agent/test_change_command.py -k "complexity or continue"`

## Risks and Mitigations

- Risk: mismatch between preview and apply behavior.
  - Mitigation: ensure apply consumes persisted preview score metadata.

## Review Guidance

- Verify score categories map exactly to thresholds.
- Verify high complexity path cannot bypass explicit user decision.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:10:59Z – unknown – shell_pid=635875 – lane=for_review – All 5 subtasks done (T013-T017): deterministic classifier, preview integration, continue/stop gate, scoring persistence, 111+14 tests. 200 integration tests green.
- 2026-02-09T14:14:05Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T14:24:30Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:20:07Z – claude-opus – shell_pid=1344620 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:24:57Z – claude-opus – shell_pid=1344620 – lane=for_review – Review fix: --request-text now required for apply, complexity gate always enforced. All 145 tests pass.
- 2026-02-10T19:47:23Z – claude-opus – shell_pid=1344620 – lane=done – Moved to done
