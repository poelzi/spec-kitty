---
work_package_id: WP04
title: Change WP Synthesis and Adaptive Packaging
lane: "done"
dependencies:
- WP03
base_branch: 029-mid-stream-change-command-WP03
base_commit: 1915b6774f664a2b4e5983ab93a49563c9866eef
created_at: '2026-02-09T11:12:13.163283+00:00'
subtasks:
- T018
- T019
- T020
- T021
- T022
- T023
phase: Phase 2 - Core Behavior
assignee: ''
agent: "claude-opus"
shell_pid: "1346267"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-09T04:11:52Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP04 - Change WP Synthesis and Adaptive Packaging

**Implementation command:**
```bash
spec-kitty implement WP04 --base WP03
```

## Objectives and Success Criteria

- Turn validated requests into deterministic WP sets.
- Support adaptive modes (`single_wp`, `orchestration`, `targeted_multi`).
- Include required metadata and final testing task in every generated change WP.

## Context and Constraints

- Spec references: FR-004, FR-008, FR-014, FR-015.
- Data model references: `ChangePlan`, `ChangeWorkPackage`.
- Keep generated WPs in flat `tasks/` directories.

## Subtasks and Detailed Guidance

### Subtask T018 - Implement mode selection logic
- **Purpose**: Deterministically choose package mode.
- **Steps**:
  1. Add selection logic based on coupling and dependency indicators.
  2. Ensure identical inputs always produce same mode.
  3. Surface mode in preview output.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T019 - Implement WP ID and file name generation
- **Purpose**: Generate new WPs safely in flat directories.
- **Steps**:
  1. Allocate next WP IDs deterministically.
  2. Create slugged filenames (`WP##-slug.md`).
  3. Avoid collisions with existing WP files.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: Yes

### Subtask T020 - Emit required frontmatter fields
- **Purpose**: Ensure generated WPs carry required change metadata.
- **Steps**:
  1. Include `change_stack`, `change_request_id`, `change_mode`, `stack_rank`, `review_attention`.
  2. Include standard lane and activity fields.
  3. Ensure parser compatibility with existing workflow commands.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: Yes

### Subtask T021 - Append guardrails and final testing task
- **Purpose**: Enforce user constraints and test-at-end requirement.
- **Steps**:
  1. Convert request guardrails to acceptance constraints in prompt body.
  2. Append explicit final testing task for each generated WP.
  3. Validate no generated WP omits final test task.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T022 - Add implementation command hints
- **Purpose**: Help implementers choose correct `--base` command.
- **Steps**:
  1. If no dependencies, render `spec-kitty implement WP##`.
  2. If dependencies exist, render `spec-kitty implement WP## --base WP##`.
  3. Keep output in WP prompt body near top section.
- **Files**: `src/specify_cli/core/change_stack.py`
- **Parallel?**: No

### Subtask T023 - Add synthesis tests
- **Purpose**: Verify deterministic generation shape and metadata quality.
- **Steps**:
  1. Add tests for single/orchestration/targeted outputs.
  2. Add tests for frontmatter completeness.
  3. Add tests ensuring final testing task is always present.
- **Files**: `tests/unit/test_change_stack.py`, `tests/unit/agent/test_change_command.py`
- **Parallel?**: No

## Test Strategy

- `pytest tests/unit/test_change_stack.py -k "mode or generate or frontmatter"`
- `pytest tests/unit/agent/test_change_command.py -k "final testing"`

## Risks and Mitigations

- Risk: generated prompts too sparse for implementers.
  - Mitigation: include structured sections and command hints in generation template.

## Review Guidance

- Verify each generated WP contains required metadata and testing task.
- Verify mode selection is deterministic and traceable.

## Activity Log

- 2026-02-09T04:11:52Z - system - lane=planned - Prompt created.
- 2026-02-09T11:26:45Z – unknown – shell_pid=635875 – lane=for_review – WP04 complete: Change WP synthesis and adaptive packaging. 3 modes (single_wp/orchestration/targeted_multi), 46 synthesis tests, 214 total unit tests pass, 200+ integration tests pass.
- 2026-02-09T14:38:46Z – opencode – shell_pid=979199 – lane=doing – Started review via workflow command
- 2026-02-09T14:54:35Z – opencode – shell_pid=979199 – lane=planned – Moved to planned
- 2026-02-10T11:25:22Z – claude-opus – shell_pid=1346267 – lane=doing – Started implementation via workflow command
- 2026-02-10T11:30:51Z – claude-opus – shell_pid=1346267 – lane=for_review – Review fix: Propagate elevated review_attention into generated WP frontmatter. All 234 tests pass.
- 2026-02-10T19:47:24Z – claude-opus – shell_pid=1346267 – lane=done – Moved to done
